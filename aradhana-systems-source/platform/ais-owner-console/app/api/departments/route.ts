import { asc } from "drizzle-orm";
import { getReadyDb } from "../../../db";
import { departments } from "../../../db/schema";
import { requireSession } from "../_lib/session";

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const db = await getReadyDb();
  const rows = await db.select().from(departments).orderBy(asc(departments.sortOrder));
  return Response.json({ departments: rows });
}
