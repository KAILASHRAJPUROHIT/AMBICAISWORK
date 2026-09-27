"use client";

import React from "react";
import { SystemItem } from "./types";

interface DiagnosisModalProps {
  isOpen: boolean;
  system: SystemItem | null;
  onClose: () => void;
}

/**
 * Agent diagnosis & remediation is NOT connected to anything yet.
 *
 * An earlier version of this modal played a scripted timeline (fake
 * "diagnosing", an invented root cause, fake per-step ticks) and its APPROVE
 * button then rewrote the selected system to "Healthy 98 / Remediated by AIS
 * Agent" and logged a fake AGENT FIX event. On a dashboard staff rely on, that
 * is worse than having no button. This version states plainly what is missing
 * and shows the intended governance flow as a plan, with execution disabled.
 */
const PLANNED_FLOW = [
  "Issue detected",
  "Agent diagnosis and root cause",
  "Proposed fix drawn from an allow-listed set of routines",
  "Risk assessment",
  "Human approval",
  "Execution with validation",
  "Rollback if validation fails",
  "Audit record",
];

export const DiagnosisModal: React.FC<DiagnosisModalProps> = ({ isOpen, system, onClose }) => {
  if (!isOpen || !system) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="diag-title"
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", backdropFilter: "blur(12px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}
    >
      <div
        style={{ width: "90%", maxWidth: "620px", background: "linear-gradient(165deg, rgba(16,24,35,0.98), rgba(2,3,4,0.98))", border: "1px solid rgba(255,196,91,0.4)", borderRadius: "24px", padding: "28px", boxShadow: "0 0 50px rgba(255,196,91,0.12), 0 20px 40px rgba(0,0,0,0.8)" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
          <div>
            <div style={{ fontSize: "9.5px", letterSpacing: ".2em", color: "var(--obsidian-amber)", fontWeight: 800 }}>
              AIS AGENT · NOT CONNECTED YET
            </div>
            <div id="diag-title" style={{ fontSize: "20px", fontWeight: 800, letterSpacing: "-.01em", marginTop: "4px" }}>
              Diagnose &amp; fix is not available for {system.name}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: "none", border: "none", color: "var(--obsidian-muted)", fontSize: "22px", cursor: "pointer", padding: "4px", minWidth: "44px", minHeight: "44px" }}
          >
            ×
          </button>
        </div>

        <p style={{ margin: "0 0 14px", fontSize: "13px", lineHeight: 1.6, color: "#C6D2E2" }}>
          No agent is wired to this system, so nothing can be diagnosed or changed from here. The controls that would
          make it safe — an allow-list of routines, approval, rollback and an audit log — are not built yet.
          This button will stay inert rather than pretend.
        </p>

        <div style={{ border: "1px solid var(--obsidian-border)", borderRadius: "16px", background: "rgba(255,255,255,.02)", padding: "14px 16px" }}>
          <div style={{ fontSize: "8.5px", letterSpacing: ".18em", color: "var(--obsidian-cyan)", fontWeight: 800 }}>PLANNED FLOW</div>
          <ol style={{ margin: "8px 0 0 18px", padding: 0, fontSize: "12.5px", color: "#C6D2E2", lineHeight: 1.7 }}>
            {PLANNED_FLOW.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>

        <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end", marginTop: "18px" }}>
          <button
            disabled
            aria-disabled="true"
            title="Unavailable until agent execution, approval and audit are built"
            style={{ padding: "10px 22px", borderRadius: "12px", border: "1px solid rgba(129,144,163,.35)", background: "rgba(129,144,163,.08)", color: "var(--obsidian-dim)", fontSize: "12px", fontWeight: 800, letterSpacing: ".08em", minHeight: "44px" }}
          >
            APPROVE &amp; EXECUTE — UNAVAILABLE
          </button>
          <button
            onClick={onClose}
            style={{ padding: "10px 24px", borderRadius: "12px", border: "1px solid rgba(36,217,255,.5)", background: "rgba(36,217,255,.2)", color: "#BFF3FF", fontWeight: 700, fontSize: "12px", cursor: "pointer", minHeight: "44px" }}
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  );
};
