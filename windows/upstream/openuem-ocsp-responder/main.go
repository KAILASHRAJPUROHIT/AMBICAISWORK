package main

import (
	"log"
	"os"

	"github.com/open-uem/openuem-ocsp-responder/internal/commands"
	"github.com/urfave/cli/v2"
)

func main() {
	app := &cli.App{
		Name:      "openuem-ocsp-responder",
		Commands:  getCommands(),
		Usage:     "Manage the Online Certification Signing Protocol (OCSP) responder, required to check if a certificate is valid",
		Authors:   []*cli.Author{{Name: "Miguel Angel Alvarez Cabrerizo", Email: "mcabrerizo@sologitops.com"}},
		Copyright: "2024 - Miguel Angel Alvarez Cabrerizo <https://github.com/doncicuto>",
	}

	if err := app.Run(os.Args); err != nil {
		log.Fatal(err)
	}
}

func getCommands() []*cli.Command {
	return []*cli.Command{
		commands.StartOCSPResponder(),
		commands.StopOCSPResponder(),
	}
}
