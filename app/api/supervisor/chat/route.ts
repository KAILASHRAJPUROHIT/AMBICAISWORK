const endpoint = process.env.LOCAL_SUPERVISOR_URL || "http://127.0.0.1:11434";
const preferredModel = process.env.LOCAL_SUPERVISOR_MODEL || "qwen3:8b";
const scannerEndpoint = process.env.PROJECT_SCANNER_URL || "http://127.0.0.1:8787";
import { controlPlaneJson } from "../../_lib/control-plane";

type Message = { role: "user" | "assistant"; content: string };
type ScannedRepo = {
  name: string;
  path: string;
  branch: string;
  remote: string;
  dirty: boolean;
  lastCommitAt: string;
  lastCommitMessage: string;
  readmeSnippet: string;
};
type ScannedProject = { name: string; path: string; type: string; readmeSnippet: string };
type ScanIndex = {
  lastScanAt: string | null;
  lastScanTruncated: boolean;
  repos: ScannedRepo[];
  projects: ScannedProject[];
};
type ChangeEvent = {
  time: string;
  project: string;
  projectPath: string;
  isRepo: boolean;
  file: string;
  relFile: string;
  event: string;
};

const basePrompt = `You are the local Qwen supervisor for Aradhana Intelligence System. Be concise, factual and operational. You supervise project progress, Git health, production monitoring, model routing, departments, tasks, ETAs and daily reports. Never claim that a test, deployment, endpoint or task passed without deterministic evidence. Never self-approve security, authentication, payments, destructive migrations, infrastructure, cross-project architecture or irreversible work. For those, prepare a brief for Codex CEO approval. Distinguish known data from assumptions. Ask for missing repository or monitoring evidence when needed.`;

async function buildProjectIndexContext(): Promise<string> {
  try {
    const response = await fetch(`${scannerEndpoint}/index.json`, { signal: AbortSignal.timeout(2000) });
    if (!response.ok) return "";
    const data = (await response.json()) as ScanIndex;
    const repos = [...(data.repos || [])].sort((a, b) => (b.lastCommitAt || "").localeCompare(a.lastCommitAt || ""));
    const projects = data.projects || [];
    const shown = repos.slice(0, 40);
    const lines = shown.map((repo) => {
      const readme = repo.readmeSnippet ? ` — ${repo.readmeSnippet.slice(0, 160)}` : "";
      return `- ${repo.name} (${repo.path}) · branch ${repo.branch} · ${repo.dirty ? "uncommitted changes" : "clean"} · remote ${repo.remote || "none"} · last commit ${repo.lastCommitAt || "unknown"}: "${repo.lastCommitMessage || ""}"${readme}`;
    });
    const otherProjects = projects
      .slice(0, 15)
      .map((project) => `- ${project.name} (${project.path}) · ${project.type}${project.readmeSnippet ? ` — ${project.readmeSnippet.slice(0, 160)}` : ""}`);
    if (lines.length === 0 && otherProjects.length === 0) return "";
    return [
      `\n\nLOCAL PROJECT INDEX (from the disk scanner, last refreshed ${data.lastScanAt || "unknown"}${data.lastScanTruncated ? ", scan was time/entry-limited and may be incomplete" : ""}):`,
      `Total Git repos found: ${repos.length}${repos.length > shown.length ? ` (showing ${shown.length} most recently committed)` : ""}.`,
      ...lines,
      otherProjects.length > 0 ? `Other non-Git projects (showing up to 15 of ${projects.length}):` : "",
      ...otherProjects,
      "\nUse this index to answer questions about what projects/repos exist on this PC. It is metadata plus a short README excerpt only — you do not have access to full file contents. If asked about something not in this list, say it wasn't found in the last scan rather than guessing.",
    ]
      .filter(Boolean)
      .join("\n");
  } catch {
    return "";
  }
}

