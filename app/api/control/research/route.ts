import { controlPlaneFetch } from "../../_lib/control-plane";
import { requireSession } from "../../_lib/session";

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  try {
    const upstream = await controlPlaneFetch("/api/research/run", { method: "POST" });
    return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Improvement radar unavailable" }, { status: 503 });
  }
}
