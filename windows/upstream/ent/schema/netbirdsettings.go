package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// NetbirdSettings holds the schema definition for the Rustdesk entity.
type NetbirdSettings struct {
	ent.Schema
}

// Fields of the NetbirdSettings.
func (NetbirdSettings) Fields() []ent.Field {
	return []ent.Field{
		field.String("management_url").Optional().Default(""),
		field.String("access_token").Optional().Default(""),
	}
}

// Edges of the NetbirdSettings.
func (NetbirdSettings) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("tenant", Tenant.Type).Ref("netbird"),
	}
}
