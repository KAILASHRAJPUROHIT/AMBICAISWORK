import { desc, eq } from "drizzle-orm";
import { getReadyDb } from "../../../../../db";
import { dailyReports } from "../../../../../db/schema";
import { requireSession } from "../../../_lib/session";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const { id } = await params;
  const itemId = Number(id);
  if (!Number.isInteger(itemId)) {
    return Response.json({ error: "Invalid item id" }, { status: 400 });
  }

  const db = await getReadyDb();
  const rows = await db
    .select()
    .from(dailyReports)
    .where(eq(dailyReports.itemId, itemId))
    .orderBy(desc(dailyReports.reportDate), desc(dailyReports.id));
  return Response.json({ reports: rows });
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const { id } = await params;
  const itemId = Number(id);
  if (!Number.isInteger(itemId)) {
    return Response.json({ error: "Invalid item id" }, { status: 400 });
  }

  const body = (await request.json().catch(() => null)) as {
    reportDate?: string;
    summary?: string;
    blockers?: string;
    hoursSpent?: number;
  } | null;

  const summary = body?.summary?.trim() || "";
  if (!summary) {
    return Response.json({ error: "summary is required" }, { status: 400 });
  }

  const db = await getReadyDb();
  const [report] = await db
    .insert(dailyReports)
    .values({
      itemId,
      reportDate: body?.reportDate?.trim() || todayIso(),
      summary,
      blockers: body?.blockers?.trim() || "",
      hoursSpent: Number.isFinite(body?.hoursSpent) ? Number(body?.hoursSpent) : 0,
    })
    .returning();

  return Response.json({ report }, { status: 201 });
}
