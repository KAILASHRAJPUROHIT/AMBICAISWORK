package common

import (
	"log"
	"time"

	"github.com/go-co-op/gocron/v2"
	"github.com/open-uem/utils"
	"gopkg.in/ini.v1"
)

func (w *Worker) GenerateOCSPResponderConfig() error {
	var err error

	// Get config file location
	configFile := utils.GetConfigFile()

	// Get new OCSP Responder
	w.DBUrl, err = utils.CreatePostgresDatabaseURL()
	if err != nil {
		log.Printf("[ERROR]: %v", err)
		return err
	}

	// Open ini file
	cfg, err := ini.Load(configFile)
	if err != nil {
		return err
	}

	key, err := cfg.Section("Certificates").GetKey("CACert")
	if err != nil {
		return err
	}

	w.CACert, err = utils.ReadPEMCertificate(key.String())
	if err != nil {
		log.Printf("[ERROR]: could not read CA certificate in %s", key.String())
		return err
	}

	key, err = cfg.Section("Certificates").GetKey("OCSPCert")
	if err != nil {
		return err
	}

	w.OCSPCert, err = utils.ReadPEMCertificate(key.String())
	if err != nil {
		log.Println("[ERROR]: could not read OCSP certificate")
		return err
	}

	key, err = cfg.Section("Certificates").GetKey("OCSPKey")
	if err != nil {
		return err
	}

	w.OCSPPrivateKey, err = utils.ReadPEMPrivateKey(key.String())
	if err != nil {
		log.Println("[ERROR]: could not read OCSP private key")
		return err
	}

	key, err = cfg.Section("OCSP").GetKey("OCSPPort")
	if err != nil {
		return err
	}

	w.Port = key.String()

	return nil
}

func (w *Worker) StartGenerateOCSPResponderConfigJob() error {
	var err error

	// Create task for getting the worker config
	w.ConfigJob, err = w.TaskScheduler.NewJob(
		gocron.DurationJob(
			time.Duration(time.Duration(1*time.Minute)),
		),
		gocron.NewTask(
			func() {
				err = w.GenerateOCSPResponderConfig()
				if err != nil {
					log.Printf("[ERROR]: could not generate config for OCSP responder, reason: %v", err)
					return
				}

				log.Println("[INFO]: responder's config has been successfully generated")
				if err := w.TaskScheduler.RemoveJob(w.ConfigJob.ID()); err != nil {
					return
				}
				return
			},
		),
	)
	if err != nil {
		log.Fatalf("[FATAL]: could not start the generate OCSP responder config job: %v", err)
		return err
	}
	log.Printf("[INFO]: new generate OCSP responder config job has been scheduled every %d minute", 1)
	return nil
}
