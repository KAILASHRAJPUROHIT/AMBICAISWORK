package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/field"
	"github.com/google/uuid"
)

// SoftwarePackage holds the schema definition for the SoftwarePackage entity.
type SoftwarePackage struct {
	ent.Schema
}

// Fields of the SoftwarePackage.
func (SoftwarePackage) Fields() []ent.Field {
	return []ent.Field{
		field.UUID("id", uuid.UUID{}).Default(uuid.New),
		field.String("package_id"),
		field.String("name"),
		field.String("version").Optional(),
		field.String("branch").Optional(),
		field.String("arch").Optional(),
		field.String("brew_type").Optional(),
		field.Bool("verified").Optional(),
		field.String("source"),
	}
}
