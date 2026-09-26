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

export const QuantumSystemMesh: React.FC<QuantumSystemMeshProps> = ({
  systems,
  selectedSystemId,
  onSelectSystem,
  fleetHealth = "93.4%",
  incidentsCount = "02",
  agentsReadyCount = "06",
}) => {
  const meshCardRef = useRef<HTMLDivElement>(null);

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
              {selectedSystemId === "qr-print" && <circle cx="280" cy="170" r="27" fill="none" stroke="#24D9FF" strokeWidth="1.5" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-ok" cx="280" cy="170" r="21" fill="rgba(55,227,161,.18)" />
              <circle cx="280" cy="170" r="14" fill="#031410" stroke="#37E3A1" strokeWidth="1.6" filter="url(#glowS)" />
              <text x="280" y="174" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill="#8CF2CB">QR</text>
              <text x="280" y="145" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill="#8CF2CB">QR Print</text>
            </g>

            {/* Gold Rate Monitor */}
            <g className="node-interactive" onClick={() => onSelectSystem("gold-rate")}>
              {selectedSystemId === "gold-rate" && <circle cx="375" cy="335" r="27" fill="none" stroke="#24D9FF" strokeWidth="1.5" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-ok" cx="375" cy="335" r="21" fill="rgba(55,227,161,.18)" style={{ animationDelay: "-1.4s" }} />
              <circle cx="375" cy="335" r="14" fill="#031410" stroke="#37E3A1" strokeWidth="1.6" filter="url(#glowS)" />
              <text x="375" y="339" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill="#8CF2CB">AU</text>
              <text x="375" y="364" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill="#8CF2CB">Gold Rate</text>
            </g>

            {/* Print Server (Warning) */}
            <g className="node-interactive" onClick={() => onSelectSystem("print-server")}>
              {selectedSystemId === "print-server" && <circle cx="185" cy="335" r="29" fill="none" stroke="#FFC45B" strokeWidth="1.8" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-warn" cx="185" cy="335" r="25" fill="rgba(255,196,91,.24)" />
              <circle cx="185" cy="335" r="15" fill="#1A1104" stroke="#FFC45B" strokeWidth="2.2" filter="url(#glowS)" />
              <text x="185" y="339" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="800" fill="#FFE0A0">PR</text>
              <text x="185" y="366" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="700" fill="#FFC45B">Print Server</text>
            </g>

            {/* Payment Notifier */}
            <g className="node-interactive" onClick={() => onSelectSystem("payment-notifier")}>
              {selectedSystemId === "payment-notifier" && <circle cx="432" cy="193" r="28" fill="none" stroke="#24D9FF" strokeWidth="1.5" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-ok" cx="432" cy="193" r="22" fill="rgba(36,217,255,.24)" style={{ animationDuration: "2s" }} />
              <circle cx="432" cy="193" r="14" fill="#031319" stroke="#24D9FF" strokeWidth="1.8" filter="url(#glowS)" />
              <text x="432" y="197" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill="#BFF3FF">PN</text>
              <text x="432" y="168" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill="#9AECFF">Payment</text>
            </g>

            {/* Order Tracker */}
            <g className="node-interactive" onClick={() => onSelectSystem("order-tracker")}>
              {selectedSystemId === "order-tracker" && <circle cx="280" cy="455" r="27" fill="none" stroke="#4D84FF" strokeWidth="1.5" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-ok" cx="280" cy="455" r="21" fill="rgba(77,132,255,.2)" style={{ animationDelay: "-2.6s" }} />
              <circle cx="280" cy="455" r="14" fill="#03091A" stroke="#4D84FF" strokeWidth="1.6" filter="url(#glowS)" />
              <text x="280" y="459" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="700" fill="#AEC6FF">OT</text>
              <text x="280" y="484" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill="#AEC6FF">Order Tracker</text>
            </g>

            {/* Catalogue Tool */}
            <g className="node-interactive" onClick={() => onSelectSystem("catalogue-tool")}>
              {selectedSystemId === "catalogue-tool" && <circle cx="72" cy="160" r="30" fill="none" stroke="#FF5F78" strokeWidth="1.8" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-fail" cx="72" cy="160" r="26" fill="rgba(255,95,120,.26)" />
              <circle cx="72" cy="160" r="15" fill="#1A0609" stroke="#FF5F78" strokeWidth="2.2" filter="url(#glowS)" />
              <text x="72" y="164" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="9" fontWeight="800" fill="#FFB3BF">CT</text>
              <text x="72" y="133" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="700" fill="#FF5F78">Catalogue</text>
              <text className="ais-blink" x="72" y="192" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="7.5" letterSpacing=".6" fontWeight="700" fill="#B9A5F5">AGENT ON IT</text>
            </g>

            {/* AMBIC MDM */}
            <g className="node-interactive" onClick={() => onSelectSystem("ambic-mdm")}>
              {selectedSystemId === "ambic-mdm" && <circle cx="450" cy="450" r="27" fill="none" stroke="#FF4FD8" strokeWidth="1.5" strokeDasharray="3 3" opacity=".9" />}
              <circle className="ais-ok" cx="450" cy="450" r="21" fill="rgba(255,79,216,.2)" style={{ animationDelay: "-3.3s" }} />
              <circle cx="450" cy="450" r="14" fill="#170618" stroke="#FF4FD8" strokeWidth="1.6" filter="url(#glowS)" />
              <text x="450" y="454" textAnchor="middle" fontFamily="'Geist Mono',monospace" fontSize="8.5" fontWeight="800" fill="#F9B8E8">MDM</text>
              <text x="450" y="479" textAnchor="middle" fontFamily="'Geist',sans-serif" fontSize="8.5" fontWeight="600" fill="#F3A8DF">AMBIC MDM</text>
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
            <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "16px", fontWeight: 700, color: "var(--obsidian-amber)", marginTop: "2px" }}>{incidentsCount}</div>
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
