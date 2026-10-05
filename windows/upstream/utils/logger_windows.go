//go:build windows

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
	logger := OpenUEMLogger{}

	// Get executable path to store logs
	ex, err := os.Executable()
	if err != nil {
		log.Fatalf("could not get executable info: %v", err)
	}
	wd := filepath.Dir(ex)

	logPath := filepath.Join(wd, "logs", logFilename)
	logger.LogFile, err = os.OpenFile(logPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		log.Fatalf("could not create log file: %v", err)
	}

	logPrefix := strings.TrimSuffix(filepath.Base(logFilename), filepath.Ext(logFilename))
	log.SetOutput(logger.LogFile)
	log.SetPrefix(logPrefix + ": ")
	log.SetFlags(log.Ldate | log.Ltime)

	return &logger
}

func (l *OpenUEMLogger) Close() {
	l.LogFile.Close()
}

func NewAuthLogger() *log.Logger {
	// Get executable path to store logs
	ex, err := os.Executable()
	if err != nil {
		log.Fatalf("could not get executable info: %v", err)
	}
	wd := filepath.Dir(ex)

	if _, err := os.Stat(wd); os.IsNotExist(err) {
		if err := os.MkdirAll(wd, 0600); err != nil {
			log.Fatalf("[FATAL]: could not create log directory, reason: %v", err)
		}
	}

	f, err := os.OpenFile(filepath.Join(wd, "logs", "openuem-auth.txt"), os.O_RDWR|os.O_CREATE|os.O_APPEND, 0660)
	if err != nil {
		log.Fatalf("[FATAL]: auth log file not created, reason: %v", err)
	}
	return log.New(f, "", log.Ldate|log.Ltime)
}
