import { requireSession } from "../../../../_lib/session";
import { clearChallengeCookie, verifyRegistration } from "../../../../_lib/webauthn";

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  const body = await request.json().catch(() => null) as { response?: Parameters<typeof verifyRegistration>[1]; label?: string } | null;
  if (!body?.response) return Response.json({ error: "Missing passkey registration response." }, { status: 400 });
  try {
    const result = await verifyRegistration(request, body.response, body.label || "Windows Hello");
    return Response.json({ ok: true, ...result }, { headers: { "set-cookie": clearChallengeCookie("registration"), "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Could not verify passkey." }, { status: 400, headers: { "set-cookie": clearChallengeCookie("registration") } });
  }
}
