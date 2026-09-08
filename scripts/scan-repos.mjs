#!/usr/bin/env node
/**
 * Local project/repo scanner companion process.
 *
 * This is intentionally NOT part of the Cloudflare Worker app — Workers
 * (even under `vinext dev` / Miniflare) have no access to the real host
 * filesystem. This is a plain Node.js process with real `fs` access that
 * walks the disk and serves a read-only JSON index over localhost, the
 * same way a local Ollama runtime is queried at 127.0.0.1:11434.
 *
 * It reads file *metadata* and (optionally) the first slice of each
 * project's README — never full file contents, never anything outside a
 * detected project/repo root.
 *
 * Run with: npm run scan
 */

// libuv's threadpool (default size 4) backs fs.promises calls. A whole-disk
// walk will inevitably hit a few genuinely slow directory reads (huge
// system folders, indexer/AV-intercepted paths); with only 4 worker
// threads, a handful of those in flight at once can starve every other
// pending filesystem call process-wide — even ones our own JS-level
// withTimeout() has already given up on, since that only abandons *our*
// promise, not the underlying OS read still occupying a thread. Must be set
// before the first threadpool-using async call (libuv reads it lazily).
process.env.UV_THREADPOOL_SIZE = process.env.UV_THREADPOOL_SIZE || "64";

import { createServer } from "node:http";
import { readdir, readFile, lstat, access, mkdir, writeFile } from "node:fs/promises";
import { watch } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import os from "node:os";

const execFileAsync = promisify(execFile);

const PORT = Number(process.env.PROJECT_SCANNER_PORT || 8787);
const MAX_DEPTH = Number(process.env.PROJECT_SCAN_MAX_DEPTH || 14);
const MAX_MINUTES = Number(process.env.PROJECT_SCAN_MAX_MINUTES || 30);
const RESCAN_MINUTES = Number(process.env.PROJECT_SCAN_RESCAN_MINUTES || 180);
const README_CHARS = Number(process.env.PROJECT_SCAN_README_CHARS || 500);
const MAX_ENTRIES = Number(process.env.PROJECT_SCAN_MAX_ENTRIES || 3000);
const CONCURRENCY = Number(process.env.PROJECT_SCAN_CONCURRENCY || 8);
const CACHE_FILE = path.join(process.cwd(), ".local", "repo-index.json");

const WATCH_ENABLED = (process.env.PROJECT_WATCH_ENABLED ?? "true") !== "false";
const WATCH_MAX_EVENTS = Number(process.env.PROJECT_WATCH_MAX_EVENTS || 500);
const WATCH_MAX_ROOTS = Number(process.env.PROJECT_WATCH_MAX_ROOTS || 200);
const WATCH_RECURSIVE_SUPPORTED = os.platform() === "win32" || os.platform() === "darwin";

const DEFAULT_EXCLUDE_NAMES = new Set(
  [
    "node_modules", "bundled_node_modules", ".git", "dist", "build", "out", ".next", ".vinext", ".turbo",
    ".venv", "venv", "__pycache__", ".cache", ".wrangler", "target", "vendor", ".local",
    "AppData", "Windows", "Program Files", "Program Files (x86)", "ProgramData",
    "$Recycle.Bin", "System Volume Information", "Recovery", "PerfLogs",
    "MSOCache", "Config.Msi", "WindowsApps", ".Trash", ".npm", ".cargo",
    ".nuget", ".gradle", ".m2", "Windows.old",
    // Package-manager / dependency caches: these hold OTHER people's package
    // source (each with its own package.json/go.mod/etc.), not your projects.
    "site-packages", "labextensions", "pkgs", "pkg", "envs", "conda", "miniconda3",
    "go-install", "adobeTemp",
    // One-off personal backup archive that happens to contain a stray package.json.
    "claude-history-backup-20260822",
  ].map((name) => name.toLowerCase()),
);

