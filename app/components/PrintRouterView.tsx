"use client";

import { useEffect, useMemo, useState } from "react";

type Printer = { Name: string; IsOnline: boolean; status: string; DriverName?: string; PortName?: string };
type Node = { id: string; name: string; status: "healthy" | "warning" | "error" | "unregistered"; detail: string; stationName?: string; nodeId?: string; uptimeSeconds?: number; emergencyBypassActive?: boolean; printerSummary?: { total: number; online: number; offline: number }; printers?: Printer[]; routing?: { configHash?: string; ruleCount?: number; writesEnabled?: boolean } | null };
type NodesResponse = { status: string; detail: string; nodes: Node[]; error?: string };
const tone = (status?: string) => status === "healthy" ? "#37E3A1" : status === "warning" ? "#FFC45B" : status === "unregistered" ? "#A0AABD" : "#FF5F78";

export function PrintRouterView() {
  const [data, setData] = useState<NodesResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const load = async (refresh = false) => {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/print-router/nodes", refresh ? { method: "POST" } : { cache: "no-store" });
      const result = await response.json() as NodesResponse;
      if (!response.ok) throw new Error(result.error || "Could not load authenticated print nodes.");
      setData(result); setSelectedId((current) => current || result.nodes[0]?.id || "");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load authenticated print nodes."); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const node = useMemo(() => data?.nodes.find((item) => item.id === selectedId) || null, [data, selectedId]);
  return <main style={{ marginTop: "14px", minHeight: "calc(100vh - 230px)" }}><section className="ais-panel" style={{ padding: "24px", border: "1px solid rgba(36,217,255,.28)", borderRadius: "22px", background: "linear-gradient(145deg, rgba(13,20,29,.98), rgba(5,7,10,.96))" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", flexWrap: "wrap" }}><div><div className="ais-spec" style={{ color: "var(--obsidian-cyan)", fontSize: "10px", fontWeight: 800, letterSpacing: ".2em" }}>AUTHENTICATED NODE CONTROL</div><h1 style={{ margin: "6px 0", fontSize: "26px" }}>Print Router</h1><p style={{ margin: 0, color: "var(--obsidian-muted)", fontSize: "12px" }}>Real PC state only. Routing writes remain locked until signed commands and rollback are deployed.</p></div><button disabled={busy} onClick={() => void load(true)} style={{ padding: "9px 14px", borderRadius: "9px", border: "1px solid rgba(36,217,255,.45)", background: "rgba(36,217,255,.11)", color: "#BFF3FF", cursor: "pointer", fontWeight: 700 }}>{busy ? "CHECKING…" : "REFRESH REAL STATE"}</button></div>
    {error && <p style={{ color: "var(--obsidian-red)", marginTop: "20px" }}>{error}</p>}
    {!busy && data?.nodes.length === 0 && <div style={{ marginTop: "24px", border: "1px dashed rgba(255,196,91,.45)", borderRadius: "14px", padding: "20px", color: "#E9D9B4" }}><b>No authenticated PCs registered.</b><br /><span style={{ fontSize: "12px" }}>{data?.detail || "Install a secured Print Node and register its per-node secret."}</span></div>}
    {data && data.nodes.length > 0 && <><label style={{ display: "grid", gap: "7px", marginTop: "22px", maxWidth: "480px", color: "var(--obsidian-muted)", fontSize: "11px", letterSpacing: ".1em" }}>SELECT WORKSTATION<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} style={{ color: "#F5F8FF", background: "#0A0D13", border: "1px solid rgba(120,170,220,.3)", padding: "11px", borderRadius: "9px" }}>{data.nodes.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.status.toUpperCase()}</option>)}</select></label>
      {node && <><div style={{ marginTop: "18px", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: "12px" }}>{[["NODE HEALTH", node.status.toUpperCase()], ["STATION", node.stationName || node.nodeId || "—"], ["PRINTERS", `${node.printerSummary?.online ?? 0}/${node.printerSummary?.total ?? 0} online`], ["CONFIG", node.routing?.configHash ? `${node.routing.configHash.slice(0, 12)}…` : "—"], ["RULES", String(node.routing?.ruleCount ?? "—")]].map(([label, value]) => <div key={label} style={{ padding: "13px", borderRadius: "12px", border: "1px solid rgba(120,170,220,.18)", background: "rgba(13,20,29,.72)" }}><div style={{ fontSize: "9px", letterSpacing: ".16em", color: "var(--obsidian-dim)" }}>{label}</div><div style={{ marginTop: "7px", fontWeight: 800, color: label === "NODE HEALTH" ? tone(node.status) : "#F5F8FF" }}>{value}</div></div>)}</div>
      <div style={{ marginTop: "18px", display: "grid", gridTemplateColumns: "minmax(0,1.4fr) minmax(260px,.6fr)", gap: "14px" }}><div style={{ border: "1px solid rgba(120,170,220,.18)", borderRadius: "14px", overflow: "hidden" }}><div style={{ padding: "12px 14px", borderBottom: "1px solid rgba(120,170,220,.16)", fontWeight: 700 }}>Detected printers</div>{(node.printers || []).map((printer) => <div key={printer.Name} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "10px 14px", borderBottom: "1px solid rgba(120,170,220,.09)", fontSize: "12px" }}><div><b>{printer.Name}</b><br /><span style={{ color: "var(--obsidian-muted)", fontSize: "10px" }}>{printer.DriverName || "Unknown driver"} · {printer.PortName || "Unknown port"}</span></div><span style={{ color: printer.IsOnline ? "var(--obsidian-green)" : "var(--obsidian-red)", fontWeight: 700 }}>{printer.IsOnline ? "ONLINE" : "OFFLINE"}</span></div>)}</div><aside style={{ border: "1px solid rgba(255,196,91,.28)", borderRadius: "14px", padding: "16px", background: "rgba(255,196,91,.05)" }}><div className="ais-spec" style={{ color: "var(--obsidian-amber)", fontSize: "9px", fontWeight: 800 }}>ROUTING CONTROLS</div><p style={{ fontSize: "12px", color: "#E9D9B4", lineHeight: 1.5 }}>Locked until signed command validation, rollback snapshot and post-apply config-hash confirmation are active.</p><button disabled style={{ width: "100%", padding: "10px", borderRadius: "9px", border: "1px solid rgba(255,196,91,.25)", background: "rgba(255,196,91,.08)", color: "#BBAE8F" }}>SIGNED RULE UPDATE — LOCKED</button></aside></div></>}</>}
  </section></main>;
}
