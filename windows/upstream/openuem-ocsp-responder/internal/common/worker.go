package common

import (
	"crypto/rsa"
	"crypto/x509"
	"log"

	"github.com/go-co-op/gocron/v2"
	"github.com/open-uem/openuem-ocsp-responder/internal/models"
	"github.com/open-uem/openuem-ocsp-responder/internal/server"
	"github.com/open-uem/utils"
)

type Worker struct {
	Model          *models.Model
	WebServer      *server.WebServer
	Logger         *utils.OpenUEMLogger
	DBConnectJob   gocron.Job
	ConfigJob      gocron.Job
	TaskScheduler  gocron.Scheduler
	DBUrl          string
	CACert         *x509.Certificate
	OCSPCert       *x509.Certificate
	OCSPPrivateKey *rsa.PrivateKey
	Port           string
}

func NewWorker(logName string) *Worker {
	worker := Worker{}
	if logName != "" {
		worker.Logger = utils.NewLogger(logName)
	}

	return &worker
}

func (w *Worker) StartWorker() {
	// Start a job to try to connect with the database
	if err := w.StartDBConnectJob(); err != nil {
		log.Printf("[ERROR]: could not start DB connect job, reason: %s", err.Error())
		return
	}
}

func (w *Worker) StopWorker() {
	if w.Model != nil {
		w.Model.Close()
	}

	if w.TaskScheduler != nil {
		if err := w.TaskScheduler.Shutdown(); err != nil {
			log.Printf("[ERROR]: could not stop the task scheduler, reason: %s", err.Error())
		}
	}

	if w.WebServer != nil {
		w.WebServer.Close()
	}

	log.Println("[INFO]: the OCSP responder has stopped")
	if w.Logger != nil {
		w.Logger.Close()
	}

}
