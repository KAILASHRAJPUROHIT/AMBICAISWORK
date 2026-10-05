package schema

import (
	"time"

	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// Settings holds the schema definition for the Settings entity.
type Settings struct {
	ent.Schema
}

// Fields of the Settings.
func (Settings) Fields() []ent.Field {
	return []ent.Field{
		field.String("language").Optional(),
		field.String("organization").Optional(),
		field.String("postal_address").Optional(),
		field.String("postal_code").Optional(),
		field.String("locality").Optional(),
		field.String("province").Optional(),
		field.String("state").Optional(),
		field.String("country").Optional().Default("ES"),
		field.String("smtp_server").Optional(),
		field.Int("smtp_port").Optional().Default(587),
		field.String("smtp_user").Optional(),
		field.String("smtp_password").Optional(),
		field.String("smtp_auth").Optional().Default("LOGIN"),
		field.String("nats_server").Optional(),
		field.String("nats_port").Optional(),
		field.String("message_from").Optional(),
		field.String("max_upload_size").Optional().Default("512M"),
		field.Int("user_cert_years_valid").Optional().Default(1),
		field.Int("nats_request_timeout_seconds").Optional().Default(20),
		field.Int("refresh_time_in_minutes").Optional().Default(5),
		field.Int("session_lifetime_in_minutes").Optional().Default(1440),
		field.String("update_channel").Optional().Default("stable"),
		field.Time("created").Optional().Default(time.Now),
		field.Time("modified").Optional().Default(time.Now).UpdateDefault(time.Now),
		field.Int("agent_report_frequence_in_minutes").Optional().Default(60),
		field.Bool("request_vnc_pin").Optional().Default(true),
		field.Int("profiles_application_frequence_in_minutes").Optional().Default(30),
		field.Bool("use_winget").Optional().Default(true),
		field.Bool("use_flatpak").Optional().Default(true),
		field.Bool("use_brew").Optional().Default(true),
		field.Bool("disable_sftp").Optional().Default(false),
		field.Bool("disable_remote_assistance").Optional().Default(false),
		field.Bool("detect_remote_agents").Optional().Default(false),
		field.Bool("auto_admit_agents").Optional().Default(false),
		field.Int("default_items_per_page").Optional().Default(5),
		field.Float("register_rate_limit").Optional().Default(0.000833333),
		field.String("turnstile_site_key").Optional().Default(""),
		field.String("turnstile_secret_key").Optional().Default(""),
		field.Enum("smtp_encryption_type").Values("none", "smtps", "starttls").Optional().Default("none"),
	}
}

// Edges of the Settings.
func (Settings) Edges() []ent.Edge {
	return []ent.Edge{
		edge.To("tag", Tag.Type).Unique(),
		edge.From("tenant", Tenant.Type).Unique().Ref("settings"),
	}
}
