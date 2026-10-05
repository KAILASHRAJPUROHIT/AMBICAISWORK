package schema

import (
	"time"

	"entgo.io/ent"
	"entgo.io/ent/dialect/entsql"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
	"entgo.io/ent/schema/index"
)

// Agent holds the schema definition for the Agent entity.
type Agent struct {
	ent.Schema
}

// Fields of the Agent.
func (Agent) Fields() []ent.Field {
	return []ent.Field{
		field.String("id").NotEmpty().Unique().StorageKey("oid"),
		field.String("os").NotEmpty(),
		field.String("hostname").NotEmpty(),
		field.String("ip").Default(""),
		field.String("mac").Default(""),
		field.Time("first_contact").Optional(),
		field.Time("last_contact").Optional(),
		field.String("vnc").Optional().Default(""),
		field.Text("notes").Optional(),
		field.String("update_task_status").Optional().Default(""),
		field.String("update_task_description").Optional().Default(""),
		field.String("update_task_result").Optional().Default(""),
		field.Time("update_task_execution").Optional(),
		field.String("update_task_version").Optional().Default(""),
		field.String("vnc_proxy_port").Optional().Default(""),
		field.String("sftp_port").Optional().Default(""),
		field.Enum("agent_status").Values("WaitingForAdmission", "Enabled", "Disabled", "No contact").Optional().Default("WaitingForAdmission"),
		field.Bool("certificate_ready").Optional().Default(false),
		field.Bool("restart_required").Optional().Default(false),
		field.Bool("is_remote").Optional().Default(false),
		field.Bool("debug_mode").Optional().Default(false),
		field.Bool("sftp_service").Optional().Default(true),
		field.Bool("remote_assistance").Optional().Default(true),
		field.Time("settings_modified").Optional().Default(time.Now),
		field.String("description").Optional().Default(""),
		field.String("nickname").Optional().Default(""),
		field.Enum("endpoint_type").Values("DesktopPC", "Laptop", "Server", "Tablet", "VM", "AllInOne", "Other").Optional().Default("Other"),
		field.Bool("has_rustdesk").Optional().Default(false),
		field.Bool("is_wayland").Optional().Default(false),
		field.Bool("is_flatpak_rustdesk").Optional().Default(false),
		field.String("wan").Default(""),
	}
}

// Edges of the Agent.
func (Agent) Edges() []ent.Edge {
	return []ent.Edge{
		edge.To("computer", Computer.Type).Unique().Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("operatingsystem", OperatingSystem.Type).Unique().Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("systemupdate", SystemUpdate.Type).Unique().Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("antivirus", Antivirus.Type).Unique().Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("logicaldisks", LogicalDisk.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("apps", App.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("monitors", Monitor.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("shares", Share.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("printers", Printer.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("networkadapters", NetworkAdapter.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("deployments", Deployment.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("updates", Update.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("tags", Tag.Type),
		edge.To("metadata", Metadata.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("wingetcfgexclusions", WingetConfigExclusion.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("memoryslots", MemorySlot.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.From("release", Release.Type).Ref("agents").Unique(),
		edge.From("profileissue", ProfileIssue.Type).Ref("agents"),
		edge.From("site", Site.Type).Ref("agents"),
		edge.To("physicaldisks", PhysicalDisk.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("netbird", Netbird.Type).Unique().Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
	}
}

// Indexes of the Agent.
func (Agent) Indexes() []ent.Index {
	return []ent.Index{
		index.Fields("nickname").StorageKey("agent_nickname_idx"),
	}
}
