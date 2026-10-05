package commands

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/open-uem/utils"
	"github.com/urfave/cli/v2"
	"software.sslmate.com/src/go-pkcs12"
)

func CreateCodeSigningCertificate() *cli.Command {
	return &cli.Command{
		Name:   "code-signing-cert",
		Usage:  "Generate a certicate file and a private key file both in PEM format to sign OpenUEM installers (testing only)",
		Action: generateCodeSigningCert,
		Flags:  generateCodeSigningCertFlags(),
	}
}

func generateCodeSigningCert(cCtx *cli.Context) error {
	log.Printf("... reading CA cert PEM file")
	caCert, err := utils.ReadPEMCertificate(cCtx.String("cacert"))
	if err != nil {
		return err
	}

	log.Printf("... reading CA private key PEM file")
	caPrivKey, err := utils.ReadPEMPrivateKey(cCtx.String("cakey"))
	if err != nil {
		return err
	}

	log.Printf("... generating private key")
	certPrivKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return err
	}

	log.Printf("... generating certificate's template")
	cert, err := NewX509CodeSigningCertificate(cCtx, caCert)
	if err != nil {
		return err
	}

	log.Printf("... creating certificate")
	certBytes, err := x509.CreateCertificate(rand.Reader, cert, caCert, &certPrivKey.PublicKey, caPrivKey)
	if err != nil {
		return err
	}

	log.Printf("... parsing certificate")
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

	path := cCtx.String("dst")
	if path == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return err
		}
		path = filepath.Join(cwd, "certificates")
	}

	err = utils.SavePFX(pfxBytes, filepath.Join(path, cCtx.String("filename")+".pfx"))
	if err != nil {
		return err
	}

	log.Println("✅ Done! Your code signing certificate as a PFX file has been generated")
	return nil
}

func NewX509CodeSigningCertificate(cCtx *cli.Context, serverCert *x509.Certificate) (*x509.Certificate, error) {
	serialNumber, err := utils.GenerateSerialNumber()
	if err != nil {
		return nil, err
	}

	ocspServers := []string{}
	for _, ocsp := range strings.Split(cCtx.String("ocsp"), ",") {
		ocspServers = append(ocspServers, strings.TrimSpace(ocsp))
	}

	return &x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			CommonName:         cCtx.String("name"),
			OrganizationalUnit: []string{cCtx.String("type")},
			Organization:       []string{cCtx.String("org")},
			Country:            []string{cCtx.String("country")},
			Province:           []string{cCtx.String("province")},
			Locality:           []string{cCtx.String("locality")},
			StreetAddress:      []string{cCtx.String("address")},
			PostalCode:         []string{cCtx.String("postal-code")},
		},
		Issuer:      serverCert.Subject,
		NotBefore:   time.Now().Add(-5 * time.Minute).UTC(),
		NotAfter:    time.Now().AddDate(cCtx.Int("years-valid"), cCtx.Int("months-valid"), cCtx.Int("days-valid")),
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageCodeSigning},
		KeyUsage:    x509.KeyUsageDigitalSignature,
		OCSPServer:  ocspServers,
	}, nil
}

func generateCodeSigningCertFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:     "name",
			Usage:    "the common name for this certificate",
			Required: true,
		},
		&cli.StringFlag{
			Name:     "cacert",
			Usage:    "the path to your CA certificate file in PEM format",
			EnvVars:  []string{"CA_CRT_FILENAME"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "cakey",
			Usage:    "the path to your CA private key file in PEM format",
			EnvVars:  []string{"CA_KEY_FILENAME"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "filename",
			Usage:    "filename to be used for certificate and private key files",
			Required: true,
		},
		&cli.StringFlag{
			Name:  "description",
			Value: "",
			Usage: "an optional description for this certificate",
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
			Name:  "dst",
			Usage: "the folder where the certificates will be stored",
		},
		&cli.StringFlag{
			Name:  "pass",
			Usage: "the password that will be asked when the certificates is imported (default: changeit)",
		},
	}
}
