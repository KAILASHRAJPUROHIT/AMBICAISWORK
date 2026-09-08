const endpoint = process.env.LOCAL_SUPERVISOR_URL || "http://127.0.0.1:11434";
const preferredModel = process.env.LOCAL_SUPERVISOR_MODEL || "qwen3:8b";
const scannerEndpoint = process.env.PROJECT_SCANNER_URL || "http://127.0.0.1:8787";
import { controlPlaneJson } from "../../_lib/control-plane";

async function scannerStatus() {
  try {
    const response = await fetch(`${scannerEndpoint}/health`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) throw new Error(`Scanner returned ${response.status}`);
    const data = (await response.json()) as {
      scanning?: boolean;
      scanProgress?: { visited: number; repos: number; projects: number; elapsedSec: number } | null;
      lastScanAt?: string | null;
      totalRepos?: number;
      totalProjects?: number;
      watching?: number;
      recentChangeCount?: number;
    };
    return {
      online: true,
      scanning: Boolean(data.scanning),
      scanProgress: data.scanProgress || null,
      lastScanAt: data.lastScanAt || null,
      totalRepos: data.totalRepos || 0,
      totalProjects: data.totalProjects || 0,
      watching: data.watching || 0,
      recentChangeCount: data.recentChangeCount || 0,
    };
  } catch {
    return { online: false, scanning: false, scanProgress: null, lastScanAt: null, totalRepos: 0, totalProjects: 0, watching: 0, recentChangeCount: 0 };
  }
}

export async function GET() {
  const [scanner, controlPlane] = await Promise.all([
    scannerStatus(),
    controlPlaneJson<{ service?: { online?: boolean; uptimeSeconds?: number; pollSeconds?: number }; projects?: unknown[]; generatedAt?: string }>("/api/dashboard")
      .then((data) => ({ online: Boolean(data.service?.online), uptimeSeconds: data.service?.uptimeSeconds || 0, pollSeconds: data.service?.pollSeconds || 0, projects: data.projects?.length || 0, generatedAt: data.generatedAt || null }))
      .catch(() => ({ online: false, uptimeSeconds: 0, pollSeconds: 0, projects: 0, generatedAt: null })),
  ]);
  try {
    const response = await fetch(`${endpoint}/api/tags`, { signal: AbortSignal.timeout(2500) });
    if (!response.ok) throw new Error(`Runtime returned ${response.status}`);
    const data = (await response.json()) as { models?: Array<{ name?: string; model?: string }> };
    const installed = data.models || [];
    const exact = installed.find((entry) => (entry.name || entry.model) === preferredModel);
    const qwen = installed
      .filter((entry) => /qwen/i.test(entry.name || entry.model || ""))
      .sort((left, right) => (right.name || right.model || "").localeCompare(left.name || left.model || ""))[0];
    const model = exact?.name || exact?.model || qwen?.name || qwen?.model || preferredModel;
    return Response.json({ online: true, model, detail: `${installed.length} local model${installed.length === 1 ? "" : "s"} available`, scanner, controlPlane });
  } catch {
    return Response.json({ online: false, model: preferredModel, detail: `Waiting for ${endpoint}`, scanner, controlPlane }, { status: 503 });
  }
}
