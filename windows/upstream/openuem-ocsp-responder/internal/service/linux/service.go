//go:build linux

package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/go-co-op/gocron/v2"
	"github.com/open-uem/openuem-ocsp-responder/internal/common"
)

func main() {
	var err error

	w := common.NewWorker("openuem-ocsp-responder")

	// Start Task Scheduler
	w.TaskScheduler, err = gocron.NewScheduler()
	if err != nil {
		log.Printf("[ERROR]: could not create task scheduler, reason: %s", err.Error())
		return
	}
	w.TaskScheduler.Start()
	log.Println("[INFO]: task scheduler has been started")

	if err := w.GenerateOCSPResponderConfig(); err != nil {
		log.Printf("[ERROR]: could not generate config for OCSP responder: %v", err)
		if err := w.StartGenerateOCSPResponderConfigJob(); err != nil {
			log.Fatalf("[FATAL]: could not start job to generate config for OCSP responder: %v", err)
		}
	}

	w.StartWorker()

	// Keep the connection alive
	done := make(chan os.Signal, 1)
	signal.Notify(done, syscall.SIGINT, syscall.SIGTERM, os.Interrupt)
	<-done

	w.StopWorker()
}
