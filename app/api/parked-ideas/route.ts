import { desc } from "drizzle-orm";
import { getReadyDb } from "../../../db";
import { parkedIdeas } from "../../../db/schema";
import { requireSession } from "../_lib/session";

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const db = await getReadyDb();
  const rows = await db.select().from(parkedIdeas).orderBy(desc(parkedIdeas.createdAt), desc(parkedIdeas.id));
  return Response.json({ ideas: rows });
}

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const body = (await request.json().catch(() => null)) as {
    title?: string;
    notes?: string;
    department?: string;
    phase?: string;
    targetDate?: string;
    trigger?: string;
    status?: string;
  } | null;

  const title = body?.title?.trim() || "";
  const phase = body?.phase?.trim() || "";
  const targetDate = body?.targetDate?.trim() || "";

  if (!title) {
    return Response.json({ error: "title is required" }, { status: 400 });
  }
  if (!phase) {
    return Response.json({ error: "expected implementation phase is required" }, { status: 400 });
  }
  if (!targetDate) {
    return Response.json({ error: "expected implementation date is required" }, { status: 400 });
  }

  const db = await getReadyDb();
  const [idea] = await db
    .insert(parkedIdeas)
    .values({
      title,
      notes: body?.notes?.trim() || "",
      department: body?.department?.trim() || "Management",
      phase,
      targetDate,
      triggerEvent: body?.trigger?.trim() || "",
      status: body?.status?.trim() || "Parked",
    })
    .returning();

  return Response.json({ idea }, { status: 201 });
}
