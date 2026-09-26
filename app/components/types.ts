export type SystemHealthStatus = "Healthy" | "Active" | "Warning" | "Degraded" | "Failure";

export type SystemTone = "green" | "cyan" | "amber" | "red" | "violet";

export interface SystemItem {
  id: string;
  name: string;
  abbr: string;
  health: SystemHealthStatus;
  healthScore: number;
  statusTone: SystemTone;
  errorReason: string;
  host: string;
  lastWorkBy: string;
  lastWorkTime: string;
  lastWorkDesc: string;
  cleanUptime: string;
  cpu: string;
  memory: string;
  events: string;
  dependencies: string[];
  recentActivity: Array<{
    time: string;
    note: string;
    tone: SystemTone;
  }>;
}

export interface PipelineTask {
  id: string;
  title: string;
  system: string;
  assignedTo: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "READY" | "IN PROGRESS" | "BLOCKED" | "COMPLETED";
  progress: number;
  due: string;
  nextAction: string;
}

export interface ActivityFeedItem {
  id: string | number;
  time: string;
  systemName: string;
  message: string;
  tag: string;
  tagColor: string;
}
