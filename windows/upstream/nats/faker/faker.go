package main

import (
	"encoding/json"
	"log"
	"os"
	"time"

	"github.com/open-uem/nats"
	"github.com/open-uem/nats/faker/data"
	"github.com/urfave/cli/v2"
)

func main() {
	app := &cli.App{
		Name:      "openuem-fake-agents",
		Commands:  []*cli.Command{FakeAgentsWorker()},
		Usage:     "Manage an OpenUEM worker",
		Authors:   []*cli.Author{{Name: "Miguel Angel Alvarez Cabrerizo", Email: "mcabrerizo@openuem.eu"}},
		Copyright: "2024 - Miguel Angel Alvarez Cabrerizo <https://github.com/open-uem>",
	}

	if err := app.Run(os.Args); err != nil {
		log.Fatal(err)
	}
}

func FakeAgentsWorker() *cli.Command {
	return &cli.Command{
		Name:   "start",
		Usage:  "Start the OpenUEM Fake Agents worker",
		Flags:  flags(),
		Action: fakeAgentsStart,
	}
}
func fakeAgentsStart(cCtx *cli.Context) error {
	conn, err := nats.ConnectWithNATS(cCtx.String("nats-servers"), cCtx.String("cert"), cCtx.String("key"), cCtx.String("cacert"), "")
	if err != nil {
		return err
	}

	for i := 0; i < cCtx.Int("num"); i++ {
		r := data.GetFakeAgent(i)
		natsReport, err := json.Marshal(r)
		if err != nil {
			return err
		}

		if _, err := conn.Request("report", natsReport, 4*time.Minute); err != nil {
			return err
		}
	}
	return nil
}

func flags() []cli.Flag {
	return []cli.Flag{
		&cli.IntFlag{
			Name:     "num",
			Usage:    "how many fake agents we want to run",
			EnvVars:  []string{"NUM_AGENTS"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "nats-servers",
			Usage:    "comma-separated list of NATS servers urls e.g (tls://localhost:4433)",
			EnvVars:  []string{"NATS_SERVERS"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "cacert",
			Usage:    "the path to your CA certificate file in PEM format",
			EnvVars:  []string{"CA_CRT_FILENAME"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "cert",
			Usage:    "the path to your agent's certificate file in PEM format",
			EnvVars:  []string{"CERT_FILENAME"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "key",
			Usage:    "the path to your agent's private key file in PEM format",
			EnvVars:  []string{"KEY_FILENAME"},
			Required: true,
		},
	}
}
