"use client";

import React from "react";
import { SystemItem } from "./types";

interface SystemRegistryProps {
  systems: Record<string, SystemItem>;
  selectedSystemId: string;
  onSelectSystem: (id: string) => void;
}

export const SystemRegistry: React.FC<SystemRegistryProps> = ({
  systems,
  selectedSystemId,
  onSelectSystem,
}) => {
  return (
    <div
      className="ais-panel"
      style={{
        flex: 1,
        border: "1px solid var(--obsidian-border)",
        borderRadius: "24px",
        background: "linear-gradient(170deg, rgba(11,16,23,.95), rgba(2,3,4,.94))",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 18px",
          borderBottom: "1px solid var(--obsidian-border)",
        }}
      >
        <div
          className="ais-spec"
          style={{
            fontSize: "9.5px",
            letterSpacing: ".24em",
            fontWeight: 800,
            backgroundImage: "linear-gradient(90deg,#24D9FF,#FF4FD8,#24D9FF)",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          INFRASTRUCTURE REGISTRY
        </div>
        <div
          style={{
            fontFamily: "'Geist Mono',monospace",
            fontSize: "10px",
            color: "var(--obsidian-dim)",
            letterSpacing: ".06em",
          }}
        >
          {Object.keys(systems).length} SYSTEMS MONITORED · <span className="ais-blink" style={{ color: "var(--obsidian-green)" }}>● LIVE</span> · CLICK ANY ROW FOR DEEP TELEMETRY
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "160px 120px minmax(0,1fr) 110px 130px 100px",
          gap: "12px",
          padding: "8px 18px",
          borderBottom: "1px solid var(--obsidian-border)",
          fontSize: "8px",
          letterSpacing: ".16em",
          color: "var(--obsidian-dim)",
          fontWeight: 700,
        }}
      >
        <div>SYSTEM</div>
        <div>HEALTH</div>
        <div>LAST WORK DONE</div>
        <div>HOSTED ON</div>
        <div>BY · WHEN</div>
        <div>CLEAN UPTIME</div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", overflowY: "auto", maxHeight: "430px" }}>
        {Object.values(systems).map((sys) => {
          const isSelected = sys.id === selectedSystemId;
          let badgeClass = "ais-ok";
          let colorHex = "var(--obsidian-green)";
          let badgeColor = "#8CF2CB";
          let scoreBorder = "rgba(55,227,161,.32)";

          if (sys.statusTone === "amber") {
            badgeClass = "ais-warn";
            colorHex = "var(--obsidian-amber)";
            badgeColor = "#FFD98C";
            scoreBorder = "rgba(255,196,91,.4)";
          } else if (sys.statusTone === "red") {
            badgeClass = "ais-fail";
            colorHex = "var(--obsidian-red)";
            badgeColor = "#FFB3BF";
            scoreBorder = "rgba(255,95,120,.4)";
          } else if (sys.statusTone === "cyan") {
            colorHex = "var(--obsidian-cyan)";
            badgeColor = "#BFF3FF";
            scoreBorder = "rgba(36,217,255,.35)";
          }

          let rowBg = "transparent";
          let borderLeftStyle = "none";

          if (sys.statusTone === "amber") {
            rowBg = "linear-gradient(90deg, rgba(255,196,91,.12), rgba(255,196,91,.02) 55%, transparent)";
            borderLeftStyle = "2px solid #FFC45B";
          } else if (sys.statusTone === "red") {
            rowBg = "linear-gradient(90deg, rgba(255,95,120,.12), rgba(139,92,255,.05) 45%, transparent)";
            borderLeftStyle = "2px solid #FF5F78";
          }

          return (
            <div
              key={sys.id}
              className={`ais-row ${isSelected ? "active" : ""}`}
              onClick={() => onSelectSystem(sys.id)}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 120px minmax(0,1fr) 110px 130px 100px",
                gap: "12px",
                padding: "10px 18px",
                borderBottom: "1px solid rgba(120,170,220,.07)",
                alignItems: "center",
                background: rowBg,
                borderLeft: borderLeftStyle,
              }}
            >
              <span className="sh" />
              <div>
                <div style={{ fontSize: "12.5px", fontWeight: 700, display: "flex", alignItems: "center", gap: "6px" }}>
                  {sys.name}
                  <span
                    title={sys.source === "live" ? "Health status is live; host, metrics and history on this row are sample values" : "Sample data — not connected to real monitoring yet"}
                    style={{ fontSize: "7.5px", letterSpacing: ".14em", fontWeight: 800, padding: "1px 5px", borderRadius: "5px", border: sys.source === "live" ? "1px solid rgba(55,227,161,.5)" : "1px solid rgba(129,144,163,.45)", color: sys.source === "live" ? "var(--obsidian-green)" : "var(--obsidian-muted)" }}
                  >
                    {sys.source === "live" ? "HEALTH LIVE" : "SAMPLE"}
                  </span>
                </div>
                <div style={{ fontSize: "9.5px", color: colorHex, marginTop: "1px" }}>{sys.errorReason}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span
                  className={badgeClass}
                  style={{
                    width: "7px",
                    height: "7px",
                    borderRadius: "50%",
                    background: colorHex,
                    boxShadow: `0 0 9px ${colorHex}`,
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: "11px", color: badgeColor, fontWeight: 700 }}>{sys.health}</span>
                <span
                  style={{
                    fontFamily: "'Geist Mono',monospace",
                    fontSize: "9.5px",
                    color: colorHex,
                    border: `1px solid ${scoreBorder}`,
                    borderRadius: "5px",
                    padding: "0 5px",
                  }}
                >
                  {sys.source === "live" ? "—" : sys.healthScore}
                </span>
              </div>
              <div
                style={{
                  fontSize: "11.5px",
                  color: "#C6D2E2",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {sys.lastWorkDesc}
              </div>
              <div style={{ fontSize: "11px", color: "var(--obsidian-muted)" }}>{sys.host}</div>
              <div style={{ fontSize: "11px", color: "var(--obsidian-muted)" }}>
                {sys.lastWorkBy} · {sys.lastWorkTime.includes("·") ? sys.lastWorkTime.split("·")[1].trim() : sys.lastWorkTime}
              </div>
              <div style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11.5px", color: colorHex }}>
                {sys.cleanUptime}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
