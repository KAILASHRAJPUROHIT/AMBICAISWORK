package commands

import (
	"fmt"
	"log"
	"os"
	"strconv"

	"github.com/urfave/cli/v2"
)

func StopOCSPResponder() *cli.Command {
	return &cli.Command{
		Name:   "stop",
		Usage:  "Stop OCSP Responder server",
		Action: stopOCSPResponder,
	}
}

func stopOCSPResponder(cCtx *cli.Context) error {
	pidByte, err := os.ReadFile("PIDFILE")
	if err != nil {
		return fmt.Errorf("could not find the PIDFILE")
	}

	pid, err := strconv.Atoi(string(pidByte))
	if err != nil {
		return fmt.Errorf("could not parse the pid from PIDFILE")
	}

	p, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("could not find process associated with OCSP Responder")
	}

	if err := p.Signal(os.Interrupt); err != nil {
		return fmt.Errorf("could not terminate the process associated with OCSP Responder, reason: %s", err.Error())
	}

	log.Printf("👋 Done! Your OCSP responder has stopped listening\n\n")

	if err := os.Remove("PIDFILE"); err != nil {
		return err
	}
	return nil
}
