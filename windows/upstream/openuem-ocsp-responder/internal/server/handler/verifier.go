package handler

import (
	"bytes"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
	"github.com/open-uem/ent"
	"golang.org/x/crypto/ocsp"
)

var (
	malformedRequest = byte(1)
	internalError    = byte(2)
)

func (h *Handler) Verify(c echo.Context) error {
	var req *ocsp.Request
	var requestBody []byte
	var err error

	if c.Request().Method == "POST" {
		requestBody, err = io.ReadAll(c.Request().Body)
		if err != nil {
			return sendOCSPError(c, http.StatusBadRequest, malformedRequest)
		}
	}

	if c.Request().Method == "GET" {
		uri := c.Request().URL.Path
		if strings.Contains(uri, "health") {
			return healthCheck(c, h)
		}

		requestBody, err = base64.StdEncoding.DecodeString(strings.TrimPrefix(uri, "/"))
		if err != nil {
			return sendOCSPError(c, http.StatusBadRequest, malformedRequest)
		}
	}

	// Parse request
	req, err = ocsp.ParseRequest(requestBody)
	if err != nil {
		return sendOCSPError(c, http.StatusInternalServerError, internalError)
	}

	// Verify issuer name and key hashes
	if err := verifyIssuer(h.CACert, req); err != nil {
		return sendOCSPError(c, http.StatusInternalServerError, malformedRequest)
	}

	// create response template
	responseTemplate := h.createResponseTemplate(req)

	// make a response to return
	response, err := ocsp.CreateResponse(h.CACert, h.OCSPCert, responseTemplate, h.OCSPKey)
	if err != nil {
		return sendOCSPError(c, http.StatusInternalServerError, internalError)
	}

	// send response
	return sendOCSPResponse(c, responseTemplate, response)
}

func sendOCSPError(c echo.Context, code int, status byte) error {
	c.Response().Status = code
	// Reference: https://github.com/cloudflare/cfssl/blob/master/ocsp/responder.go#L33
	c.Response().Write([]byte{0x30, 0x03, 0x0A, 0x01, status})
	return nil
}

func (h *Handler) createResponseTemplate(req *ocsp.Request) ocsp.Response {
	serial := req.SerialNumber

	// construct response template
	responseTemplate := ocsp.Response{
		SerialNumber: req.SerialNumber,
		Certificate:  h.OCSPCert,
		IssuerHash:   req.HashAlgorithm,
		ThisUpdate:   time.Now().Truncate(time.Hour),
		NextUpdate:   time.Now().AddDate(0, 0, 1).UTC(),
	}

	// check if certificate has been revoked querying the database
	revoked, err := h.Model.GetRevoked(serial.Int64())
	if err != nil && !ent.IsNotFound(err) {
		log.Println("... could not check if certificate has been revoked")
		responseTemplate.Status = ocsp.Unknown
	} else {
		// complete response based on status
		if revoked != nil {
			responseTemplate.Status = ocsp.Revoked
			responseTemplate.RevocationReason = revoked.Reason
			responseTemplate.RevokedAt = time.Now()
		} else {
			responseTemplate.Status = ocsp.Good
		}
	}

	return responseTemplate
}

func sendOCSPResponse(c echo.Context, responseTemplate ocsp.Response, response []byte) error {
	c.Response().Header().Add("Content-Type", "application/ocsp-response")
	c.Response().Header().Add("Last-Modified", responseTemplate.ThisUpdate.Format(time.RFC1123))
	c.Response().Header().Add("Expires", responseTemplate.NextUpdate.Format(time.RFC1123))
	c.Response().Header().Set("Cache-Control", fmt.Sprintf("max-age=%d, public, no-transform, must-revalidate", 0))
	c.Response().Header().Add("ETag", fmt.Sprintf("\"%X\"", sha256.Sum256(responseTemplate.Raw)))
	c.Response().Status = http.StatusOK
	c.Response().Write(response)
	return nil
}

func healthCheck(c echo.Context, h *Handler) error {
	if _, err := h.Model.GetRevoked(0); err != nil {
		if ent.IsNotFound(err) {
			return c.String(http.StatusOK, "OCSP Responder is healthy")
		} else {
			return c.String(http.StatusInternalServerError, "OCSP Responder is not healthy")
		}
	}
	return c.String(http.StatusOK, "OCSP Responder is healthy")
}

/* MIT License

Copyright (c) 2016 SMFS Inc. DBA GRIMM https://grimm-co.com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE. */

func verifyIssuer(caCert *x509.Certificate, req *ocsp.Request) error {
	h := req.HashAlgorithm.New()
	h.Write(caCert.RawSubject)
	if !bytes.Equal(h.Sum(nil), req.IssuerNameHash) {
		log.Println("[INFO]: issuer name does not match")
		return errors.New("issuer name does not match")
	}
	h.Reset()
	var publicKeyInfo struct {
		Algorithm pkix.AlgorithmIdentifier
		PublicKey asn1.BitString
	}
	if _, err := asn1.Unmarshal(caCert.RawSubjectPublicKeyInfo, &publicKeyInfo); err != nil {
		log.Println("[INFO]: cannot unmarshall caCert.RawSubjectPublicKeyInfo")
		return err
	}
	h.Write(publicKeyInfo.PublicKey.RightAlign())
	if !bytes.Equal(h.Sum(nil), req.IssuerKeyHash) {
		log.Println("[INFO]: issuer key hash does not match")
		return errors.New("issuer key hash does not match")
	}
	return nil
}
