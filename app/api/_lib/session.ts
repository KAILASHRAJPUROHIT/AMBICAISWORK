export function sessionValue() {
  return process.env.AIS_SESSION_VALUE || "";
}

export function hasValidSession(request: Request) {
  const expected = sessionValue();
  if (!expected) return false;
  const cookie = request.headers.get("cookie") || "";
  return cookie.split(";").some((part) => part.trim() === `ais_session=${expected}`);
}

export function requireSession(request: Request): Response | null {
  if (hasValidSession(request)) return null;
  return Response.json({ error: "Not authenticated" }, { status: 401 });
}
