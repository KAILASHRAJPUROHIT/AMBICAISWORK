//go:build linux

package utils

import (
	"fmt"

	"gopkg.in/ini.v1"
)

func GetJWTKey() (string, error) {
	// Open ini file
	configFile := GetConfigFile()
	cfg, err := ini.Load(configFile)
	if err != nil {
		return "", err
	}

	key, err := cfg.Section("JWT").GetKey("Key")
	if err != nil {
		return "", fmt.Errorf("could not read PostgresDatabase from INI")
	}

	return key.String(), nil
}
