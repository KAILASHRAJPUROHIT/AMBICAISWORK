//go:build windows

package utils

import (
	"log"
	"path/filepath"
)

func GetConfigFile() string {
	wd, err := GetWd()
	if err != nil {
		log.Fatalf("[FATAL]: could not get working directory")
	}

	return filepath.Join(wd, "config", "openuem.ini")
}

func GetAgentConfigFile() string {
	return GetConfigFile()
}
