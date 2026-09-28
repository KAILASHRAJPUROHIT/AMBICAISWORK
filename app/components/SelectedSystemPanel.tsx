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
  let issueBg = "linear-gradient(100deg, rgba(55,227,161,.08), rgba(36,217,255,.04))";
  let issueColor = "var(--obsidian-green)";

  if (system.statusTone === "amber") {
    issueBg = "linear-gradient(100deg, rgba(255,196,91,.12), rgba(255,95,120,.06))";
    issueColor = "var(--obsidian-amber)";
  } else if (system.statusTone === "red") {
    issueBg = "linear-gradient(100deg, rgba(255,95,120,.14), rgba(139,92,255,.08))";
    issueColor = "var(--obsidian-red)";
  } else if (system.statusTone === "grey") {
    issueBg = "linear-gradient(100deg, rgba(120,144,163,.08), rgba(8,11,16,.4))";
    issueColor = "var(--obsidian-muted)";
  }

  const unregistered = system.health === "Unregistered";

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
      {/* Left Column: Title & status */}
      <div style={{ width: "310px", flexShrink: 0 }}>
        <div style={{ fontSize: "8.5px", letterSpacing: ".22em", color: "var(--obsidian-dim)", fontWeight: 700 }}>
          SELECTED SYSTEM
        </div>
        <div style={{ fontSize: "10px", color: system.source === "registry" ? "var(--obsidian-green)" : "var(--obsidian-muted)", marginTop: "4px" }}>
          {system.source === "registry"
            ? unregistered
              ? "No system is registered under this key yet."
              : system.manual
                ? "Operator-declared status — no automated check exists for this system."
                : "Live from the systems registry."
            : "Waiting for the systems registry to answer…"}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginTop: "5px" }}>
          <span style={{ fontSize: "22px", fontWeight: 800, letterSpacing: "-.01em" }}>{system.name}</span>
          <span
            style={{
              fontFamily: "'Geist Mono',monospace",
              fontSize: "10.5px",
              borderRadius: "999px",
              padding: "2px 10px",
              border: system.statusTone === "amber" ? "1px solid rgba(255,196,91,.45)" : system.statusTone === "red" ? "1px solid rgba(255,95,120,.45)" : system.statusTone === "grey" ? "1px solid rgba(120,144,163,.4)" : "1px solid rgba(55,227,161,.45)",
              color: system.statusTone === "amber" ? "var(--obsidian-amber)" : system.statusTone === "red" ? "var(--obsidian-red)" : system.statusTone === "grey" ? "var(--obsidian-muted)" : "var(--obsidian-green)",
              boxShadow: system.statusTone === "amber" ? "0 0 14px rgba(255,196,91,.22)" : system.statusTone === "red" ? "0 0 14px rgba(255,95,120,.22)" : "none",
            }}
          >
            {system.health.toUpperCase()}
          </span>
        </div>
        {!unregistered && (
          <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            {system.cleanUptime === "—" ? "Clean uptime not yet established" : `${system.cleanUptime} clean uptime`}
          </div>
        )}

        <div style={{ marginTop: "14px", border: "1px solid rgba(255,79,216,.25)", borderRadius: "14px", padding: "10px 12px", background: "linear-gradient(150deg, rgba(255,79,216,.08), rgba(8,11,16,.8))" }}>
          <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "#C98BB4", fontWeight: 700 }}>HOST</div>
          <div style={{ fontSize: "13.5px", fontWeight: 700, marginTop: "4px", color: "#F9B8E8" }}>
            {system.host}
          </div>
        </div>
        {!unregistered && (
          <div style={{ fontSize: "9.5px", color: "var(--obsidian-dim)", marginTop: "8px", lineHeight: 1.5 }}>
            No per-system CPU, memory or event-rate telemetry exists yet — that needs a host agent on each machine, not built here. Showing what is real: health, host, and the last known change.
          </div>
        )}
      </div>

      {/* Center Column: Current Issue, Last Work */}
      <div style={{ flexGrow: 1, minWidth: "280px", display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ border: "1px solid rgba(120,170,220,.2)", borderRadius: "16px", background: issueBg, padding: "10px 14px" }}>
          <div style={{ fontSize: "8px", letterSpacing: ".18em", color: issueColor, fontWeight: 700 }}>CURRENT ISSUE / STATE</div>
          <div style={{ fontSize: "14px", marginTop: "4px", color: "#FFE7BC", fontWeight: 600 }}>{system.errorReason}</div>
        </div>

        <div style={{ border: "1px solid var(--obsidian-border)", borderRadius: "16px", background: "rgba(8,11,16,.65)", padding: "10px 14px" }}>
          <div style={{ fontSize: "8px", letterSpacing: ".18em", color: "var(--obsidian-dim)", fontWeight: 700 }}>
            {system.manual ? "OPERATOR NOTE" : "LAST KNOWN CHANGE (SOURCE CONTROL)"}
          </div>
          <div style={{ fontSize: "12.5px", marginTop: "4px", color: "#C6D2E2" }}>{system.lastWorkDesc}</div>
          <div style={{ fontSize: "10.5px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            {system.lastWorkBy} &middot; {system.lastWorkTime}
          </div>
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
          Not connected yet — no state change without human sign-off
        </div>
      </div>
    </section>
  );
};
