//go:build windows

package utils

import (
	"encoding/binary"
	"fmt"
	"net/url"
	"text/template"

	"github.com/danieljoos/wincred"
	"gopkg.in/ini.v1"
)

func CreatePostgresDatabaseURL() (string, error) {
	var err error

	// Open ini file
	configFile := GetConfigFile()
	cfg, err := ini.Load(configFile)
	if err != nil {
		return "", err
	}

	user, err := cfg.Section("DB").GetKey("PostgresUser")
	if err != nil {
		return "", fmt.Errorf("could not read PostgresUser from INI")
	}
	username := url.PathEscape(user.String())

	host, err := cfg.Section("DB").GetKey("PostgresHost")
	if err != nil {
		return "", fmt.Errorf("could not read PostgresHost from INI")
	}
	hostname := url.PathEscape(host.String())

	port, err := cfg.Section("DB").GetKey("PostgresPort")
	if err != nil {
		return "", fmt.Errorf("could not read PostgresPort from INI")
	}
	dbPort := url.PathEscape(port.String())

	database, err := cfg.Section("DB").GetKey("PostgresDatabase")
	if err != nil {
		return "", fmt.Errorf("could not read PostgresDatabase from INI")
	}
	databaseName := url.PathEscape(database.String())

	pass, err := wincred.GetGenericCredential(host.String() + ":" + port.String())
	if err != nil {
		return "", fmt.Errorf("could not read password from Windows Credential Manager")
	}
	decodedPass := UTF16BytesToString(pass.CredentialBlob, binary.LittleEndian)

	password := template.URLQueryEscaper(decodedPass)

	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s", username, password, hostname, dbPort, databaseName), nil
}
