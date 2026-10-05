package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// MemorySlot holds the schema definition for the Monitor entity.
type MemorySlot struct {
	ent.Schema
}

// Fields of the Memory.
func (MemorySlot) Fields() []ent.Field {
	return []ent.Field{
		field.String("slot").Optional(),
		field.String("size").Optional(),
		field.String("type").Optional(),
		field.String("serial_number").Optional(),
		field.String("part_number").Optional(),
		field.String("speed").Optional(),
		field.String("manufacturer").Optional(),
	}
}

// Edges of the Memory.
func (MemorySlot) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("owner", Agent.Type).Unique().Ref("memoryslots").Required(),
	}
}
