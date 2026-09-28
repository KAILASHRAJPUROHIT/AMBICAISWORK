import { clearChallengeCookie, verifyAuthentication } from "../../../../_lib/webauthn";
import { sessionValue } from "../../../../_lib/session";
import { requireCloudflareAccess } from "../../../../_lib/cloudflare-access";

export async function POST(request: Request) {
  const accessDenied = await requireCloudflareAccess(request);
  if (accessDenied) return accessDenied;
  const body = await request.json().catch(() => null) as { response?: Parameters<typeof verifyAuthentication>[1] } | null;
  if (!body?.response) return Response.json({ error: "Missing passkey assertion response." }, { status: 400 });
  try {
    await verifyAuthentication(request, body.response);
    const session = sessionValue();
    if (!session) throw new Error("AIS session is not configured.");
    return Response.json(
      { ok: true },
      { headers: { "set-cookie": `ais_session=${session}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=28800`, "cache-control": "no-store" } },
    );
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Could not verify passkey." }, { status: 401, headers: { "set-cookie": clearChallengeCookie("assertion") } });
  }
}
