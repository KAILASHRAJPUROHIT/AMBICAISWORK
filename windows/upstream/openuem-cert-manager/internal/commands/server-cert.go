package commands

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"fmt"
	"log"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/chmike/domain"
	"github.com/open-uem/ent/certificate"
	"github.com/open-uem/openuem-cert-manager/internal/models"
	"github.com/open-uem/utils"
	"github.com/urfave/cli/v2"
)

func CreateServerCertificate() *cli.Command {
	return &cli.Command{
		Name:   "server-cert",
		Usage:  "Generate a server cert signed by your Certificate Authority",
		Action: generateServerCert,
		Flags:  generateServerCertFlags(),
	}
}

func generateServerCert(cCtx *cli.Context) error {
	log.Printf("... connecting to database")
	model, err := models.New(cCtx.String("dburl"))
	if err != nil {
		return fmt.Errorf("could not connect to database, reason: %s", err.Error())
	}

	log.Printf("... validating your DNS names")

	dnsNames, err := validateDNSNames(cCtx.String("dns-names"))
	if err != nil {
		return err
	}

	path := cCtx.String("dst")
	if path == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return err
		}
		path = filepath.Join(cwd, "certificates")
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

	log.Printf("... generating your server certificate and its private key")

	cert, err := NewX509Certificate(cCtx, dnsNames, caCert)
	if err != nil {
		return err
	}

	certPrivKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return err
	}

	log.Printf("... creating your server certificate")

	certBytes, err := x509.CreateCertificate(rand.Reader, cert, caCert, &certPrivKey.PublicKey, caPrivKey)
	if err != nil {
		return err
	}

	log.Printf("... saving your server certificate")

	if err := utils.SaveCertificate(certBytes, filepath.Join(path, cCtx.String("filename")+".cer")); err != nil {
		return err
	}

	log.Printf("... saving your private key")

	if err := utils.SavePrivateKey(certPrivKey, filepath.Join(path, cCtx.String("filename")+".key")); err != nil {
		return err
	}

	log.Printf("... saving certificate info to database")
	err = model.SaveCertificate(cert.SerialNumber.Int64(), certificate.Type(cCtx.String("type")), cCtx.String("description"), cert.NotAfter, false, "")
	if err != nil {
		return err
	}

	log.Printf("✅ Done! Your server certificate and its private key has been stored in the certificates folder. Create a backup of these files\n\n")
	return nil
}

func NewX509Certificate(cCtx *cli.Context, names []string, caCert *x509.Certificate) (*x509.Certificate, error) {
	serialNumber, err := utils.GenerateSerialNumber()
	if err != nil {
		return nil, err
	}

	extKeyUsage := []x509.ExtKeyUsage{}
	ocspServers := []string{}
	if cCtx.Bool("sign-ocsp") {
		extKeyUsage = append(extKeyUsage, x509.ExtKeyUsageOCSPSigning)
	} else {
		extKeyUsage = append(extKeyUsage, x509.ExtKeyUsageServerAuth)
		if cCtx.Bool("client-too") {
			extKeyUsage = append(extKeyUsage, x509.ExtKeyUsageClientAuth)
		}

		for _, ocsp := range strings.Split(cCtx.String("ocsp"), ",") {
			ocspServers = append(ocspServers, strings.TrimSpace(ocsp))
		}
	}

	return &x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			CommonName:    cCtx.String("name"),
			Organization:  []string{cCtx.String("org")},
			Country:       []string{cCtx.String("country")},
			Province:      []string{cCtx.String("province")},
			Locality:      []string{cCtx.String("locality")},
			StreetAddress: []string{cCtx.String("address")},
			PostalCode:    []string{cCtx.String("postal-code")},
		},
		Issuer:      caCert.Subject,
		DNSNames:    names,
		NotBefore:   time.Now().Add(-5 * time.Minute).UTC(),
		NotAfter:    time.Now().AddDate(cCtx.Int("years-valid"), cCtx.Int("months-valid"), cCtx.Int("days-valid")),
		ExtKeyUsage: extKeyUsage,
		KeyUsage:    x509.KeyUsageDigitalSignature,
		OCSPServer:  ocspServers,
	}, nil
}

