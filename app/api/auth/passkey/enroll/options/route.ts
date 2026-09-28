import { requireSession } from "../../../../_lib/session";
import { registrationOptions } from "../../../../_lib/webauthn";

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;
  try {
    const result = await registrationOptions();
    return Response.json({ options: result.options }, { headers: { "set-cookie": result.cookie, "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Could not begin passkey enrollment." }, { status: 400 });
  }
}
