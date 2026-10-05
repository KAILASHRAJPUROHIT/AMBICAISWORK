package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// TaskReport holds the schema definition for the Task entity.
type TaskReport struct {
	ent.Schema
}

// Fields of the Task.
func (TaskReport) Fields() []ent.Field {
	return []ent.Field{
		field.String("std_output").Optional().Default(""),
		field.String("std_error").Optional().Default(""),
		field.Bool("failed").Default(false),
		field.String("end").Optional().Default(""),
	}
}

// Edges of the TaskReport.
func (TaskReport) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("profileissue", ProfileIssue.Type).Unique().Ref("tasksreports"),
		edge.From("task", Task.Type).Unique().Ref("reports"),
	}
}
