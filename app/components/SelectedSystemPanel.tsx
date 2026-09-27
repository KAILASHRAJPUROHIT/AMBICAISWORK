"use client";

import React from "react";
import { SystemItem } from "./types";

interface SelectedSystemPanelProps {
  system: SystemItem;
  onDiagnoseAndFix: (systemId: string) => void;
}

export const SelectedSystemPanel: React.FC<SelectedSystemPanelProps> = ({
  system,
  onDiagnoseAndFix,
}) => {
  let statusBadgeStyle = "border: 1px solid rgba(55,227,161,.45); color: var(--obsidian-green); box-shadow: 0 0 14px rgba(55,227,161,.22)";
  let issueBg = "linear-gradient(100deg, rgba(55,227,161,.08), rgba(36,217,255,.04))";
  let issueColor = "var(--obsidian-green)";

  if (system.statusTone === "amber") {
    statusBadgeStyle = "border: 1px solid rgba(255,196,91,.45); color: var(--obsidian-amber); box-shadow: 0 0 14px rgba(255,196,91,.22)";
    issueBg = "linear-gradient(100deg, rgba(255,196,91,.12), rgba(255,95,120,.06))";
    issueColor = "var(--obsidian-amber)";
  } else if (system.statusTone === "red") {
    statusBadgeStyle = "border: 1px solid rgba(255,95,120,.45); color: var(--obsidian-red); box-shadow: 0 0 14px rgba(255,95,120,.22)";
    issueBg = "linear-gradient(100deg, rgba(255,95,120,.14), rgba(139,92,255,.08))";
    issueColor = "var(--obsidian-red)";
  }

  return (
    <section
      className="ais-panel"
      style={{
        marginTop: "16px",
        border: "1px solid rgba(255,196,91,.35)",
        borderRadius: "26px",
        background: "linear-gradient(120deg, rgba(26,17,4,.92), rgba(5,7,10,.95) 45%, rgba(16,8,22,.92))",
        padding: "16px 22px",
        display: "flex",
        gap: "22px",
        flexWrap: "wrap",
        alignItems: "stretch",
      }}
    >
      {/* Left Column: Title & Telemetry Gauges */}
      <div style={{ width: "310px", flexShrink: 0 }}>
        <div style={{ fontSize: "8.5px", letterSpacing: ".22em", color: "var(--obsidian-dim)", fontWeight: 700 }}>
          SELECTED SYSTEM
        </div>
        <div style={{ fontSize: "10px", color: system.source === "live" ? "var(--obsidian-green)" : "var(--obsidian-muted)", marginTop: "4px" }}>
          {system.source === "live"
            ? "Health status is live. Host, scores, metrics and history below are sample values."
            : "Sample data — this system is not connected to real monitoring yet."}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginTop: "5px" }}>
          <span style={{ fontSize: "22px", fontWeight: 800, letterSpacing: "-.01em" }}>{system.name}</span>
          <span
            style={{
              fontFamily: "'Geist Mono',monospace",
              fontSize: "10.5px",
              borderRadius: "999px",
              padding: "2px 10px",
              border: system.statusTone === "amber" ? "1px solid rgba(255,196,91,.45)" : system.statusTone === "red" ? "1px solid rgba(255,95,120,.45)" : "1px solid rgba(55,227,161,.45)",
              color: system.statusTone === "amber" ? "var(--obsidian-amber)" : system.statusTone === "red" ? "var(--obsidian-red)" : "var(--obsidian-green)",
              boxShadow: system.statusTone === "amber" ? "0 0 14px rgba(255,196,91,.22)" : system.statusTone === "red" ? "0 0 14px rgba(255,95,120,.22)" : "0 0 14px rgba(55,227,161,.22)",
            }}
          >
            {system.health.toUpperCase()}{system.source === "live" ? "" : ` · ${system.healthScore}%`}
          </span>
        </div>
        <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
          {system.cleanUptime} clean uptime
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "8px", marginTop: "14px" }}>
          <div style={{ border: "1px solid rgba(255,196,91,.25)", borderRadius: "14px", padding: "8px 12px", background: "linear-gradient(150deg, rgba(255,196,91,.08), rgba(8,11,16,.8))" }}>
            <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "#CBA868", fontWeight: 700 }}>CPU</div>
            <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "18px", fontWeight: 700, color: "var(--obsidian-amber)", marginTop: "2px" }}>
              {system.cpu}
            </div>
            <div style={{ height: "3px", borderRadius: "2px", background: "rgba(120,170,220,.15)", marginTop: "5px", overflow: "hidden" }}>
              <div className="ais-fillx" style={{ width: system.cpu, height: "100%", borderRadius: "2px", background: "linear-gradient(90deg, var(--obsidian-amber), var(--obsidian-red))" }}></div>
            </div>
          </div>

          <div style={{ border: "1px solid rgba(36,217,255,.25)", borderRadius: "14px", padding: "8px 12px", background: "linear-gradient(150deg, rgba(36,217,255,.08), rgba(8,11,16,.8))" }}>
            <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "#7FB9CE", fontWeight: 700 }}>MEMORY</div>
            <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "18px", fontWeight: 700, color: "var(--obsidian-cyan)", marginTop: "2px" }}>
              {system.memory}
            </div>
            <div style={{ height: "3px", borderRadius: "2px", background: "rgba(120,170,220,.15)", marginTop: "5px", overflow: "hidden" }}>
              <div className="ais-fillx" style={{ width: system.memory, height: "100%", borderRadius: "2px", background: "linear-gradient(90deg, var(--obsidian-cyan), var(--obsidian-violet))", animationDelay: "-.6s" }}></div>
            </div>
          </div>

          <div style={{ border: "1px solid rgba(139,92,255,.25)", borderRadius: "14px", padding: "8px 12px", background: "linear-gradient(150deg, rgba(139,92,255,.08), rgba(8,11,16,.8))" }}>
            <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "#A794D6", fontWeight: 700 }}>EVENTS</div>
            <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "18px", fontWeight: 700, color: "var(--obsidian-violet)", marginTop: "2px" }}>
              {system.events}
            </div>
          </div>

          <div style={{ border: "1px solid rgba(255,79,216,.25)", borderRadius: "14px", padding: "8px 12px", background: "linear-gradient(150deg, rgba(255,79,216,.08), rgba(8,11,16,.8))" }}>
            <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "#C98BB4", fontWeight: 700 }}>HOST</div>
            <div style={{ fontSize: "13.5px", fontWeight: 700, marginTop: "4px", color: "#F9B8E8" }}>
              {system.host}
            </div>
          </div>
        </div>
      </div>

      {/* Center Column: Current Issue, Last Work, Dependencies */}
      <div style={{ flexGrow: 1, minWidth: "280px", display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ border: "1px solid rgba(120,170,220,.2)", borderRadius: "16px", background: issueBg, padding: "10px 14px" }}>
          <div style={{ fontSize: "8px", letterSpacing: ".18em", color: issueColor, fontWeight: 700 }}>CURRENT ISSUE / STATE</div>
          <div style={{ fontSize: "14px", marginTop: "4px", color: "#FFE7BC", fontWeight: 600 }}>{system.errorReason}</div>
        </div>

        <div style={{ border: "1px solid var(--obsidian-border)", borderRadius: "16px", background: "rgba(8,11,16,.65)", padding: "10px 14px" }}>
          <div style={{ fontSize: "8px", letterSpacing: ".18em", color: "var(--obsidian-dim)", fontWeight: 700 }}>LAST WORK DONE</div>
          <div style={{ fontSize: "12.5px", marginTop: "4px", color: "#C6D2E2" }}>{system.lastWorkDesc}</div>
          <div style={{ fontSize: "10.5px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            {system.lastWorkBy} &middot; {system.lastWorkTime}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "8px", letterSpacing: ".18em", color: "var(--obsidian-dim)", fontWeight: 700, marginBottom: "6px" }}>
            DEPENDENCIES
          </div>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {system.dependencies.map((dep, idx) => (
              <span
                key={idx}
                style={{
                  fontSize: "10px",
                  color: "#BFF3FF",
                  border: "1px solid rgba(36,217,255,.35)",
                  borderRadius: "999px",
                  padding: "4px 10px",
                  background: "rgba(36,217,255,.06)",
                }}
              >
                {dep}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Right-Center Column: Recent Activity Timeline */}
      <div style={{ width: "260px", flexShrink: 0, borderLeft: "1px solid var(--obsidian-border)", paddingLeft: "18px" }}>
        <div style={{ fontSize: "8px", letterSpacing: ".18em", color: "var(--obsidian-dim)", fontWeight: 700, marginBottom: "9px" }}>
          RECENT ACTIVITY
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {system.recentActivity.map((act, idx) => {
            let actColor = "var(--obsidian-green)";
            if (act.tone === "amber") actColor = "var(--obsidian-amber)";
            if (act.tone === "red") actColor = "var(--obsidian-red)";
            if (act.tone === "cyan") actColor = "var(--obsidian-cyan)";
            if (act.tone === "violet") actColor = "var(--obsidian-violet)";
            return (
              <div key={idx} style={{ display: "flex", gap: "9px", alignItems: "center" }}>
                <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: actColor, boxShadow: `0 0 7px ${actColor}`, flexShrink: 0 }}></span>
                <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "9.5px", color: "var(--obsidian-dim)", width: "32px", flexShrink: 0 }}>{act.time}</span>
                <span style={{ fontSize: "11px", color: "#C6D2E2" }}>{act.note}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Action Column: Ask Agent Button */}
      <div style={{ width: "240px", flexShrink: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: "8px" }}>
        <button
          type="button"
          onClick={() => onDiagnoseAndFix(system.id)}
          style={{
            position: "relative",
            overflow: "hidden",
            border: "1px solid rgba(36,217,255,.55)",
            borderRadius: "14px",
            background: "linear-gradient(120deg, rgba(36,217,255,.26), rgba(139,92,255,.28) 55%, rgba(255,79,216,.24))",
            color: "#F0FBFF",
            padding: "14px 16px",
            fontFamily: "inherit",
            fontSize: "12px",
            fontWeight: 800,
            letterSpacing: ".08em",
            lineHeight: 1.4,
            textAlign: "left",
            cursor: "pointer",
            boxShadow: "0 0 28px rgba(139,92,255,.35)",
            transition: "transform .15s ease",
          }}
        >
          <span className="ais-sweepx" style={{ position: "absolute", top: 0, bottom: 0, width: "36%", background: "linear-gradient(90deg, transparent, rgba(255,255,255,.22), transparent)", pointerEvents: "none" }}></span>
          <span style={{ position: "relative", display: "flex", alignItems: "center", gap: "10px" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#9AECFF" strokeWidth="2" aria-hidden="true">
              <path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4z" />
              <path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
            </svg>
            ASK AIS AGENT TO<br />DIAGNOSE &amp; FIX
          </span>
        </button>
        <div style={{ fontSize: "9.5px", color: "var(--obsidian-dim)", lineHeight: 1.55 }}>
          diagnose <span style={{ color: "var(--obsidian-cyan)" }}>&rarr;</span> root cause <span style={{ color: "var(--obsidian-violet)" }}>&rarr;</span> fix plan <span style={{ color: "var(--obsidian-amber)" }}>&rarr;</span> risk <span style={{ color: "var(--obsidian-magenta)" }}>&rarr;</span> <span style={{ color: "var(--obsidian-green)", fontWeight: 700 }}>human approval</span> <span style={{ color: "var(--obsidian-magenta)" }}>&rarr;</span> execute <span style={{ color: "var(--obsidian-cyan)" }}>&rarr;</span> audit
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9.5px", color: "var(--obsidian-muted)" }}>
          <span className="ais-blink" style={{ width: "5px", height: "5px", borderRadius: "50%", background: "var(--obsidian-violet)", boxShadow: "0 0 8px var(--obsidian-violet)" }}></span>
          No state change without human sign-off
        </div>
      </div>
    </section>
  );
};
