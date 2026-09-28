"use client";

import React, { useState, useEffect, useMemo } from "react";

export interface WorkTask {
  id: string;
  staff_id: string;
  staff_name: string;
  day: string;
  category: string;
  title: string;
  description: string;
  time_spent: string;
  time_hours: number;
  frequency: string;
  current_tool: string;
  pain_points: string;
  ais_target: string;
  priority: string;
  created_at: string;
  updated_at: string;
}

const PRIMARY_STAFF = [
  { id: "br_parmar", en: "B. R. Parmar", hi: "बी. आर. परमार" },
  { id: "bharat_singh", en: "Bharat Singh", hi: "भरत सिंह" },
  { id: "govind_singh", en: "Govind Singh", hi: "गोविन्द सिंह" },
  { id: "harish_singh", en: "Harish Singh", hi: "हरीश सिंह" },
  { id: "hitesh_kumar", en: "Hitesh Kumar", hi: "हितेश कुमार" },
];

const ALL_STAFF_MASTER = [
  ...PRIMARY_STAFF,
  { id: "keshar_singh", en: "Keshar Singh", hi: "केशर सिंह" },
  { id: "kuldeep_singh", en: "Kuldeep Singh", hi: "कुलदीप सिंह" },
  { id: "manish_mali", en: "Manish Mali", hi: "मनीष माली" },
  { id: "samar_jana", en: "Samar Jana (Kochi)", hi: "समर जाना (कोच्चि)" },
  { id: "shambhunath", en: "Shambhunath", hi: "शंभूनाथ" },
  { id: "sukhdev_singh", en: "Sukhdev Singh", hi: "सुखदेव सिंह" },
  { id: "vane_singh", en: "Vane Singh", hi: "वने सिंह" },
];

const DAYS = [
  { id: "Monday", en: "Monday", hi: "सोमवार" },
  { id: "Tuesday", en: "Tuesday", hi: "मंगलवार" },
  { id: "Wednesday", en: "Wednesday", hi: "बुधवार" },
  { id: "Thursday", en: "Thursday", hi: "गुरुवार" },
  { id: "Friday", en: "Friday", hi: "शुक्रवार" },
  { id: "Saturday", en: "Saturday", hi: "शनिवार" },
  { id: "Sunday", en: "Sunday", hi: "रविवार" },
  { id: "all", en: "All Week", hi: "पूरा सप्ताह" },
];

const CATEGORIES: Record<string, { en: string; hi: string; color: string }> = {
  sales: { en: "Sales & Customer Handling", hi: "बिक्री एवं ग्राहक सेवा", color: "var(--obsidian-cyan)" },
  stock: { en: "Stock, Barcoding & Tagging", hi: "स्टॉक, बारकोडिंग और टैगिंग", color: "var(--obsidian-green)" },
  karigar: { en: "Karigar Order & Follow-up", hi: "कारीगर आर्डर व फॉलो-अप", color: "var(--obsidian-amber)" },
  billing: { en: "Billing & Accounts", hi: "बिलिंग व हिसाब-किताब", color: "var(--obsidian-violet)" },
  old_gold: { en: "Scheme & Old Gold (URD)", hi: "स्कीम व पुराना सोना (URD)", color: "var(--obsidian-red)" },
  upkeep: { en: "Store Upkeep & Opening/Closing", hi: "स्टोर व्यवस्था", color: "var(--obsidian-muted)" },
  other: { en: "Other Daily Duties", hi: "अन्य दैनिक कार्य", color: "#4D84FF" },
};

const AIS_BADGES: Record<string, { label_en: string; label_hi: string; color: string; border: string; bg: string }> = {
  automate_full: {
    label_en: "Full AIS Automation",
    label_hi: "पूर्ण स्वचालित",
    color: "var(--obsidian-green)",
    border: "rgba(55,227,161,.35)",
    bg: "rgba(55,227,161,.1)",
  },
  automate_ai: {
    label_en: "AI Assisted Workflow",
    label_hi: "एआई सहायता प्राप्त",
    color: "var(--obsidian-cyan)",
    border: "rgba(36,217,255,.35)",
    bg: "rgba(36,217,255,.1)",
  },
  tablet_kiosk: {
    label_en: "Tablet Kiosk Entry",
    label_hi: "टैबलेट कियोस्क सीधा दाखिला",
    color: "var(--obsidian-amber)",
    border: "rgba(255,196,91,.35)",
    bg: "rgba(255,196,91,.1)",
  },
  keep_manual: {
    label_en: "Keep Manual",
    label_hi: "भौतिक / मैन्युअल",
    color: "var(--obsidian-muted)",
    border: "rgba(120,170,220,.2)",
    bg: "rgba(120,170,220,.06)",
  },
  under_review: {
    label_en: "Under Review",
    label_hi: "समीक्षाधीन",
    color: "var(--obsidian-violet)",
    border: "rgba(139,92,255,.35)",
    bg: "rgba(139,92,255,.1)",
  },
};

