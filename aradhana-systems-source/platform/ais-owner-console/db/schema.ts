import { sql } from "drizzle-orm";
import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const departments = sqliteTable("departments", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  name: text("name").notNull().unique(),
  focus: text("focus").notNull().default(""),
  sortOrder: integer("sort_order").notNull().default(0),
});

export const workItems = sqliteTable("work_items", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  kind: text("kind").notNull(), // "PROJECT" | "BIG TASK" | "SMALL TASK"
  title: text("title").notNull(),
  project: text("project").notNull().default("Company-wide"),
  department: text("department").notNull(),
  assignee: text("assignee").notNull().default("Unassigned"),
  eta: text("eta").notNull(),
  priority: text("priority").notNull().default("Normal"),
  status: text("status").notNull().default("Queued"),
  definitionOfDone: text("definition_of_done").notNull().default(""),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});

export const dailyReports = sqliteTable("daily_reports", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  itemId: integer("item_id").notNull(),
  reportDate: text("report_date").notNull(),
  summary: text("summary").notNull(),
  blockers: text("blockers").notNull().default(""),
  hoursSpent: integer("hours_spent").notNull().default(0),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});

export const parkedIdeas = sqliteTable("parked_ideas", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  title: text("title").notNull(),
  notes: text("notes").notNull().default(""),
  department: text("department").notNull().default("Management"),
  phase: text("phase").notNull().default("Phase 1"),
  targetDate: text("target_date").notNull().default(""),
  triggerEvent: text("trigger_event").notNull().default(""),
  status: text("status").notNull().default("Parked"),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});
