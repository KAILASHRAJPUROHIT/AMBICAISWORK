import { createRemoteJWKSet, jwtVerify } from "jose";

const ASSERTION_HEADER = "cf-access-jwt-assertion";
let cachedJwks: { url: string; keySet: ReturnType<typeof createRemoteJWKSet> } | null = null;

function enabled() {
  return process.env.AIS_REQUIRE_CF_ACCESS === "true";
}

function configuration() {
  const teamDomain = process.env.CF_ACCESS_TEAM_DOMAIN?.trim().replace(/^https:\/\//, "").replace(/\/$/, "") || "";
  const audience = process.env.CF_ACCESS_AUD?.trim() || "";
  const allowedEmails = (process.env.AIS_ALLOWED_EMAILS || "")
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean);
  if (!teamDomain || !audience || allowedEmails.length === 0) {
    throw new Error("Cloudflare Access is required but CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD, or AIS_ALLOWED_EMAILS is not configured.");
  }
  return { issuer: `https://${teamDomain}`, audience, allowedEmails, jwks: new URL(`https://${teamDomain}/cdn-cgi/access/certs`) };
}

export async function hasValidCloudflareAccess(request: Request) {
  if (!enabled()) return true;
  const assertion = request.headers.get(ASSERTION_HEADER);
  if (!assertion) return false;
  try {
    const config = configuration();
    if (!cachedJwks || cachedJwks.url !== config.jwks.href) {
      cachedJwks = { url: config.jwks.href, keySet: createRemoteJWKSet(config.jwks) };
    }
    const { payload } = await jwtVerify(assertion, cachedJwks.keySet, {
      issuer: config.issuer,
      audience: config.audience,
    });
    const email = typeof payload.email === "string" ? payload.email.trim().toLowerCase() : "";
    return Boolean(email && config.allowedEmails.includes(email));
  } catch {
    return false;
  }
}

export async function requireCloudflareAccess(request: Request): Promise<Response | null> {
  if (await hasValidCloudflareAccess(request)) return null;
  return Response.json({ error: "Cloudflare Access authorization required" }, { status: 403, headers: { "cache-control": "no-store" } });
}