// IDE/tool config and extension directories (.vscode, .cursor, .codex, .claude,
// .gemini, .continue, .antigravity-ide, ...) are near-universally caches or
// installed extensions, never a project you're working on — skip all of them
// by convention rather than naming each one.
function isNoiseDirName(name) {
  return name.startsWith(".") || DEFAULT_EXCLUDE_NAMES.has(name.toLowerCase());
}
const extraExcludes = (process.env.PROJECT_SCAN_EXCLUDES || "")
  .split(",")
  .map((name) => name.trim().toLowerCase())
  .filter(Boolean);
for (const name of extraExcludes) DEFAULT_EXCLUDE_NAMES.add(name);

// Whole-subtree excludes by absolute path prefix — for known third-party
// reference/vendored clones that live under an otherwise-normal folder name
// (so a bare directory-name exclude would be too broad or too narrow).
const EXCLUDE_PATH_PREFIXES = [
  "C:\\MCX_AI_Knowledge_Base\\source_repos",
  "C:\\Tools\\Exv",
  "C:\\Tools\\Trading",
  "C:\\Kuldeep_Avatar\\Gemini-API",
  path.join(os.homedir(), "ComfyUI-Installs"),
  ...(process.env.PROJECT_SCAN_EXCLUDE_PATHS || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean),
].map((prefix) => prefix.toLowerCase());

function isExcludedPath(dir) {
  const lower = dir.toLowerCase();
  return EXCLUDE_PATH_PREFIXES.some((prefix) => lower === prefix || lower.startsWith(prefix + path.sep));
}

// Directories that should still be walked into (so their real subfolders get
// scanned) but never registered as a "project" themselves — e.g. a user's
// home directory root sometimes picks up a stray package.json from some
// global tool, which isn't a project.
const SKIP_SELF_REGISTRATION_PATHS = new Set([os.homedir().toLowerCase()]);

const PROJECT_MARKERS = [
  "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
  "go.mod", "composer.json", "Gemfile", "pom.xml", "build.gradle",
];
const README_NAMES = ["README.md", "Readme.md", "readme.md", "README.txt", "README"];

function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function limiter(concurrency) {
  let active = 0;
  const queue = [];
  const next = () => {
    if (active >= concurrency || queue.length === 0) return;
    active++;
    const { fn, resolve, reject } = queue.shift();
    fn()
      .then(resolve, reject)
      .finally(() => {
        active--;
        next();
      });
  };
  return (fn) =>
    new Promise((resolve, reject) => {
      queue.push({ fn, resolve, reject });
      next();
    });
}

