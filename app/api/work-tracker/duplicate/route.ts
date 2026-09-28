import { promises as fs } from "node:fs";
import path from "node:path";
import { requireSession } from "../../_lib/session";

const TASKS_PATH = path.resolve("c:/AradhanaSystems/projects/aradhana-work-tracker/data/tasks.json");

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const body = (await request.json().catch(() => null)) as {
    source_id?: string;
    target_days?: string[];
  } | null;

  if (!body || !body.source_id || !body.target_days || !body.target_days.length) {
    return Response.json({ error: "source_id and target_days required" }, { status: 400 });
  }

  let tasks = [];
  try {
    const raw = await fs.readFile(TASKS_PATH, "utf-8");
    tasks = JSON.parse(raw);
  } catch {
    return Response.json({ error: "Failed to read tasks" }, { status: 500 });
  }

  const source = tasks.find((t: any) => t.id === body.source_id);
  if (!source) {
    return Response.json({ error: "Source task not found" }, { status: 404 });
  }

  const created = [];
  for (const day of body.target_days) {
    if (day === source.day) continue;
    const duplicated = {
      ...source,
      id: `t-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      day,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    tasks.unshift(duplicated);
    created.push(duplicated);
  }

  const tmp = TASKS_PATH + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(tasks, null, 2), "utf-8");
  await fs.rename(tmp, TASKS_PATH);

  return Response.json({ created, count: created.length });
}
