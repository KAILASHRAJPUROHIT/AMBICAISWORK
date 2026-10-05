package handler

import (
	"crypto/rsa"
	"crypto/x509"

	"github.com/open-uem/openuem-ocsp-responder/internal/models"
)

type Handler struct {
	Model    *models.Model
	CACert   *x509.Certificate
	OCSPCert *x509.Certificate
	OCSPKey  *rsa.PrivateKey
}

func NewHandler(model *models.Model, caCert *x509.Certificate, ocspCert *x509.Certificate, ocspKey *rsa.PrivateKey) *Handler {
	return &Handler{
		Model:    model,
		CACert:   caCert,
		OCSPCert: ocspCert,
		OCSPKey:  ocspKey,
	}
}
