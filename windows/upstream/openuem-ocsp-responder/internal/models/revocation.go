package models

import (
	"context"

	openuem_ent "github.com/open-uem/ent"
	"github.com/open-uem/ent/revocation"
)

func (m *Model) GetRevoked(serial int64) (*openuem_ent.Revocation, error) {
	return m.Client.Revocation.Query().Where(revocation.ID(serial)).Only(context.Background())
}
