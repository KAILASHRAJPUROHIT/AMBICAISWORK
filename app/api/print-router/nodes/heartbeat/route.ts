import { createHmac, timingSafeEqual } from "node:crypto";
import { controlPlaneFetch } from "../../../_lib/control-plane";

type RegisteredNode = { id: string; name: string; token: string; expectedNodeId?: string };

function registry(): RegisteredNode[] {
  try {
    const value = JSON.parse(process.env.AIS_PRINT_NODES_JSON || "[]");
    return Array.isArray(value) ? value.filter((node): node is RegisteredNode =>
      node && typeof node.id === "string" && typeof node.name === "string" && typeof node.token === "string" && node.token.length >= 32,
    ) : [];
  } catch { return []; }
}

function validSignature(token: string, timestamp: string, body: string, supplied: string) {
  if (!/^[a-f0-9]{64}$/i.test(supplied)) return false;
  const expected = createHmac("sha256", token).update(`${timestamp}.${body}`, "utf8").digest();
  const received = Buffer.from(supplied, "hex");
  return received.length === expected.length && timingSafeEqual(received, expected);
}

// Public only to registered print nodes. Authentication is a timestamped HMAC;
// browser sessions cannot submit a node heartbeat. Cloudflare Access/mTLS will
// additionally restrict this route before production node enrollment.
export async function POST(request: Request) {
  const nodeId = request.headers.get("x-ais-node-id")?.trim() || "";
  const timestamp = request.headers.get("x-ais-timestamp")?.trim() || "";
  const signature = request.headers.get("x-ais-signature")?.trim() || "";
  const seconds = Number(timestamp);
  if (!nodeId || !Number.isInteger(seconds) || Math.abs(Date.now() - seconds * 1000) > 60_000) {
    return Response.json({ error: "Invalid or expired node heartbeat" }, { status: 401 });
  }

  const node = registry().find((entry) => entry.id === nodeId || entry.expectedNodeId === nodeId);
  if (!node) return Response.json({ error: "Unknown print node" }, { status: 401 });

  const body = await request.text();
  if (!validSignature(node.token, timestamp, body, signature)) return Response.json({ error: "Invalid node signature" }, { status: 401 });

  let payload: unknown;
  try { payload = JSON.parse(body); } catch { return Response.json({ error: "Malformed heartbeat JSON" }, { status: 400 }); }
  if (!payload || typeof payload !== "object" || (payload as { nodeId?: unknown }).nodeId !== nodeId) {
    return Response.json({ error: "Heartbeat identity mismatch" }, { status: 400 });
  }

  try {
    const upstream = await controlPlaneFetch("/api/print-router/nodes/heartbeat", {
      method: "POST", body: JSON.stringify(payload),
    });
    return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Control plane unavailable" }, { status: 503 });
  }
}
