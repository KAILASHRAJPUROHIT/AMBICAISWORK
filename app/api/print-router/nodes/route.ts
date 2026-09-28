import { controlPlaneFetch } from "../../_lib/control-plane";
import { requireSession } from "../../_lib/session";

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  try {
    const upstream = await controlPlaneFetch("/api/print-router/nodes");
    return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Print Router control plane unavailable" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  try {
    const upstream = await controlPlaneFetch("/api/print-router/nodes/refresh", { method: "POST" });
    return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Print Router control plane unavailable" }, { status: 503 });
  }
}
