import { hasValidCloudflareAccess } from "./cloudflare-access";

export function sessionValue() {
  return process.env.AIS_SESSION_VALUE || "";
}

export async function hasValidSession(request: Request) {
  const expected = sessionValue();
  if (!expected) return false;
  const cookie = request.headers.get("cookie") || "";
  if (!cookie.split(";").some((part) => part.trim() === `ais_session=${expected}`)) return false;
  return hasValidCloudflareAccess(request);
}

export async function requireSession(request: Request): Promise<Response | null> {
  if (await hasValidSession(request)) return null;
  return Response.json({ error: "Not authenticated" }, { status: 401 });
}