func validateDNSNames(dnsNames string) ([]string, error) {
	names := []string{}
	for _, name := range strings.Split(dnsNames, ",") {
		host := ""
		if !strings.Contains(name, ":") {
			host = name
		} else {
			u, err := url.Parse(name)
			if err != nil {
				return nil, err
			}

			host, _, err = net.SplitHostPort(u.Host)
			if err != nil {
				return nil, err
			}

			name = strings.TrimPrefix(host, "*.")
			if err := domain.Check(name); err != nil {
				return nil, err
			}
		}

		names = append(names, host)
	}
	return names, nil
}

func generateServerCertFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:     "name",
			Usage:    "the common name for this certificate",
			Required: true,
		},
		&cli.StringFlag{
			Name:  "cacert",
			Value: "certificates/ca.cer",
			Usage: "the path to your CA certificate file in PEM format",
		},
		&cli.StringFlag{
			Name:  "cakey",
			Value: "certificates/ca.key",
			Usage: "the path to your CA private key file in PEM format",
		},
		&cli.StringFlag{
			Name:  "dns-names",
			Value: "localhost",
			Usage: "comma-separated string containing the DNS names associated with this server e.g example.com,test.example.com (Subject Alternative Name)",
		},
		&cli.StringFlag{
			Name:  "org",
			Usage: "organization name associated with this CA",
		},
		&cli.StringFlag{
			Name:  "country",
			Usage: "two-letter ISO_3166 country code",
		},
		&cli.StringFlag{
			Name:  "province",
			Usage: "the province your organization is located",
		},
		&cli.StringFlag{
			Name:  "locality",
			Usage: "the locality your organization is located",
		},
		&cli.StringFlag{
			Name:  "address",
			Usage: "the address your organization is located",
		},
		&cli.StringFlag{
			Name:  "postal-code",
			Usage: "the postal code associated with your organization's address",
		},
		&cli.IntFlag{
			Name:  "years-valid",
			Usage: "the number of years for which the certificate will be valid",
		},
		&cli.IntFlag{
			Name:  "months-valid",
			Usage: "the number of months for which the certificate will be valid",
		},
		&cli.IntFlag{
			Name:  "days-valid",
			Usage: "the number of days for which the certificate will be valid",
		},
		&cli.StringFlag{
			Name:     "filename",
			Usage:    "the name to be used for the certificate and private key files",
			Required: true,
		},
		&cli.StringFlag{
			Name:     "ocsp",
			Usage:    "comma-separated string containing the OCSP responders used to validate certificates, e.g http://ocsp1.example.com,http://ocsp2.example.com",
			Required: true,
		},
		&cli.BoolFlag{
			Name:  "sign-ocsp",
			Usage: "allow this certificate to sign OCSP requests",
		},
		&cli.BoolFlag{
			Name:  "client-too",
			Usage: "the certificate will be used for client authentication too",
			Value: false,
		},
		&cli.StringFlag{
			Name:  "description",
			Value: "",
			Usage: "an optional description for this certificate",
		},
		&cli.StringFlag{
			Name:     "dburl",
			Usage:    "the Postgres database connection url e.g (postgres://user:password@host:5432/openuem)",
			EnvVars:  []string{"DATABASE_URL"},
			Required: true,
		},
		&cli.StringFlag{
			Name:  "dst",
			Usage: "the folder where the certificates will be stored",
		},
		&cli.StringFlag{
			Name:     "type",
			Usage:    "OpenUEM client type assigned to this certificate (one of 'console', 'proxy', 'ocsp' or 'nats')",
			Required: true,
		},
	}
}
