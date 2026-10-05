package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// Physical Disk holds the schema definition for the Physical Disk entity.
type PhysicalDisk struct {
	ent.Schema
}

// Fields of the Physical Disk.
func (PhysicalDisk) Fields() []ent.Field {
	return []ent.Field{
		field.String("device_id"),
		field.String("model").Optional(),
		field.String("serial_number").Optional(),
		field.String("size_in_units").Optional(),
	}
}

// Edges of the Physical Disk.
func (PhysicalDisk) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("owner", Agent.Type).Unique().Ref("physicaldisks").Required(),
	}
}
