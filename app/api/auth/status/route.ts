import { hasValidSession } from "../../_lib/session";

export async function GET(request: Request) {
  const authenticated = hasValidSession(request);
  return authenticated ? Response.json({ authenticated: true }) : Response.json({ authenticated: false }, { status: 401 });
}