const WorkTrackerViewComponent: React.FC = () => {
  const [tasks, setTasks] = useState<WorkTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStaff, setSelectedStaff] = useState<string>("all");
  const [selectedDay, setSelectedDay] = useState<string>("Monday");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [filterAis, setFilterAis] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Modals state
  const [modalOpen, setModalOpen] = useState(false);
  const [editTask, setEditTask] = useState<WorkTask | null>(null);
  const [duplicateModalOpen, setDuplicateModalOpen] = useState(false);
  const [duplicatingTaskId, setDuplicatingTaskId] = useState<string | null>(null);
  const [selectedDupDays, setSelectedDupDays] = useState<string[]>([]);
  const [blueprintModalOpen, setBlueprintModalOpen] = useState(false);

  // Form inputs
  const [formStaffId, setFormStaffId] = useState("br_parmar");
  const [formDay, setFormDay] = useState("Monday");
  const [formCategory, setFormCategory] = useState("sales");
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formTimeSpent, setFormTimeSpent] = useState("1 Hour / 1 घंटा");
  const [formFrequency, setFormFrequency] = useState("Daily / प्रतिदिन");
  const [formCurrentTool, setFormCurrentTool] = useState("Notebook / Register / खाता-बही / रजिस्टर");
  const [formPainPoints, setFormPainPoints] = useState("");
  const [formAisTarget, setFormAisTarget] = useState("automate_full");
  const [formPriority, setFormPriority] = useState("Medium / मध्यम");
  const [saving, setSaving] = useState(false);

  // Fetch tasks
  const loadTasks = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/work-tracker");
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
      }
    } catch (err) {
      console.error("Error loading work tracker tasks:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  // Filter tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      if (selectedStaff !== "all" && t.staff_id !== selectedStaff) return false;
      if (selectedDay !== "all" && t.day !== selectedDay) return false;
      if (filterCategory !== "all" && t.category !== filterCategory) return false;
      if (filterAis !== "all" && t.ais_target !== filterAis) return false;
      if (searchQuery) {
        const text = `${t.title} ${t.description || ""} ${t.pain_points || ""} ${t.current_tool || ""} ${t.staff_name || ""}`.toLowerCase();
        if (!text.includes(searchQuery.toLowerCase())) return false;
      }
      return true;
    });
  }, [tasks, selectedStaff, selectedDay, filterCategory, filterAis, searchQuery]);

  // KPIs
  const kpis = useMemo(() => {
    const total = tasks.length;
    let hours = 0;
    let autoCount = 0;
    const staffSet = new Set<string>();

    tasks.forEach((t) => {
      hours += Number(t.time_hours || 0.5);
      if (t.staff_id) staffSet.add(t.staff_id);
      if (t.ais_target === "automate_full" || t.ais_target === "automate_ai" || t.ais_target === "tablet_kiosk") {
        autoCount++;
      }
    });

    const percent = total > 0 ? Math.round((autoCount / total) * 100) : 0;
    return { total, hours: hours.toFixed(1), percent, activeStaff: staffSet.size || 5 };
  }, [tasks]);

  // Day counts
  const dayCounts = useMemo(() => {
    const counts: Record<string, number> = {
      Monday: 0,
      Tuesday: 0,
      Wednesday: 0,
      Thursday: 0,
      Friday: 0,
      Saturday: 0,
      Sunday: 0,
      all: 0,
    };
    tasks.forEach((t) => {
      if (selectedStaff === "all" || t.staff_id === selectedStaff) {
        if (counts[t.day] !== undefined) counts[t.day]++;
        counts.all++;
      }
    });
    return counts;
  }, [tasks, selectedStaff]);

  // Open modal for new
  const openNewModal = () => {
    setEditTask(null);
    setFormStaffId(selectedStaff !== "all" ? selectedStaff : "br_parmar");
    setFormDay(selectedDay !== "all" ? selectedDay : "Monday");
    setFormCategory("sales");
    setFormTitle("");
    setFormDescription("");
    setFormTimeSpent("1 Hour / 1 घंटा");
    setFormFrequency("Daily / प्रतिदिन");
    setFormCurrentTool("Notebook / Register / खाता-बही / रजिस्टर");
    setFormPainPoints("");
    setFormAisTarget("automate_full");
    setFormPriority("Medium / मध्यम");
    setModalOpen(true);
  };

  // Open modal for edit
  const openEditModal = (task: WorkTask) => {
    setEditTask(task);
    setFormStaffId(task.staff_id);
    setFormDay(task.day);
    setFormCategory(task.category);
    setFormTitle(task.title);
    setFormDescription(task.description || "");
    setFormTimeSpent(task.time_spent);
    setFormFrequency(task.frequency);
    setFormCurrentTool(task.current_tool);
    setFormPainPoints(task.pain_points || "");
    setFormAisTarget(task.ais_target);
    setFormPriority(task.priority || "Medium / मध्यम");
    setModalOpen(true);
  };

  // Handle Save
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim()) return;

    setSaving(true);
    const staffObj = ALL_STAFF_MASTER.find((s) => s.id === formStaffId);
    const staffName = staffObj ? `${staffObj.en} / ${staffObj.hi}` : formStaffId;

    const payload = {
      staff_id: formStaffId,
      staff_name: staffName,
      day: formDay,
      category: formCategory,
      priority: formPriority,
      title: formTitle.trim(),
      description: formDescription.trim(),
      time_spent: formTimeSpent,
      frequency: formFrequency,
      current_tool: formCurrentTool,
      pain_points: formPainPoints.trim(),
      ais_target: formAisTarget,
    };

    try {
      if (editTask) {
        const res = await fetch("/api/work-tracker", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, id: editTask.id }),
        });
        if (res.ok) {
          setModalOpen(false);
          await loadTasks();
        }
      } else {
        const res = await fetch("/api/work-tracker", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          setModalOpen(false);
          await loadTasks();
        }
      }
    } catch (err) {
      console.error("Save error:", err);
    } finally {
      setSaving(false);
    }
  };

  // Delete
  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this work item? / क्या आप यह कार्य हटाना चाहते हैं?")) return;
    try {
      const res = await fetch(`/api/work-tracker?id=${id}`, { method: "DELETE" });
      if (res.ok) {
        await loadTasks();
      }
    } catch (err) {
      console.error("Delete error:", err);
    }
  };

  // Open Duplicate Modal
  const openDuplicate = (task: WorkTask) => {
    setDuplicatingTaskId(task.id);
    setSelectedDupDays([]);
    setDuplicateModalOpen(true);
  };

  const handleDuplicate = async () => {
    if (!duplicatingTaskId || !selectedDupDays.length) return;
    try {
      const res = await fetch("/api/work-tracker/duplicate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: duplicatingTaskId, target_days: selectedDupDays }),
      });
      if (res.ok) {
        setDuplicateModalOpen(false);
        await loadTasks();
      }
    } catch (err) {
      console.error("Duplicate error:", err);
    }
  };

  // Export CSV
  const handleExportCsv = () => {
    window.location.href = "http://localhost:8085/api/export-csv";
  };

  const sourceTaskForDup = tasks.find((t) => t.id === duplicatingTaskId);

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
      {/* Top Banner / Access Badge */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "18px",
          paddingBottom: "16px",
          borderBottom: "1px solid var(--obsidian-border)",
        }}
      >
        <div>
          <div
            className="ais-spec"
            style={{
              fontSize: "10px",
              letterSpacing: ".25em",
              fontWeight: 800,
              backgroundImage: "linear-gradient(90deg, #FFC45B, #24D9FF, #8B5CFF)",
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            ARADHANA WORK TRACKER &amp; AIS BLUEPRINT
          </div>
          <div style={{ fontSize: "22px", fontWeight: 800, letterSpacing: "-.02em", marginTop: "2px" }}>
            Staff Operations Matrix <span style={{ fontSize: "15px", color: "var(--obsidian-muted)" }}>/ दैनिक कार्य ट्रैकर</span>
          </div>
          <div style={{ fontSize: "12px", color: "var(--obsidian-muted)", marginTop: "2px" }}>
            Identify manual bottlenecks, automate routine store duties, and prepare workflows for AIS
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <div
            style={{
              padding: "6px 14px",
              borderRadius: "10px",
              border: "1px solid rgba(255,196,91,.35)",
              background: "rgba(255,196,91,.08)",
              fontSize: "11px",
              color: "var(--obsidian-amber)",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span>🔒</span>
            <span>Private: <strong>info@aradhanajewellers.com</strong></span>
          </div>

          <button
            onClick={() => setBlueprintModalOpen(true)}
            style={{
              padding: "7px 14px",
              borderRadius: "10px",
              border: "1px solid rgba(36,217,255,.35)",
              background: "rgba(36,217,255,.08)",
              color: "var(--obsidian-cyan)",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            📊 AIS Insights / सारांश
          </button>

          <button
            onClick={handleExportCsv}
            style={{
              padding: "7px 14px",
              borderRadius: "10px",
              border: "1px solid rgba(55,227,161,.35)",
              background: "linear-gradient(135deg, rgba(55,227,161,.2), rgba(36,217,255,.2))",
              color: "var(--obsidian-green)",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            📥 Export CSV / डाउनलोड
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div
          className="ais-panel slow"
          style={{
            border: "1px solid rgba(36,217,255,.25)",
            borderRadius: "16px",
            background: "linear-gradient(160deg, rgba(36,217,255,.08), rgba(5,7,10,.95) 70%)",
            padding: "14px 18px",
          }}
        >
          <div style={{ fontSize: "9px", letterSpacing: ".18em", color: "var(--obsidian-cyan)", fontWeight: 700 }}>
            TOTAL TASKS / कुल कार्य
          </div>
          <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "28px", fontWeight: 800, marginTop: "4px", color: "#BFF3FF" }}>
            {kpis.total}
          </div>
          <div style={{ fontSize: "10px", color: "var(--obsidian-dim)", marginTop: "2px" }}>Across all 7 showroom days</div>
        </div>

        <div
          className="ais-panel slow"
          style={{
            border: "1px solid rgba(255,196,91,.25)",
            borderRadius: "16px",
            background: "linear-gradient(160deg, rgba(255,196,91,.08), rgba(5,7,10,.95) 70%)",
            padding: "14px 18px",
          }}
        >
          <div style={{ fontSize: "9px", letterSpacing: ".18em", color: "var(--obsidian-amber)", fontWeight: 700 }}>
            WEEKLY TIME / साप्ताहिक समय
          </div>
          <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "28px", fontWeight: 800, marginTop: "4px", color: "var(--obsidian-amber)" }}>
            {kpis.hours} hrs
          </div>
          <div style={{ fontSize: "10px", color: "var(--obsidian-dim)", marginTop: "2px" }}>Logged operational workload</div>
        </div>

        <div
          className="ais-panel slow"
          style={{
            border: "1px solid rgba(55,227,161,.25)",
            borderRadius: "16px",
            background: "linear-gradient(160deg, rgba(55,227,161,.08), rgba(5,7,10,.95) 70%)",
            padding: "14px 18px",
          }}
        >
          <div style={{ fontSize: "9px", letterSpacing: ".18em", color: "var(--obsidian-green)", fontWeight: 700 }}>
            AIS AUTOMATION READY / एआईएस तैयार
          </div>
          <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "28px", fontWeight: 800, marginTop: "4px", color: "var(--obsidian-green)" }}>
            {kpis.percent}%
          </div>
          <div style={{ fontSize: "10px", color: "var(--obsidian-dim)", marginTop: "2px" }}>Can be migrated to software</div>
        </div>

        <div
          className="ais-panel slow"
          style={{
            border: "1px solid rgba(139,92,255,.25)",
            borderRadius: "16px",
            background: "linear-gradient(160deg, rgba(139,92,255,.08), rgba(5,7,10,.95) 70%)",
            padding: "14px 18px",
          }}
        >
          <div style={{ fontSize: "9px", letterSpacing: ".18em", color: "var(--obsidian-violet)", fontWeight: 700 }}>
            ACTIVE SHOWROOM STAFF / सक्रिय कर्मचारी
          </div>
          <div className="ais-num" style={{ fontFamily: "'Geist Mono',monospace", fontSize: "28px", fontWeight: 800, marginTop: "4px", color: "#EAD4FF" }}>
            {kpis.activeStaff}
          </div>
          <div style={{ fontSize: "10px", color: "var(--obsidian-dim)", marginTop: "2px" }}>Logging daily routines</div>
        </div>
      </div>

      {/* Staff Selector Pills (5 core staff + all) */}
      <div style={{ marginBottom: "16px", background: "rgba(5,7,10,0.7)", border: "1px solid var(--obsidian-border)", borderRadius: "18px", padding: "12px 16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "8px" }}>
          <span style={{ fontSize: "10px", letterSpacing: ".15em", color: "var(--obsidian-cyan)", fontWeight: 800 }}>
            STAFF MEMBER / कर्मचारी चुनें:
          </span>
          <select
            value={selectedStaff}
            onChange={(e) => setSelectedStaff(e.target.value)}
            style={{
              padding: "4px 10px",
              borderRadius: "8px",
              background: "rgba(11,16,23,0.9)",
              border: "1px solid rgba(120,170,220,0.25)",
              color: "#F5F8FF",
              fontSize: "11px",
              outline: "none",
            }}
          >
            <option value="all">All 12 Staff Master / सभी कर्मचारी</option>
            {ALL_STAFF_MASTER.map((s) => (
              <option key={s.id} value={s.id}>
                {s.en} / {s.hi}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "4px" }}>
          <button
            onClick={() => setSelectedStaff("all")}
            style={{
              padding: "7px 14px",
              borderRadius: "10px",
              fontSize: "11px",
              fontWeight: 700,
              background: selectedStaff === "all" ? "linear-gradient(135deg, rgba(36,217,255,.25), rgba(77,132,255,.25))" : "rgba(11,16,23,0.8)",
              border: selectedStaff === "all" ? "1px solid rgba(36,217,255,.6)" : "1px solid rgba(120,170,220,0.18)",
              color: selectedStaff === "all" ? "var(--obsidian-cyan)" : "var(--obsidian-muted)",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            All Staff / सभी
          </button>
          {PRIMARY_STAFF.map((s) => {
            const active = selectedStaff === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setSelectedStaff(s.id)}
                style={{
                  padding: "6px 14px",
                  borderRadius: "10px",
                  fontSize: "11px",
                  fontWeight: 700,
                  background: active ? "linear-gradient(135deg, rgba(255,196,91,.25), rgba(215,170,58,.2))" : "rgba(11,16,23,0.8)",
                  border: active ? "1px solid rgba(255,196,91,.6)" : "1px solid rgba(120,170,220,0.18)",
                  color: active ? "var(--obsidian-amber)" : "var(--obsidian-muted)",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  textAlign: "left",
                }}
              >
                <div>{s.en}</div>
                <div style={{ fontSize: "9.5px", opacity: 0.8 }}>{s.hi}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Day Selector Tabs (Monday to Sunday) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(90px, 1fr))", gap: "8px", marginBottom: "18px" }}>
        {DAYS.map((d) => {
          const active = selectedDay === d.id;
          const count = dayCounts[d.id] || 0;
          return (
            <button
              key={d.id}
              onClick={() => setSelectedDay(d.id)}
              style={{
                padding: "8px 6px",
                borderRadius: "12px",
                textAlign: "center",
                background: active ? "linear-gradient(135deg, rgba(36,217,255,.2), rgba(139,92,255,.15))" : "rgba(11,16,23,0.8)",
                border: active ? "1px solid rgba(36,217,255,.55)" : "1px solid rgba(120,170,220,0.15)",
                color: active ? "#BFF3FF" : "var(--obsidian-muted)",
                cursor: "pointer",
                position: "relative",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 700 }}>{d.en}</div>
              <div style={{ fontSize: "9px", opacity: 0.8 }}>{d.hi}</div>
              <div
                style={{
                  display: "inline-block",
                  marginTop: "4px",
                  padding: "1px 6px",
                  borderRadius: "999px",
                  fontSize: "9px",
                  fontFamily: "'Geist Mono',monospace",
                  background: active ? "var(--obsidian-cyan)" : "rgba(120,170,220,0.15)",
                  color: active ? "#04060A" : "var(--obsidian-dim)",
                  fontWeight: 800,
                }}
              >
                {count}
              </div>
            </button>
          );
        })}
      </div>

      {/* Filters & Actions Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "10px",
          marginBottom: "16px",
          background: "rgba(5,7,10,0.6)",
          padding: "10px 14px",
          borderRadius: "14px",
          border: "1px solid var(--obsidian-border)",
        }}
      >
        <div style={{ display: "flex", gap: "8px", flex: 1, flexWrap: "wrap", minWidth: "260px" }}>
          <input
            type="text"
            placeholder="Search work, bottleneck, tool... / खोजें..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              minWidth: "180px",
              padding: "7px 12px",
              borderRadius: "10px",
              background: "rgba(11,16,23,0.9)",
              border: "1px solid rgba(120,170,220,0.25)",
              color: "#fff",
              fontSize: "11px",
              outline: "none",
            }}
          />

          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            style={{
              padding: "7px 12px",
              borderRadius: "10px",
              background: "rgba(11,16,23,0.9)",
              border: "1px solid rgba(120,170,220,0.25)",
              color: "#fff",
              fontSize: "11px",
              outline: "none",
            }}
          >
            <option value="all">All Categories / सभी श्रेणियां</option>
            {Object.entries(CATEGORIES).map(([key, c]) => (
              <option key={key} value={key}>
                {c.en} / {c.hi}
              </option>
            ))}
          </select>

          <select
            value={filterAis}
            onChange={(e) => setFilterAis(e.target.value)}
            style={{
              padding: "7px 12px",
              borderRadius: "10px",
              background: "rgba(11,16,23,0.9)",
              border: "1px solid rgba(120,170,220,0.25)",
              color: "#fff",
              fontSize: "11px",
              outline: "none",
            }}
          >
            <option value="all">All AIS Status / सभी स्थिति</option>
            <option value="automate_full">Full AIS Automation / पूर्ण स्वचालित</option>
            <option value="automate_ai">AI Assisted / एआई सहायता</option>
            <option value="tablet_kiosk">Tablet Kiosk / कियोस्क</option>
            <option value="keep_manual">Keep Manual / मैन्युअल</option>
            <option value="under_review">Under Review / समीक्षाधीन</option>
          </select>
        </div>

        <button
          onClick={openNewModal}
          style={{
            padding: "8px 16px",
            borderRadius: "10px",
            border: "1px solid rgba(255,196,91,.6)",
            background: "linear-gradient(135deg, rgba(255,196,91,.25), rgba(215,170,58,.3))",
            color: "var(--obsidian-amber)",
            fontSize: "12px",
            fontWeight: 800,
            cursor: "pointer",
            boxShadow: "0 0 16px rgba(255,196,91,.2)",
          }}
        >
          + Add Work Item / नया कार्य जोड़ें
        </button>
      </div>

      {/* Task Cards Grid */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--obsidian-muted)" }}>
          <span className="ais-ok" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--obsidian-cyan)", display: "inline-block", marginRight: "8px" }} />
          Loading tasks from storage...
        </div>
      ) : filteredTasks.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px 20px",
            borderRadius: "18px",
            border: "1px dashed rgba(120,170,220,0.25)",
            background: "rgba(5,7,10,0.4)",
            color: "var(--obsidian-muted)",
          }}
        >
          <div style={{ fontSize: "24px", marginBottom: "8px" }}>📋</div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: "#fff" }}>No work items recorded for this filter</div>
          <div style={{ fontSize: "11px", marginTop: "4px" }}>
            Tap <strong>+ Add Work Item</strong> above to log tasks for AIS migration.
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "14px" }}>
          {filteredTasks.map((t) => {
            const cat = CATEGORIES[t.category] || { en: t.category, hi: "", color: "var(--obsidian-cyan)" };
            const badge = AIS_BADGES[t.ais_target] || AIS_BADGES.under_review;

            return (
              <div
                key={t.id}
                className="ais-row"
                style={{
                  borderRadius: "18px",
                  border: "1px solid var(--obsidian-border)",
                  background: "linear-gradient(170deg, rgba(13,20,29,0.9), rgba(5,7,10,0.95))",
                  padding: "16px 18px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: "12px",
                }}
              >
                <div>
                  {/* Top Bar: Category + Day */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "6px" }}>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "6px",
                        border: `1px solid ${cat.color}40`,
                        background: `${cat.color}15`,
                        color: cat.color,
                        fontSize: "10px",
                        fontWeight: 700,
                      }}
                    >
                      {cat.en}
                    </span>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "6px",
                        border: "1px solid rgba(120,170,220,0.2)",
                        background: "rgba(120,170,220,0.06)",
                        fontSize: "10px",
                        color: "var(--obsidian-muted)",
                        fontFamily: "'Geist Mono',monospace",
                      }}
                    >
                      {t.day}
                    </span>
                  </div>

                  {/* Title */}
                  <h4 style={{ fontSize: "13.5px", fontWeight: 700, color: "#fff", margin: "0 0 6px 0", lineHeight: 1.4 }}>
                    {t.title}
                  </h4>

                  {/* Staff */}
                  <div style={{ fontSize: "10.5px", color: "var(--obsidian-muted)", marginBottom: "8px" }}>
                    👤 {t.staff_name}
                  </div>

                  {/* Description */}
                  {t.description && (
                    <p
                      style={{
                        fontSize: "11px",
                        color: "#BCC5D3",
                        background: "rgba(0,0,0,0.35)",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        border: "1px solid rgba(120,170,220,0.1)",
                        margin: "0 0 8px 0",
                        lineHeight: 1.45,
                      }}
                    >
                      {t.description}
                    </p>
                  )}

                  {/* Time & Tool Tags */}
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", fontSize: "10px", color: "var(--obsidian-dim)" }}>
                    <span style={{ padding: "2px 6px", borderRadius: "5px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(120,170,220,0.12)" }}>
                      ⏱️ {t.time_spent}
                    </span>
                    <span style={{ padding: "2px 6px", borderRadius: "5px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(120,170,220,0.12)" }}>
                      📁 {t.current_tool}
                    </span>
                    <span style={{ padding: "2px 6px", borderRadius: "5px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(120,170,220,0.12)" }}>
                      🔄 {t.frequency}
                    </span>
                  </div>

                  {/* Pain Point Highlight */}
                  {t.pain_points && (
                    <div
                      style={{
                        marginTop: "10px",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        border: "1px solid rgba(255,196,91,.25)",
                        background: "rgba(255,196,91,.06)",
                        fontSize: "10.5px",
                        color: "#FFE8B8",
                      }}
                    >
                      <strong style={{ color: "var(--obsidian-amber)" }}>⚠️ Bottleneck / अड़चन:</strong> {t.pain_points}
                    </div>
                  )}
                </div>

                {/* Card Footer: AIS Badge & Actions */}
                <div style={{ borderTop: "1px solid rgba(120,170,220,0.1)", paddingTop: "10px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <span style={{ fontSize: "9px", letterSpacing: ".1em", color: "var(--obsidian-dim)", fontWeight: 700 }}>
                      AIS MIGRATION:
                    </span>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "6px",
                        fontSize: "10px",
                        fontWeight: 700,
                        border: `1px solid ${badge.border}`,
                        background: badge.bg,
                        color: badge.color,
                      }}
                    >
                      {badge.label_en} / {badge.label_hi}
                    </span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <button
                      onClick={() => openDuplicate(t)}
                      style={{
                        padding: "4px 8px",
                        borderRadius: "6px",
                        border: "1px solid rgba(120,170,220,0.18)",
                        background: "rgba(255,255,255,0.03)",
                        color: "var(--obsidian-muted)",
                        fontSize: "10.5px",
                        cursor: "pointer",
                      }}
                    >
                      📋 Copy / कॉपी
                    </button>

                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        onClick={() => openEditModal(t)}
                        style={{
                          padding: "4px 8px",
                          borderRadius: "6px",
                          border: "1px solid rgba(36,217,255,0.3)",
                          background: "rgba(36,217,255,0.06)",
                          color: "var(--obsidian-cyan)",
                          fontSize: "10.5px",
                          cursor: "pointer",
                        }}
                      >
                        ✏️ Edit
                      </button>
                      <button
                        onClick={() => handleDelete(t.id)}
                        style={{
                          padding: "4px 8px",
                          borderRadius: "6px",
                          border: "1px solid rgba(255,95,120,0.3)",
                          background: "rgba(255,95,120,0.06)",
                          color: "var(--obsidian-red)",
                          fontSize: "10.5px",
                          cursor: "pointer",
                        }}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ADD / EDIT MODAL */}
      {modalOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            background: "rgba(0,0,0,0.8)",
            backdropFilter: "blur(6px)",
            display: "grid",
            placeItems: "center",
            padding: "16px",
          }}
        >
          <div
            className="ais-panel"
            style={{
              width: "min(640px, 100%)",
              maxHeight: "90vh",
              overflowY: "auto",
              borderRadius: "24px",
              border: "1px solid var(--obsidian-border)",
              background: "linear-gradient(170deg, rgba(13,20,29,0.98), rgba(5,7,10,0.98))",
              padding: "24px",
              boxShadow: "0 0 40px rgba(36,217,255,0.2)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <div>
                <h3 style={{ fontSize: "16px", fontWeight: 800, margin: 0, color: "#fff" }}>
                  {editTask ? "Edit Work Item / कार्य संपादित करें" : "Add Work Item / नया कार्य जोड़ें"}
                </h3>
                <p style={{ fontSize: "11px", color: "var(--obsidian-muted)", margin: "2px 0 0 0" }}>
                  Record staff activity for AIS migration / एआईएस में स्वतः करने हेतु जानकारी
                </p>
              </div>
              <button
                onClick={() => setModalOpen(false)}
                style={{
                  background: "transparent",
                  border: "1px solid rgba(120,170,220,0.2)",
                  borderRadius: "8px",
                  color: "var(--obsidian-muted)",
                  width: "28px",
                  height: "28px",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSave} style={{ display: "grid", gap: "12px", fontSize: "11.5px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Staff Member / कर्मचारी का नाम *
                  <select
                    value={formStaffId}
                    onChange={(e) => setFormStaffId(e.target.value)}
                    required
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    {ALL_STAFF_MASTER.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.en} / {s.hi}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Day of Week / सप्ताह का दिन *
                  <select
                    value={formDay}
                    onChange={(e) => setFormDay(e.target.value)}
                    required
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    {DAYS.filter((d) => d.id !== "all").map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.en} / {d.hi}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Category / कार्य श्रेणी *
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    required
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    {Object.entries(CATEGORIES).map(([key, c]) => (
                      <option key={key} value={key}>
                        {c.en} / {c.hi}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Priority / प्राथमिकता
                  <select
                    value={formPriority}
                    onChange={(e) => setFormPriority(e.target.value)}
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    <option value="High / उच्च">High / उच्च</option>
                    <option value="Medium / मध्यम">Medium / मध्यम</option>
                    <option value="Low / सामान्य">Low / सामान्य</option>
                  </select>
                </label>
              </div>

              <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                Work Item Title / कार्य का मुख्य नाम *
                <input
                  type="text"
                  required
                  placeholder="e.g., Check custom customer jewellery orders / कस्टम आर्डर चेक करना"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  style={{
                    padding: "8px",
                    borderRadius: "8px",
                    background: "rgba(5,7,10,0.9)",
                    border: "1px solid rgba(120,170,220,0.25)",
                    color: "#fff",
                    outline: "none",
                  }}
                />
              </label>

              <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                Detailed Steps / विस्तृत विवरण
                <textarea
                  rows={2}
                  placeholder="Describe exact operational steps taken / कार्य कैसे किया जाता है..."
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  style={{
                    padding: "8px",
                    borderRadius: "8px",
                    background: "rgba(5,7,10,0.9)",
                    border: "1px solid rgba(120,170,220,0.25)",
                    color: "#fff",
                    outline: "none",
                    resize: "vertical",
                  }}
                />
              </label>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Time / समय
                  <select
                    value={formTimeSpent}
                    onChange={(e) => setFormTimeSpent(e.target.value)}
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    <option value="15 mins / 15 मिनट">15 mins / 15 मिनट</option>
                    <option value="30 mins / 30 मिनट">30 mins / 30 मिनट</option>
                    <option value="45 mins / 45 मिनट">45 mins / 45 मिनट</option>
                    <option value="1 Hour / 1 घंटा">1 Hour / 1 घंटा</option>
                    <option value="2 Hours / 2 घंटे">2 Hours / 2 घंटे</option>
                    <option value="Half Day / आधा दिन">Half Day / आधा दिन</option>
                    <option value="Full Day / पूरा दिन">Full Day / पूरा दिन</option>
                  </select>
                </label>

                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Frequency / आवृत्ति
                  <select
                    value={formFrequency}
                    onChange={(e) => setFormFrequency(e.target.value)}
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    <option value="Daily / प्रतिदिन">Daily / प्रतिदिन</option>
                    <option value="Multiple times / कई बार">Multiple times / कई बार</option>
                    <option value="Weekly / साप्ताहिक">Weekly / साप्ताहिक</option>
                    <option value="Monthly / मासिक">Monthly / मासिक</option>
                    <option value="As needed / आवश्यकतानुसार">As needed / आवश्यकतानुसार</option>
                  </select>
                </label>

                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                  Tool / साधन
                  <select
                    value={formCurrentTool}
                    onChange={(e) => setFormCurrentTool(e.target.value)}
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(120,170,220,0.25)",
                      color: "#fff",
                      outline: "none",
                    }}
                  >
                    <option value="Notebook / Register / खाता-बही / रजिस्टर">Register / नोटबुक</option>
                    <option value="Ornate ERP / ऑर्नेट ईआरपी">Ornate ERP / ऑर्नेट</option>
                    <option value="WhatsApp / व्हाट्सएप">WhatsApp / व्हाट्सएप</option>
                    <option value="Memory / मौखिक / याददाश्त">Memory / याददाश्त</option>
                    <option value="Excel / Sheet / एक्सेल">Excel / शीट</option>
                    <option value="Manual Slip / कच्ची पर्ची">Manual Slip / पर्ची</option>
                  </select>
                </label>
              </div>

              <div
                style={{
                  padding: "10px",
                  borderRadius: "10px",
                  border: "1px solid rgba(255,196,91,.3)",
                  background: "rgba(255,196,91,.06)",
                }}
              >
                <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-amber)", fontWeight: 700 }}>
                  ⚠️ Bottleneck / क्या परेशानी या देरी होती है?
                  <textarea
                    rows={2}
                    placeholder="e.g. Karigar does not reply, manual tally causes errors... / क्या समय बर्बाद होता है?"
                    value={formPainPoints}
                    onChange={(e) => setFormPainPoints(e.target.value)}
                    style={{
                      padding: "8px",
                      borderRadius: "8px",
                      background: "rgba(5,7,10,0.9)",
                      border: "1px solid rgba(255,196,91,0.3)",
                      color: "#FFE8B8",
                      outline: "none",
                      resize: "vertical",
                    }}
                  />
                </label>
              </div>

              <label style={{ display: "grid", gap: "4px", color: "var(--obsidian-muted)", fontWeight: 700 }}>
                AIS Migration Target / एआईएस स्थिति
                <select
                  value={formAisTarget}
                  onChange={(e) => setFormAisTarget(e.target.value)}
                  style={{
                    padding: "8px",
                    borderRadius: "8px",
                    background: "rgba(5,7,10,0.9)",
                    border: "1px solid rgba(120,170,220,0.25)",
                    color: "#fff",
                    outline: "none",
                  }}
                >
                  <option value="automate_full">Direct Candidate for AIS (Full Automation) / पूर्ण स्वचालित</option>
                  <option value="automate_ai">AIS + AI Assisted Workflow / एआई सहायता प्राप्त</option>
                  <option value="tablet_kiosk">Tablet Kiosk Direct Entry / टैबलेट कियोस्क सीधा दाखिला</option>
                  <option value="keep_manual">Keep Manual (Physical/In-Person) / भौतिक रहेगा</option>
                  <option value="under_review">Under Review / समीक्षाधीन</option>
                </select>
              </label>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "8px" }}>
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  style={{
                    padding: "8px 16px",
                    borderRadius: "8px",
                    border: "1px solid rgba(120,170,220,0.2)",
                    background: "transparent",
                    color: "var(--obsidian-muted)",
                    cursor: "pointer",
                  }}
                >
                  Cancel / रद्द
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  style={{
                    padding: "8px 20px",
                    borderRadius: "8px",
                    border: "1px solid rgba(36,217,255,0.6)",
                    background: "linear-gradient(135deg, rgba(36,217,255,0.3), rgba(77,132,255,0.3))",
                    color: "#BFF3FF",
                    fontWeight: 800,
                    cursor: "pointer",
                  }}
                >
                  {saving ? "Saving…" : "Save Task / सुरक्षित करें"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DUPLICATE MODAL */}
      {duplicateModalOpen && sourceTaskForDup && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            background: "rgba(0,0,0,0.8)",
            backdropFilter: "blur(6px)",
            display: "grid",
            placeItems: "center",
            padding: "16px",
          }}
        >
          <div
            className="ais-panel"
            style={{
              width: "min(480px, 100%)",
              borderRadius: "24px",
              border: "1px solid var(--obsidian-border)",
              background: "linear-gradient(170deg, rgba(13,20,29,0.98), rgba(5,7,10,0.98))",
              padding: "22px",
            }}
          >
            <h3 style={{ fontSize: "15px", fontWeight: 800, color: "#fff", margin: "0 0 4px 0" }}>
              Copy Task to Other Days / अन्य दिनों में कॉपी करें
            </h3>
            <p style={{ fontSize: "11px", color: "var(--obsidian-amber)", margin: "0 0 14px 0" }}>
              {sourceTaskForDup.day}: {sourceTaskForDup.title}
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "16px" }}>
              {DAYS.filter((d) => d.id !== "all" && d.id !== sourceTaskForDup.day).map((d) => {
                const checked = selectedDupDays.includes(d.id);
                return (
                  <label
                    key={d.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "8px 10px",
                      borderRadius: "8px",
                      background: checked ? "rgba(36,217,255,0.12)" : "rgba(5,7,10,0.6)",
                      border: checked ? "1px solid rgba(36,217,255,0.4)" : "1px solid rgba(120,170,220,0.15)",
                      cursor: "pointer",
                      fontSize: "11px",
                      color: checked ? "#BFF3FF" : "var(--obsidian-muted)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedDupDays([...selectedDupDays, d.id]);
                        else setSelectedDupDays(selectedDupDays.filter((x) => x !== d.id));
                      }}
                    />
                    <span>
                      <strong>{d.en}</strong> / {d.hi}
                    </span>
                  </label>
                );
              })}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button
                onClick={() => setDuplicateModalOpen(false)}
                style={{
                  padding: "7px 14px",
                  borderRadius: "8px",
                  border: "1px solid rgba(120,170,220,0.2)",
                  background: "transparent",
                  color: "var(--obsidian-muted)",
                  fontSize: "11px",
                  cursor: "pointer",
                }}
              >
                Cancel / रद्द
              </button>
              <button
                onClick={handleDuplicate}
                style={{
                  padding: "7px 16px",
                  borderRadius: "8px",
                  border: "1px solid rgba(255,196,91,.5)",
                  background: "linear-gradient(135deg, rgba(255,196,91,.25), rgba(215,170,58,.3))",
                  color: "var(--obsidian-amber)",
                  fontSize: "11px",
                  fontWeight: 800,
                  cursor: "pointer",
                }}
              >
                Copy to Selected / कॉपी करें
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AIS BLUEPRINT INSIGHTS MODAL */}
      {blueprintModalOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            background: "rgba(0,0,0,0.8)",
            backdropFilter: "blur(6px)",
            display: "grid",
            placeItems: "center",
            padding: "16px",
          }}
        >
          <div
            className="ais-panel"
            style={{
              width: "min(720px, 100%)",
              maxHeight: "90vh",
              overflowY: "auto",
              borderRadius: "24px",
              border: "1px solid var(--obsidian-border)",
              background: "linear-gradient(170deg, rgba(13,20,29,0.98), rgba(5,7,10,0.98))",
              padding: "24px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <div>
                <h3 style={{ fontSize: "16px", fontWeight: 800, margin: 0, color: "#fff" }}>
                  AIS Migration Blueprint / एआईएस माइग्रेशन कार्य योजना
                </h3>
                <p style={{ fontSize: "11px", color: "var(--obsidian-muted)", margin: "2px 0 0 0" }}>
                  Classification of showroom duties ready for automated software codification
                </p>
              </div>
              <button
                onClick={() => setBlueprintModalOpen(false)}
                style={{
                  background: "transparent",
                  border: "1px solid rgba(120,170,220,0.2)",
                  borderRadius: "8px",
                  color: "var(--obsidian-muted)",
                  width: "28px",
                  height: "28px",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "10px", marginBottom: "18px" }}>
              <div style={{ padding: "10px", borderRadius: "10px", background: "rgba(55,227,161,.08)", border: "1px solid rgba(55,227,161,.25)" }}>
                <div style={{ fontSize: "9px", color: "var(--obsidian-green)", fontWeight: 700 }}>FULL AIS AUTOMATION</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "var(--obsidian-green)", marginTop: "2px" }}>
                  {tasks.filter((t) => t.ais_target === "automate_full").length}
                </div>
              </div>
              <div style={{ padding: "10px", borderRadius: "10px", background: "rgba(36,217,255,.08)", border: "1px solid rgba(36,217,255,.25)" }}>
                <div style={{ fontSize: "9px", color: "var(--obsidian-cyan)", fontWeight: 700 }}>AI ASSISTED</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "var(--obsidian-cyan)", marginTop: "2px" }}>
                  {tasks.filter((t) => t.ais_target === "automate_ai").length}
                </div>
              </div>
              <div style={{ padding: "10px", borderRadius: "10px", background: "rgba(255,196,91,.08)", border: "1px solid rgba(255,196,91,.25)" }}>
                <div style={{ fontSize: "9px", color: "var(--obsidian-amber)", fontWeight: 700 }}>TABLET KIOSK</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "var(--obsidian-amber)", marginTop: "2px" }}>
                  {tasks.filter((t) => t.ais_target === "tablet_kiosk").length}
                </div>
              </div>
              <div style={{ padding: "10px", borderRadius: "10px", background: "rgba(120,170,220,.08)", border: "1px solid rgba(120,170,220,.2)" }}>
                <div style={{ fontSize: "9px", color: "var(--obsidian-muted)", fontWeight: 700 }}>MANUAL RETAINED</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "#fff", marginTop: "2px" }}>
                  {tasks.filter((t) => t.ais_target === "keep_manual").length}
                </div>
              </div>
            </div>

            <div style={{ marginBottom: "18px" }}>
              <div style={{ fontSize: "11px", letterSpacing: ".15em", color: "var(--obsidian-cyan)", fontWeight: 800, marginBottom: "8px" }}>
                AUTOMATION ROADMAP TARGETS:
              </div>
              <div style={{ display: "grid", gap: "6px" }}>
                {tasks
                  .filter((t) => t.ais_target === "automate_full" || t.ais_target === "automate_ai")
                  .slice(0, 6)
                  .map((t) => (
                    <div
                      key={t.id}
                      style={{
                        padding: "8px 12px",
                        borderRadius: "8px",
                        background: "rgba(5,7,10,0.6)",
                        border: "1px solid rgba(120,170,220,0.12)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "11px",
                      }}
                    >
                      <div>
                        <strong style={{ color: "#fff" }}>{t.title}</strong>
                        <div style={{ fontSize: "9.5px", color: "var(--obsidian-muted)" }}>
                          {t.staff_name} &bull; {t.day} &bull; {t.current_tool}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: "9.5px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          background: t.ais_target === "automate_full" ? "rgba(55,227,161,.15)" : "rgba(36,217,255,.15)",
                          color: t.ais_target === "automate_full" ? "var(--obsidian-green)" : "var(--obsidian-cyan)",
                        }}
                      >
                        {t.ais_target === "automate_full" ? "AIS Feature" : "AI Agent"}
                      </span>
                    </div>
                  ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: "11px", letterSpacing: ".15em", color: "var(--obsidian-amber)", fontWeight: 800, marginBottom: "8px" }}>
                TOP REPORTED BOTTLENECKS / कर्मचारियों द्वारा दर्ज अड़चनें:
              </div>
              <div style={{ display: "grid", gap: "6px" }}>
                {tasks
                  .filter((t) => Boolean(t.pain_points))
                  .slice(0, 5)
                  .map((t) => (
                    <div
                      key={t.id}
                      style={{
                        padding: "8px 12px",
                        borderRadius: "8px",
                        background: "rgba(255,196,91,.06)",
                        border: "1px solid rgba(255,196,91,.2)",
                        fontSize: "11px",
                        color: "#FFE8B8",
                      }}
                    >
                      &ldquo;{t.pain_points}&rdquo;
                      <div style={{ fontSize: "9.5px", color: "var(--obsidian-amber)", marginTop: "2px" }}>
                        &mdash; {t.staff_name} ({t.title})
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "18px" }}>
              <button
                onClick={() => setBlueprintModalOpen(false)}
                style={{
                  padding: "7px 16px",
                  borderRadius: "8px",
                  border: "1px solid rgba(120,170,220,0.2)",
                  background: "transparent",
                  color: "var(--obsidian-muted)",
                  fontSize: "11px",
                  cursor: "pointer",
                }}
              >
                Close / बंद करें
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export const WorkTrackerView = React.memo(WorkTrackerViewComponent);
