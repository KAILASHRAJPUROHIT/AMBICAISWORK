import { createServer } from "node:http";
import { DatabaseSync } from "node:sqlite";
import { execFile, execFileSync } from "node:child_process";
import { promisify } from "node:util";
import { mkdirSync, readFileSync, existsSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomUUID } from "node:crypto";

const execFileAsync = promisify(execFile);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dataDir = join(root, "data");
const logsDir = join(root, "logs");
const worktreesDir = join(root, "worktrees");
mkdirSync(dataDir, { recursive: true });
mkdirSync(logsDir, { recursive: true });
mkdirSync(worktreesDir, { recursive: true });

const port = Number(process.env.AIS_CONTROL_PORT || 4317);
const pollMs = Math.max(15, Number(process.env.AIS_POLL_SECONDS || 60)) * 1000;
const controlToken = process.env.AIS_CONTROL_TOKEN || "";
const ollamaUrl = process.env.LOCAL_SUPERVISOR_URL || "http://127.0.0.1:11434";
const requestedSupervisor = process.env.LOCAL_SUPERVISOR_MODEL || "";
const configPath = join(root, "config", "projects.json");
const db = new DatabaseSync(join(dataDir, "ais.db"));
db.exec("PRAGMA journal_mode=WAL");
db.exec("PRAGMA foreign_keys=ON");
db.exec("PRAGMA busy_timeout=5000");

const schema = [
  `CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    phase TEXT NOT NULL,
    local_path TEXT,
    remote_url TEXT,
    endpoints_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
  )`,
  `CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    project_id TEXT,
    department TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    eta_at TEXT,
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    assigned_to TEXT NOT NULL DEFAULT 'local-supervisor-current',
    risk_class TEXT NOT NULL DEFAULT 'R1',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id)
  )`,
  `CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    project_id TEXT,
    work_item_id TEXT,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS model_health (
    model_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    checked_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS daily_reports (
    id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    evidence_cutoff TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(report_date, revision)
  )`,
  `CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    checked_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    platform TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'Unassigned',
    content_summary TEXT NOT NULL DEFAULT '',
    planned_at TEXT,
    published_at TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_observations_project_time ON observations(project_id, observed_at DESC)`,
  `CREATE INDEX IF NOT EXISTS idx_work_items_status_eta ON work_items(status, eta_at)`,
  `CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC)`,
  `CREATE INDEX IF NOT EXISTS idx_reports_date_revision ON daily_reports(report_date, revision DESC)`,
];
for (const statement of schema) db.prepare(statement).run();
function ensureColumn(table, column, definition) {
  const columns = db.prepare(`PRAGMA table_info(${table})`).all().map((row) => row.name);
  if (!columns.includes(column)) db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
}
ensureColumn("projects", "description", "TEXT NOT NULL DEFAULT ''");
ensureColumn("projects", "expected_completion", "TEXT");
ensureColumn("projects", "completed_at", "TEXT");
db.exec("PRAGMA optimize");

const isoNow = () => new Date().toISOString();
const indiaDate = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const json = (value) => JSON.stringify(value ?? null);
const parseJson = (value, fallback) => {
  try { return JSON.parse(value); } catch { return fallback; }
};

function logEvent(eventType, severity, message, projectId = null, workItemId = null, payload = {}) {
  db.prepare(`INSERT INTO events(event_type,severity,project_id,work_item_id,message,payload_json,created_at) VALUES(?,?,?,?,?,?,?)`)
    .run(eventType, severity, projectId, workItemId, message, json(payload), isoNow());
}

function seedSettings() {
  const defaults = {
    master: true,
    coding: true,
    development: true,
    production: true,
    git: true,
    research: true,
    marketing: true,
    emergency_reserve_percent: 15,
  };
  const insert = db.prepare("INSERT OR IGNORE INTO settings(key,value_json,updated_at) VALUES(?,?,?)");
  for (const [key, value] of Object.entries(defaults)) insert.run(key, json(value), isoNow());
}

function discoverRemote(localPath) {
  if (!localPath || !existsSync(join(localPath, ".git"))) return null;
  try {
    return execFileSync("git", ["-C", localPath, "remote", "get-url", "origin"], { encoding: "utf8", timeout: 4000, stdio: ["ignore", "pipe", "ignore"] }).trim() || null;
  } catch { return null; }
}

function seedProjects() {
  const projects = parseJson(readFileSync(configPath, "utf8"), []);
  const upsert = db.prepare(`INSERT INTO projects(id,name,department,phase,local_path,remote_url,endpoints_json,enabled,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name,department=excluded.department,phase=excluded.phase,
    local_path=excluded.local_path,remote_url=excluded.remote_url,endpoints_json=excluded.endpoints_json,enabled=1,updated_at=excluded.updated_at`);
  for (const project of projects) {
    upsert.run(project.id, project.name, project.department, project.phase, project.localPath, project.remoteUrl || discoverRemote(project.localPath), json(project.endpoints || []), 1, isoNow(), isoNow());
  }
}

seedSettings();
seedProjects();

