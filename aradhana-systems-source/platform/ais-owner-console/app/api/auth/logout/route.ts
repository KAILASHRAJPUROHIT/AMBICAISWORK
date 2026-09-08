export async function POST() {
  return Response.json(
    { ok: true },
    { headers: { "set-cookie": "ais_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" } },
  );
}
