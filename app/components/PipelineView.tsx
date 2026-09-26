"use client";

import React from "react";
import { PipelineTask } from "./types";

interface PipelineViewProps {
  tasks: PipelineTask[];
}

export const PipelineView: React.FC<PipelineViewProps> = ({ tasks }) => {
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "14px", marginBottom: "18px" }}>
        <div>
          <div
            className="ais-spec"
            style={{
              fontSize: "10px",
              letterSpacing: ".25em",
              fontWeight: 800,
              backgroundImage: "linear-gradient(90deg,#24D9FF,#8B5CFF,#FF4FD8)",
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            WORK PIPELINE
          </div>
          <div style={{ fontSize: "22px", fontWeight: 800, letterSpacing: "-.02em", marginTop: "2px" }}>Execution Matrix</div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "2px" }}>
            Automated agent tasks, operational remediations, and multi-agent queue
          </div>
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(36,217,255,.3)", background: "rgba(36,217,255,.08)", color: "var(--obsidian-cyan)" }}>
            {tasks.length} ACTIVE TASKS
          </span>
          <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(255,196,91,.3)", background: "rgba(255,196,91,.08)", color: "var(--obsidian-amber)" }}>
            {tasks.filter((t) => t.status === "BLOCKED").length} BLOCKED
          </span>
          <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px", padding: "6px 12px", borderRadius: "10px", border: "1px solid rgba(55,227,161,.3)", background: "rgba(55,227,161,.08)", color: "var(--obsidian-green)" }}>
            68% AVG PROGRESS
          </span>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--obsidian-border)", color: "var(--obsidian-dim)", fontSize: "8.5px", letterSpacing: ".16em" }}>
              <th style={{ padding: "10px 14px" }}>TASK</th>
              <th style={{ padding: "10px 14px" }}>SYSTEM / PROJECT</th>
              <th style={{ padding: "10px 14px" }}>ASSIGNED TO</th>
              <th style={{ padding: "10px 14px" }}>PRIORITY</th>
              <th style={{ padding: "10px 14px" }}>STATUS</th>
              <th style={{ padding: "10px 14px" }}>PROGRESS</th>
              <th style={{ padding: "10px 14px" }}>DUE</th>
              <th style={{ padding: "10px 14px" }}>NEXT ACTION</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              let priorityColor = "var(--obsidian-cyan)";
              if (task.priority === "HIGH") priorityColor = "var(--obsidian-amber)";
              if (task.priority === "CRITICAL") priorityColor = "var(--obsidian-red)";

              let statusColor = "var(--obsidian-green)";
              if (task.status === "IN PROGRESS") statusColor = "var(--obsidian-cyan)";
              if (task.status === "BLOCKED") statusColor = "var(--obsidian-red)";

              return (
                <tr
                  key={task.id}
                  className="ais-row"
                  style={{
                    borderBottom: "1px solid rgba(120,170,220,0.08)",
                    background: task.status === "BLOCKED" ? "linear-gradient(90deg, rgba(255,95,120,0.08), transparent)" : task.priority === "HIGH" ? "linear-gradient(90deg, rgba(255,196,91,0.08), transparent)" : "transparent",
                  }}
                >
                  <td style={{ padding: "12px 14px", fontWeight: 700 }}>{task.title}</td>
                  <td style={{ padding: "12px 14px" }}>
                    <span style={{ border: "1px solid rgba(120,170,220,.25)", borderRadius: "6px", padding: "2px 7px", color: "var(--obsidian-cyan)", fontSize: "10.5px" }}>
                      {task.system}
                    </span>
                  </td>
                  <td style={{ padding: "12px 14px", color: "var(--obsidian-muted)" }}>{task.assignedTo}</td>
                  <td style={{ padding: "12px 14px" }}>
                    <span style={{ color: priorityColor, fontWeight: 700 }}>{task.priority}</span>
                  </td>
                  <td style={{ padding: "12px 14px" }}>
                    <span style={{ color: statusColor, fontWeight: 700 }}>{task.status}</span>
                  </td>
                  <td style={{ padding: "12px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{ flex: 1, width: "70px", height: "4px", background: "rgba(255,255,255,.1)", borderRadius: "2px", overflow: "hidden" }}>
                        <div style={{ width: `${task.progress}%`, height: "100%", background: task.status === "BLOCKED" ? "var(--obsidian-red)" : "linear-gradient(90deg, var(--obsidian-cyan), var(--obsidian-violet))" }} />
                      </div>
                      <span style={{ fontFamily: "'Geist Mono',monospace", fontSize: "11px" }}>{task.progress}%</span>
                    </div>
                  </td>
                  <td style={{ padding: "12px 14px", fontFamily: "'Geist Mono',monospace", color: "var(--obsidian-muted)" }}>{task.due}</td>
                  <td style={{ padding: "12px 14px", color: "var(--obsidian-muted)" }}>{task.nextAction}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
