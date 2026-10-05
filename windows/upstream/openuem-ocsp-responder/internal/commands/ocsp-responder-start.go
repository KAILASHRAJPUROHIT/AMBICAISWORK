package commands

import (
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	"github.com/go-co-op/gocron/v2"
	"github.com/open-uem/openuem-ocsp-responder/internal/common"
	"github.com/urfave/cli/v2"
)

func StartOCSPResponder() *cli.Command {
	return &cli.Command{
		Name:   "start",
		Usage:  "Start OCSP Responder server",
		Action: startOCSPResponder,
		Flags:  OCSPResponderFlags(),
	}
}

func OCSPResponderFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:    "cacert",
			Value:   "certificates/ca.cer",
			Usage:   "the path to your CA certificate file in PEM format",
			EnvVars: []string{"CA_CERT_FILENAME"},
		},
		&cli.StringFlag{
			Name:    "cert",
			Value:   "certificates/ocsp.cer",
			Usage:   "the path to your OCSP server certificate file in PEM format",
			EnvVars: []string{"SERVER_CERT_FILENAME"},
		},
		&cli.StringFlag{
			Name:    "key",
			Value:   "certificates/ocsp.key",
			Usage:   "the path to your OCSP server private key file in PEM format",
			EnvVars: []string{"SERVER_KEY_FILENAME"},
		},
		&cli.StringFlag{
			Name:     "dburl",
			Usage:    "the Postgres database connection url e.g (postgres://user:password@host:5432/openuem)",
			EnvVars:  []string{"DATABASE_URL"},
			Required: true,
		},
		&cli.StringFlag{
			Name:    "port",
			Usage:   "the port used by the OCSP Responder",
			EnvVars: []string{"OCSP_PORT"},
			Value:   "8000",
		},
	}
}

func startOCSPResponder(cCtx *cli.Context) error {
	var err error

	worker := common.NewWorker("")

	if err := worker.GenerateOCSPResponderConfigFromCLI(cCtx); err != nil {
		log.Printf("[ERROR]: could not generate config for OCSP responder: %v", err)
	}

	// Save pid to PIDFILE
	if err := os.WriteFile("PIDFILE", []byte(strconv.Itoa(os.Getpid())), 0666); err != nil {
		return err
	}

	// Start Task Scheduler
	worker.TaskScheduler, err = gocron.NewScheduler()
	if err != nil {
		log.Printf("[ERROR]: could not create task scheduler, reason: %s", err.Error())
		return err
	}
	worker.TaskScheduler.Start()
	log.Println("[INFO]: task scheduler has been started")

	// Start worker
	worker.StartWorker()

	// Keep the connection alive
	done := make(chan os.Signal, 1)
	signal.Notify(done, syscall.SIGINT, syscall.SIGTERM, os.Interrupt)
	log.Printf("[INFO]: the OCSP responder is ready and listening on %s\n", cCtx.String("address"))
	<-done

	worker.StopWorker()

	log.Printf("[INFO]: the OCSP responder has stopped listening\n")
	return nil
}
