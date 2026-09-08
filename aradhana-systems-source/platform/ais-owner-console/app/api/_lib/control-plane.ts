const baseUrl = process.env.AIS_CONTROL_URL || "http://127.0.0.1:4317";
const token = process.env.AIS_CONTROL_TOKEN || "";

export async function controlPlaneFetch(path: string, init: RequestInit = {}) {
  if (!token) throw new Error("AIS control-plane token is not configured");
  const headers = new Headers(init.headers);
  headers.set("x-ais-token", token);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  return fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
}

export async function controlPlaneJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await controlPlaneFetch(path, init);
  const data = (await response.json().catch(() => null)) as T & { error?: string };
  if (!response.ok) throw new Error(data?.error || `AIS control plane returned ${response.status}`);
  return data;
}
