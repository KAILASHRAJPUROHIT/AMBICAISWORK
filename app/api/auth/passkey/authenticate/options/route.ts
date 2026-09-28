import { authenticationOptions, clearChallengeCookie } from "../../../../_lib/webauthn";
import { requireCloudflareAccess } from "../../../../_lib/cloudflare-access";

export async function POST(request: Request) {
  const accessDenied = await requireCloudflareAccess(request);
  if (accessDenied) return accessDenied;
  try {
    const result = await authenticationOptions(request);
    return Response.json({ options: result.options }, { headers: { "set-cookie": result.cookie, "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Could not begin passkey verification." }, { status: 401, headers: { "set-cookie": clearChallengeCookie("assertion") } });
  }
}
