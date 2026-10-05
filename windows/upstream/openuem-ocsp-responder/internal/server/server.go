package server

import (
	"crypto/rsa"
	"crypto/x509"
	"log"
	"net/http"

	"github.com/labstack/echo/v4"
	"github.com/open-uem/openuem-ocsp-responder/internal/models"
	"github.com/open-uem/openuem-ocsp-responder/internal/server/handler"
)

type WebServer struct {
	Handler *handler.Handler
	Server  *http.Server
	Address string
}

func New(m *models.Model, address string, caCert *x509.Certificate, ocspCert *x509.Certificate, ocspKey *rsa.PrivateKey) *WebServer {
	w := WebServer{}
	w.Handler = handler.NewHandler(m, caCert, ocspCert, ocspKey)
	w.Address = address
	return &w
}

func (w *WebServer) Serve() error {
	e := echo.New()
	w.Handler.Register(e)
	w.Server = &http.Server{
		Addr:    w.Address,
		Handler: e,
	}
	// e.Use(middleware.Logger()) // -> TODO set an env variable for debug
	return w.Server.ListenAndServe()
}

func (w *WebServer) Close() {
	if err := w.Server.Close(); err != nil {
		log.Println("[ERROR]: could not shutdown web server")
	}
}
