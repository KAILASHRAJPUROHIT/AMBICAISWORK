//go:build linux

package utils

import (
	"log"
	"os"
	"path/filepath"
	"strings"
)

type OpenUEMLogger struct {
	LogFile *os.File
}

func NewLogger(logFilename string) *OpenUEMLogger {
	var err error

	logger := OpenUEMLogger{}

	// Get executable path to store logs
	wd := "/var/log/openuem-server"

	if _, err := os.Stat(wd); os.IsNotExist(err) {
		if err := os.MkdirAll(wd, 0660); err != nil {
			log.Fatalf("[FATAL]: could not create log directory, reason: %v", err)
		}
	}

	logPath := filepath.Join(wd, logFilename)
	logger.LogFile, err = os.Create(logPath)
	if err != nil {
		log.Fatalf("could not create log file: %v", err)
	}

	logPrefix := strings.TrimSuffix(filepath.Base(logFilename), filepath.Ext(logFilename))
	log.SetOutput(logger.LogFile)
	log.SetPrefix(logPrefix + ": ")
	log.SetFlags(log.Ldate | log.Ltime)

	return &logger
}

func NewAuthLogger() *log.Logger {
	wd := "/var/log/openuem-server"

	if _, err := os.Stat(wd); os.IsNotExist(err) {
		if err := os.MkdirAll(wd, 0660); err != nil {
			log.Fatalf("[FATAL]: could not create log directory, reason: %v", err)
		}
	}

	f, err := os.OpenFile(filepath.Join(wd, "openuem-auth"), os.O_RDWR|os.O_CREATE|os.O_APPEND, 0660)
	if err != nil {
		log.Fatalf("[FATAL]: auth log file not created, reason: %v", err)
	}
	return log.New(f, "", log.Ldate|log.Ltime)
}

func (l *OpenUEMLogger) Close() {
	l.LogFile.Close()
}
