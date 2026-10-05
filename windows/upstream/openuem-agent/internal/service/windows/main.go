//go:build windows

package main

import (
	"log"
	"runtime"

	"github.com/open-uem/openuem-agent/internal/logger"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/debug"
)

func main() {

	// the agent will use two CPUs at maximum
	runtime.GOMAXPROCS(2)

	// Instantiate logger
	l := logger.New()

	// Instantiate service
	s := NewService(l)

	// Run service. AMBIC change: when started from a console (not by the Service Control Manager) run the same
	// service code in the foreground, so the agent can be developed and tested without installing a Windows service.
	var err error
	if isService, ierr := svc.IsWindowsService(); ierr == nil && !isService {
		err = debug.Run("openuem-agent", s)
	} else {
		err = svc.Run("openuem-agent", s)
	}
	if err != nil {
		log.Fatalf("could not run service: %v", err)
	}
}
