import { requireSession } from "../../_lib/session";
import { controlPlaneFetch } from "../../_lib/control-plane";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const unauthorized = await requireSession(request);
  if (unauthorized) return unauthorized;

  try {
    const upstream = await controlPlaneFetch("/api/system/metrics");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store, no-cache, must-revalidate, proxy-revalidate",
      },
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "System metrics service unavailable" },
      { status: 503 }
    );
  }
}