function seedConnectors() {
  const rows = [
    ["google-ai-pro-1", "Google AI Pro account 1", "model-account", "not_configured", "OAuth not connected"],
    ["google-ai-pro-2", "Google AI Pro account 2", "model-account", "not_configured", "OAuth not connected"],
    ["google-ai-pro-3", "Google AI Pro account 3", "model-account", "not_configured", "OAuth not connected"],
    ["codex-ceo", "Codex CEO audit", "governance", "not_configured", "Recurring Codex audit is not connected to the local event queue"],
    ["instagram", "Instagram", "social", "not_configured", "Meta account not connected; no statistics available"],
    ["facebook", "Facebook", "social", "not_configured", "Meta account not connected; no statistics available"],
    ["trend-decoder", "Trend Decoder", "research", "planned", "Planned connector; no competitor feed connected"],
  ];
  const insert = db.prepare("INSERT OR IGNORE INTO connectors(id,name,category,status,detail,payload_json,checked_at) VALUES(?,?,?,?,?,?,?)");
  for (const row of rows) insert.run(...row, "{}", isoNow());
}
seedConnectors();

function getSettings() {
  return Object.fromEntries(db.prepare("SELECT key,value_json FROM settings").all().map((row) => [row.key, parseJson(row.value_json, null)]));
}

function setSetting(key, value) {
  db.prepare(`INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at`)
    .run(key, json(value), isoNow());
  logEvent("control.changed", "info", `${key} set to ${String(value)}`, null, null, { key, value });
}

async function gitObservation(project) {
  if (!project.local_path) return { status: "unconfigured", detail: "Local repository not linked", observedAt: isoNow() };
  if (!existsSync(project.local_path)) return { status: "missing", detail: "Configured project path is missing", path: project.local_path, observedAt: isoNow() };
  if (!existsSync(join(project.local_path, ".git"))) return { status: "not_git", detail: "Project folder present; Git not initialized", path: project.local_path, observedAt: isoNow() };
  try {
    const run = async (args, timeout = 7000) => (await execFileAsync("git", ["-C", project.local_path, ...args], { encoding: "utf8", timeout, windowsHide: true })).stdout.trim();
    const branch = await run(["branch", "--show-current"]);
    const head = await run(["rev-parse", "--short=12", "HEAD"]).catch(() => "unborn");
    const statusText = await run(["status", "--porcelain=v1"]);
    const changes = statusText ? statusText.split(/\r?\n/).length : 0;
    const lastCommit = await run(["log", "-1", "--format=%cI|%s"]).catch(() => "");
    const remoteUrl = await run(["remote", "get-url", "origin"]).catch(() => "");
    let remoteHead = null;
    if (remoteUrl) {
      const remote = await run(["ls-remote", "origin", "HEAD"], 12000).catch(() => "");
      remoteHead = remote ? remote.split(/\s+/)[0]?.slice(0, 12) : null;
    }
    return {
      status: changes > 0 ? "warning" : "healthy",
      detail: changes > 0 ? `${changes} uncommitted change${changes === 1 ? "" : "s"}` : "Working tree clean",
      branch, head, changes, lastCommit, remoteUrl: remoteUrl || null, remoteHead, observedAt: isoNow(),
    };
  } catch (error) {
    return { status: "error", detail: error instanceof Error ? error.message : "Git observation failed", observedAt: isoNow() };
  }
}

async function endpointObservation(project) {
  const endpoints = parseJson(project.endpoints_json, []);
  if (!endpoints.length) return { status: "unconfigured", detail: "No endpoint registered", checks: [], observedAt: isoNow() };
  const checks = await Promise.all(endpoints.map(async (endpoint) => {
    const started = Date.now();
    try {
      const response = await fetch(endpoint.url, { signal: AbortSignal.timeout(15000), redirect: "follow" });
      const ok = (endpoint.expected || [200]).includes(response.status);
      let evidence = null;
      if (/\/api\/health(?:$|\?)/.test(endpoint.url)) {
        evidence = await response.json().catch(() => null);
      }
      return { name: endpoint.name, url: endpoint.url, ok, statusCode: response.status, latencyMs: Date.now() - started, evidence };
    } catch (error) {
      return { name: endpoint.name, url: endpoint.url, ok: false, statusCode: null, latencyMs: Date.now() - started, error: error instanceof Error ? error.message : "Request failed" };
    }
  }));
  const failing = checks.filter((check) => !check.ok);
  return { status: failing.length ? "error" : "healthy", detail: failing.length ? `${failing.length}/${checks.length} endpoint checks failing` : `${checks.length}/${checks.length} endpoint checks passed`, checks, observedAt: isoNow() };
}

async function dependencyObservation(project) {
  const packagePath = project.local_path ? join(project.local_path, "package.json") : "";
  if (!packagePath || !existsSync(packagePath)) return { status: "unconfigured", detail: "No supported online dependency manifest", insights: [], observedAt: isoNow() };
  const npmExecutable = process.platform === "win32" ? "C:\\Program Files\\nodejs\\npm.cmd" : "npm";
  let stdout = "";
  try {
    ({ stdout } = await execFileAsync(npmExecutable, ["outdated", "--json"], { cwd: project.local_path, encoding: "utf8", timeout: 180000, windowsHide: true, maxBuffer: 4 * 1024 * 1024 }));
  } catch (error) {
    stdout = error.stdout || "";
    if (!stdout.trim()) return { status: "error", detail: error instanceof Error ? error.message : "Online dependency check failed", insights: [], observedAt: isoNow() };
  }
  const outdated = parseJson(stdout, {});
  const insights = Object.entries(outdated).slice(0, 25).map(([name, value]) => ({
    name, current: value.current || null, wanted: value.wanted || null, latest: value.latest || null, homepage: value.homepage || `https://www.npmjs.com/package/${encodeURIComponent(name)}`,
  }));
  return {
    status: insights.length ? "warning" : "healthy",
    detail: insights.length ? `${insights.length} dependency improvement candidate${insights.length === 1 ? "" : "s"}` : "Dependencies match the latest compatible versions",
    insights,
    source: "npm registry",
    observedAt: isoNow(),
  };
}

