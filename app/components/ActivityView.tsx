"use client";

import React from "react";
import { ActivityFeedItem } from "./types";

interface ActivityViewProps {
  activities: ActivityFeedItem[];
}

export const ActivityView: React.FC<ActivityViewProps> = ({ activities }) => {
  return (
    <div
      className="ais-panel"
      style={{
        border: "1px solid var(--obsidian-border)",
        borderRadius: "26px",
        background: "linear-gradient(170deg, rgba(11,16,23,.95), rgba(2,3,4,.94))",
        padding: "22px 26px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "14px", marginBottom: "20px" }}>
        <div>
          <div
            className="ais-spec"
            style={{
              fontSize: "10px",
              letterSpacing: ".25em",
              fontWeight: 800,
              backgroundImage: "linear-gradient(90deg,#24D9FF,#FF4FD8)",
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            OPERATIONAL MEMORY
          </div>
          <div style={{ fontSize: "22px", fontWeight: 800, letterSpacing: "-.02em", marginTop: "2px" }}>Recent Activity Stream</div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "2px" }}>
            Audited ledger of automated agent actions, human changes, and incident lifecycle
          </div>
        </div>

        <div style={{ display: "flex", gap: "10px" }}>
          <div style={{ padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(36,217,255,.3)", background: "rgba(36,217,255,.08)", fontSize: "11px" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>TODAY: </span>
            <span style={{ color: "var(--obsidian-cyan)", fontWeight: 700 }}>41 AGENT ACTIONS</span>
          </div>
          <div style={{ padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(139,92,255,.3)", background: "rgba(139,92,255,.08)", fontSize: "11px" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>HUMAN: </span>
            <span style={{ color: "var(--obsidian-violet)", fontWeight: 700 }}>17 CHANGES</span>
          </div>
          <div style={{ padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(55,227,161,.3)", background: "rgba(55,227,161,.08)", fontSize: "11px" }}>
            <span style={{ color: "var(--obsidian-dim)" }}>RECOVERIES: </span>
            <span style={{ color: "var(--obsidian-green)", fontWeight: 700 }}>02 RESOLVED</span>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {activities.map((act) => (
          <div
            key={act.id}
            style={{
              display: "flex",
              gap: "14px",
              alignItems: "center",
              padding: "10px 14px",
              borderRadius: "14px",
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(120,170,220,0.08)",
            }}
          >
            <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", color: "var(--obsidian-muted)", width: "45px" }}>{act.time}</span>
            <span
              style={{
                border: "1px solid rgba(120,170,220,.25)",
                borderRadius: "6px",
                padding: "2px 8px",
                color: "var(--obsidian-cyan)",
                fontSize: "11px",
                fontWeight: 600,
              }}
            >
              {act.systemName}
            </span>
            <span style={{ fontSize: "12.5px", color: "var(--obsidian-white)", flex: 1 }}>{act.message}</span>
            <span
              style={{
                fontSize: "10px",
                color: act.tagColor || "var(--obsidian-violet)",
                border: "1px solid rgba(120,170,220,.2)",
                borderRadius: "999px",
                padding: "2px 8px",
              }}
            >
              {act.tag}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
