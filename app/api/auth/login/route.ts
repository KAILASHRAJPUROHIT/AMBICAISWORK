import { sessionValue } from "../../_lib/session";
import { createLoginGrant, credentialCount, webauthnEnabled } from "../../_lib/webauthn";

async function sha256(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function POST(request: Request) {
  const expectedCredentialHash = process.env.AIS_CREDENTIAL_HASH || "";
  const session = sessionValue();
  if (!expectedCredentialHash || !session) {
    return Response.json({ error: "Login is not configured" }, { status: 503 });
  }
  const body = (await request.json().catch(() => null)) as { username?: string; password?: string } | null;
  const candidate = await sha256(`${body?.username?.trim().toLowerCase() || ""}:${body?.password || ""}`);
  if (candidate !== expectedCredentialHash) {
    return Response.json({ error: "Invalid credentials" }, { status: 401 });
  }
  if (webauthnEnabled()) {
    try {
      if (await credentialCount() === 0) {
        return Response.json({ error: "WebAuthn is enabled but no AIS passkey is enrolled. Disable AIS_WEBAUTHN_ENABLED until initial enrollment is complete." }, { status: 503 });
      }
      return Response.json(
        { ok: true, requiresPasskey: true },
        { headers: { "set-cookie": await createLoginGrant(), "cache-control": "no-store" } },
      );
    } catch (error) {
      return Response.json({ error: error instanceof Error ? error.message : "Could not start passkey verification." }, { status: 503 });
    }
  }
  return Response.json(
    { ok: true },
    {
      headers: {
        "set-cookie": `ais_session=${session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800`,
      },
    },
  );
}