function saveObservation(projectId, source, result) {
  db.prepare("INSERT INTO observations(project_id,source,status,payload_json,observed_at) VALUES(?,?,?,?,?)")
    .run(projectId, source, result.status, json(result), result.observedAt || isoNow());
  db.prepare(`DELETE FROM observations WHERE id IN (
    SELECT id FROM observations WHERE project_id=? AND source=? ORDER BY observed_at DESC LIMIT -1 OFFSET 120
  )`).run(projectId, source);
}

async function observeModels() {
  const checkedAt = isoNow();
  const upsert = db.prepare(`INSERT INTO model_health(model_key,provider,role,status,detail,payload_json,checked_at) VALUES(?,?,?,?,?,?,?)
    ON CONFLICT(model_key) DO UPDATE SET provider=excluded.provider,role=excluded.role,
    status=excluded.status,detail=excluded.detail,payload_json=excluded.payload_json,checked_at=excluded.checked_at`);
  try {
    const response = await fetch(`${ollamaUrl}/api/tags`, { signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error(`Ollama returned ${response.status}`);
    const data = await response.json();
    const qwen = (data.models || []).filter((model) => /qwen/i.test(model.name || model.model || "")).sort((a, b) => Number(b.size || 0) - Number(a.size || 0));
    for (const [index, model] of qwen.entries()) {
      const name = model.name || model.model;
      upsert.run(`ollama/${name}`, "Ollama", index === 0 ? "Local supervisor" : "Local reserve", "ready", `${Math.round(Number(model.size || 0) / 1024 / 1024 / 1024 * 10) / 10} GB installed`, json({ ...model, rank: index === 0 ? -20 : -10 }), checkedAt);
    }
    if (!qwen.length) upsert.run("ollama/qwen", "Ollama", "Local supervisor", "unavailable", "No installed Qwen model", "{}", checkedAt);
  } catch (error) {
    upsert.run("ollama/qwen", "Ollama", "Local supervisor", "offline", error instanceof Error ? error.message : "Ollama unavailable", "{}", checkedAt);
  }

  try {
    const command = process.platform === "win32" ? "cmd.exe" : "opencode";
    const args = process.platform === "win32" ? ["/d", "/s", "/c", "opencode models opencode"] : ["models", "opencode"];
    const { stdout } = await execFileAsync(command, args, { encoding: "utf8", timeout: 20000, windowsHide: true });
    const free = stdout.split(/\r?\n/).map((line) => line.trim()).filter((line) => /(?:free|big-pickle)/i.test(line)).slice(0, 5);
    for (const [index, model] of free.entries()) {
      const current = db.prepare("SELECT status,checked_at FROM model_health WHERE model_key=?").get(model);
      const freshProbe = current?.status === "ready" && Date.now() - Date.parse(current.checked_at) < 6 * 60 * 60 * 1000;
      if (!freshProbe) upsert.run(model, "OpenCode Zen", `Free reserve ${index + 1}`, "catalogued", current?.status === "ready" ? "Probe expired; live smoke test required" : "Catalogued; live smoke test required before code deployment", json({ rank: 20 + index }), checkedAt);
    }
    upsert.run("opencode/provider", "OpenCode", "Coding harness", "ready", `${stdout.split(/\r?\n/).filter(Boolean).length} catalog models visible`, json({ rank: 999 }), checkedAt);
  } catch (error) {
    upsert.run("opencode/provider", "OpenCode", "Coding harness", "offline", error instanceof Error ? error.message : "OpenCode unavailable", "{}", checkedAt);
  }

  db.prepare("DELETE FROM model_health WHERE model_key IN ('claude/opus/accounts-1-3','claude/sonnet/accounts-1-3','google/gemini-3.1-pro/accounts-1-3','google/gemini-3.7-flash/accounts-1-3')").run();
  const premiumTiers = [
    ["claude/opus", "Claude", "Highest coding tier"],
    ["claude/sonnet", "Claude", "Primary coding tier"],
    ["google/gemini-3.1-pro", "Google", "Strongest Google tier"],
    ["google/gemini-3.7-flash", "Google", "Certified fast fallback"],
  ];
  let rank = 1;
  for (const [prefix, provider, role] of premiumTiers) {
    for (let account = 1; account <= 3; account += 1) {
      upsert.run(`${prefix}/account-${account}`, provider, `${role} · Account ${account}`, "not_configured", "OAuth connector not configured; quota unknown", json({ rank, account, quotaRemaining: null, executableModel: null }), checkedAt);
      rank += 1;
    }
  }
}

let checksRunning = false;
async function runChecks(reason = "schedule") {
  if (checksRunning) return { skipped: true, reason: "already-running" };
  checksRunning = true;
  const settings = getSettings();
  const projects = db.prepare("SELECT * FROM projects WHERE enabled=1 ORDER BY name").all();
  try {
    for (const project of projects) {
      if (settings.git !== false) saveObservation(project.id, "git", await gitObservation(project));
      if (settings.production !== false) {
        const endpoint = await endpointObservation(project);
        saveObservation(project.id, "endpoint", endpoint);
        if (endpoint.status === "error") logEvent("health.failed", "warning", `${project.name}: ${endpoint.detail}`, project.id, null, endpoint);
      }
    }
    await observeModels();
    logEvent("checks.completed", "info", `Portfolio checks completed (${reason})`, null, null, { projectCount: projects.length });
    generateDailyReport(false);
    return { ok: true, projectCount: projects.length, checkedAt: isoNow() };
  } finally { checksRunning = false; }
}

function latestObservation(projectId, source) {
  const row = db.prepare("SELECT status,payload_json,observed_at FROM observations WHERE project_id=? AND source=? ORDER BY observed_at DESC LIMIT 1").get(projectId, source);
  return row ? { status: row.status, ...parseJson(row.payload_json, {}), observedAt: row.observed_at } : { status: "unknown", detail: "No evidence yet", observedAt: null };
}

function projectProjection(project) {
  const git = latestObservation(project.id, "git");
  const endpoint = latestObservation(project.id, "endpoint");
  const research = latestObservation(project.id, "research");
  const taskStats = db.prepare(`SELECT COUNT(*) total,
    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
    SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) blocked
    FROM work_items WHERE project_id=?`).get(project.id);
  const taskTotal = Number(taskStats?.total || 0);
  const taskCompleted = Number(taskStats?.completed || 0);
  let health = "unknown";
  if (endpoint.status === "error" || git.status === "error" || git.status === "missing") health = "error";
  else if (git.status === "warning") health = "warning";
  else if (endpoint.status === "healthy" || git.status === "healthy") health = "healthy";
  else if (git.status === "unconfigured" && endpoint.status === "unconfigured") health = "unconfigured";
  return {
    id: project.id, name: project.name, department: project.department, phase: project.phase,
    localPath: project.local_path, remoteUrl: git.remoteUrl || project.remote_url, enabled: Boolean(project.enabled),
    description: project.description || "", expectedCompletion: project.expected_completion || null, completedAt: project.completed_at || null,
    progress: taskTotal ? Math.round(taskCompleted / taskTotal * 100) : null,
    taskStats: { total: taskTotal, completed: taskCompleted, blocked: Number(taskStats?.blocked || 0) },
    health, git, endpoint, research,
  };
}

function projectIdFromName(name) {
  const base = String(name || "project").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "project";
  let id = base;
  let suffix = 2;
  while (db.prepare("SELECT 1 FROM projects WHERE id=?").get(id)) id = `${base}-${suffix++}`;
  return id;
}

function saveProject(input) {
  const name = String(input.name || "").trim();
  const localPath = String(input.localPath || "").trim();
  if (!name) throw new Error("Project name is required");
  if (!localPath || !existsSync(localPath)) throw new Error("A real existing local project path is required");
  const phase = ["planning", "development", "testing", "production", "monitoring", "completed", "parked"].includes(input.phase) ? input.phase : "development";
  const endpoints = Array.isArray(input.endpoints) ? input.endpoints.filter((endpoint) => endpoint?.name && /^https?:\/\//i.test(endpoint?.url || "")).map((endpoint) => ({ name: String(endpoint.name), url: String(endpoint.url), expected: Array.isArray(endpoint.expected) ? endpoint.expected : [200] })) : [];
  const id = input.id && db.prepare("SELECT 1 FROM projects WHERE id=?").get(input.id) ? input.id : projectIdFromName(name);
  const existing = db.prepare("SELECT * FROM projects WHERE id=?").get(id);
  const now = isoNow();
  db.prepare(`INSERT INTO projects(id,name,department,phase,local_path,remote_url,endpoints_json,enabled,description,expected_completion,completed_at,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name,department=excluded.department,phase=excluded.phase,local_path=excluded.local_path,
    remote_url=excluded.remote_url,endpoints_json=excluded.endpoints_json,enabled=excluded.enabled,description=excluded.description,
    expected_completion=excluded.expected_completion,completed_at=excluded.completed_at,updated_at=excluded.updated_at`)
    .run(id, name, input.department || "Technology", phase, localPath, input.remoteUrl || discoverRemote(localPath), json(endpoints), input.enabled === false ? 0 : 1, input.description || "", input.expectedCompletion || null, input.completedAt || (phase === "completed" ? now : existing?.completed_at || null), existing?.created_at || now, now);
  logEvent(existing ? "project.updated" : "project.created", "info", `${name} ${existing ? "updated" : "registered"}`, id, null, { phase, endpointCount: endpoints.length });
  return projectProjection(db.prepare("SELECT * FROM projects WHERE id=?").get(id));
}

function createCampaign(input) {
  const title = String(input.title || "").trim();
  if (!title) throw new Error("Campaign title is required");
  const now = isoNow();
  const id = `cmp_${randomUUID()}`;
  db.prepare(`INSERT INTO campaigns(id,title,platform,status,owner,content_summary,planned_at,published_at,metrics_json,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?)`).run(id, title, input.platform || "Multi-platform", input.status || "planned", input.owner || "Unassigned", input.contentSummary || "", input.plannedAt || null, null, "{}", now, now);
  logEvent("campaign.created", "info", `${title} added to campaign pipeline`, null, null, { id });
  return db.prepare("SELECT * FROM campaigns WHERE id=?").get(id);
}

let researchCursor = 0;
async function runResearch(reason = "schedule") {
  if (getSettings().research === false) return { skipped: true, reason: "disabled" };
  const candidates = db.prepare("SELECT * FROM projects WHERE enabled=1 AND local_path IS NOT NULL ORDER BY name").all()
    .filter((project) => existsSync(join(project.local_path, "package.json")));
  if (!candidates.length) return { skipped: true, reason: "no-supported-projects" };
  const project = candidates[researchCursor % candidates.length];
  researchCursor += 1;
  const result = await dependencyObservation(project);
  saveObservation(project.id, "research", result);
  logEvent("research.completed", result.status === "error" ? "warning" : "info", `${project.name}: ${result.detail}`, project.id, null, { reason, source: result.source || null });
  return { ok: result.status !== "error", projectId: project.id, result };
}

function generateDailyReport(force = false) {
  const date = indiaDate();
  const existing = db.prepare("SELECT * FROM daily_reports WHERE report_date=? ORDER BY revision DESC LIMIT 1").get(date);
  if (existing && !force) return parseJson(existing.content_json, {});
  const projects = db.prepare("SELECT * FROM projects WHERE enabled=1 ORDER BY name").all().map(projectProjection);
  const tasks = db.prepare("SELECT * FROM work_items ORDER BY created_at DESC").all();
  const events = db.prepare("SELECT * FROM events WHERE created_at>=? ORDER BY created_at DESC LIMIT 100").all(`${date}T00:00:00.000Z`);
  const content = {
    date,
    executiveSummary: {
      projectsObserved: projects.length,
      healthy: projects.filter((project) => project.health === "healthy").length,
      warning: projects.filter((project) => project.health === "warning").length,
      failing: projects.filter((project) => project.health === "error").length,
      unknown: projects.filter((project) => ["unknown", "unconfigured"].includes(project.health)).length,
    },
    work: {
      total: tasks.length,
      completed: tasks.filter((task) => task.status === "completed").length,
      inProgress: tasks.filter((task) => ["assigned", "in_progress", "verification"].includes(task.status)).length,
      blocked: tasks.filter((task) => task.status === "blocked").length,
      intake: tasks.filter((task) => task.status === "intake").length,
    },
    incidents: events.filter((event) => ["warning", "critical"].includes(event.severity)).slice(0, 20),
    projects,
    evidenceCutoff: isoNow(),
  };
  const revision = Number(existing?.revision || 0) + 1;
  db.prepare("INSERT INTO daily_reports(id,report_date,revision,content_json,evidence_cutoff,created_at) VALUES(?,?,?,?,?,?)")
    .run(randomUUID(), date, revision, json(content), content.evidenceCutoff, isoNow());
  return content;
}

function dashboardProjection() {
  const projects = db.prepare("SELECT * FROM projects WHERE enabled=1 ORDER BY name").all().map(projectProjection);
  const workItems = db.prepare("SELECT * FROM work_items ORDER BY created_at DESC LIMIT 100").all();
  const models = db.prepare("SELECT * FROM model_health").all().map((row) => ({ ...row, payload: parseJson(row.payload_json, {}) }))
    .sort((a, b) => Number(a.payload.rank ?? 500) - Number(b.payload.rank ?? 500) || a.model_key.localeCompare(b.model_key));
  const events = db.prepare("SELECT * FROM events ORDER BY created_at DESC LIMIT 30").all().map((row) => ({ ...row, payload: parseJson(row.payload_json, {}) }));
  const reportRow = db.prepare("SELECT * FROM daily_reports ORDER BY report_date DESC,revision DESC LIMIT 1").get();
  const connectors = db.prepare("SELECT * FROM connectors ORDER BY category,name").all().map((row) => ({ ...row, payload: parseJson(row.payload_json, {}) }));
  const campaigns = db.prepare("SELECT * FROM campaigns ORDER BY COALESCE(planned_at,created_at) DESC LIMIT 100").all().map((row) => ({ ...row, metrics: parseJson(row.metrics_json, {}) }));
  return {
    service: { online: true, startedAt, uptimeSeconds: Math.floor(process.uptime()), pollSeconds: pollMs / 1000, checksRunning },
    settings: getSettings(), projects, workItems, models, events, connectors, campaigns,
    approvals: workItems.filter((item) => item.status === "approval"),
    completedProducts: projects.filter((project) => ["completed", "monitoring"].includes(project.phase)),
    report: reportRow ? { ...reportRow, content: parseJson(reportRow.content_json, {}) } : null,
    generatedAt: isoNow(),
  };
}

function createWorkItem(input) {
  const kind = ["PROJECT", "BIG TASK", "SMALL TASK"].includes(input.kind) ? input.kind : "SMALL TASK";
  const title = String(input.title || "").trim();
  if (!title) throw new Error("Title is required");
  const id = `ais_${kind === "PROJECT" ? "prj" : "tsk"}_${randomUUID()}`;
  const now = isoNow();
  const description = String(input.description || "").trim();
  const acceptance = String(input.acceptanceCriteria || "").trim();
  const riskText = `${title} ${description}`.toLowerCase();
  const riskClass = /(payment|security|credential|production deploy|migration|delete|customer data|auth)/.test(riskText) ? "R3" : kind === "SMALL TASK" ? "R1" : "R2";
  const projectAliases = {
    "aradhana android app": "aradhana-android-expo",
    "smartqr": "smartqr-print-server",
    "rate dashboard": "gold-rate-monitor",
  };
  const requestedProject = String(input.projectName || input.source?.project || "").trim().toLowerCase();
  const projectId = input.projectId || projectAliases[requestedProject] || db.prepare("SELECT id FROM projects WHERE lower(name)=? AND enabled=1").get(requestedProject)?.id || null;
  const status = riskClass === "R3" ? "approval" : kind === "SMALL TASK" && acceptance && projectId ? "ready" : "intake";
  db.prepare(`INSERT INTO work_items(id,kind,title,description,project_id,department,priority,status,eta_at,acceptance_criteria,assigned_to,risk_class,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, kind, title, description, projectId, input.department || "Technology", input.priority || "Normal", status, input.eta || null, acceptance, "local-supervisor-current", riskClass, now, now);
  logEvent("work.created", "info", `${kind}: ${title}`, projectId, id, { status, riskClass, source: input.source || null });
  return db.prepare("SELECT * FROM work_items WHERE id=?").get(id);
}

function recordModelProbe(input) {
  const modelKey = String(input.modelKey || "").trim();
  if (!modelKey.startsWith("opencode/")) throw new Error("Only OpenCode reserve probes may be recorded here");
  const current = db.prepare("SELECT * FROM model_health WHERE model_key=?").get(modelKey);
  if (!current) throw new Error("Model is not present in the live catalog");
  const ok = Boolean(input.ok);
  const detail = ok
    ? `Live smoke test passed${Number.isFinite(Number(input.latencyMs)) ? ` in ${Number(input.latencyMs)} ms` : ""}`
    : `Smoke test failed: ${String(input.detail || "unknown failure")}`;
  db.prepare("UPDATE model_health SET status=?,detail=?,checked_at=? WHERE model_key=?")
    .run(ok ? "ready" : "offline", detail, isoNow(), modelKey);
  logEvent("model.probed", ok ? "info" : "warning", `${modelKey}: ${detail}`, null, null, { modelKey, ok, latencyMs: input.latencyMs || null });
  return db.prepare("SELECT * FROM model_health WHERE model_key=?").get(modelKey);
}

function setWorkStatus(id, status, assignedTo = null) {
  db.prepare("UPDATE work_items SET status=?,assigned_to=COALESCE(?,assigned_to),updated_at=? WHERE id=?")
    .run(status, assignedTo, isoNow(), id);
}

function trackedSensitiveFiles(repoPath) {
  try {
    const output = execFileSync("git", ["-C", repoPath, "ls-files"], { encoding: "utf8", timeout: 10000, windowsHide: true });
    return output.split(/\r?\n/).filter((file) => /(^|\/)(\.env(?:\.|$)|credentials?|secrets?|google-services\.json$)|\.(jks|keystore|pem|p12|pfx)$/i.test(file));
  } catch {
    return ["<unable-to-enumerate-tracked-files>"];
  }
}

function chooseCodingModel() {
  const premium = db.prepare("SELECT model_key,payload_json FROM model_health WHERE status='ready' AND provider IN ('Claude','Google')").all()
    .map((row) => ({ ...row, payload: parseJson(row.payload_json, {}) }))
    .filter((row) => row.payload.executableModel)
    .sort((a, b) => Number(a.payload.rank ?? 999) - Number(b.payload.rank ?? 999))[0];
  if (premium?.payload.executableModel) return premium.payload.executableModel;
  const freeOrder = ["opencode/big-pickle", "opencode/mimo-v2.5-free", "opencode/hy3-free", "opencode/muse-spark-1.2-contributor-free", "opencode/nemotron-3-ultra-free"];
  for (const modelKey of freeOrder) {
    const row = db.prepare("SELECT status FROM model_health WHERE model_key=?").get(modelKey);
    if (row?.status === "ready") return modelKey;
  }
  return null;
}

async function verifyWorktree(worktreePath) {
  const checks = [];
  const packagePath = join(worktreePath, "package.json");
  if (existsSync(packagePath)) {
    const packageJson = parseJson(readFileSync(packagePath, "utf8"), {});
    const scripts = packageJson.scripts || {};
    const npmExecutable = process.platform === "win32" ? "C:\\Program Files\\nodejs\\npm.cmd" : "npm";
    const script = scripts.test && !/no test specified/i.test(String(scripts.test)) ? "test" : scripts.lint ? "lint" : null;
    if (script) {
      try {
        const result = await execFileAsync(npmExecutable, ["run", script], { cwd: worktreePath, encoding: "utf8", timeout: 900000, windowsHide: true, maxBuffer: 4 * 1024 * 1024 });
        checks.push({ name: `npm run ${script}`, passed: true, output: result.stdout.slice(-4000) });
      } catch (error) {
        checks.push({ name: `npm run ${script}`, passed: false, output: `${error.stdout || ""}\n${error.stderr || error.message}`.slice(-4000) });
      }
    }
  }
  if (existsSync(join(worktreePath, "requirements.txt")) || existsSync(join(worktreePath, "pyproject.toml"))) {
    try {
      await execFileAsync("python", ["-m", "compileall", "-q", "."], { cwd: worktreePath, encoding: "utf8", timeout: 300000, windowsHide: true, maxBuffer: 2 * 1024 * 1024 });
      checks.push({ name: "python compileall", passed: true, output: "Python sources compiled" });
    } catch (error) {
      checks.push({ name: "python compileall", passed: false, output: `${error.stdout || ""}\n${error.stderr || error.message}`.slice(-4000) });
    }
  }
  if (!checks.length) checks.push({ name: "project verifier", passed: false, output: "Blocked: no project-owned automated verifier is configured" });
  return checks;
}

let workerRunning = false;
async function workerTick() {
  if (workerRunning) return;
  const settings = getSettings();
  if (settings.master === false || settings.coding === false || settings.development === false) return;
  const task = db.prepare("SELECT * FROM work_items WHERE status='ready' AND kind='SMALL TASK' ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 ELSE 2 END,created_at LIMIT 1").get();
  if (!task) return;
  workerRunning = true;
  try {
    const project = task.project_id ? db.prepare("SELECT * FROM projects WHERE id=? AND enabled=1").get(task.project_id) : null;
    if (!project?.local_path || !existsSync(join(project.local_path, ".git"))) {
      setWorkStatus(task.id, "blocked");
      logEvent("worker.blocked", "warning", "Task has no executable Git project", task.project_id, task.id);
      return;
    }
    const git = await gitObservation(project);
    if (git.status !== "healthy") {
      setWorkStatus(task.id, "blocked");
      logEvent("worker.blocked", "warning", `Repository is not clean: ${git.detail}`, project.id, task.id, git);
      return;
    }
    const model = chooseCodingModel();
    if (!model) {
      setWorkStatus(task.id, "blocked");
      logEvent("worker.blocked", "warning", "No verified coding model available", project.id, task.id);
      return;
    }
    if (model.startsWith("opencode/") && trackedSensitiveFiles(project.local_path).length) {
      const files = trackedSensitiveFiles(project.local_path);
      setWorkStatus(task.id, "blocked");
      logEvent("worker.blocked", "warning", "Free-model route blocked by tracked sensitive files", project.id, task.id, { files });
      return;
    }
    const shortId = task.id.replace(/[^a-z0-9]/gi, "").slice(-16).toLowerCase();
    const branch = `ais/${shortId}`;
    const worktreePath = join(worktreesDir, shortId);
    await execFileAsync("git", ["-C", project.local_path, "worktree", "add", "-b", branch, worktreePath, "HEAD"], { encoding: "utf8", timeout: 60000, windowsHide: true });
    setWorkStatus(task.id, "in_progress", model);
    logEvent("worker.started", "info", `${model} started ${task.title}`, project.id, task.id, { model, branch, worktreePath });
    const prompt = `Implement this approved small task in the current Git worktree.\n\nTask: ${task.title}\nDescription: ${task.description}\nAcceptance criteria: ${task.acceptance_criteria}\n\nRules: stay inside this repository; do not access credentials; do not deploy, merge, push, publish, or contact external users; do not weaken tests; make the smallest reliable change; run relevant local checks; leave all changes uncommitted for deterministic AIS verification and human review.`;
    const opencodeExecutable = process.platform === "win32"
      ? "C:\\Users\\kaila\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\bin\\opencode.exe"
      : "opencode";
    const started = Date.now();
    const result = await execFileAsync(opencodeExecutable, ["run", "-m", model, prompt], { cwd: worktreePath, encoding: "utf8", timeout: 1800000, windowsHide: true, maxBuffer: 8 * 1024 * 1024 });
    setWorkStatus(task.id, "verification", model);
    const diff = await execFileAsync("git", ["-C", worktreePath, "diff", "--binary"], { encoding: "utf8", timeout: 60000, windowsHide: true, maxBuffer: 16 * 1024 * 1024 });
    const status = await execFileAsync("git", ["-C", worktreePath, "status", "--porcelain=v1"], { encoding: "utf8", timeout: 30000, windowsHide: true });
    const checks = await verifyWorktree(worktreePath);
    const evidence = {
      model, branch, worktreePath, durationMs: Date.now() - started,
      changed: status.stdout.trim().split(/\r?\n/).filter(Boolean),
      diffSha256: createHash("sha256").update(diff.stdout).digest("hex"),
      checks,
      workerOutput: result.stdout.slice(-6000),
    };
    const passed = evidence.changed.length > 0 && checks.every((check) => check.passed);
    setWorkStatus(task.id, passed ? "approval" : "blocked", model);
    logEvent(passed ? "worker.verified" : "worker.failed", passed ? "info" : "warning", passed ? "Worker output passed available deterministic checks; human approval required" : "Worker output failed verification", project.id, task.id, evidence);
  } catch (error) {
    setWorkStatus(task.id, "blocked");
    logEvent("worker.failed", "warning", error instanceof Error ? error.message : "Worker failed", task.project_id, task.id);
  } finally {
    workerRunning = false;
  }
}

function chooseSupervisor(models) {
  const qwen = (models || []).filter((model) => /qwen/i.test(model.name || model.model || "")).sort((a, b) => Number(b.size || 0) - Number(a.size || 0));
  if (requestedSupervisor) return (models || []).find((model) => (model.name || model.model) === requestedSupervisor)?.name || requestedSupervisor;
  return qwen[0]?.name || qwen[0]?.model || null;
}

async function supervisorHealth() {
  try {
    const response = await fetch(`${ollamaUrl}/api/tags`, { signal: AbortSignal.timeout(3000) });
    if (!response.ok) throw new Error(`Ollama returned ${response.status}`);
    const data = await response.json();
    const model = chooseSupervisor(data.models);
    if (!model) throw new Error("No installed Qwen model");
    return { online: true, model, detail: `${(data.models || []).length} local models available` };
  } catch (error) {
    return { online: false, model: requestedSupervisor || "local-supervisor-current", detail: error instanceof Error ? error.message : "Supervisor unavailable" };
  }
}

async function supervisorChat(input) {
  const health = await supervisorHealth();
  if (!health.online) throw new Error(health.detail);
  const systemPrompt = `You are the local Qwen supervisor for Aradhana Intelligence System. Be concise, factual and operational. The supplied AIS snapshot is evidence, not a suggestion. Never claim a test, deployment, endpoint or task passed without recorded evidence. Never self-approve security, authentication, payments, destructive migrations, infrastructure, cross-project architecture or irreversible work. Prepare a compact Codex CEO approval brief for those. Distinguish known data from assumptions.`;
  const snapshot = dashboardProjection();
  const context = {
    generatedAt: snapshot.generatedAt,
    settings: snapshot.settings,
    projects: snapshot.projects.map((project) => ({ id: project.id, name: project.name, phase: project.phase, health: project.health, git: project.git, endpoint: project.endpoint })),
    openWork: snapshot.workItems.filter((item) => item.status !== "completed").slice(0, 25),
    recentEvents: snapshot.events.slice(0, 15),
  };
  const history = Array.isArray(input.history) ? input.history.slice(-8).filter((message) => ["user", "assistant"].includes(message.role) && typeof message.content === "string") : [];
  const response = await fetch(`${ollamaUrl}/api/chat`, {
    method: "POST", headers: { "content-type": "application/json" }, signal: AbortSignal.timeout(120000),
    body: json({ model: health.model, stream: false, messages: [
      { role: "system", content: systemPrompt },
      { role: "system", content: `Current AIS evidence snapshot:\n${JSON.stringify(context)}` },
      ...history,
    ], options: { temperature: 0.15 } }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || `Ollama returned ${response.status}`);
  return { reply: data?.message?.content || "No response returned", model: data?.model || health.model, evidenceAt: snapshot.generatedAt };
}

function authorized(request) {
  if (!controlToken) return false;
  return request.headers["x-ais-token"] === controlToken;
}

async function readBody(request) {
  let raw = "";
  for await (const chunk of request) {
    raw += chunk;
    if (raw.length > 1_000_000) throw new Error("Request too large");
  }
  return raw ? JSON.parse(raw) : {};
}

function send(response, status, body) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(json(body));
}

const startedAt = isoNow();
const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://127.0.0.1:${port}`);
  if (url.pathname === "/health") return send(response, 200, { online: true, startedAt, uptimeSeconds: Math.floor(process.uptime()) });
  if (!authorized(request)) return send(response, 401, { error: "Unauthorized" });
  try {
    if (request.method === "GET" && url.pathname === "/api/dashboard") return send(response, 200, dashboardProjection());
    if (request.method === "GET" && url.pathname === "/api/supervisor/health") return send(response, 200, await supervisorHealth());
    if (request.method === "POST" && url.pathname === "/api/supervisor/chat") return send(response, 200, await supervisorChat(await readBody(request)));
    if (request.method === "POST" && url.pathname === "/api/checks/run") return send(response, 200, await runChecks("manual"));
    if (request.method === "POST" && url.pathname === "/api/research/run") return send(response, 200, await runResearch("manual"));
    if (request.method === "PUT" && url.pathname.startsWith("/api/controls/")) {
      const key = decodeURIComponent(url.pathname.split("/").pop());
      const allowed = ["master", "coding", "development", "production", "git", "research", "marketing"];
      if (!allowed.includes(key)) return send(response, 400, { error: "Unknown control" });
      const body = await readBody(request);
      setSetting(key, Boolean(body.enabled));
      if (key === "master") for (const child of allowed.slice(1)) setSetting(child, Boolean(body.enabled));
      if (key !== "master" && Boolean(body.enabled)) setSetting("master", true);
      return send(response, 200, { settings: getSettings() });
    }
    if (request.method === "POST" && url.pathname === "/api/projects") return send(response, 201, { project: saveProject(await readBody(request)) });
    if (request.method === "POST" && url.pathname === "/api/campaigns") return send(response, 201, { campaign: createCampaign(await readBody(request)) });
    if (request.method === "POST" && url.pathname === "/api/work-items") return send(response, 201, { item: createWorkItem(await readBody(request)) });
    if (request.method === "POST" && url.pathname === "/api/models/probe-result") return send(response, 200, { model: recordModelProbe(await readBody(request)) });
    if (request.method === "POST" && url.pathname === "/api/reports/generate") return send(response, 201, { report: generateDailyReport(true) });
    return send(response, 404, { error: "Not found" });
  } catch (error) {
    logEvent("api.error", "warning", error instanceof Error ? error.message : "API error");
    return send(response, 500, { error: error instanceof Error ? error.message : "Internal error" });
  }
});

server.listen(port, "127.0.0.1", () => {
  writeFileSync(join(root, "ais-control.pid"), String(process.pid));
  logEvent("service.started", "info", `AIS control plane started on 127.0.0.1:${port}`);
  runChecks("startup").catch((error) => logEvent("checks.failed", "warning", error.message));
});

const pollTimer = setInterval(() => {
  const settings = getSettings();
  if (settings.master !== false) runChecks("schedule").catch((error) => logEvent("checks.failed", "warning", error.message));
}, pollMs);
pollTimer.unref();

const workerTimer = setInterval(() => {
  workerTick().catch((error) => logEvent("worker.failed", "warning", error.message));
}, 30000);
workerTimer.unref();

setTimeout(() => runResearch("startup").catch((error) => logEvent("research.failed", "warning", error.message)), 30000).unref();
const researchTimer = setInterval(() => {
  if (getSettings().master !== false) runResearch("schedule").catch((error) => logEvent("research.failed", "warning", error.message));
}, 30 * 60 * 1000);
researchTimer.unref();

function shutdown(signal) {
  logEvent("service.stopped", "info", `AIS control plane stopping (${signal})`);
  server.close(() => { db.close(); process.exit(0); });
  setTimeout(() => process.exit(1), 5000).unref();
}
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
