"use client";

import Image from "next/image";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type Control = {
  id: string;
  name: string;
  detail: string;
  enabled: boolean;
  tone: "purple" | "gold" | "green";
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  time: string;
};

type ItemKind = "PROJECT" | "BIG TASK" | "SMALL TASK";

type Department = {
  id: number;
  name: string;
  focus: string;
  sortOrder: number;
};

type WorkItem = {
  id: number;
  kind: ItemKind;
  title: string;
  project: string;
  department: string;
  assignee: string;
  eta: string;
  priority: string;
  status: "Queued" | "In Progress" | "Blocked" | "Done";
  definitionOfDone: string;
  createdAt: string;
};

type DailyReport = {
  id: number;
  itemId: number;
  reportDate: string;
  summary: string;
  blockers: string;
  hoursSpent: number;
  createdAt: string;
};

type ParkedIdea = {
  id: number;
  title: string;
  notes: string;
  department: string;
  phase: string;
  targetDate: string;
  triggerEvent: string;
  status: string;
  createdAt: string;
};

type LiveProject = {
  id: string;
  name: string;
  department: string;
  phase: string;
  health: "healthy" | "warning" | "error" | "unknown" | "unconfigured";
  remoteUrl?: string | null;
  localPath?: string | null;
  description?: string;
  expectedCompletion?: string | null;
  completedAt?: string | null;
  progress?: number | null;
  taskStats?: { total: number; completed: number; blocked: number };
  git: {
    status: string;
    detail: string;
    branch?: string;
    head?: string;
    remoteHead?: string | null;
    lastCommit?: string;
    observedAt?: string | null;
  };
  endpoint: {
    status: string;
    detail: string;
    checks?: Array<{ name: string; ok: boolean; statusCode?: number | null; latencyMs?: number }>;
    observedAt?: string | null;
  };
  research?: {
    status: string;
    detail: string;
    source?: string;
    insights?: Array<{ name: string; current: string | null; wanted: string | null; latest: string | null; homepage?: string }>;
    observedAt?: string | null;
  };
};

type LiveModel = {
  model_key: string;
  provider: string;
  role: string;
  status: string;
  detail: string;
  checked_at: string;
  payload?: { rank?: number; account?: number; quotaRemaining?: number | null };
};

type ControlWorkItem = {
  id: string;
  kind: string;
  title: string;
  description: string;
  project_id?: string | null;
  department: string;
  priority: string;
  status: string;
  eta_at?: string | null;
  acceptance_criteria: string;
  assigned_to: string;
  risk_class: string;
  created_at: string;
};

type Connector = { id: string; name: string; category: string; status: string; detail: string; checked_at: string };
type Campaign = { id: string; title: string; platform: string; status: string; owner: string; content_summary: string; planned_at?: string | null; metrics?: Record<string, number> };

type ControlSnapshot = {
  service: { online: boolean; uptimeSeconds: number; pollSeconds: number; checksRunning: boolean };
  settings: Record<string, boolean | number>;
  projects: LiveProject[];
  models: LiveModel[];
  workItems: ControlWorkItem[];
  approvals: ControlWorkItem[];
  completedProducts: LiveProject[];
  connectors: Connector[];
  campaigns: Campaign[];
  report?: { report_date: string; revision: number; content: { executiveSummary?: Record<string, number>; work?: Record<string, number>; evidenceCutoff?: string } } | null;
  events: Array<{ id: number; event_type: string; severity: string; message: string; created_at: string }>;
  generatedAt: string;
};

const initialControls: Control[] = [
  {
    id: "coding",
    name: "Coding agents",
    detail: "Assignment, implementation, tests and reviews",
    enabled: true,
    tone: "purple",
  },
  {
    id: "development",
    name: "Development loop",
    detail: "Backlog processing and approved improvements",
    enabled: true,
    tone: "gold",
  },
  {
    id: "production",
    name: "Production monitoring",
    detail: "Endpoints, builds, jobs and subdomains",
    enabled: true,
    tone: "green",
  },
  {
    id: "git",
    name: "Git intelligence",
    detail: "Local/remote drift, branch health and progress",
    enabled: true,
    tone: "purple",
  },
  {
    id: "research",
    name: "Improvement radar",
    detail: "Project-specific reliability and feature research",
    enabled: true,
    tone: "gold",
  },
  {
    id: "marketing",
    name: "Campaign pipeline",
    detail: "Instagram, Facebook and content workflow",
    enabled: true,
    tone: "green",
  },
];

