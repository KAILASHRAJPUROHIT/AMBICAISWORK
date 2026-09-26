"use client";

import React, { useEffect, useState } from "react";
import { SystemItem } from "./types";

interface DiagnosisModalProps {
  isOpen: boolean;
  system: SystemItem | null;
  onClose: () => void;
  onRemediationComplete: (systemId: string) => void;
}

type ModalStage = "diagnosing" | "proposal" | "executing" | "complete";

export const DiagnosisModal: React.FC<DiagnosisModalProps> = ({
  isOpen,
  system,
  onClose,
  onRemediationComplete,
}) => {
  const [stage, setStage] = useState<ModalStage>("diagnosing");
  const [diagStep, setDiagStep] = useState(1);
  const [execStep, setExecStep] = useState(1);

  useEffect(() => {
    if (!isOpen || !system) {
      setStage("diagnosing");
      setDiagStep(1);
      setExecStep(1);
      return;
    }

    setStage("diagnosing");
    setDiagStep(1);

    const t1 = setTimeout(() => setDiagStep(2), 600);
    const t2 = setTimeout(() => setDiagStep(3), 1200);
    const t3 = setTimeout(() => setDiagStep(4), 1800);
    const t4 = setTimeout(() => setDiagStep(5), 2400);
    const t5 = setTimeout(() => setStage("proposal"), 3000);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      clearTimeout(t5);
    };
  }, [isOpen, system]);

  const handleApproveAndExecute = () => {
    setStage("executing");
    setExecStep(1);

    setTimeout(() => setExecStep(2), 650);
    setTimeout(() => setExecStep(3), 1300);
    setTimeout(() => setExecStep(4), 1950);
    setTimeout(() => setExecStep(5), 2600);
    setTimeout(() => {
      setStage("complete");
      if (system) {
        onRemediationComplete(system.id);
      }
    }, 3300);
  };

  if (!isOpen || !system) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.85)",
        backdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
    >
      <div
        style={{
          width: "90%",
          maxWidth: "680px",
          background: "linear-gradient(165deg, rgba(16,24,35,0.98), rgba(2,3,4,0.98))",
          border: "1px solid rgba(36,217,255,0.4)",
          borderRadius: "24px",
          padding: "28px",
          boxShadow: "0 0 50px rgba(36,217,255,0.2), 0 20px 40px rgba(0,0,0,0.8)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="ais-ok" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--obsidian-violet)" }}></span>
              <span style={{ fontSize: "9.5px", letterSpacing: ".2em", color: "var(--obsidian-violet)", fontWeight: 800 }}>
                AIS AGENT DIAGNOSTIC &amp; REMEDIATION ENGINE
              </span>
            </div>
            <div style={{ fontSize: "20px", fontWeight: 800, letterSpacing: "-.01em", marginTop: "4px" }}>
              {stage === "diagnosing" && `Analyzing ${system.name}...`}
              {stage === "proposal" && `Diagnosis Complete: ${system.name}`}
              {stage === "executing" && `Executing Remediation: ${system.name}`}
              {stage === "complete" && `Remediation Success: ${system.name}`}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "var(--obsidian-muted)", fontSize: "22px", cursor: "pointer", padding: "4px" }}
          >
            &times;
          </button>
        </div>

        {/* STAGE 1: DIAGNOSING */}
        {stage === "diagnosing" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", margin: "20px 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: diagStep > 1 ? "var(--obsidian-green)" : "var(--obsidian-muted)" }}>
              {diagStep > 1 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>◌</span>}
              <span>Checking {system.dependencies[0] || "primary subsystem"}...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: diagStep > 2 ? "var(--obsidian-green)" : diagStep === 2 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {diagStep > 2 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : diagStep === 2 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>◌</span> : <span>○</span>}
              <span>Inspecting telemetry baseline &amp; queue depth...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: diagStep > 3 ? "var(--obsidian-green)" : diagStep === 3 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {diagStep > 3 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : diagStep === 3 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>◌</span> : <span>○</span>}
              <span>Testing host socket reachability ({system.host})...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: diagStep > 4 ? "var(--obsidian-green)" : diagStep === 4 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {diagStep > 4 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : diagStep === 4 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>◌</span> : <span>○</span>}
              <span>Reading Windows event logs &amp; journal locks...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: diagStep === 5 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {diagStep === 5 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>◌</span> : <span>○</span>}
              <span>Correlating operational memory &amp; incident history...</span>
            </div>
          </div>
        )}

        {/* STAGE 2: PROPOSAL & HUMAN APPROVAL */}
        {stage === "proposal" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", margin: "16px 0" }}>
            <div style={{ border: "1px solid rgba(255,196,91,.4)", borderRadius: "16px", background: "rgba(255,196,91,.08)", padding: "14px" }}>
              <div style={{ fontSize: "8.5px", letterSpacing: ".18em", color: "var(--obsidian-amber)", fontWeight: 800 }}>ROOT CAUSE IDENTIFIED</div>
              <div style={{ fontSize: "13.5px", color: "#FFE0A0", fontWeight: 600, marginTop: "4px" }}>
                Orphaned lock handle identified in {system.dependencies[0] || "worker queue"}. Target host socket {system.host} reporting elevated latency.
              </div>
            </div>

            <div style={{ border: "1px solid var(--obsidian-border)", borderRadius: "16px", background: "rgba(255,255,255,.02)", padding: "14px" }}>
              <div style={{ fontSize: "8.5px", letterSpacing: ".18em", color: "var(--obsidian-cyan)", fontWeight: 800 }}>PROPOSED CONTROLLED ROUTINE</div>
              <ol style={{ margin: "8px 0 0 18px", padding: 0, fontSize: "12.5px", color: "#C6D2E2", lineHeight: 1.7 }}>
                <li>Pause incoming queue buffer to prevent backlog multiplication</li>
                <li>Clear orphaned lock files &amp; validate registry integrity</li>
                <li>Restart local service worker under supervisor governance</li>
                <li>Re-authenticate TCP socket connection to {system.host}</li>
                <li>Emit synthetic probe &amp; observe baseline for 60 seconds</li>
              </ol>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div style={{ border: "1px solid rgba(55,227,161,.25)", borderRadius: "12px", padding: "10px 14px", background: "rgba(55,227,161,.04)" }}>
                <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "var(--obsidian-green)", fontWeight: 700 }}>ASSESSED RISK</div>
                <div style={{ fontSize: "14px", fontWeight: 800, color: "var(--obsidian-green)", marginTop: "2px" }}>LOW (R1)</div>
              </div>
              <div style={{ border: "1px solid rgba(36,217,255,.25)", borderRadius: "12px", padding: "10px 14px", background: "rgba(36,217,255,.04)" }}>
                <div style={{ fontSize: "8px", letterSpacing: ".16em", color: "var(--obsidian-cyan)", fontWeight: 700 }}>EXPECTED INTERRUPTION</div>
                <div style={{ fontSize: "14px", fontWeight: 800, color: "var(--obsidian-cyan)", marginTop: "2px" }}>&lt; 8 SECONDS</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end", marginTop: "8px" }}>
              <button
                onClick={onClose}
                style={{ padding: "10px 18px", borderRadius: "12px", border: "1px solid var(--obsidian-border)", background: "transparent", color: "var(--obsidian-muted)", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}
              >
                CANCEL
              </button>
              <button
                onClick={handleApproveAndExecute}
                style={{
                  padding: "10px 22px",
                  borderRadius: "12px",
                  border: "1px solid rgba(55,227,161,.6)",
                  background: "linear-gradient(135deg, rgba(55,227,161,.3), rgba(36,217,255,.3))",
                  color: "#fff",
                  fontSize: "12px",
                  fontWeight: 800,
                  letterSpacing: ".08em",
                  cursor: "pointer",
                  boxShadow: "0 0 20px rgba(55,227,161,.3)",
                }}
              >
                APPROVE &amp; EXECUTE
              </button>
            </div>
          </div>
        )}

        {/* STAGE 3: EXECUTING */}
        {stage === "executing" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px", margin: "20px 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: execStep > 1 ? "var(--obsidian-green)" : "var(--obsidian-muted)" }}>
              {execStep > 1 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>⚙</span>}
              <span>01 Pausing queue buffer on {system.host}...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: execStep > 2 ? "var(--obsidian-green)" : execStep === 2 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {execStep > 2 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : execStep === 2 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>⚙</span> : <span>○</span>}
              <span>02 Purging orphaned locks and validating registry keys...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: execStep > 3 ? "var(--obsidian-green)" : execStep === 3 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {execStep > 3 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : execStep === 3 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>⚙</span> : <span>○</span>}
              <span>03 Restarting Windows service daemon via local supervisor...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: execStep > 4 ? "var(--obsidian-green)" : execStep === 4 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {execStep > 4 ? <span style={{ color: "var(--obsidian-green)" }}>✓</span> : execStep === 4 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>⚙</span> : <span>○</span>}
              <span>04 Reconnecting socket pipeline &amp; restoring buffer flow...</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "13px", color: execStep === 5 ? "var(--obsidian-muted)" : "var(--obsidian-dim)" }}>
              {execStep === 5 ? <span className="ais-blink" style={{ color: "var(--obsidian-cyan)" }}>⚙</span> : <span>○</span>}
              <span>05 Validating queue drain and latency baseline...</span>
            </div>
          </div>
        )}

        {/* STAGE 4: COMPLETE */}
        {stage === "complete" && (
          <div>
            <div style={{ border: "1px solid rgba(55,227,161,.4)", borderRadius: "18px", background: "rgba(55,227,161,.08)", padding: "18px", textAlign: "center", margin: "16px 0" }}>
              <div style={{ fontSize: "28px" }}>✓</div>
              <div style={{ fontSize: "16px", fontWeight: 800, color: "var(--obsidian-green)", marginTop: "6px" }}>SYSTEM HEALTH RESTORED</div>
              <div style={{ fontSize: "12px", color: "#C6D2E2", marginTop: "4px" }}>
                Service latency normalized below baseline (84ms). Controlled routine logged to operational audit memory.
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                onClick={onClose}
                style={{
                  padding: "10px 24px",
                  borderRadius: "12px",
                  border: "1px solid rgba(36,217,255,.5)",
                  background: "rgba(36,217,255,.2)",
                  color: "#BFF3FF",
                  fontWeight: 700,
                  fontSize: "12px",
                  cursor: "pointer",
                }}
              >
                RETURN TO DASHBOARD
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
