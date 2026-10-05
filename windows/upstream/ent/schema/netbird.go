package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// Netbird holds the schema definition for the Netbird entity.
type Netbird struct {
	ent.Schema
}

// Fields of the Netbird.
func (Netbird) Fields() []ent.Field {
	return []ent.Field{
		field.String("version").Default(""),
		field.Bool("installed").Default(false),
		field.String("service_status").Default(""),
		field.String("ip").Default("").Optional(),
		field.String("profile").Default("").Optional(),
		field.String("management_url").Default("").Optional(),
		field.Bool("management_connected").Default(false),
		field.String("signal_url").Default("").Optional(),
		field.Bool("signal_connected").Default(false),
		field.Bool("ssh_enabled").Default(false),
		field.Int("peers_total").Default(0).Optional(),
		field.Int("peers_connected").Default(0).Optional(),
		field.String("profiles_available").Default("").Optional(),
		field.String("dns_server").Default("").Optional(),
	}
}

// Edges of the Netbird.
func (Netbird) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("owner", Agent.Type).Unique().Ref("netbird").Required(),
	}
}