const nowTime = () =>
  new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date());

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`switch ${checked ? "is-on" : ""}`}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
    >
      <span />
    </button>
  );
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [controls, setControls] = useState(initialControls);
  const [supervisorOnline, setSupervisorOnline] = useState(false);
  const [supervisorModel, setSupervisorModel] = useState("Qwen local supervisor");
  const [healthDetail, setHealthDetail] = useState("Checking local runtime…");
  const [scannerStatus, setScannerStatus] = useState("Checking project index…");
  const [controlSnapshot, setControlSnapshot] = useState<ControlSnapshot | null>(null);
  const [controlOnline, setControlOnline] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Command centre ready. I can summarise project health, inspect failures, prepare work and identify decisions that require CEO approval.",
      time: nowTime(),
    },
  ]);
  const [modalType, setModalType] = useState<ItemKind | null>(null);
  const [modalError, setModalError] = useState("");
  const [modalBusy, setModalBusy] = useState(false);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [parkedIdeas, setParkedIdeas] = useState<ParkedIdea[]>([]);
  const [ideaModalOpen, setIdeaModalOpen] = useState(false);
  const [ideaError, setIdeaError] = useState("");
  const [ideaBusy, setIdeaBusy] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [itemReports, setItemReports] = useState<DailyReport[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [campaignModalOpen, setCampaignModalOpen] = useState(false);
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [campaignError, setCampaignError] = useState("");
  const [researchBusy, setResearchBusy] = useState(false);
  const [view, setView] = useState<"home" | "tools" | "work" | "admin">("home");
  const chatEnd = useRef<HTMLDivElement>(null);

  const masterOn = controls.every((control) => control.enabled);

  useEffect(() => {
    fetch("/api/auth/status")
      .then((response) => setAuthenticated(response.ok))
      .catch(() => setAuthenticated(false));
  }, []);

  const loadWorkspaceData = async () => {
    try {
      const [deptResponse, itemsResponse, ideasResponse] = await Promise.all([
        fetch("/api/departments"),
        fetch("/api/items"),
        fetch("/api/parked-ideas"),
      ]);
      const deptData = (await deptResponse.json()) as { departments?: Department[] };
      const itemsData = (await itemsResponse.json()) as { items?: WorkItem[] };
      const ideasData = (await ideasResponse.json()) as { ideas?: ParkedIdea[] };
      setDepartments(deptData.departments || []);
      setItems(itemsData.items || []);
      setParkedIdeas(ideasData.ideas || []);
      setSelectedItemId((current) => current ?? itemsData.items?.[0]?.id ?? null);
    } catch {
      setNotice("Unable to load workspace data.");
      window.setTimeout(() => setNotice(""), 3200);
    }
  };

  useEffect(() => {
    if (authenticated) loadWorkspaceData();
  }, [authenticated]);

  const loadControlSnapshot = async () => {
    try {
      const response = await fetch("/api/control/snapshot", { cache: "no-store" });
      const data = (await response.json()) as ControlSnapshot & { error?: string };
      if (!response.ok) throw new Error(data.error || "Control plane unavailable");
      setControlSnapshot(data);
      setControlOnline(Boolean(data.service?.online));
      if (data.settings) {
        setControls((current) => current.map((item) => ({ ...item, enabled: data.settings[item.id] !== false })));
      }
    } catch {
      setControlOnline(false);
    }
  };

  useEffect(() => {
    if (!authenticated) return;
    loadControlSnapshot();
    const timer = window.setInterval(loadControlSnapshot, 30_000);
    return () => window.clearInterval(timer);
  }, [authenticated]);

  useEffect(() => {
    if (!authenticated || selectedItemId === null) {
      setItemReports([]);
      return;
    }
    let active = true;
    setReportsLoading(true);
    fetch(`/api/items/${selectedItemId}/reports`)
      .then((response) => response.json())
      .then((data: { reports?: DailyReport[] }) => {
        if (active) setItemReports(data.reports || []);
      })
      .catch(() => {
        if (active) setItemReports([]);
      })
      .finally(() => {
        if (active) setReportsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authenticated, selectedItemId]);

  useEffect(() => {
    if (!authenticated) return;
    let active = true;
    const check = async () => {
      try {
        const response = await fetch("/api/supervisor/health", { cache: "no-store" });
        const data = (await response.json()) as {
          online?: boolean;
          model?: string;
          detail?: string;
          scanner?: {
            online?: boolean;
            scanning?: boolean;
            scanProgress?: { visited: number; repos: number; projects: number; elapsedSec: number } | null;
            totalRepos?: number;
            totalProjects?: number;
            lastScanAt?: string | null;
            watching?: number;
            recentChangeCount?: number;
          };
        };
        if (!active) return;
        setSupervisorOnline(Boolean(data.online));
        setSupervisorModel(data.model || "Qwen local supervisor");
        setHealthDetail(data.detail || (data.online ? "Connected" : "Unavailable"));
        if (data.scanner?.online) {
          const progress = data.scanner.scanProgress;
          const base = data.scanner.scanning
            ? progress
              ? `Project index: scanning… ${progress.visited} dirs, ${progress.repos} repos, ${progress.projects} projects found (${progress.elapsedSec}s)`
              : "Project index: scanning…"
            : `Project index: ${data.scanner.totalRepos || 0} repos, ${data.scanner.totalProjects || 0} other projects`;
          setScannerStatus(`${base} · watching ${data.scanner.watching || 0} live, ${data.scanner.recentChangeCount || 0} recent changes`);
        } else {
          setScannerStatus("Project index offline · run npm run scan");
        }
      } catch {
        if (!active) return;
        setSupervisorOnline(false);
        setHealthDetail("Local supervisor endpoint unavailable");
      }
    };
    check();
    const timer = window.setInterval(check, 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [authenticated]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const runningCount = useMemo(() => controls.filter((control) => control.enabled).length, [controls]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      if (!response.ok) throw new Error("Invalid login ID or password.");
      setAuthenticated(true);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Unable to sign in.");
    } finally {
      setLoginBusy(false);
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    setAuthenticated(false);
  }

  async function setAll(enabled: boolean) {
    setControls((current) => current.map((control) => ({ ...control, enabled })));
    try {
      const response = await fetch("/api/control/controls/master", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error("Control plane rejected the change");
      await loadControlSnapshot();
      setNotice(enabled ? "All approved operations resumed." : "All automated work paused by Admin.");
    } catch {
      setNotice("Control plane unavailable. No operational state was changed.");
      await loadControlSnapshot();
    }
    window.setTimeout(() => setNotice(""), 3200);
  }

  async function flipControl(id: string) {
    const target = controls.find((control) => control.id === id);
    if (!target) return;
    setControls((current) =>
      current.map((control) =>
        control.id === id ? { ...control, enabled: !control.enabled } : control,
      ),
    );
    try {
      const response = await fetch(`/api/control/controls/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled: !target.enabled }),
      });
      if (!response.ok) throw new Error("Control change failed");
      await loadControlSnapshot();
    } catch {
      setNotice("Control plane unavailable. Switch restored to recorded state.");
      await loadControlSnapshot();
      window.setTimeout(() => setNotice(""), 3200);
    }
  }

  async function runChecks() {
    setNotice("Running Git, production and model checks…");
    try {
      const response = await fetch("/api/control/checks", { method: "POST" });
      if (!response.ok) throw new Error("Checks failed");
      await loadControlSnapshot();
      setNotice("Fresh evidence collected across the registered portfolio.");
    } catch {
      setNotice("Unable to run checks. Confirm the AIS control plane is online.");
    }
    window.setTimeout(() => setNotice(""), 3200);
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || chatBusy) return;
    const userMessage: ChatMessage = { role: "user", content: text, time: nowTime() };
    const nextHistory = [...messages, userMessage];
    setMessages(nextHistory);
    setChatInput("");
    setChatBusy(true);
    try {
      const response = await fetch("/api/supervisor/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: nextHistory.slice(-10).map(({ role, content }) => ({ role, content })),
        }),
      });
      const data = (await response.json()) as { reply?: string; error?: string; model?: string };
      if (!response.ok) throw new Error(data.error || "Supervisor did not respond.");
      if (data.model) setSupervisorModel(data.model);
      setSupervisorOnline(true);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: data.reply || "No response returned.", time: nowTime() },
      ]);
    } catch (error) {
      setSupervisorOnline(false);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content:
            error instanceof Error
              ? `${error.message} Start the local Qwen runtime, then retry.`
              : "Local supervisor unavailable.",
          time: nowTime(),
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  async function createItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!modalType) return;
    const form = new FormData(event.currentTarget);
    const eta = String(form.get("eta") || "").trim();
    if (!eta) {
      setModalError("ETA is required.");
      return;
    }
    setModalBusy(true);
    setModalError("");
    try {
      if (modalType === "PROJECT") {
        const endpoints = String(form.get("endpoints") || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line, index) => {
          const [label, url] = line.includes("|") ? line.split("|", 2).map((part) => part.trim()) : [`Endpoint ${index + 1}`, line];
          return { name: label, url, expected: [200] };
        });
        const response = await fetch("/api/control/projects", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: form.get("title"),
            description: form.get("done"),
            localPath: form.get("localPath"),
            remoteUrl: form.get("remoteUrl"),
            department: form.get("department"),
            phase: form.get("phase"),
            expectedCompletion: eta,
            endpoints,
          }),
        });
        const data = (await response.json()) as { project?: LiveProject; error?: string };
        if (!response.ok || !data.project) throw new Error(data.error || "Unable to register project.");
        await loadControlSnapshot();
        setModalType(null);
        setNotice("Project registered with real local path and monitoring configuration.");
        window.setTimeout(() => setNotice(""), 3200);
        return;
      }
      const response = await fetch("/api/items", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kind: modalType,
          title: form.get("title"),
          project: form.get("project"),
          department: form.get("department"),
          assignee: form.get("assignee"),
          eta,
          priority: form.get("priority"),
          definitionOfDone: form.get("done"),
        }),
      });
      const data = (await response.json()) as { item?: WorkItem; error?: string };
      if (!response.ok || !data.item) throw new Error(data.error || "Unable to create item.");
      setItems((current) => [data.item as WorkItem, ...current]);
      setSelectedItemId(data.item.id);
      setModalType(null);
      setNotice(`${modalType} created and queued for supervisor triage.`);
      window.setTimeout(() => setNotice(""), 3200);
    } catch (error) {
      setModalError(error instanceof Error ? error.message : "Unable to create item.");
    } finally {
      setModalBusy(false);
    }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setCampaignBusy(true);
    setCampaignError("");
    try {
      const response = await fetch("/api/control/campaigns", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: form.get("title"), platform: form.get("platform"), owner: form.get("owner"), contentSummary: form.get("summary"), plannedAt: form.get("plannedAt") }),
      });
      const data = (await response.json()) as { campaign?: Campaign; error?: string };
      if (!response.ok || !data.campaign) throw new Error(data.error || "Unable to create campaign.");
      await loadControlSnapshot();
      setCampaignModalOpen(false);
      setNotice("Campaign added to the real planning pipeline. Publishing remains blocked until the platform connector is authenticated.");
      window.setTimeout(() => setNotice(""), 4200);
    } catch (error) {
      setCampaignError(error instanceof Error ? error.message : "Unable to create campaign.");
    } finally {
      setCampaignBusy(false);
    }
  }

  async function runResearch() {
    setResearchBusy(true);
    setNotice("Checking one registered project against its live dependency source…");
    try {
      const response = await fetch("/api/control/research", { method: "POST" });
      const data = (await response.json()) as { result?: { detail?: string }; error?: string; skipped?: boolean; reason?: string };
      if (!response.ok) throw new Error(data.error || "Improvement check failed");
      await loadControlSnapshot();
      setNotice(data.skipped ? `Improvement check skipped: ${data.reason}.` : data.result?.detail || "Improvement evidence refreshed.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Improvement radar unavailable.");
    } finally {
      setResearchBusy(false);
      window.setTimeout(() => setNotice(""), 4200);
    }
  }

  async function createIdea(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIdeaBusy(true);
    setIdeaError("");
    try {
      const response = await fetch("/api/parked-ideas", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: form.get("title"),
          notes: form.get("notes"),
          department: form.get("department"),
          phase: form.get("phase"),
          targetDate: form.get("targetDate"),
          trigger: form.get("trigger"),
        }),
      });
      const data = (await response.json()) as { idea?: ParkedIdea; error?: string };
      if (!response.ok || !data.idea) throw new Error(data.error || "Unable to park idea.");
      setParkedIdeas((current) => [data.idea as ParkedIdea, ...current]);
      setIdeaModalOpen(false);
      setNotice("Idea parked for a future implementation phase.");
      window.setTimeout(() => setNotice(""), 3200);
    } catch (error) {
      setIdeaError(error instanceof Error ? error.message : "Unable to park idea.");
    } finally {
      setIdeaBusy(false);
    }
  }

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedItemId === null) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const summary = String(form.get("summary") || "").trim();
    if (!summary) {
      setReportError("A summary is required.");
      return;
    }
    setReportBusy(true);
    setReportError("");
    try {
      const response = await fetch(`/api/items/${selectedItemId}/reports`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reportDate: form.get("reportDate"),
          summary,
          blockers: form.get("blockers"),
          hoursSpent: Number(form.get("hoursSpent") || 0),
        }),
      });
      const data = (await response.json()) as { report?: DailyReport; error?: string };
      if (!response.ok || !data.report) throw new Error(data.error || "Unable to save report.");
      setItemReports((current) => [data.report as DailyReport, ...current]);
      formElement.reset();
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Unable to save report.");
    } finally {
      setReportBusy(false);
    }
  }

  const selectedItem = items.find((item) => item.id === selectedItemId) || null;
  const departmentWorkload = departments.map((department) => {
    const deptItems = items.filter((item) => item.department === department.name);
    return {
      ...department,
      active: deptItems.filter((item) => item.status !== "Done").length,
      blocked: deptItems.filter((item) => item.status === "Blocked").length,
    };
  });
  const reportSummary = {
    total: items.length,
    completed: items.filter((item) => item.status === "Done").length,
    inProgress: items.filter((item) => item.status === "In Progress").length,
    waiting: items.filter((item) => item.status === "Queued" || item.status === "Blocked").length,
  };
  const liveProjects = controlSnapshot?.projects || [];
  const projectRows = liveProjects.length
    ? liveProjects.map((project) => {
        const lastCommitParts = project.git.lastCommit?.split("|") || [];
        return {
          id: project.id,
          name: project.name,
          phase: project.phase.replace(/^./, (letter) => letter.toUpperCase()),
          progress: project.progress ?? null,
          local: project.git.detail,
          localTone: project.git.status,
          remote: project.remoteUrl ? (project.git.remoteHead ? `HEAD ${project.git.remoteHead}` : "Connected") : "No remote",
          prod: project.endpoint.detail,
          prodTone: project.endpoint.status,
          next: lastCommitParts[1] || "No commit evidence",
          eta: project.git.observedAt ? new Date(project.git.observedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Unknown",
        };
      })
    : [];
  const modelLabel = (key: string) => {
    const account = key.match(/account-(\d+)/)?.[1];
    if (key.includes("claude/opus")) return `Claude Opus · Account ${account}`;
    if (key.includes("claude/sonnet")) return `Claude Sonnet · Account ${account}`;
    if (key.includes("gemini-3.1-pro")) return `Gemini 3.1 Pro · Account ${account}`;
    if (key.includes("gemini-3.7-flash")) return `Gemini 3.7 Flash · Account ${account}`;
    return key.replace(/^ollama\//, "").replace(/^opencode\//, "OpenCode · ");
  };
  const fleetRows = controlSnapshot?.models?.length
    ? controlSnapshot.models.map((model) => [
        modelLabel(model.model_key),
        model.provider,
        model.role,
        model.detail,
        model.status === "ready" ? "Ready" : model.status === "catalogued" ? "Candidate" : model.status === "not_configured" ? "Setup needed" : "Offline",
      ])
    : [];
  const productionProjects = liveProjects.filter((project) => project.phase === "production");
  const productionFailures = productionProjects.filter((project) => project.health === "error").length;
  const monitoringGaps = liveProjects.filter((project) => project.endpoint.status === "unconfigured").length;
  const readyModels = controlSnapshot?.models?.filter((model) => model.status === "ready" && model.model_key !== "opencode/provider").length || 0;
  const liveAlerts = liveProjects.filter((project) => project.health === "error").length;
  const approvals = controlSnapshot?.approvals || [];
  const completedProducts = controlSnapshot?.completedProducts || [];
  const connectorRows = controlSnapshot?.connectors || [];
  const campaigns = controlSnapshot?.campaigns || [];
  const researchProjects = liveProjects.filter((project) => project.research?.status && project.research.status !== "unknown");
  const selectedLiveProject = liveProjects.find((project) => project.id === selectedProjectId) || null;
  const selectedDepartmentItems = selectedDepartment ? items.filter((item) => item.department === selectedDepartment) : [];
  const attentionProjects = liveProjects.filter((project) => ["error", "warning"].includes(project.health));
  const operationalTools = [
    { name: "Payments", detail: "Bank activity, transaction alerts and audit", url: "http://192.168.0.12:5173", match: "payment" },
    { name: "Documents", detail: "ID proofs waiting for billing or direct print", url: "https://print.aradhanajewellers.com", match: "document" },
    { name: "Print routing", detail: "Ornate bill and voucher routing", url: null, match: "print" },
    { name: "Gold rates", detail: "Live rate monitoring and verification", url: "http://192.168.0.12:8080", match: "gold" },
    { name: "Catalogue", detail: "Jewellery catalogue and CaptureCam", url: null, match: "catalogue" },
    { name: "Stock intake", detail: "Inbound stock automation", url: null, match: "stock" },
    { name: "Devices (MDM)", detail: "Screens, settings and enrollment across the device fleet", url: "http://localhost:8090", match: "fleet" },
  ].map((tool) => {
    const project = liveProjects.find((item) => item.name.toLowerCase().includes(tool.match));
    const health = project?.health || "unconfigured";
    return { ...tool, health, status: health === "healthy" ? "Ready" : health === "warning" ? "Needs attention" : health === "error" ? "Problem" : "Not connected" };
  });

  if (authenticated === null) {
    return <main className="loading-screen">Loading Aradhana Intelligence System…</main>;
  }

  if (!authenticated) {
    return (
      <main className="login-screen">
        <div className="login-aura" />
        <section className="login-card" aria-labelledby="login-title">
          <Image src="/aradhana-logo-transparent.png" alt="Aradhana Jewellers" className="login-logo" width={1600} height={1600} priority />
          <p className="eyebrow">ARADHANA INTELLIGENCE SYSTEM</p>
          <h1 id="login-title">Company command centre</h1>
          <p className="login-copy">Secure access to projects, production, AI workforce and approvals.</p>
          <form onSubmit={login} className="login-form">
            <label>
              Login ID
              <input name="username" autoComplete="username" required />
            </label>
            <label>
              Password
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            {loginError && <p className="form-error">{loginError}</p>}
            <button className="primary-button" disabled={loginBusy}>
              {loginBusy ? "Checking…" : "Enter command centre"}
            </button>
          </form>
          <p className="secure-note"><span>●</span> Local administrator access</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <Image src="/aradhana-logo-transparent.png" alt="Aradhana Jewellers" width={1600} height={1600} priority />
          <div><strong>AIS</strong><span>Command Centre</span></div>
        </div>
        <nav aria-label="Dashboard navigation">
          <button className={view === "home" ? "active" : ""} onClick={() => setView("home")}><b>⌂</b> Today</button>
          <button className={view === "tools" ? "active" : ""} onClick={() => setView("tools")}><b>▦</b> Tools</button>
          <button className={view === "work" ? "active" : ""} onClick={() => setView("work")}><b>✓</b> Work queue</button>
          <button className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}><b>⚙</b> Admin</button>
        </nav>
        <div className="side-health">
          <div className="health-line"><span className={supervisorOnline ? "pulse" : "pulse offline"} /> <b>{supervisorOnline ? "Supervisor online" : "Supervisor offline"}</b></div>
          <p>{supervisorModel}</p>
          <small>{healthDetail}</small>
          <small>{scannerStatus}</small>
        </div>
        <button className="logout-button" onClick={logout}>Sign out</button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="breadcrumb">ARADHANA JEWELLERS</p>
            <h1>{view === "home" ? "Today at Aradhana" : view === "tools" ? "Business tools" : view === "work" ? "Work queue" : "AIS administration"}</h1>
          </div>
          <div className="top-actions">
            <span className="live-clock"><i /> {controlOnline ? "AIS ONLINE" : "CHECKING AIS"}</span>
            <button className="primary-button compact" onClick={() => setModalType("SMALL TASK")}>＋ Add work</button>
          </div>
        </header>

        {notice && <div className="notice" role="status">{notice}</div>}

        {view === "home" && <>
          <section className="owner-summary">
            <article><span>Systems</span><strong>{productionProjects.length}</strong><small>{productionFailures ? `${productionFailures} need attention` : "All monitored systems stable"}</small></article>
            <article><span>Needs attention</span><strong className={attentionProjects.length || approvals.length ? "attention-value" : ""}>{attentionProjects.length + approvals.length}</strong><small>{approvals.length} approvals · {attentionProjects.length} system alerts</small></article>
            <article><span>Work in progress</span><strong>{reportSummary.inProgress}</strong><small>{reportSummary.waiting} waiting for a decision</small></article>
            <article><span>AI and automation</span><strong>{controlOnline ? "On" : "Checking"}</strong><small>{supervisorOnline ? "Local assistant available" : "Assistant unavailable"}</small></article>
          </section>
          <section className="owner-grid">
            <article className="owner-card">
              <div className="section-heading"><div><p className="eyebrow">PRIORITY</p><h2>What needs you</h2></div><button className="text-button" onClick={() => setView("work")}>Open work queue →</button></div>
              {attentionProjects.length === 0 && approvals.length === 0 && <p className="empty-note">Nothing urgent. AIS has no reported production problems or approvals waiting.</p>}
              {attentionProjects.slice(0, 3).map((project) => <div className="owner-row" key={project.id}><i className="dot warn" /><div><b>{project.name}</b><small>{project.endpoint.detail || "Needs review"}</small></div><button className="text-button" onClick={() => setSelectedProjectId(project.id)}>View</button></div>)}
              {approvals.slice(0, 3).map((approval) => <div className="owner-row" key={approval.id}><i className="dot warn" /><div><b>{approval.title}</b><small>{approval.description || approval.department}</small></div><button className="text-button" onClick={() => setView("work")}>Review</button></div>)}
            </article>
            <article className="owner-card">
              <div className="section-heading"><div><p className="eyebrow">RECENT ACTIVITY</p><h2>AIS activity</h2></div></div>
              {controlSnapshot?.events?.slice(0, 4).map((event) => <div className="owner-row" key={event.id}><i className={`dot ${event.severity === "error" ? "warn" : "good"}`} /><div><b>{event.message}</b><small>{new Date(event.created_at).toLocaleString()}</small></div></div>)}
              {!controlSnapshot?.events?.length && <p className="empty-note">Activity will appear here as connected systems report in.</p>}
            </article>
          </section>
          <section className="owner-card quick-tools"><div className="section-heading"><div><p className="eyebrow">QUICK ACCESS</p><h2>Your most-used tools</h2></div><button className="text-button" onClick={() => setView("tools")}>All tools →</button></div><div className="quick-tool-grid">{operationalTools.slice(0, 4).map((tool) => <button key={tool.name} onClick={() => tool.url ? window.open(tool.url, "_blank", "noopener,noreferrer") : setView("tools")}><span className={`tool-state ${tool.health}`} /> <b>{tool.name}</b><small>{tool.status}</small></button>)}</div></section>
        </>}

        {view === "tools" && <section className="tool-grid">{operationalTools.map((tool) => <article className="tool-card" key={tool.name}><div className="tool-card-head"><span className={`tool-state ${tool.health}`} /><span>{tool.status}</span></div><h2>{tool.name}</h2><p>{tool.detail}</p>{tool.url ? <a className="primary-button compact" href={tool.url} target="_blank" rel="noreferrer">Open tool</a> : <button className="secondary-button" onClick={() => setView("work")}>View status</button>}</article>)}</section>}

        {view === "work" && <section className="owner-grid work-grid">
          <article className="owner-card"><div className="section-heading"><div><p className="eyebrow">APPROVALS</p><h2>Decisions waiting</h2></div><span className="alert-count">{approvals.length}</span></div>{approvals.length ? approvals.map((approval) => <div className="work-row" key={approval.id}><b>{approval.title}</b><small>{approval.description || approval.acceptance_criteria}</small><span>{approval.department}</span></div>) : <p className="empty-note">No decisions waiting for approval.</p>}</article>
          <article className="owner-card"><div className="section-heading"><div><p className="eyebrow">ACTIVE WORK</p><h2>Tasks in progress</h2></div><button className="text-button" onClick={() => setModalType("SMALL TASK")}>＋ Add work</button></div>{items.filter((item) => item.status !== "Done").slice(0, 8).map((item) => <div className="work-row" key={item.id}><b>{item.title}</b><small>{item.project} · {item.assignee || "Unassigned"}</small><span>{item.status}</span></div>)}{items.filter((item) => item.status !== "Done").length === 0 && <p className="empty-note">No active work logged yet.</p>}</article>
        </section>}

        <div className={`legacy-admin ${view === "admin" ? "is-active" : ""}`}>

        <section className="hero-grid" id="overview">
          <article className="command-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">MASTER OPERATIONS</p>
                <h2>{masterOn ? "Approved local loops are enabled" : "Company intelligence is partially paused"}</h2>
              </div>
              <div className={`master-status ${masterOn ? "running" : "paused"}`}>
                <span /> {masterOn ? "ALL CONTROLS ENABLED" : `${runningCount}/6 ENABLED`}
              </div>
            </div>
            <p className="command-copy">
              Enabled loops run while this laptop and AIS are on. External connectors remain unavailable until authenticated.
            </p>
            <div className="master-actions">
              <button className="resume-button" onClick={() => setAll(true)} disabled={masterOn}>▶ Run all approved work</button>
              <button className="pause-button" onClick={() => setAll(false)} disabled={runningCount === 0}>Ⅱ Pause all</button>
              <span>Last evidence refresh <b>{controlSnapshot?.generatedAt ? new Date(controlSnapshot.generatedAt).toLocaleTimeString() : "unavailable"}</b></span>
            </div>
            <div className="control-strip" id="controls">
              {controls.map((control) => (
                <div className="mini-control" key={control.id}>
                  <div className={`control-icon ${control.tone}`}>{control.name.slice(0, 1)}</div>
                  <div className="control-label"><strong>{control.name}</strong><span>{control.enabled ? "Running" : "Paused"}</span></div>
                  <Toggle checked={control.enabled} onChange={() => flipControl(control.id)} label={`Toggle ${control.name}`} />
                </div>
              ))}
            </div>
          </article>

          <article className="chat-card">
            <div className="chat-header">
              <div className="supervisor-avatar">Q</div>
              <div><p className="eyebrow">LOCAL SUPERVISOR</p><h2>{supervisorModel}</h2><span className={supervisorOnline ? "online-text" : "offline-text"}>{supervisorOnline ? "● Online · local and private" : "● Offline · start local runtime"}</span></div>
              <button className="icon-button" aria-label="Supervisor evidence" onClick={() => { setNotice(`${supervisorModel}: ${healthDetail}`); window.setTimeout(() => setNotice(""), 3200); }}>ⓘ</button>
            </div>
            <div className="chat-stream" aria-live="polite">
              {messages.map((message, index) => (
                <div className={`message ${message.role}`} key={`${message.time}-${index}`}>
                  <div>{message.content}</div><time>{message.time}</time>
                </div>
              ))}
              {chatBusy && <div className="typing"><span /><span /><span /></div>}
              <div ref={chatEnd} />
            </div>
            <div className="prompt-row">
              <button onClick={() => setChatInput("Give me the company-wide health summary.")}>Health summary</button>
              <button onClick={() => setChatInput("What needs my approval today?")}>My approvals</button>
              <button onClick={() => setChatInput("Show blocked tasks and recommended action.")}>Blocked work</button>
            </div>
            <form className="chat-form" onSubmit={sendMessage}>
              <textarea value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask the local supervisor about any project…" rows={2} />
              <button aria-label="Send message" disabled={!chatInput.trim() || chatBusy}>➤</button>
            </form>
          </article>
        </section>

        <section className="metric-grid">
          <article><span className="metric-icon purple">◆</span><div><p>Registered projects</p><strong>{liveProjects.length || 0}</strong><small>{liveProjects.filter((project) => project.phase === "development").length} development · {liveProjects.filter((project) => project.phase === "testing").length} testing</small></div><em>{controlOnline ? "Live evidence" : "Unavailable"}</em></article>
          <article><span className="metric-icon green">✓</span><div><p>Production systems</p><strong>{productionProjects.length}</strong><small>{productionProjects.length - productionFailures} not failing · {productionFailures} failing</small></div><em className={monitoringGaps ? "warning" : ""}>{monitoringGaps} projects unmonitored</em></article>
          <article><span className="metric-icon gold">✦</span><div><p>AI workforce</p><strong>{readyModels}</strong><small>verified local services ready</small></div><em>{controlSnapshot?.models.filter((model) => model.status === "catalogued").length || 0} candidates</em></article>
          <article><span className="metric-icon red">!</span><div><p>Needs attention</p><strong>{liveAlerts + monitoringGaps}</strong><small>{liveAlerts} failures · {monitoringGaps} coverage gaps</small></div><em className={liveAlerts + monitoringGaps ? "warning" : ""}>{liveAlerts + monitoringGaps ? "Review now" : "Fully covered"}</em></article>
        </section>

        <section className="content-card" id="projects">
          <div className="section-heading">
            <div><p className="eyebrow">PORTFOLIO INTELLIGENCE</p><h2>Projects and production</h2></div>
            <button className="text-button" onClick={runChecks} disabled={!controlOnline || controlSnapshot?.service.checksRunning}>{controlSnapshot?.service.checksRunning ? "Checking…" : "Run fresh checks →"}</button>
          </div>
          <div className="project-table table-scroll">
            <div className="table-row table-head"><span>Project</span><span>Evidence</span><span>Local Git</span><span>Remote Git</span><span>Production</span><span>Latest commit evidence</span></div>
            {projectRows.length === 0 && <p className="empty-note">No live project evidence available.</p>}
            {projectRows.map((project) => (
              <div className="table-row" key={project.name}>
                <span><b>{project.name}</b><small>{project.phase}</small></span>
                <span>{project.progress === null ? <small>No task progress evidence</small> : <><div className="progress"><i style={{ width: `${project.progress}%` }} /></div><small>{project.progress}% from completed tasks</small></>}</span>
                <span className={project.localTone === "error" ? "warn-cell" : ""}><i className={`dot ${project.localTone === "healthy" ? "good" : project.localTone === "warning" || project.localTone === "error" ? "warn" : "neutral"}`} />{project.local}</span>
                <span><i className={`dot ${project.remote === "No remote" ? "neutral" : "good"}`} />{project.remote}</span>
                <span className={project.prodTone === "error" ? "warn-cell" : ""}><i className={`dot ${project.prodTone === "healthy" ? "good" : project.prodTone === "error" ? "warn" : "neutral"}`} />{project.prod}</span>
                <span><b>{project.next}</b><small>Observed {project.eta}</small><button className="text-button" onClick={() => setSelectedProjectId(project.id)}>Details →</button></span>
              </div>
            ))}
          </div>
        </section>

        <section className="split-grid">
          <article className="content-card" id="models">
            <div className="section-heading"><div><p className="eyebrow">ROUTING HIERARCHY</p><h2>Model fleet health</h2></div><span className="healthy-pill">{readyModels} models ready</span></div>
            <div className="model-list">
              {fleetRows.map((model, index) => (
                <div className="model-row" key={model[0]}>
                  <span className="rank">{index + 1}</span>
                  <div><b>{model[0]}</b><small>{model[1]}</small></div>
                  <div><b>{model[2]}</b><small>Responsibility</small></div>
                  <span className="quota" title={model[3]}>{model[3].length > 16 ? `${model[3].slice(0, 14)}…` : model[3]}</span>
                  <span className={`model-state ${model[4] === "Canary" ? "canary" : ""}`}><i />{model[4]}</span>
                </div>
              ))}
            </div>
            <div className="routing-note"><b>Evidence rule:</b> unknown OAuth quotas remain unavailable. Rotation order: Opus accounts 1–3, Sonnet 1–3, Pro 1–3, Flash 1–3, then verified free reserves. Emergency reserve: {Number(controlSnapshot?.settings.emergency_reserve_percent || 15)}%.</div>
          </article>

          <article className="content-card approvals-card">
            <div className="section-heading"><div><p className="eyebrow">CEO GATE</p><h2>Decisions requiring approval</h2></div><span className="alert-count">{approvals.length}</span></div>
            {approvals.length === 0 && <p className="empty-note">No evidence-backed CEO approvals are waiting.</p>}
            {approvals.map((approval) => (
              <div className={`approval-item ${approval.risk_class === "R3" ? "urgent" : ""}`} key={approval.id}>
                <div className="approval-top"><span>{approval.risk_class}</span><time>{new Date(approval.created_at).toLocaleString()}</time></div>
                <h3>{approval.title}</h3>
                <p>{approval.description || approval.acceptance_criteria || "No decision brief supplied."}</p>
                <div className="approval-meta"><span>{approval.department}</span><span>{approval.project_id || "Company-wide"}</span></div>
              </div>
            ))}
          </article>
        </section>

        <section className="split-grid">
          <article className="content-card" id="departments">
            <div className="section-heading"><div><p className="eyebrow">COMPANY WORKFLOW</p><h2>Department workload</h2></div><span className="healthy-pill">{departments.length} departments</span></div>
            <div className="department-list">
              {departmentWorkload.length === 0 && <p className="empty-note">Loading departments…</p>}
              {departmentWorkload.map((department) => (
                <div className="department-row" key={department.id}><span className="dept-letter">{department.name.slice(0, 1)}</span><div><b>{department.name}</b><small>{department.focus}</small></div><div><strong>{department.active}</strong><small>Active</small></div><div className={department.blocked > 0 ? "attention" : ""}><strong>{department.blocked}</strong><small>Blocked</small></div><button onClick={() => setSelectedDepartment(department.name)}>Open</button></div>
              ))}
            </div>
          </article>

          <article className="content-card" id="reports">
            <div className="section-heading"><div><p className="eyebrow">DAILY DETAILED REPORT</p><h2>{selectedItem ? selectedItem.title : "Select a task"}</h2></div></div>
            {controlSnapshot?.report?.content && <div className="routing-note"><b>Portfolio report {controlSnapshot.report.report_date} · revision {controlSnapshot.report.revision}:</b> {controlSnapshot.report.content.executiveSummary?.healthy || 0} healthy, {controlSnapshot.report.content.executiveSummary?.warning || 0} warning, {controlSnapshot.report.content.executiveSummary?.failing || 0} failing. Evidence cutoff {controlSnapshot.report.content.evidenceCutoff ? new Date(controlSnapshot.report.content.evidenceCutoff).toLocaleString() : "unknown"}.</div>}
            {items.length === 0 ? (
              <p className="empty-note">Create a project or task above to start logging daily reports against it.</p>
            ) : (
              <>
                <label className="report-picker">Task<select value={selectedItemId ?? ""} onChange={(event) => setSelectedItemId(Number(event.target.value))}>
                  {items.map((item) => <option key={item.id} value={item.id}>{item.kind} · {item.title}</option>)}
                </select></label>
                <div className="report-summary"><div><strong>{reportSummary.total}</strong><span>tasks tracked</span></div><div><strong>{reportSummary.completed}</strong><span>completed</span></div><div><strong>{reportSummary.inProgress}</strong><span>in progress</span></div><div><strong>{reportSummary.waiting}</strong><span>waiting</span></div></div>
                <div className="timeline">
                  {reportsLoading && <p className="empty-note">Loading reports…</p>}
                  {!reportsLoading && itemReports.length === 0 && <p className="empty-note">No daily reports logged for this task yet.</p>}
                  {itemReports.map((report) => (
                    <div key={report.id}><time>{report.reportDate}</time><i className={report.blockers ? "warn" : "good"} /><p><b>{report.summary}</b><span>{report.hoursSpent}h logged{report.blockers ? ` · Blocker: ${report.blockers}` : ""}</span></p></div>
                  ))}
                </div>
                <form className="report-form" onSubmit={submitReport}>
                  <div className="form-grid"><label>Date<input name="reportDate" type="date" defaultValue={new Date().toISOString().slice(0, 10)} /></label><label>Hours spent<input name="hoursSpent" type="number" min={0} step={0.5} defaultValue={0} /></label></div>
                  <label>Summary<textarea name="summary" rows={2} required placeholder="What happened on this task today" /></label>
                  <label>Blockers (optional)<input name="blockers" placeholder="Leave blank if none" /></label>
                  {reportError && <p className="form-error">{reportError}</p>}
                  <button className="primary-button compact" disabled={reportBusy}>{reportBusy ? "Saving…" : "Add daily report"}</button>
                </form>
              </>
            )}
          </article>
        </section>

        <section className="content-card">
          <div className="section-heading"><div><p className="eyebrow">SUPERVISOR TRIAGE QUEUE</p><h2>Projects &amp; tasks</h2></div><span className="healthy-pill">{items.length} total</span></div>
          {items.length === 0 ? (
            <p className="empty-note">Nothing created yet. Use New project, Big task or Small task above.</p>
          ) : (
            <div className="created-grid">{items.map((item) => (
              <article key={item.id} className={item.id === selectedItemId ? "is-selected" : ""}>
                <span>{item.kind}</span>
                <h3>{item.title}</h3>
                <p>{item.project} · {item.department} · {item.assignee}</p>
                <small>ETA {new Date(item.eta).toLocaleString()} · {item.priority} · {item.status}</small>
                <button className="text-button" onClick={() => setSelectedItemId(item.id)}>View daily reports →</button>
              </article>
            ))}</div>
          )}
        </section>

        <section className="split-grid">
          <article className="content-card">
            <div className="section-heading"><div><p className="eyebrow">COMPLETED PRODUCTS</p><h2>Monitoring and updates</h2></div><span className="healthy-pill">{completedProducts.length}</span></div>
            {completedProducts.length === 0 && <p className="empty-note">No project has a completed/monitoring lifecycle state and completion date recorded yet.</p>}
            <div className="created-grid">
              {completedProducts.map((project) => <article key={project.id}><span>{project.phase.toUpperCase()}</span><h3>{project.name}</h3><p>Completed {project.completedAt ? new Date(project.completedAt).toLocaleDateString() : "date not recorded"}</p><small>{project.endpoint.detail}</small><button className="text-button" onClick={() => setSelectedProjectId(project.id)}>View project details →</button></article>)}
            </div>
          </article>

          <article className="content-card">
            <div className="section-heading"><div><p className="eyebrow">IMPROVEMENT RADAR</p><h2>Live project research</h2></div><button className="text-button" onClick={runResearch} disabled={researchBusy}>{researchBusy ? "Checking…" : "Check next project →"}</button></div>
            {researchProjects.length === 0 && <p className="empty-note">No online improvement evidence collected yet. AIS checks one supported project every 30 minutes.</p>}
            <div className="created-grid">
              {researchProjects.slice(0, 6).map((project) => <article key={project.id}><span>{project.research?.source || "SOURCE UNAVAILABLE"}</span><h3>{project.name}</h3><p>{project.research?.detail}</p><small>{project.research?.observedAt ? `Checked ${new Date(project.research.observedAt).toLocaleString()}` : "Not checked"}</small></article>)}
            </div>
          </article>
        </section>

        <section className="content-card" id="campaigns">
          <div className="section-heading"><div><p className="eyebrow">SOCIAL &amp; MARKETING</p><h2>Campaign pipeline and connector health</h2></div><button className="gold-button" onClick={() => setCampaignModalOpen(true)}>＋ Plan campaign</button></div>
          <div className="connector-grid">
            {connectorRows.filter((connector) => ["social", "research"].includes(connector.category)).map((connector) => <article key={connector.id}><span className={`dot ${connector.status === "ready" ? "good" : "neutral"}`} /><div><b>{connector.name}</b><small>{connector.detail}</small></div><em>{connector.status.replaceAll("_", " ")}</em></article>)}
          </div>
          {campaigns.length === 0 ? <p className="empty-note">No campaign records yet. Planning works now; publishing and statistics stay blocked until Meta connectors are authenticated.</p> : <div className="created-grid">{campaigns.map((campaign) => <article key={campaign.id}><span>{campaign.platform.toUpperCase()} · {campaign.status.toUpperCase()}</span><h3>{campaign.title}</h3><p>{campaign.content_summary || "No content brief"}</p><small>{campaign.owner} · {campaign.planned_at ? new Date(campaign.planned_at).toLocaleString() : "No publish date"}</small></article>)}</div>}
        </section>

        <section className="content-card ideas-card" id="ideas">
          <div className="section-heading"><div><p className="eyebrow">FUTURE PIPELINE</p><h2>Parked ideas</h2></div><button className="gold-button" onClick={() => setIdeaModalOpen(true)}>＋ Park an idea</button></div>
          <div className="idea-grid">
            {parkedIdeas.length === 0 && <p className="empty-note">No ideas parked yet.</p>}
            {parkedIdeas.map((idea) => (
              <article key={idea.id}><span>{idea.phase.toUpperCase()} · {idea.targetDate}</span><h3>{idea.title}</h3><p>{idea.notes}</p><footer>{idea.department} <b>{idea.status}</b></footer>{idea.triggerEvent && <small className="idea-trigger">Trigger: {idea.triggerEvent}</small>}</article>
            ))}
          </div>
        </section>

        <section className="content-card" id="devices">
          <div className="section-heading">
            <div><p className="eyebrow">DEVICE FLEET</p><h2>Screens, settings and enrollment (Fleet MDM)</h2></div>
            <a className="text-button" href="http://localhost:8090" target="_blank" rel="noreferrer">Open in new tab ↗</a>
          </div>
          <p className="command-copy">
            Self-hosted Fleet, embedded directly. Covers the Windows machines, Android tablets/phones once enrolled.
            The iPad Mini 2 stays out of scope (iOS 12 can&apos;t do the modern MDM screen-sharing protocol).
          </p>
          <iframe
            src="http://localhost:8090"
            title="Fleet MDM"
            style={{ width: "100%", height: "80vh", border: "1px solid rgba(255,255,255,0.12)", borderRadius: "12px", background: "#fff" }}
          />
        </section>
        </div>
      </section>

      {modalType && (
        <div className="modal-backdrop">
          <button type="button" className="modal-dismiss" aria-label="Close work item dialog" onClick={() => !modalBusy && setModalType(null)} />
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <button className="modal-close" onClick={() => setModalType(null)} aria-label="Close">×</button>
            <p className="eyebrow">CREATE WORK</p><h2 id="modal-title">New {modalType.toLowerCase()}</h2>
            <p>{modalType === "PROJECT" ? "Register a real local project and its monitoring coverage." : "The local supervisor will validate context, assess risk and assign the right model."}</p>
            <form onSubmit={createItem}>
              <label>Title<input name="title" required placeholder="Clear outcome" /></label>
              {modalType === "PROJECT" ? <>
                <label>Existing local folder (required)<input name="localPath" required placeholder="C:\\path\\to\\project" /></label>
                <div className="form-grid">
                  <label>Department<select name="department">{departments.map((department) => <option key={department.id}>{department.name}</option>)}</select></label>
                  <label>Lifecycle<select name="phase"><option value="planning">Planning</option><option value="development">Development</option><option value="testing">Testing</option><option value="production">Production</option><option value="monitoring">Monitoring</option><option value="completed">Completed</option><option value="parked">Parked</option></select></label>
                </div>
                <label>Remote Git URL<input name="remoteUrl" type="url" placeholder="https://github.com/org/repo.git" /></label>
                <label>Endpoints/subdomains<textarea name="endpoints" rows={3} placeholder={"Dashboard|https://project.example.com\nHealth|https://api.example.com/health"} /></label>
                <label>Expected completion (required)<input name="eta" type="datetime-local" required /></label>
                <label>Project description<textarea name="done" rows={3} placeholder="Purpose, scope and success evidence" /></label>
              </> : <>
                <div className="form-grid">
                  <label>Project<select name="project">{liveProjects.map((project) => <option key={project.id} value={project.name}>{project.name}</option>)}<option>Company-wide</option></select></label>
                  <label>Department<select name="department">{departments.map((department) => <option key={department.id}>{department.name}</option>)}</select></label>
                </div>
                <div className="form-grid">
                  <label>Assignee<input name="assignee" placeholder="Person responsible" /></label>
                  <label>Priority<select name="priority"><option>Normal</option><option>High</option><option>Critical</option></select></label>
                </div>
                <label>ETA (required)<input name="eta" type="datetime-local" required /></label>
                <label>Definition of done (required for execution)<textarea name="done" rows={3} required placeholder="Evidence required before this can be marked complete" /></label>
              </>}
              {modalError && <p className="form-error">{modalError}</p>}
              <button className="primary-button" disabled={modalBusy}>{modalBusy ? "Creating…" : modalType === "PROJECT" ? "Register project" : "Create and send to supervisor"}</button>
            </form>
          </section>
        </div>
      )}

      {selectedLiveProject && (
        <div className="modal-backdrop">
          <button type="button" className="modal-dismiss" aria-label="Close project details" onClick={() => setSelectedProjectId(null)} />
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="project-detail-title">
            <button className="modal-close" onClick={() => setSelectedProjectId(null)} aria-label="Close">×</button>
            <p className="eyebrow">LIVE PROJECT EVIDENCE</p><h2 id="project-detail-title">{selectedLiveProject.name}</h2>
            <p>{selectedLiveProject.description || "No project description recorded."}</p>
            <div className="detail-list">
              <div><b>Lifecycle</b><span>{selectedLiveProject.phase} · expected {selectedLiveProject.expectedCompletion ? new Date(selectedLiveProject.expectedCompletion).toLocaleString() : "not recorded"}</span></div>
              <div><b>Local path</b><span>{selectedLiveProject.localPath || "Not connected"}</span></div>
              <div><b>Remote Git</b><span>{selectedLiveProject.remoteUrl || "Not connected"}</span></div>
              <div><b>Git evidence</b><span>{selectedLiveProject.git.detail}</span></div>
              <div><b>Task progress</b><span>{selectedLiveProject.taskStats?.total ? `${selectedLiveProject.taskStats.completed}/${selectedLiveProject.taskStats.total} completed · ${selectedLiveProject.taskStats.blocked} blocked` : "No linked tasks"}</span></div>
              <div><b>Completion date</b><span>{selectedLiveProject.completedAt ? new Date(selectedLiveProject.completedAt).toLocaleString() : "Not completed"}</span></div>
            </div>
            <h3>Endpoints and subdomains</h3>
            {!selectedLiveProject.endpoint.checks?.length ? <p className="empty-note">No endpoint or subdomain monitoring configured.</p> : <div className="connector-grid">{selectedLiveProject.endpoint.checks.map((check) => <article key={check.name}><span className={`dot ${check.ok ? "good" : "warn"}`} /><div><b>{check.name}</b><small>{check.statusCode || "No response"} · {check.latencyMs} ms</small></div><em>{check.ok ? "passing" : "failing"}</em></article>)}</div>}
            <h3>Latest improvement evidence</h3>
            {!selectedLiveProject.research?.insights?.length ? <p className="empty-note">No sourced improvement candidates collected.</p> : <div className="detail-list">{selectedLiveProject.research.insights.slice(0, 10).map((insight) => <div key={insight.name}><b>{insight.name}</b><span>{insight.current || "?"} → {insight.latest || "?"}</span></div>)}</div>}
          </section>
        </div>
      )}

      {selectedDepartment && (
        <div className="modal-backdrop">
          <button type="button" className="modal-dismiss" aria-label="Close department workflow" onClick={() => setSelectedDepartment(null)} />
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="department-detail-title">
            <button className="modal-close" onClick={() => setSelectedDepartment(null)} aria-label="Close">×</button>
            <p className="eyebrow">DEPARTMENT WORKFLOW</p><h2 id="department-detail-title">{selectedDepartment}</h2>
            {selectedDepartmentItems.length === 0 ? <p className="empty-note">No tasks assigned to this department.</p> : <div className="created-grid">{selectedDepartmentItems.map((item) => <article key={item.id}><span>{item.kind} · {item.status}</span><h3>{item.title}</h3><p>{item.assignee} · {item.project}</p><small>ETA {new Date(item.eta).toLocaleString()}</small></article>)}</div>}
          </section>
        </div>
      )}

      {campaignModalOpen && (
        <div className="modal-backdrop">
          <button type="button" className="modal-dismiss" aria-label="Close campaign planner" onClick={() => !campaignBusy && setCampaignModalOpen(false)} />
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="campaign-modal-title">
            <button className="modal-close" onClick={() => setCampaignModalOpen(false)} aria-label="Close">×</button>
            <p className="eyebrow">CONTENT PIPELINE</p><h2 id="campaign-modal-title">Plan campaign</h2>
            <p>This creates a real pipeline record. It cannot publish or retrieve statistics until the matching platform connector is authenticated.</p>
            <form onSubmit={createCampaign}>
              <label>Campaign title<input name="title" required placeholder="Campaign outcome" /></label>
              <div className="form-grid"><label>Platform<select name="platform"><option>Instagram</option><option>Facebook</option><option>Instagram + Facebook</option><option>Multi-platform</option></select></label><label>Owner<input name="owner" placeholder="Person responsible" /></label></div>
              <label>Planned publish time<input name="plannedAt" type="datetime-local" required /></label>
              <label>Content brief<textarea name="summary" rows={4} required placeholder="Audience, message, assets and call to action" /></label>
              {campaignError && <p className="form-error">{campaignError}</p>}
              <button className="gold-button" disabled={campaignBusy}>{campaignBusy ? "Saving…" : "Add to campaign pipeline"}</button>
            </form>
          </section>
        </div>
      )}

      {ideaModalOpen && (
        <div className="modal-backdrop">
          <button type="button" className="modal-dismiss" aria-label="Close parked idea dialog" onClick={() => !ideaBusy && setIdeaModalOpen(false)} />
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="idea-modal-title">
            <button className="modal-close" onClick={() => setIdeaModalOpen(false)} aria-label="Close">×</button>
            <p className="eyebrow">FUTURE PIPELINE</p><h2 id="idea-modal-title">Park an idea</h2>
            <p>Capture ideas that aren&apos;t ready to build yet, with when you expect to revisit them.</p>
            <form onSubmit={createIdea}>
              <label>Title<input name="title" required placeholder="Idea name" /></label>
              <label>Notes<textarea name="notes" rows={2} placeholder="What this idea covers" /></label>
              <div className="form-grid">
                <label>Owning department<select name="department">{departments.map((department) => <option key={department.id}>{department.name}</option>)}</select></label>
                <label>Expected phase (required)<input name="phase" required placeholder="e.g. Phase 2" /></label>
              </div>
              <div className="form-grid">
                <label>Expected date (required)<input name="targetDate" type="date" required /></label>
                <label>Trigger to revisit<input name="trigger" placeholder="e.g. After X ships" /></label>
              </div>
              {ideaError && <p className="form-error">{ideaError}</p>}
              <button className="gold-button" disabled={ideaBusy}>{ideaBusy ? "Saving…" : "Park this idea"}</button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
