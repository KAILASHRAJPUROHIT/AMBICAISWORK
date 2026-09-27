"use client";

import React from "react";

export const AgentsView: React.FC = () => {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "18px" }}>
      <div role="note" style={{ gridColumn: "1 / -1", padding: "8px 12px", borderRadius: "12px", border: "1px solid rgba(255,196,91,.3)", background: "rgba(255,196,91,.06)", fontSize: "11px", color: "#E9D9B4" }}>
        <b style={{ color: "var(--obsidian-amber)", letterSpacing: ".14em", fontSize: "9px", marginRight: "8px" }}>CONCEPT</b>
        These are the planned agent roles. The ONLINE and CONTROLLED badges are design placeholders, not live agent status.
      </div>
      {/* Infrastructure Agent */}
      <div
        className="ais-panel"
        style={{
          border: "1px solid rgba(36,217,255,0.35)",
          borderRadius: "24px",
          background: "linear-gradient(165deg, rgba(8,16,28,.96), rgba(2,4,7,.94))",
          padding: "22px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "14px",
              background: "linear-gradient(135deg,#24D9FF,#4D84FF)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(36,217,255,0.4)",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#04060A" strokeWidth="2.2">
              <rect x="2" y="2" width="20" height="8" rx="2" />
              <rect x="2" y="14" width="20" height="8" rx="2" />
              <line x1="6" y1="6" x2="6.01" y2="6" />
              <line x1="6" y1="18" x2="6.01" y2="18" />
            </svg>
          </div>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "'Geist Mono',monospace",
              fontSize: "10px",
              color: "var(--obsidian-green)",
              border: "1px solid rgba(55,227,161,.3)",
              borderRadius: "999px",
              padding: "3px 10px",
              background: "rgba(55,227,161,.08)",
            }}
          >
            <span className="ais-ok" style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-green)" }}></span>
            ONLINE
          </span>
        </div>
        <div>
          <div style={{ fontSize: "18px", fontWeight: 800, letterSpacing: "-.01em" }}>Infrastructure Agent</div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            Low-level OS daemon, spooler recovery, SMB mounts, and network host monitoring.
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--obsidian-border)", paddingTop: "12px", display: "flex", flexDirection: "column", gap: "8px", fontSize: "11.5px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>CONTROL SCOPE</span>
            <span style={{ color: "var(--obsidian-cyan)", fontWeight: 600 }}>Windows Services · Spooler · Printers · Hosts</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>ACTIONS (24H)</span>
            <span style={{ fontFamily: "'Geist Mono',monospace" }}>28 successful routines</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>LAST RUN</span>
            <span style={{ fontFamily: "'Geist Mono',monospace" }}>Cleared stale spool jobs (17:02)</span>
          </div>
        </div>
      </div>

      {/* Application Agent */}
      <div
        className="ais-panel"
        style={{
          border: "1px solid rgba(139,92,255,0.35)",
          borderRadius: "24px",
          background: "linear-gradient(165deg, rgba(20,12,30,.96), rgba(4,2,7,.94))",
          padding: "22px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "14px",
              background: "linear-gradient(135deg,#8B5CFF,#FF4FD8)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(139,92,255,0.4)",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#04060A" strokeWidth="2.2">
              <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
            </svg>
          </div>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "'Geist Mono',monospace",
              fontSize: "10px",
              color: "var(--obsidian-cyan)",
              border: "1px solid rgba(36,217,255,.3)",
              borderRadius: "999px",
              padding: "3px 10px",
              background: "rgba(36,217,255,.08)",
            }}
          >
            <span className="ais-ok" style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-cyan)" }}></span>
            ACTIVE DIAGNOSIS
          </span>
        </div>
        <div>
          <div style={{ fontSize: "18px", fontWeight: 800, letterSpacing: "-.01em" }}>Application Agent</div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            API gateways, background workers, webhooks, failed jobs, and model orchestration.
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--obsidian-border)", paddingTop: "12px", display: "flex", flexDirection: "column", gap: "8px", fontSize: "11.5px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>CONTROL SCOPE</span>
            <span style={{ color: "var(--obsidian-magenta)", fontWeight: 600 }}>Gold Rate · Webhooks · Catalogue · MDM</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>ACTIONS (24H)</span>
            <span style={{ fontFamily: "'Geist Mono',monospace" }}>13 successful routines</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>CURRENT FOCUS</span>
            <span style={{ color: "var(--obsidian-violet)", fontWeight: 600 }}>Investigating Catalogue queue backlog</span>
          </div>
        </div>
      </div>

      {/* Human Control Layer */}
      <div
        className="ais-panel"
        style={{
          border: "1px solid rgba(55,227,161,0.35)",
          borderRadius: "24px",
          background: "linear-gradient(165deg, rgba(8,24,18,.96), rgba(2,6,4,.94))",
          padding: "22px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "14px",
              background: "linear-gradient(135deg,#37E3A1,#24D9FF)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(55,227,161,0.4)",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#04060A" strokeWidth="2.2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "'Geist Mono',monospace",
              fontSize: "10px",
              color: "var(--obsidian-green)",
              border: "1px solid rgba(55,227,161,.3)",
              borderRadius: "999px",
              padding: "3px 10px",
              background: "rgba(55,227,161,.08)",
            }}
          >
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-green)" }}></span>
            GOVERNANCE ACTIVE
          </span>
        </div>
        <div>
          <div style={{ fontSize: "18px", fontWeight: 800, letterSpacing: "-.01em" }}>Human Control Layer</div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "4px" }}>
            Zero-trust human verification, approval policies, rollback authority, and audit logging.
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--obsidian-border)", paddingTop: "12px", display: "flex", flexDirection: "column", gap: "8px", fontSize: "11.5px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>POLICY GATE</span>
            <span style={{ color: "var(--obsidian-green)", fontWeight: 600 }}>Strict Confirmation Required</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>CURRENT OPERATOR</span>
            <span style={{ fontFamily: "'Geist Mono',monospace" }}>Kuldeep (Admin)</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>SHELL ACCESS</span>
            <span style={{ color: "var(--obsidian-green)", fontWeight: 600 }}>Sandboxed Routines Only (No Raw CLI)</span>
          </div>
        </div>
      </div>
    </div>
  );
};
