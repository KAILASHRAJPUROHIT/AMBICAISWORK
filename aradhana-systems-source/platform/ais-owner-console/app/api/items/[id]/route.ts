import { eq } from "drizzle-orm";
import { getReadyDb } from "../../../../db";
import { dailyReports, workItems } from "../../../../db/schema";
import { requireSession } from "../../_lib/session";

const VALID_STATUSES = new Set(["Queued", "In Progress", "Blocked", "Done"]);

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const { id } = await params;
  const itemId = Number(id);
  if (!Number.isInteger(itemId)) {
    return Response.json({ error: "Invalid item id" }, { status: 400 });
  }

  const body = (await request.json().catch(() => null)) as {
    status?: string;
    priority?: string;
    eta?: string;
  } | null;

  const updates: Partial<typeof workItems.$inferInsert> = {};
  if (body?.status !== undefined) {
    if (!VALID_STATUSES.has(body.status)) {
      return Response.json({ error: "status must be Queued, In Progress, Blocked or Done" }, { status: 400 });
    }
    updates.status = body.status;
  }
  if (body?.priority !== undefined) updates.priority = body.priority;
  if (body?.eta !== undefined) {
    if (!body.eta.trim()) {
      return Response.json({ error: "ETA cannot be cleared" }, { status: 400 });
    }
    updates.eta = body.eta.trim();
  }

  if (Object.keys(updates).length === 0) {
    return Response.json({ error: "No updatable fields provided" }, { status: 400 });
  }

  const db = await getReadyDb();
  const [item] = await db.update(workItems).set(updates).where(eq(workItems.id, itemId)).returning();
  if (!item) {
    return Response.json({ error: "Item not found" }, { status: 404 });
  }
  return Response.json({ item });
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const { id } = await params;
  const itemId = Number(id);
  if (!Number.isInteger(itemId)) {
    return Response.json({ error: "Invalid item id" }, { status: 400 });
  }

  const db = await getReadyDb();
  await db.delete(dailyReports).where(eq(dailyReports.itemId, itemId));
  const [item] = await db.delete(workItems).where(eq(workItems.id, itemId)).returning();
  if (!item) {
    return Response.json({ error: "Item not found" }, { status: 404 });
  }
  return Response.json({ ok: true });
}
