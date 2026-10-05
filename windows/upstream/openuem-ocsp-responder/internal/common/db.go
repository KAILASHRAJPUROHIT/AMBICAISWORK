package common

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/go-co-op/gocron/v2"
	"github.com/open-uem/openuem-ocsp-responder/internal/models"
	"github.com/open-uem/openuem-ocsp-responder/internal/server"
)

func (w *Worker) StartDBConnectJob() error {
	var err error

	w.Model, err = models.New(w.DBUrl)
	if err == nil {
		log.Println("[INFO]: connection established with database")

		w.StartOCSPResponderWebService()
		return nil
	}
	log.Printf("[ERROR]: could not connect with database %v", err)

	// Create task for running the agent
	w.DBConnectJob, err = w.TaskScheduler.NewJob(
		gocron.DurationJob(
			time.Duration(time.Duration(30*time.Second)),
		),
		gocron.NewTask(
			func() {
				w.Model, err = models.New(w.DBUrl)
				if err != nil {
					log.Printf("[ERROR]: could not connect with database %v", err)
					return
				}
				log.Println("[INFO]: connection established with database")

				if err := w.TaskScheduler.RemoveJob(w.DBConnectJob.ID()); err != nil {
					return
				}

				w.StartOCSPResponderWebService()
			},
		),
	)
	if err != nil {
		log.Fatalf("[FATAL]: could not start the DB connect job: %v", err)
		return err
	}
	log.Printf("[INFO]: new DB connect job has been scheduled every %d seconds", 30)
	return nil
}

func (w *Worker) StartOCSPResponderWebService() {
	log.Println("[INFO]: launching server")

	port := ":8000"
	if w.Port != "" {
		port = fmt.Sprintf(":%s", w.Port)
	}
	w.WebServer = server.New(w.Model, port, w.CACert, w.OCSPCert, w.OCSPPrivateKey)

	go func() {
		if err := w.WebServer.Serve(); err != http.ErrServerClosed {
			log.Printf("[ERROR]: the server has stopped, reason: %v", err.Error())
		}
	}()

	log.Println("[INFO]: OCSP responder is running")
}
