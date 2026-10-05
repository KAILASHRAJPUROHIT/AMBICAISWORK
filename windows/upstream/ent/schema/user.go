package schema

import (
	"time"

	"entgo.io/ent"
	"entgo.io/ent/dialect/entsql"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
	"entgo.io/ent/schema/index"
)

// User holds the schema definition for the User entity.
type User struct {
	ent.Schema
}

// Fields of the User.
func (User) Fields() []ent.Field {
	return []ent.Field{
		field.String("id").NotEmpty().Unique().StorageKey("uid"),
		field.String("name"),
		field.String("email").Optional(),
		field.String("phone").Optional(),
		field.String("country").Optional(),
		field.Bool("email_verified").Default(false),
		field.String("register").Default("users.pending_email_confirmation"),
		field.String("cert_clear_password").Optional(),
		field.Time("expiry").Optional(),
		field.Bool("openid").Optional().Default(false),
		field.Bool("passwd").Optional().Default(false),
		field.Bool("use2fa").Optional().Default(false),
		field.Time("created").Optional().Default(time.Now),
		field.Time("modified").Optional().Default(time.Now).UpdateDefault(time.Now),
		field.String("hash").Optional().Default(""),
		field.String("totp_secret").Optional().Default(""),
		field.Bool("totp_secret_confirmed").Optional().Default(false),
		field.String("forgot_password_code").Optional().Default(""),
		field.Time("forgot_password_code_expires_at").Optional().Default(time.Now),
		field.String("new_user_token").Optional().Default(""),
	}
}

func (User) Edges() []ent.Edge {
	return []ent.Edge{
		edge.To("sessions", Sessions.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
		edge.To("recoverycodes", RecoveryCode.Type).Annotations(entsql.Annotation{OnDelete: entsql.Cascade}),
	}
}

func (User) Indexes() []ent.Index {
	return []ent.Index{
		index.Fields("email").StorageKey("users_email_idx"),
	}
}
