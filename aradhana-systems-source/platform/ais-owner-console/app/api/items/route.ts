import { desc } from "drizzle-orm";
import { getReadyDb } from "../../../db";
import { workItems } from "../../../db/schema";
import { requireSession } from "../_lib/session";
import { controlPlaneFetch } from "../_lib/control-plane";

const VALID_KINDS = new Set(["PROJECT", "BIG TASK", "SMALL TASK"]);

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const db = await getReadyDb();
  const rows = await db.select().from(workItems).orderBy(desc(workItems.createdAt), desc(workItems.id));
  return Response.json({ items: rows });
}

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const body = (await request.json().catch(() => null)) as {
    kind?: string;
    title?: string;
    project?: string;
    department?: string;
    assignee?: string;
    eta?: string;
    priority?: string;
    definitionOfDone?: string;
  } | null;

  const kind = body?.kind || "";
  const title = body?.title?.trim() || "";
  const department = body?.department?.trim() || "";
  const eta = body?.eta?.trim() || "";

  if (!VALID_KINDS.has(kind)) {
    return Response.json({ error: "kind must be PROJECT, BIG TASK or SMALL TASK" }, { status: 400 });
  }
  if (!title) {
    return Response.json({ error: "title is required" }, { status: 400 });
  }
  if (!department) {
    return Response.json({ error: "department is required" }, { status: 400 });
  }
  if (!eta) {
    return Response.json({ error: "ETA is required" }, { status: 400 });
  }

  const db = await getReadyDb();
  const [item] = await db
    .insert(workItems)
    .values({
      kind,
      title,
      project: body?.project?.trim() || "Company-wide",
      department,
      assignee: body?.assignee?.trim() || "Unassigned",
      eta,
      priority: body?.priority?.trim() || "Normal",
      definitionOfDone: body?.definitionOfDone?.trim() || "",
    })
    .returning();

  // Mirror into the always-on local control plane. D1 remains the CRM source;
  // a failed mirror never discards the user's saved task.
  try {
    await controlPlaneFetch("/api/work-items", {
      method: "POST",
      body: JSON.stringify({
        kind: item.kind,
        title: item.title,
        description: item.definitionOfDone,
        projectId: null,
        projectName: item.project,
        department: item.department,
        priority: item.priority,
        eta: item.eta,
        acceptanceCriteria: item.definitionOfDone,
        source: { system: "dashboard-d1", id: item.id, project: item.project, assignee: item.assignee },
      }),
    });
  } catch {
    // The dashboard exposes control-plane availability separately and can retry
    // from the event ledger after the local service returns.
  }

  return Response.json({ item }, { status: 201 });
}