async function detectDriveRoots() {
  const override = (process.env.PROJECT_SCAN_ROOTS || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (override.length > 0) return override;
  if (os.platform() !== "win32") return ["/"];
  const roots = [];
  for (const code of "CDEFGHIJKLMNOPQRSTUVWXYZ") {
    const drive = `${code}:\\`;
    try {
      await access(drive);
      roots.push(drive);
    } catch {
      // drive not present, skip
    }
  }
  return roots.length ? roots : [os.homedir()];
}

async function readReadmeSnippet(dir) {
  for (const name of README_NAMES) {
    try {
      const content = await withTimeout(readFile(path.join(dir, name), "utf8"), 5000);
      return content.replace(/\s+/g, " ").trim().slice(0, README_CHARS);
    } catch {
      // try next candidate
    }
  }
  return "";
}

async function gitInfo(dir) {
  const run = async (args) => {
    try {
      // Belt-and-suspenders: execFile's own `timeout` option should kill a
      // hung git process, but a stdio pipe that doesn't close on kill (a
      // known Windows edge case) can leave the callback — and this promise —
      // pending forever. withTimeout() bounds our own control flow either way.
      const { stdout } = await withTimeout(
        execFileAsync("git", args, { cwd: dir, timeout: 4000, windowsHide: true }),
        6000,
      );
      return stdout.trim();
    } catch {
      return "";
    }
  };
  const [branch, remote, lastCommitRaw, status] = await Promise.all([
    run(["rev-parse", "--abbrev-ref", "HEAD"]),
    run(["remote", "get-url", "origin"]),
    run(["log", "-1", "--format=%cI%s"]),
    // -uno: don't enumerate untracked files/dirs individually — on Windows,
    // a large or unignored tree (e.g. a stray node_modules) can make plain
    // `git status --porcelain` take a very long time. This only reports
    // tracked-file changes as "dirty", which is enough for a health signal.
    run(["status", "--porcelain", "-uno"]),
  ]);
  const [lastCommitAt, lastCommitMessage] = lastCommitRaw ? lastCommitRaw.split("") : ["", ""];
  return {
    branch: branch || "unknown",
    remote: remote || "",
    lastCommitAt: lastCommitAt || "",
    lastCommitMessage: lastCommitMessage || "",
    dirty: Boolean(status),
  };
}

function projectType(markerFiles) {
  if (markerFiles.includes("package.json")) return "node";
  if (markerFiles.includes("pyproject.toml") || markerFiles.includes("requirements.txt")) return "python";
  if (markerFiles.includes("Cargo.toml")) return "rust";
  if (markerFiles.includes("go.mod")) return "go";
  if (markerFiles.includes("composer.json")) return "php";
  if (markerFiles.includes("Gemfile")) return "ruby";
  if (markerFiles.includes("pom.xml") || markerFiles.includes("build.gradle")) return "java";
  return "unknown";
}

const state = {
  scanning: false,
  scanProgress: null,
  lastScanAt: null,
  lastScanDurationMs: null,
  lastScanTruncated: false,
  repos: [],
  projects: [],
  roots: [],
};

const watchState = {
  watchers: new Map(), // rootPath -> fs.FSWatcher
  events: [], // most-recent-first ring buffer
  watchedRootCount: 0,
  skippedRootCount: 0,
};

function isExcludedRelPath(relPath) {
  return relPath.split(/[\\/]/).some((segment) => isNoiseDirName(segment));
}

function recordChange(root, eventType, filename) {
  if (!filename) return;
  const relPath = filename.toString();
  if (isExcludedRelPath(relPath)) return;
  watchState.events.unshift({
    time: new Date().toISOString(),
    project: root.name,
    projectPath: root.path,
    isRepo: root.isRepo,
    file: path.join(root.path, relPath),
    relFile: relPath,
    event: eventType,
  });
  if (watchState.events.length > WATCH_MAX_EVENTS) {
    watchState.events.length = WATCH_MAX_EVENTS;
  }
}

function updateWatchers(repos, projects) {
  if (!WATCH_ENABLED) return;
  if (!WATCH_RECURSIVE_SUPPORTED) {
    console.warn(`[scan-repos] recursive fs.watch is not reliably supported on ${os.platform()}; skipping live change tracking.`);
    return;
  }

  // Prioritise the most recently active repos, then projects, capped so we
  // don't hold thousands of OS watch handles open when the scan scope is
  // the whole PC.
  const rankedRepos = [...repos].sort((a, b) => (b.lastCommitAt || "").localeCompare(a.lastCommitAt || ""));
  const desired = [
    ...rankedRepos.map((repo) => ({ path: repo.path, name: repo.name, isRepo: true })),
    ...projects.map((project) => ({ path: project.path, name: project.name, isRepo: false })),
  ].slice(0, WATCH_MAX_ROOTS);
  watchState.skippedRootCount = Math.max(0, repos.length + projects.length - desired.length);

  const desiredPaths = new Set(desired.map((entry) => entry.path));

  for (const [rootPath, watcher] of watchState.watchers) {
    if (!desiredPaths.has(rootPath)) {
      watcher.close();
      watchState.watchers.delete(rootPath);
    }
  }

  for (const root of desired) {
    if (watchState.watchers.has(root.path)) continue;
    try {
      const watcher = watch(root.path, { recursive: true }, (eventType, filename) => recordChange(root, eventType, filename));
      watcher.on("error", () => {
        watcher.close();
        watchState.watchers.delete(root.path);
      });
      watchState.watchers.set(root.path, watcher);
    } catch {
      // permission-denied or otherwise unwatchable root — skip it
    }
  }

  watchState.watchedRootCount = watchState.watchers.size;
}

async function blameFile(rawPath) {
  // Accept either slash style from callers — normalise to the platform separator
  // before comparing against indexed repo paths (which use path.sep).
  const absoluteFilePath = path.normalize(rawPath.replace(/\//g, path.sep));
  const repo = state.repos.find(
    (candidate) => absoluteFilePath === candidate.path || absoluteFilePath.startsWith(candidate.path + path.sep),
  );
  if (!repo) return { error: "File is not inside any indexed Git repository." };
  const relFile = path.relative(repo.path, absoluteFilePath);
  try {
    const { stdout } = await execFileAsync(
      "git",
      ["log", "-1", "--format=%an\x1f%ae\x1f%aI\x1f%s", "--", relFile],
      { cwd: repo.path, timeout: 4000, windowsHide: true },
    );
    const [author, email, date, message] = stdout.trim().split("\x1f");
    if (!author) return { error: "No commit history found for this file (uncommitted or untracked)." };
    return { repo: repo.name, file: relFile, author, email, date, message };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "git log failed" };
  }
}

async function scanOnce() {
  if (state.scanning) return;
  state.scanning = true;
  const startedAt = Date.now();
  const deadline = startedAt + MAX_MINUTES * 60_000;
  const roots = await detectDriveRoots();
  state.roots = roots;
  const repos = [];
  const projects = [];
  const run = limiter(CONCURRENCY);
  let truncated = false;
  let visited = 0;

  const heartbeat = setInterval(() => {
    const elapsedSec = Math.round((Date.now() - startedAt) / 1000);
    console.log(`[scan-repos] still scanning… ${visited} dirs visited, ${repos.length} repos, ${projects.length} other projects found, ${elapsedSec}s elapsed.`);
    state.scanProgress = { visited, repos: repos.length, projects: projects.length, elapsedSec };
  }, 15_000);

  async function walk(dir, depth) {
    if (Date.now() > deadline) {
      truncated = true;
      return;
    }
    if (depth > MAX_DEPTH) return;
    if (isExcludedPath(dir)) return;
    if (repos.length + projects.length >= MAX_ENTRIES) {
      truncated = true;
      return;
    }

    let stat;
    try {
      // Only the leaf I/O call is gated by the concurrency limiter — never
      // the recursive walk() calls themselves. Gating recursion through the
      // same bounded pool a parent call also occupies is a self-deadlock:
      // once `concurrency` parent walk()s are all awaiting their own
      // children (which need a free pool slot to even start), every slot is
      // permanently held by a blocked parent and nothing can proceed.
      stat = await withTimeout(run(() => lstat(dir)), 5000);
    } catch {
      return;
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) return;

    let entries;
    try {
      entries = await withTimeout(run(() => readdir(dir, { withFileTypes: true })), 8000);
    } catch {
      return;
    }
    visited++;

    const names = entries.map((entry) => entry.name);
    const hasGit = entries.some((entry) => entry.isDirectory() && entry.name === ".git");
    const markerFiles = PROJECT_MARKERS.filter((marker) => names.includes(marker));
    const skipRegistration = SKIP_SELF_REGISTRATION_PATHS.has(dir.toLowerCase());

    if (hasGit && !skipRegistration) {
      const [info, readme] = await Promise.all([gitInfo(dir), readReadmeSnippet(dir)]);
      repos.push({
        name: path.basename(dir),
        path: dir,
        readmeSnippet: readme,
        ...info,
      });
      return; // don't descend into a detected repo's internals
    }
    if (hasGit) return; // still a repo boundary — just not registered

    if (markerFiles.length > 0 && !skipRegistration) {
      const readme = await readReadmeSnippet(dir);
      projects.push({
        name: path.basename(dir),
        path: dir,
        type: projectType(markerFiles),
        readmeSnippet: readme,
      });
      // still descend — a project folder can contain nested project subfolders
    }

    const subdirs = entries.filter(
      (entry) => entry.isDirectory() && !entry.isSymbolicLink() && !isNoiseDirName(entry.name),
    );
    // Recursion itself is NOT pool-gated (see the note above) — only the
    // readdir/lstat/git calls each walk() eventually makes are.
    await Promise.all(subdirs.map((entry) => walk(path.join(dir, entry.name), depth + 1)));
  }

  // Cooperative deadline checks inside walk() only fire between awaits, so a
  // single genuinely stuck filesystem/process call (rare, but plausible when
  // scanning an entire disk) could otherwise hang the scan forever. This
  // watchdog guarantees scanOnce() always finishes within MAX_MINUTES wall
  // clock and finalizes with whatever repos/projects were already collected.
  const walkAllRoots = (async () => {
    for (const root of roots) {
      if (Date.now() > deadline) {
        truncated = true;
        break;
      }
      await walk(root, 0);
    }
  })();
  const watchdog = new Promise((resolve) => {
    setTimeout(() => resolve("watchdog"), Math.max(0, deadline - Date.now()) + 5000);
  });
  const outcome = await Promise.race([walkAllRoots.then(() => "completed"), watchdog]);
  if (outcome === "watchdog") {
    truncated = true;
    console.warn(
      `[scan-repos] hard wall-clock limit reached with ${visited} dirs visited — a filesystem or git call likely stalled. Finalizing with the ${repos.length} repos and ${projects.length} projects collected so far.`,
    );
  }

  state.repos = repos;
  clearInterval(heartbeat);
  state.projects = projects;
  state.lastScanAt = new Date().toISOString();
  state.lastScanDurationMs = Date.now() - startedAt;
  state.lastScanTruncated = truncated;
  state.scanning = false;
  state.scanProgress = null;

  updateWatchers(repos, projects);

  try {
    await mkdir(path.dirname(CACHE_FILE), { recursive: true });
    await writeFile(CACHE_FILE, JSON.stringify(state, null, 2));
  } catch {
    // cache write is best-effort
  }

  console.log(
    `[scan-repos] scanned ${visited} dirs across ${roots.length} root(s) in ${state.lastScanDurationMs}ms — ${repos.length} repos, ${projects.length} other projects${truncated ? " (truncated by time/entry limit)" : ""}.`,
  );
}

async function loadCache() {
  try {
    const raw = await readFile(CACHE_FILE, "utf8");
    const cached = JSON.parse(raw);
    Object.assign(state, cached, { scanning: false });
    console.log(`[scan-repos] loaded cached index from ${CACHE_FILE} (${state.repos.length} repos, ${state.projects.length} projects).`);
  } catch {
    // no cache yet
  }
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  const url = new URL(req.url || "/", `http://localhost:${PORT}`);
  if (url.pathname === "/health") {
    return send(res, 200, {
      status: "ok",
      scanning: state.scanning,
      scanProgress: state.scanProgress,
      lastScanAt: state.lastScanAt,
      totalRepos: state.repos.length,
      totalProjects: state.projects.length,
      watching: watchState.watchedRootCount,
      watchSkipped: watchState.skippedRootCount,
      recentChangeCount: watchState.events.length,
    });
  }
  if (url.pathname === "/index.json") {
    return send(res, 200, state);
  }
  if (url.pathname === "/changes.json") {
    const limit = Number(url.searchParams.get("limit") || 100);
    return send(res, 200, {
      watching: watchState.watchedRootCount,
      skipped: watchState.skippedRootCount,
      events: watchState.events.slice(0, Math.max(1, Math.min(limit, WATCH_MAX_EVENTS))),
    });
  }
  if (url.pathname === "/blame") {
    const filePath = url.searchParams.get("path") || "";
    if (!filePath) return send(res, 400, { error: "?path= is required" });
    return blameFile(filePath).then((result) => send(res, result.error ? 404 : 200, result));
  }
  if (url.pathname === "/refresh" && req.method === "POST") {
    scanOnce();
    return send(res, 202, { started: true });
  }
  return send(res, 404, { error: "Not found" });
});

async function main() {
  await loadCache();
  if (state.repos.length || state.projects.length) {
    updateWatchers(state.repos, state.projects);
  }
  server.listen(PORT, "127.0.0.1", () => {
    console.log(`[scan-repos] serving project index on http://127.0.0.1:${PORT} (health, index.json, changes.json, blame, POST /refresh)`);
  });
  scanOnce();
  setInterval(scanOnce, RESCAN_MINUTES * 60_000);
}

main();
