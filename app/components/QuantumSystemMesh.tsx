"use client";

import React, { useRef } from "react";
import { SystemItem } from "./types";

interface QuantumSystemMeshProps {
  systems: Record<string, SystemItem>;
  selectedSystemId: string;
  onSelectSystem: (id: string) => void;
  fleetHealth?: string;
  incidentsCount?: string | number;
  agentsReadyCount?: string | number;
}


/** One row per statusTone -- drives every node's actual color/pulse/size, in
 * place of the fixed per-node colors this SVG shipped with (which never
 * looked at real health at all). "grey" (Disabled/Unregistered) gets no
 * pulse and reduced opacity: a system that isn't really there should not
 * pretend to be alive.
 */
const TONE_STYLE: Record<string, {
  haloClass: string; haloFill: string; nodeFill: string; nodeStroke: string; strokeW: number;
  r: number; haloR: number; textFill: string; labelFill: string; opacity: number;
}> = {
  green:  { haloClass: "ais-ok",   haloFill: "rgba(55,227,161,.18)",  nodeFill: "#031410", nodeStroke: "#37E3A1", strokeW: 1.6, r: 14, haloR: 21, textFill: "#8CF2CB", labelFill: "#8CF2CB", opacity: 1 },
  cyan:   { haloClass: "ais-ok",   haloFill: "rgba(36,217,255,.24)",  nodeFill: "#031319", nodeStroke: "#24D9FF", strokeW: 1.8, r: 14, haloR: 22, textFill: "#BFF3FF", labelFill: "#9AECFF", opacity: 1 },
  amber:  { haloClass: "ais-warn", haloFill: "rgba(255,196,91,.24)",  nodeFill: "#1A1104", nodeStroke: "#FFC45B", strokeW: 2.2, r: 15, haloR: 25, textFill: "#FFE0A0", labelFill: "#FFC45B", opacity: 1 },
  red:    { haloClass: "ais-fail", haloFill: "rgba(255,95,120,.26)",  nodeFill: "#1A0609", nodeStroke: "#FF5F78", strokeW: 2.2, r: 15, haloR: 26, textFill: "#FFB3BF", labelFill: "#FF5F78", opacity: 1 },
  violet: { haloClass: "ais-ok",   haloFill: "rgba(255,79,216,.2)",   nodeFill: "#170618", nodeStroke: "#FF4FD8", strokeW: 1.6, r: 14, haloR: 21, textFill: "#F9B8E8", labelFill: "#F3A8DF", opacity: 1 },
  grey:   { haloClass: "",         haloFill: "rgba(120,144,163,.10)", nodeFill: "#0B0F14", nodeStroke: "#5C6A7C", strokeW: 1.3, r: 14, haloR: 19, textFill: "#8190A3", labelFill: "#5C6A7C", opacity: 0.55 },
};
function toneOf(systems: Record<string, SystemItem>, id: string) {
  return TONE_STYLE[systems[id]?.statusTone ?? "grey"] ?? TONE_STYLE.grey;
}

