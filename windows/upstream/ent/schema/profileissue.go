package schema

import (
	"time"

	"entgo.io/ent"
	"entgo.io/ent/dialect/entsql"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
)

// ProfileIssue holds the schema definition for the ProfileIssue entity.
type ProfileIssue struct {
	ent.Schema
}

// Fields of the ProfileIssue.
func (ProfileIssue) Fields() []ent.Field {
	return []ent.Field{
		field.String("error").Optional(),
		field.Time("when").Optional().Default(time.Now).UpdateDefault(time.Now),
	}
}

// Edges of the ProfileIssue.
func (ProfileIssue) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("profile", Profile.Type).Unique().Ref("issues"),
		edge.To("agents", Agent.Type).Unique(),
		edge.To("tasksreports", TaskReport.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
	}
}
