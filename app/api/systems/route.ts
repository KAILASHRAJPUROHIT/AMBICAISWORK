import { requireSession } from "../_lib/session";
import { controlPlaneFetch } from "../_lib/control-plane";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  try {
    const upstream = await controlPlaneFetch("/api/systems");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store, no-cache, must-revalidate, proxy-revalidate",
      },
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Systems registry unavailable" },
      { status: 503 }
    );
  }
}
