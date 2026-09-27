export type SystemHealthStatus = "Healthy" | "Active" | "Warning" | "Degraded" | "Disabled" | "Unregistered";

export type SystemTone = "green" | "cyan" | "amber" | "red" | "violet" | "grey";

export interface SystemItem {
  id: string;
  name: string;
  abbr: string;
  /**
   * "registry" = every field below came from GET /api/systems just now.
   * Absent = the registry hasn't answered yet (first paint / an outage);
   * the row then falls back to its static identity only (id/name/abbr) and
   * everything else renders as "—", never a stale or invented value.
   */
  source?: "registry";
  health: SystemHealthStatus;
  /** Real device health has no numeric score (would need host agents this
   *  system doesn't have). Absent, not defaulted -- render "—", never 0. */
  healthScore?: number;
  statusTone: SystemTone;
  errorReason: string;
  host: string;
  lastWorkBy: string;
  lastWorkTime: string;
  lastWorkDesc: string;
  cleanUptime: string;
  manual: boolean;
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

/** GET /api/systems response shape, from control-plane's systemProjection(). */
export interface RegistrySystem {
  id: string;
  name: string;
  host: { id: string; name: string; kind: string } | null;
  projectId: string | null;
  health: "healthy" | "warning" | "error" | "disabled" | "unregistered" | "active";
  errorReason: string | null;
  manual: boolean;
  manualSetBy: string | null;
  manualSetAt: string | null;
  lastWorkBy: string | null;
  lastWorkAt: string | null;
  lastWorkDescription: string | null;
  healthySince: string | null;
  lastFailureAt: string | null;
  cleanUptimeSec: number | null;
  cleanUptimeStr: string | null;
  lastCheckedAt: string | null;
  updatedAt: string;
}
