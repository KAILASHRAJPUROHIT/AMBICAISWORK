import { controlPlaneFetch } from "../../../_lib/control-plane";
import { requireSession } from "../../../_lib/session";

export async function PUT(request: Request, context: { params: Promise<{ key: string }> }) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  const { key } = await context.params;
  const body = await request.text();
  try {
    const upstream = await controlPlaneFetch(`/api/controls/${encodeURIComponent(key)}`, { method: "PUT", body });
    return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Control plane unavailable" }, { status: 503 });
  }
}
