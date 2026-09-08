import { env } from "cloudflare:workers";
import { sql } from "drizzle-orm";
import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

export function getDb() {
  if (!env.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or let your control plane inject the real binding values before using the database."
    );
  }

  return drizzle(env.DB, { schema });
}

const DEFAULT_DEPARTMENTS = [
  { name: "Technology", focus: "Android, backend, QA, infrastructure", sortOrder: 1 },
  { name: "Operations", focus: "Monitoring, vendors, SOP and compliance", sortOrder: 2 },
  { name: "Marketing", focus: "Campaigns, content and performance", sortOrder: 3 },
  { name: "Sales & CRM", focus: "Leads, follow-ups and customer journeys", sortOrder: 4 },
  { name: "Management", focus: "Approvals, architecture and priorities", sortOrder: 5 },
  { name: "Finance", focus: "Billing, vendor payments and budgets", sortOrder: 6 },
  { name: "Customer Support", focus: "Service tickets, warranty and repairs", sortOrder: 7 },
];

const DEFAULT_PARKED_IDEAS = [
  {
    title: "Trend Decoder",
    notes: "Early content signals, competitor analysis and opportunity scoring.",
    department: "Marketing",
    phase: "Phase 2",
    targetDate: "2026-10-01",
    triggerEvent: "After the campaign engine ships to production",
    status: "Researching",
  },
  {
    title: "Customer Memory Layer",
    notes: "Consent-aware preference history connected to CRM journeys.",
    department: "Sales & CRM",
    phase: "Phase 3",
    targetDate: "2026-12-01",
    triggerEvent: "Once the CRM module is live",
    status: "Parked",
  },
  {
    title: "Inventory Forecasting",
    notes: "Demand prediction informed by rates, campaigns and historical sales.",
    department: "Operations",
    phase: "Phase 4",
    targetDate: "2027-01-15",
    triggerEvent: "After 6 months of sales data has been collected",
    status: "Expected",
  },
];

// Module-scope cache so repeated requests on a warm isolate skip the
// CREATE TABLE / seed round-trips. Reset on failure so the next request retries.
let schemaReady: Promise<void> | null = null;

async function initializeSchema() {
  const db = getDb();

  await db.run(sql`CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    focus TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
  )`);

  await db.run(sql`CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT 'Company-wide',
    department TEXT NOT NULL,
    assignee TEXT NOT NULL DEFAULT 'Unassigned',
    eta TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Normal',
    status TEXT NOT NULL DEFAULT 'Queued',
    definition_of_done TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`);

  await db.run(sql`CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    report_date TEXT NOT NULL,
    summary TEXT NOT NULL,
    blockers TEXT NOT NULL DEFAULT '',
    hours_spent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`);

  await db.run(sql`CREATE TABLE IF NOT EXISTS parked_ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT 'Management',
    phase TEXT NOT NULL DEFAULT 'Phase 1',
    target_date TEXT NOT NULL DEFAULT '',
    trigger_event TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Parked',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`);

  const existingDepartments = await db.select().from(schema.departments).limit(1);
  if (existingDepartments.length === 0) {
    await db.insert(schema.departments).values(DEFAULT_DEPARTMENTS);
  }

  const existingIdeas = await db.select().from(schema.parkedIdeas).limit(1);
  if (existingIdeas.length === 0) {
    await db.insert(schema.parkedIdeas).values(DEFAULT_PARKED_IDEAS);
  }
}

export async function ensureSchema() {
  if (!schemaReady) {
    schemaReady = initializeSchema().catch((error) => {
      schemaReady = null;
      throw error;
    });
  }
  return schemaReady;
}

/** getDb() plus a guarantee that tables exist and are seeded. */
export async function getReadyDb() {
  await ensureSchema();
  return getDb();
}