export const QuantumSystemMesh: React.FC<QuantumSystemMeshProps> = ({
  systems,
  selectedSystemId,
  onSelectSystem,
  // Defaults used to be "93.4%" / "02" / "06" -- invented. Health scoring and agent
  // status are not built, so show a dash. Incidents is derived from live checks below.
  fleetHealth = "—",
  incidentsCount,
  agentsReadyCount = "—",
}) => {
  const meshCardRef = useRef<HTMLDivElement>(null);
  const liveIncidents = Object.values(systems)
    .filter((x) => x.source === "registry" && x.health !== "Healthy" && x.health !== "Active" && x.health !== "Unregistered")
    .length.toString().padStart(2, "0");

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!meshCardRef.current) return;
    const rect = meshCardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -5;
    const rotateY = ((x - centerX) / centerX) * 5;
    meshCardRef.current.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
  };

  const handleMouseLeave = () => {
    if (!meshCardRef.current) return;
    meshCardRef.current.style.transform = "rotateX(0deg) rotateY(0deg)";
  };

  return (
    <section className="mesh-container" style={{ flex: "0 0 570px", minWidth: "320px" }}>
      <div
        ref={meshCardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="ais-panel mesh-card"
        style={{
          border: "1px solid var(--obsidian-border)",
          borderRadius: "26px",
          background: "linear-gradient(165deg, rgba(11,16,23,0.96), rgba(2,3,4,0.95))",
          padding: "16px 18px",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div
              className="ais-spec"
              style={{
                fontSize: "9.5px",
                letterSpacing: ".24em",
                fontWeight: 800,
                backgroundImage: "linear-gradient(90deg, #24D9FF, #8B5CFF, #24D9FF)",
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
              }}
            >
              QUANTUM SYSTEM MESH
            </div>
            <div style={{ fontSize: "11px", color: "var(--obsidian-muted)", marginTop: "2px" }}>
              7 active systems bound to AIS Intelligence Core
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: "8px",
              fontSize: "8px",
              letterSpacing: ".1em",
              color: "var(--obsidian-dim)",
              fontWeight: 700,
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-green)", boxShadow: "0 0 6px var(--obsidian-green)" }}></span>OK
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-cyan)", boxShadow: "0 0 6px var(--obsidian-cyan)" }}></span>PROC
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-amber)", boxShadow: "0 0 6px var(--obsidian-amber)" }}></span>WARN
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-red)", boxShadow: "0 0 6px var(--obsidian-red)" }}></span>FAIL
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--obsidian-violet)", boxShadow: "0 0 6px var(--obsidian-violet)" }}></span>AGENT
            </span>
          </div>
        </div>

        <div style={{ position: "relative", width: "530px", height: "530px", margin: "8px auto 0" }}>
          {/* Radar Sweep */}
          <div
            className="ais-radar"
            style={{
              position: "absolute",
              left: "15px",
              top: "15px",
              width: "500px",
              height: "500px",
              borderRadius: "50%",
              background: "conic-gradient(from 0deg, rgba(36,217,255,.16), rgba(36,217,255,.03) 12%, transparent 26%)",
              pointerEvents: "none",
            }}
          />

          <svg width="530" height="530" viewBox="0 0 560 560" style={{ position: "relative", display: "block" }} role="img" aria-label="Interactive Quantum System Mesh">
            <defs>
              <radialGradient id="coreG" cx="50%" cy="50%">
                <stop offset="0%" stopColor="#FFFFFF" />
                <stop offset="28%" stopColor="#9AECFF" />
                <stop offset="65%" stopColor="#24D9FF" />
                <stop offset="100%" stopColor="#8B5CFF" />
              </radialGradient>
              <linearGradient id="rg1" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#24D9FF" />
                <stop offset="50%" stopColor="#8B5CFF" />
                <stop offset="100%" stopColor="#FF4FD8" />
              </linearGradient>
              <linearGradient id="rg2" x1="1" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#37E3A1" />
                <stop offset="100%" stopColor="#4D84FF" />
              </linearGradient>
              <filter id="glow" x="-70%" y="-70%" width="240%" height="240%">
                <feGaussianBlur stdDeviation="9" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="glowS" x="-90%" y="-90%" width="280%" height="280%">
                <feGaussianBlur stdDeviation="5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Core Ripples */}
            <circle className="ais-rip" cx="280" cy="280" r="62" fill="none" stroke="rgba(36,217,255,.45)" strokeWidth="1.2" />
            <circle className="ais-rip" cx="280" cy="280" r="62" fill="none" stroke="rgba(139,92,255,.38)" strokeWidth="1.2" style={{ animationDelay: "-1.5s" }} />
            <circle className="ais-rip" cx="280" cy="280" r="62" fill="none" stroke="rgba(255,79,216,.30)" strokeWidth="1.2" style={{ animationDelay: "-3s" }} />

            {/* Rotating Rings */}
            <circle className="ais-ring" cx="280" cy="280" r="110" fill="none" stroke="url(#rg1)" strokeWidth="1.2" strokeDasharray="6 10" opacity=".65" />
            <circle className="ais-ring2" cx="280" cy="280" r="175" fill="none" stroke="url(#rg2)" strokeWidth="1.1" strokeDasharray="4 14" opacity=".5" />
            <circle className="ais-ring3" cx="280" cy="280" r="240" fill="none" stroke="url(#rg1)" strokeWidth="1" strokeDasharray="2 17" opacity=".38" />

            {/* Connection Links */}
            <path className="ais-link" d="M280 280 L280 170" stroke={selectedSystemId === "qr-print" ? "#24D9FF" : "rgba(55,227,161,.6)"} strokeWidth={selectedSystemId === "qr-print" ? "2.4" : "1.4"} fill="none" strokeDasharray="4 7" />
            <path className="ais-link" d="M280 280 L375 335" stroke={selectedSystemId === "gold-rate" ? "#24D9FF" : "rgba(55,227,161,.6)"} strokeWidth={selectedSystemId === "gold-rate" ? "2.4" : "1.4"} fill="none" strokeDasharray="4 7" />
            <path className="ais-link" d="M280 280 L185 335" stroke={selectedSystemId === "print-server" ? "#FFC45B" : "rgba(255,196,91,.88)"} strokeWidth={selectedSystemId === "print-server" ? "2.6" : "2.2"} fill="none" strokeDasharray="4 6" />
            <path className="ais-link" d="M280 280 L432 193" stroke={selectedSystemId === "payment-notifier" ? "#24D9FF" : "rgba(36,217,255,.8)"} strokeWidth={selectedSystemId === "payment-notifier" ? "2.4" : "1.8"} fill="none" strokeDasharray="4 6" />
            <path className="ais-link" d="M280 280 L280 455" stroke={selectedSystemId === "order-tracker" ? "#4D84FF" : "rgba(77,132,255,.6)"} strokeWidth={selectedSystemId === "order-tracker" ? "2.4" : "1.4"} fill="none" strokeDasharray="4 7" />
            <path className="ais-link" d="M280 280 L72 160" stroke={selectedSystemId === "catalogue-tool" ? "#FF5F78" : "rgba(139,92,255,.95)"} strokeWidth={selectedSystemId === "catalogue-tool" ? "2.6" : "2.2"} fill="none" strokeDasharray="7 5" />
            <path className="ais-link" d="M280 280 L450 450" stroke={selectedSystemId === "ambic-mdm" ? "#FF4FD8" : "rgba(255,79,216,.55)"} strokeWidth={selectedSystemId === "ambic-mdm" ? "2.4" : "1.4"} fill="none" strokeDasharray="4 7" />

            {/* Packets */}
            <circle className="ais-pkt" r="2.8" fill="#37E3A1" style={{ offsetPath: "path('M280 280 L280 170')" }} />
            <circle className="ais-pkt" r="2.4" fill="#8CF2CB" style={{ offsetPath: "path('M280 170 L280 280')", animationDuration: "3.8s", animationDelay: "-1.2s" }} />
            <circle className="ais-pkt" r="3.0" fill="#24D9FF" style={{ offsetPath: "path('M280 280 L432 193')", animationDuration: "1.9s" }} />
            <circle className="ais-pkt" r="2.4" fill="#9AECFF" style={{ offsetPath: "path('M432 193 L280 280')", animationDuration: "2.4s", animationDelay: "-.8s" }} />
            <circle className="ais-pkt" r="3.2" fill="#8B5CFF" style={{ offsetPath: "path('M280 280 L72 160')", animationDuration: "1.5s" }} />
            <circle className="ais-pkt" r="3.2" fill="#B9A5F5" style={{ offsetPath: "path('M280 280 L72 160')", animationDuration: "1.5s", animationDelay: "-.75s" }} />
            <circle className="ais-pkt" r="2.6" fill="#FF4FD8" style={{ offsetPath: "path('M72 160 L280 280')", animationDuration: "2.2s", animationDelay: "-1.1s" }} />
            <circle className="ais-pkt" r="3.0" fill="#FFC45B" style={{ offsetPath: "path('M280 280 L185 335')", animationDuration: "2.2s" }} />
            <circle className="ais-pkt" r="2.5" fill="#4D84FF" style={{ offsetPath: "path('M280 280 L280 455')", animationDuration: "3.2s", animationDelay: "-1.6s" }} />
            <circle className="ais-pkt" r="2.5" fill="#FF4FD8" style={{ offsetPath: "path('M280 280 L450 450')", animationDuration: "3.4s", animationDelay: "-2.1s" }} />

            {/* AIS Intelligence Core */}
            <circle className="ais-coreg" cx="280" cy="280" r="66" fill="rgba(36,217,255,.12)" />
            <circle cx="280" cy="280" r="48" fill="rgba(3,6,12,.94)" stroke="url(#rg1)" strokeWidth="1.6" />
            <circle cx="280" cy="280" r="29" fill="url(#coreG)" filter="url(#glow)" opacity=".98" />
            <text x="280" y="276" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="12.5" fontWeight="800" fill="#04060A">AIS</text>
            <text x="280" y="288" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="5.8" letterSpacing="1.2" fontWeight="700" fill="rgba(4,6,10,.78)">CORE</text>

            {/* Clickable System Nodes */}
            {/* QR Print Server */}
            <g className="node-interactive" onClick={() => onSelectSystem("qr-print")}>
              {selectedSystemId === "qr-print" && <circle cx="280" cy="170" r="27" fill="none" stroke={toneOf(systems, "qr-print").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "qr-print").haloClass} cx="280" cy="170" r={toneOf(systems, "qr-print").haloR} fill={toneOf(systems, "qr-print").haloFill} opacity={toneOf(systems, "qr-print").opacity} />
              <circle cx="280" cy="170" r={toneOf(systems, "qr-print").r} fill={toneOf(systems, "qr-print").nodeFill} stroke={toneOf(systems, "qr-print").nodeStroke} strokeWidth={toneOf(systems, "qr-print").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "qr-print").opacity} />
              <text x="280" y="174" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "qr-print").textFill} opacity={toneOf(systems, "qr-print").opacity}>QR</text>
              <text x="280" y="145" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "qr-print").labelFill} opacity={toneOf(systems, "qr-print").opacity}>QR Print</text>
            </g>

            {/* Gold Rate Monitor */}
            <g className="node-interactive" onClick={() => onSelectSystem("gold-rate")}>
              {selectedSystemId === "gold-rate" && <circle cx="375" cy="335" r="27" fill="none" stroke={toneOf(systems, "gold-rate").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "gold-rate").haloClass} cx="375" cy="335" r={toneOf(systems, "gold-rate").haloR} fill={toneOf(systems, "gold-rate").haloFill} opacity={toneOf(systems, "gold-rate").opacity} />
              <circle cx="375" cy="335" r={toneOf(systems, "gold-rate").r} fill={toneOf(systems, "gold-rate").nodeFill} stroke={toneOf(systems, "gold-rate").nodeStroke} strokeWidth={toneOf(systems, "gold-rate").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "gold-rate").opacity} />
              <text x="375" y="339" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "gold-rate").textFill} opacity={toneOf(systems, "gold-rate").opacity}>AU</text>
              <text x="375" y="364" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "gold-rate").labelFill} opacity={toneOf(systems, "gold-rate").opacity}>Gold Rate</text>
            </g>

            {/* Print Server (Warning) */}
            <g className="node-interactive" onClick={() => onSelectSystem("print-server")}>
              {selectedSystemId === "print-server" && <circle cx="185" cy="335" r="29" fill="none" stroke={toneOf(systems, "print-server").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "print-server").haloClass} cx="185" cy="335" r={toneOf(systems, "print-server").haloR} fill={toneOf(systems, "print-server").haloFill} opacity={toneOf(systems, "print-server").opacity} />
              <circle cx="185" cy="335" r={toneOf(systems, "print-server").r} fill={toneOf(systems, "print-server").nodeFill} stroke={toneOf(systems, "print-server").nodeStroke} strokeWidth={toneOf(systems, "print-server").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "print-server").opacity} />
              <text x="185" y="339" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "print-server").textFill} opacity={toneOf(systems, "print-server").opacity}>PR</text>
              <text x="185" y="366" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "print-server").labelFill} opacity={toneOf(systems, "print-server").opacity}>Print Server</text>
            </g>

            {/* Payment Notifier */}
            <g className="node-interactive" onClick={() => onSelectSystem("payment-notifier")}>
              {selectedSystemId === "payment-notifier" && <circle cx="432" cy="193" r="28" fill="none" stroke={toneOf(systems, "payment-notifier").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "payment-notifier").haloClass} cx="432" cy="193" r={toneOf(systems, "payment-notifier").haloR} fill={toneOf(systems, "payment-notifier").haloFill} opacity={toneOf(systems, "payment-notifier").opacity} />
              <circle cx="432" cy="193" r={toneOf(systems, "payment-notifier").r} fill={toneOf(systems, "payment-notifier").nodeFill} stroke={toneOf(systems, "payment-notifier").nodeStroke} strokeWidth={toneOf(systems, "payment-notifier").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "payment-notifier").opacity} />
              <text x="432" y="197" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "payment-notifier").textFill} opacity={toneOf(systems, "payment-notifier").opacity}>PN</text>
              <text x="432" y="168" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "payment-notifier").labelFill} opacity={toneOf(systems, "payment-notifier").opacity}>Payment</text>
            </g>

            {/* Order Tracker */}
            <g className="node-interactive" onClick={() => onSelectSystem("order-tracker")}>
              {selectedSystemId === "order-tracker" && <circle cx="280" cy="455" r="27" fill="none" stroke={toneOf(systems, "order-tracker").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "order-tracker").haloClass} cx="280" cy="455" r={toneOf(systems, "order-tracker").haloR} fill={toneOf(systems, "order-tracker").haloFill} opacity={toneOf(systems, "order-tracker").opacity} />
              <circle cx="280" cy="455" r={toneOf(systems, "order-tracker").r} fill={toneOf(systems, "order-tracker").nodeFill} stroke={toneOf(systems, "order-tracker").nodeStroke} strokeWidth={toneOf(systems, "order-tracker").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "order-tracker").opacity} />
              <text x="280" y="459" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "order-tracker").textFill} opacity={toneOf(systems, "order-tracker").opacity}>OT</text>
              <text x="280" y="484" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "order-tracker").labelFill} opacity={toneOf(systems, "order-tracker").opacity}>Order Tracker</text>
            </g>

            {/* Catalogue Tool */}
            <g className="node-interactive" onClick={() => onSelectSystem("catalogue-tool")}>
              {selectedSystemId === "catalogue-tool" && <circle cx="72" cy="160" r="30" fill="none" stroke={toneOf(systems, "catalogue-tool").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "catalogue-tool").haloClass} cx="72" cy="160" r={toneOf(systems, "catalogue-tool").haloR} fill={toneOf(systems, "catalogue-tool").haloFill} opacity={toneOf(systems, "catalogue-tool").opacity} />
              <circle cx="72" cy="160" r={toneOf(systems, "catalogue-tool").r} fill={toneOf(systems, "catalogue-tool").nodeFill} stroke={toneOf(systems, "catalogue-tool").nodeStroke} strokeWidth={toneOf(systems, "catalogue-tool").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "catalogue-tool").opacity} />
              <text x="72" y="164" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill={toneOf(systems, "catalogue-tool").textFill} opacity={toneOf(systems, "catalogue-tool").opacity}>CT</text>
              <text x="72" y="133" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "catalogue-tool").labelFill} opacity={toneOf(systems, "catalogue-tool").opacity}>Catalogue</text>
            </g>

            {/* AMBIC MDM */}
            <g className="node-interactive" onClick={() => onSelectSystem("ambic-mdm")}>
              {selectedSystemId === "ambic-mdm" && <circle cx="450" cy="450" r="27" fill="none" stroke={toneOf(systems, "ambic-mdm").nodeStroke} strokeWidth="1.6" strokeDasharray="3 3" opacity=".9" />}
              <circle className={toneOf(systems, "ambic-mdm").haloClass} cx="450" cy="450" r={toneOf(systems, "ambic-mdm").haloR} fill={toneOf(systems, "ambic-mdm").haloFill} opacity={toneOf(systems, "ambic-mdm").opacity} />
              <circle cx="450" cy="450" r={toneOf(systems, "ambic-mdm").r} fill={toneOf(systems, "ambic-mdm").nodeFill} stroke={toneOf(systems, "ambic-mdm").nodeStroke} strokeWidth={toneOf(systems, "ambic-mdm").strokeW} filter="url(#glowS)" opacity={toneOf(systems, "ambic-mdm").opacity} />
              <text x="450" y="454" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="8.5" fontWeight="700" fill={toneOf(systems, "ambic-mdm").textFill} opacity={toneOf(systems, "ambic-mdm").opacity}>MDM</text>
              <text x="450" y="479" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill={toneOf(systems, "ambic-mdm").labelFill} opacity={toneOf(systems, "ambic-mdm").opacity}>AMBIC MDM</text>
            </g>
          </svg>
        </div>

        {/* Bottom Metric Gauges */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px", marginTop: "10px", paddingTop: "12px", borderTop: "1px solid var(--obsidian-border)" }}>
          <div style={{ background: "rgba(255,255,255,.02)", borderRadius: "12px", padding: "8px 10px", border: "1px solid rgba(120,170,220,.08)" }}>
            <div style={{ fontSize: "7.5px", letterSpacing: ".16em", color: "var(--obsidian-dim)", fontWeight: 700 }}>FLEET HEALTH</div>
            <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "16px", fontWeight: 700, color: "var(--obsidian-green)", marginTop: "2px" }}>{fleetHealth}</div>
          </div>
          <div style={{ background: "rgba(255,255,255,.02)", borderRadius: "12px", padding: "8px 10px", border: "1px solid rgba(120,170,220,.08)" }}>
            <div style={{ fontSize: "7.5px", letterSpacing: ".16em", color: "var(--obsidian-dim)", fontWeight: 700 }}>INCIDENTS</div>
            <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "16px", fontWeight: 700, color: "var(--obsidian-amber)", marginTop: "2px" }}>{incidentsCount ?? liveIncidents}</div>
          </div>
          <div style={{ background: "rgba(255,255,255,.02)", borderRadius: "12px", padding: "8px 10px", border: "1px solid rgba(120,170,220,.08)" }}>
            <div style={{ fontSize: "7.5px", letterSpacing: ".16em", color: "var(--obsidian-dim)", fontWeight: 700 }}>AGENTS READY</div>
            <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "16px", fontWeight: 700, color: "var(--obsidian-cyan)", marginTop: "2px" }}>{agentsReadyCount}</div>
          </div>
        </div>
      </div>
    </section>
  );
};
