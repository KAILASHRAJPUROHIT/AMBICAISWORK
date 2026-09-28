import { promises as fs } from "node:fs";
import path from "node:path";
import { requireSession } from "../_lib/session";

const TASKS_PATH = path.resolve("C:/AradhanaSystems/projects/aradhana-work-tracker/data/tasks.json");
const LOCAL_API_URL = "http://127.0.0.1:8085/api/tasks";

interface WorkTask {
  id: string;
  staff_id: string;
  staff_name: string;
  day: string;
  category: string;
  title: string;
  description: string;
  time_spent: string;
  time_hours: number;
  frequency: string;
  current_tool: string;
  pain_points: string;
  ais_target: string;
  priority: string;
  created_at: string;
  updated_at: string;
}

async function readTasks(): Promise<WorkTask[]> {
  try {
    const res = await fetch(LOCAL_API_URL, { cache: "no-store" });
    if (res.ok) {
      return (await res.json()) as WorkTask[];
    }
  } catch {}

  try {
    const raw = await fs.readFile(TASKS_PATH, "utf-8");
    return JSON.parse(raw) as WorkTask[];
  } catch (err) {
    console.error("Error reading tasks:", err);
    return [];
  }
}

async function writeTasks(tasks: WorkTask[]): Promise<void> {
  try {
    const dir = path.dirname(TASKS_PATH);
    await fs.mkdir(dir, { recursive: true });
    const tmp = TASKS_PATH + ".tmp";
    await fs.writeFile(tmp, JSON.stringify(tasks, null, 2), "utf-8");
    await fs.rename(tmp, TASKS_PATH);
  } catch (err) {
    console.error("Error writing tasks file:", err);
  }
}

function computeHours(timeSpent: string): number {
  if (timeSpent.includes("15")) return 0.25;
  if (timeSpent.includes("30")) return 0.5;
  if (timeSpent.includes("45")) return 0.75;
  if (timeSpent.includes("1 Hour") || timeSpent.includes("1 घंटा")) return 1.0;
  if (timeSpent.includes("2 Hour") || timeSpent.includes("2 घंटे")) return 2.0;
  if (timeSpent.includes("Half") || timeSpent.includes("आधा")) return 3.5;
  if (timeSpent.includes("Full") || timeSpent.includes("पूरा")) return 7.0;
  return 0.5;
}

export async function GET(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const url = new URL(request.url);
  const staffId = url.searchParams.get("staff_id");
  const day = url.searchParams.get("day");

  let tasks = await readTasks();

  if (staffId && staffId !== "all") {
    tasks = tasks.filter((t) => t.staff_id === staffId);
  }
  if (day && day !== "all") {
    tasks = tasks.filter((t) => t.day === day);
  }

  return Response.json({ tasks });
}

export async function POST(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const body = (await request.json().catch(() => null)) as Partial<WorkTask> | null;
  if (!body || !body.title || !body.staff_id || !body.day) {
    return Response.json(
      { error: "Staff, Day and Title are required / कर्मचारी, दिन और शीर्षक आवश्यक हैं" },
      { status: 400 }
    );
  }

  // Forward to local server if available
  try {
    const res = await fetch(LOCAL_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const task = await res.json();
      return Response.json({ task }, { status: 201 });
    }
  } catch {}

  const tasks = await readTasks();
  const timeSpent = body.time_spent || "1 Hour / 1 घंटा";

  const newTask: WorkTask = {
    id: `t-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    staff_id: body.staff_id,
    staff_name: body.staff_name || body.staff_id,
    day: body.day,
    category: body.category || "other",
    title: body.title.trim(),
    description: (body.description || "").trim(),
    time_spent: timeSpent,
    time_hours: computeHours(timeSpent),
    frequency: body.frequency || "Daily / प्रतिदिन",
    current_tool: body.current_tool || "Register / नोटबुक",
    pain_points: (body.pain_points || "").trim(),
    ais_target: body.ais_target || "under_review",
    priority: body.priority || "Medium / मध्यम",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  tasks.unshift(newTask);
  await writeTasks(tasks);

  return Response.json({ task: newTask }, { status: 201 });
}

export async function PUT(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const body = ((await request.json().catch(() => null)) as (Partial<WorkTask> & { id: string }) | null);
  if (!body || !body.id) {
    return Response.json({ error: "Task ID is required" }, { status: 400 });
  }

  // Forward to local server if available
  try {
    const res = await fetch(`${LOCAL_API_URL}/${body.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const task = await res.json();
      return Response.json({ task });
    }
  } catch {}

  const tasks = await readTasks();
  const idx = tasks.findIndex((t) => t.id === body.id);
  if (idx === -1) {
    return Response.json({ error: "Task not found" }, { status: 404 });
  }

  const current = tasks[idx];
  const timeSpent = body.time_spent !== undefined ? body.time_spent : current.time_spent;

  tasks[idx] = {
    ...current,
    staff_id: body.staff_id !== undefined ? body.staff_id : current.staff_id,
    staff_name: body.staff_name !== undefined ? body.staff_name : current.staff_name,
    day: body.day !== undefined ? body.day : current.day,
    category: body.category !== undefined ? body.category : current.category,
    title: body.title !== undefined ? body.title.trim() : current.title,
    description: body.description !== undefined ? body.description.trim() : current.description,
    time_spent: timeSpent,
    time_hours: computeHours(timeSpent),
    frequency: body.frequency !== undefined ? body.frequency : current.frequency,
    current_tool: body.current_tool !== undefined ? body.current_tool : current.current_tool,
    pain_points: body.pain_points !== undefined ? body.pain_points.trim() : current.pain_points,
    ais_target: body.ais_target !== undefined ? body.ais_target : current.ais_target,
    priority: body.priority !== undefined ? body.priority : current.priority,
    updated_at: new Date().toISOString(),
  };

  await writeTasks(tasks);
  return Response.json({ task: tasks[idx] });
}

export async function DELETE(request: Request) {
  const unauthorized = requireSession(request);
  if (unauthorized) return unauthorized;

  const url = new URL(request.url);
  const id = url.searchParams.get("id");
  if (!id) {
    return Response.json({ error: "Task ID is required" }, { status: 400 });
  }

  // Forward to local server if available
  try {
    const res = await fetch(`${LOCAL_API_URL}/${id}`, {
      method: "DELETE",
    });
    if (res.ok) {
      return Response.json({ success: true });
    }
  } catch {}

  const tasks = await readTasks();
  const filtered = tasks.filter((t) => t.id !== id);
  if (filtered.length === tasks.length) {
    return Response.json({ error: "Task not found" }, { status: 404 });
  }

  await writeTasks(filtered);
  return Response.json({ success: true });
}
