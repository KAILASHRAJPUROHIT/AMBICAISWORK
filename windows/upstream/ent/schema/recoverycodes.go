package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// RecoveryCode holds the schema definition for the RecoveryCode entity.
type RecoveryCode struct {
	ent.Schema
}

// Fields of the RecoveryCode.
func (RecoveryCode) Fields() []ent.Field {
	return []ent.Field{
		field.String("code").NotEmpty(),
		field.Bool("used").Default(false),
	}
}

func (RecoveryCode) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("user", User.Type).Ref("recoverycodes").Unique(),
	}
}
