package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// Rustdesk holds the schema definition for the Rustdesk entity.
type Rustdesk struct {
	ent.Schema
}

// Fields of the Rustdesk.
func (Rustdesk) Fields() []ent.Field {
	return []ent.Field{
		field.String("custom_rendezvous_server").Optional().Default(""),
		field.String("relay_server").Optional().Default(""),
		field.String("api_server").Optional().Default(""),
		field.String("key").Optional().Default(""),
		field.Bool("use_permanent_password").Optional().Default(false),
		field.String("whitelist").Optional().Default(""),
		field.Bool("direct_ip_access").Optional().Default(false),
		field.Enum("verification_method").Values("use-temporary-password", "use-permanent-password", "use-both-passwords").Optional().Default("use-both-passwords"),
		field.Int("temporary_password_length").Optional().Default(6),
	}
}

// Edges of the Rustdesk.
func (Rustdesk) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("tenant", Tenant.Type).Ref("rustdesk"),
	}
}