async function buildRecentChangesContext(): Promise<string> {
  try {
    const response = await fetch(`${scannerEndpoint}/changes.json?limit=20`, { signal: AbortSignal.timeout(2000) });
    if (!response.ok) return "";
    const data = (await response.json()) as { watching?: number; skipped?: number; events?: ChangeEvent[] };
    const events = data.events || [];
    if (events.length === 0) return "";
    const lines = events.map(
      (event) => `- [${event.time}] ${event.event} · ${event.project} (${event.isRepo ? "git repo" : "project"}) · ${event.relFile}`,
    );
    return [
      `\n\nRECENT FILE CHANGES (live watcher across ${data.watching || 0} project folders${data.skipped ? `, ${data.skipped} more not watched due to the cap` : ""}, most recent first):`,
      ...lines,
      "\nThis only shows that a file changed and when, not who — for Git-tracked files you can ask for the last commit author via the file's history; uncommitted changes have no author attribution.",
    ].join("\n");
  } catch {
    return "";
  }
}

async function buildControlPlaneContext(): Promise<string> {
  try {
    const data = await controlPlaneJson<{
      generatedAt: string;
      settings: Record<string, unknown>;
      projects: Array<{ name: string; phase: string; health: string; git: unknown; endpoint: unknown }>;
      workItems: Array<{ kind: string; title: string; status: string; priority: string; eta_at?: string }>;
      models: Array<{ model_key: string; role: string; status: string; detail: string }>;
      events: Array<{ severity: string; message: string; created_at: string }>;
    }>("/api/dashboard");
    return `\n\nAIS CONTROL-PLANE EVIDENCE (captured ${data.generatedAt}):\n${JSON.stringify({
      controls: data.settings,
      projects: data.projects,
      openWork: data.workItems.filter((item) => item.status !== "completed").slice(0, 25),
      modelHealth: data.models,
      recentEvents: data.events.slice(0, 15),
    })}\nTreat this deterministic snapshot as evidence. Never silently replace missing or failing evidence with assumptions.`;
  } catch {
    return "\n\nAIS CONTROL-PLANE EVIDENCE: unavailable. Clearly say live operational evidence is unavailable.";
  }
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { message?: string; history?: Message[] } | null;
  if (!body?.message?.trim()) return Response.json({ error: "Message required" }, { status: 400 });
  const history = Array.isArray(body.history) ? body.history.slice(-10) : [];
  const [projectContext, changesContext, controlContext] = await Promise.all([buildProjectIndexContext(), buildRecentChangesContext(), buildControlPlaneContext()]);
  const systemPrompt = basePrompt + projectContext + changesContext + controlContext;
  try {
    const tagsResponse = await fetch(`${endpoint}/api/tags`, { signal: AbortSignal.timeout(2500) });
    if (!tagsResponse.ok) throw new Error(`Runtime returned ${tagsResponse.status}`);
    const tags = (await tagsResponse.json()) as { models?: Array<{ name?: string; model?: string }> };
    const installed = tags.models || [];
    const exact = installed.find((entry) => (entry.name || entry.model) === preferredModel);
    const qwen = installed
      .filter((entry) => /qwen/i.test(entry.name || entry.model || ""))
      .sort((left, right) => (right.name || right.model || "").localeCompare(left.name || left.model || ""))[0];
    const activeModel = exact?.name || exact?.model || qwen?.name || qwen?.model;
    if (!activeModel) throw new Error("No installed Qwen model found");
    const response = await fetch(`${endpoint}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(90_000),
      body: JSON.stringify({
        model: activeModel,
        stream: false,
        messages: [{ role: "system", content: systemPrompt }, ...history],
        options: { temperature: 0.2 },
      }),
    });
    const data = (await response.json().catch(() => null)) as { message?: { content?: string }; model?: string; error?: string } | null;
    if (!response.ok) throw new Error(data?.error || `Local runtime returned ${response.status}`);
    return Response.json({ reply: data?.message?.content || "No response returned.", model: data?.model || activeModel });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? `Local supervisor unavailable: ${error.message}` : "Local supervisor unavailable" },
      { status: 503 },
    );
  }
}
