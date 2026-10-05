package commands

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/open-uem/ent/certificate"
	"github.com/open-uem/nats"
	"github.com/open-uem/openuem-cert-manager/internal/models"
	"github.com/open-uem/utils"
	"github.com/urfave/cli/v2"
	"software.sslmate.com/src/go-pkcs12"
)

func CreateUserCertificate() *cli.Command {
	return &cli.Command{
		Name:   "user-cert",
		Usage:  "Generate a PKCS12 file in PFX format containing the user cert and its associated private key to be used for OpenUEM console mTLS access",
		Action: generateUserCert,
		Flags:  generateUserCertFlags(),
	}
}

func generateUserCert(cCtx *cli.Context) error {
	log.Printf("... connecting to database")
	model, err := models.New(cCtx.String("dburl"))
	if err != nil {
		return fmt.Errorf("could not connect to database, reason: %s", err.Error())
	}

	log.Printf("... reading your CA cert PEM file")
	caCert, err := utils.ReadPEMCertificate(cCtx.String("cacert"))
	if err != nil {
		return err
	}

	log.Printf("... reading your CA private key PEM file")
	caPrivKey, err := utils.ReadPEMPrivateKey(cCtx.String("cakey"))
	if err != nil {
		return err
	}

	log.Printf("... generating your user's private key")
	certPrivKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return err
	}

	log.Printf("... generating your user's certificate template")
	ocspServers := []string{}
	for _, ocsp := range strings.Split(cCtx.String("ocsp"), ",") {
		ocspServers = append(ocspServers, strings.TrimSpace(ocsp))
	}

	certRequest := nats.CertificateRequest{
		Username:       cCtx.String("username"),
		Organization:   cCtx.String("org"),
		Country:        cCtx.String("country"),
		Province:       cCtx.String("province"),
		Locality:       cCtx.String("locality"),
		Address:        cCtx.String("address"),
		PostalCode:     cCtx.String("postal-code"),
		YearsValid:     cCtx.Int("years-valid"),
		MonthsValid:    cCtx.Int("years-valid"),
		DaysValid:      cCtx.Int("days-valid"),
		OCSPResponders: ocspServers,
	}

	cert, err := NewX509UserCertificate(certRequest, caCert)
	if err != nil {
		return err
	}

	log.Printf("... creating your user' certificate")
	certBytes, err := x509.CreateCertificate(rand.Reader, cert, caCert, &certPrivKey.PublicKey, caPrivKey)
	if err != nil {
		return err
	}

	cert, err = x509.ParseCertificate(certBytes)
	if err != nil {
		return err
	}

	log.Printf("... creating your PKCS12 file")

	pass := cCtx.String("pass")
	if pass == "" {
		pass = pkcs12.DefaultPassword
	}
	pfxBytes, err := pkcs12.Modern.Encode(certPrivKey, cert, []*x509.Certificate{caCert}, pass)
	if err != nil {
		return err
	}

	log.Printf("... saving certificate info to database")
	err = model.SaveCertificate(cert.SerialNumber.Int64(), certificate.Type("user"), cCtx.String("description"), cert.NotAfter, true, certRequest.Username)
	if err != nil {
		return err
	}

	log.Printf("... saving your users's PFX file")

	path := cCtx.String("dst")
	if path == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return err
		}
		path = filepath.Join(cwd, "certificates")
	}

	err = utils.SavePFX(pfxBytes, filepath.Join(path, cCtx.String("username")+".pfx"))
	if err != nil {
		return err
	}

	log.Printf("✅ Done! Your user's certificate and its private key has been stored in a pfx file inside the certificates folder\n\n")
	return nil
}

func NewX509UserCertificate(certRequest nats.CertificateRequest, serverCert *x509.Certificate) (*x509.Certificate, error) {
	serialNumber, err := utils.GenerateSerialNumber()
	if err != nil {
		return nil, err
	}
	return &x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			CommonName:    certRequest.Username,
			Organization:  []string{certRequest.Organization},
			Country:       []string{certRequest.Country},
			Province:      []string{certRequest.Province},
			Locality:      []string{certRequest.Locality},
			StreetAddress: []string{certRequest.Address},
			PostalCode:    []string{certRequest.PostalCode},
		},
		Issuer:      serverCert.Subject,
		NotBefore:   time.Now().Add(-5 * time.Minute).UTC(),
		NotAfter:    time.Now().AddDate(certRequest.YearsValid, certRequest.MonthsValid, certRequest.DaysValid),
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
		KeyUsage:    x509.KeyUsageDigitalSignature,
		OCSPServer:  certRequest.OCSPResponders,
	}, nil
}

func generateUserCertFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:    "cacert",
			Value:   "certificates/ca.cer",
			Usage:   "the path to your CA certificate file in PEM format",
			EnvVars: []string{"CA_CRT_FILENAME"},
		},
		&cli.StringFlag{
			Name:    "cakey",
			Value:   "certificates/ca.key",
			Usage:   "the path to your CA private key file in PEM format",
			EnvVars: []string{"CA_KEY_FILENAME"},
		},
		&cli.StringFlag{
			Name:     "username",
			Value:    "",
			Usage:    "OpenUEM username assigned to this certificate",
			Required: true,
		},
		&cli.StringFlag{
			Name:  "org",
			Value: "",
			Usage: "organization name associated with this CA",
		},
		&cli.StringFlag{
			Name:  "country",
			Value: "",
			Usage: "two-letter ISO_3166 country code",
		},
		&cli.StringFlag{
			Name:  "province",
			Value: "",
			Usage: "the province your organization is located",
		},
		&cli.StringFlag{
			Name:  "locality",
			Value: "",
			Usage: "the locality your organization is located",
		},
		&cli.StringFlag{
			Name:  "address",
			Value: "",
			Usage: "the address your organization is located",
		},
		&cli.StringFlag{
			Name:  "postal-code",
			Value: "",
			Usage: "the postal code associated with your organization's address",
		},
		&cli.IntFlag{
			Name:  "years-valid",
			Value: 1,
			Usage: "the number of years for which the certificate will be valid",
		},
		&cli.IntFlag{
			Name:  "months-valid",
			Value: 0,
			Usage: "the number of months for which the certificate will be valid",
		},
		&cli.IntFlag{
			Name:  "days-valid",
			Value: 0,
			Usage: "the number of days for which the certificate will be valid",
		},
		&cli.StringFlag{
			Name:     "ocsp",
			Usage:    "the url of the OCSP responder, e.g https://ocsp.example.com",
			EnvVars:  []string{"OCSP"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "dburl",
			Usage:    "the Postgres database connection url e.g (postgres://user:password@host:5432/openuem)",
			EnvVars:  []string{"DATABASE_URL"},
			Required: true,
		},
		&cli.StringFlag{
			Name:  "description",
			Value: "",
			Usage: "an optional description for this certificate",
		},
		&cli.StringFlag{
			Name:  "dst",
			Usage: "the folder where the certificates will be stored",
		},
		&cli.StringFlag{
			Name:  "pass",
			Usage: "the password that will be asked when the certificates is imported (default: changeit)",
		},
	}
}
