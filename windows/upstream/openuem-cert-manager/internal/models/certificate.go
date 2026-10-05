package models

import (
	"context"
	"time"

	"github.com/open-uem/ent/certificate"
)

func (m *Model) SaveCertificate(serial int64, certType certificate.Type, description string, expiry time.Time, createUser bool, user string) error {
	if createUser {
		_, err := m.Client.Certificate.Create().SetID(serial).SetType(certType).SetDescription(description).SetExpiry(expiry).SetUID(user).Save(context.Background())
		if err != nil {
			return err
		}
	} else {
		_, err := m.Client.Certificate.Create().SetID(serial).SetType(certType).SetDescription(description).SetExpiry(expiry).Save(context.Background())
		if err != nil {
			return err
		}
	}

	if createUser {
		if _, err := m.Client.User.Create().SetID(user).SetName(description).SetExpiry(expiry).SetRegister("users.completed").Save(context.Background()); err != nil {
			return err
		}
	}
	return nil
}

func (m *Model) DeleteCertificate(serial int64) error {
	err := m.Client.Certificate.DeleteOneID(serial).Exec(context.Background())
	if err != nil {
		return err
	}
	return nil
}
