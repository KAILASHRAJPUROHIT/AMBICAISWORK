package schema

import (
	"time"

	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// holds the schema definition for the WingetConfigExclusion entity.
type WingetConfigExclusion struct {
	ent.Schema
}

// Fields of the WingetConfigExclusion.
func (WingetConfigExclusion) Fields() []ent.Field {
	return []ent.Field{
		field.String("package_id"),
		field.Time("when").Optional().Default(time.Now),
	}
}

// Edges of the WingetConfigExclusion.
func (WingetConfigExclusion) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("owner", Agent.Type).Unique().Ref("wingetcfgexclusions").Required(),
	}
}
