package commands

import (
	"fmt"
	"log"
	"strconv"

	"github.com/open-uem/openuem-cert-manager/internal/models"
	"github.com/urfave/cli/v2"
)

func RevokeCertificate() *cli.Command {
	return &cli.Command{
		Name:   "revoke",
		Usage:  "Revoke a certificate identified by its serial number and store the revocation information in database",
		Action: revokeCert,
		Flags:  revokeCertFlags(),
	}
}

func revokeCertFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:     "serial",
			Usage:    "a 16 characters string in hexadecimal format containing the serial number that identifies the certificate to be revoked e.g (feeddeadbeef1234)",
			EnvVars:  []string{"CERT_SERIAL"},
			Required: true,
		},
		&cli.StringFlag{
			Name:     "dburl",
			Usage:    "the Postgres database connection url e.g (postgres://user:password@host:5432/openuem)",
			EnvVars:  []string{"DATABASE_URL"},
			Required: true,
		},
		&cli.IntFlag{
			Name:    "reason",
			Value:   0,
			Usage:   "a number indicating the reason why this digital certificate has to be revoked. These are the possible reasons: 0 - Unspecified, 1 - KeyCompromise, 2 - CACompromise, 4 - Superseded, 5 - CessationOfOperation, 6 - CertificateHold, 8 - RemoveFromCRL, 9 - PrivilegeWithdrawn, 10 - AACompromise",
			EnvVars: []string{"REVOCATION_REASON"},
		},
		&cli.StringFlag{
			Name:    "info",
			Value:   "",
			Usage:   "a text including more information about the revocation",
			EnvVars: []string{"REVOCATION_INFO"},
		},
	}
}

func revokeCert(cCtx *cli.Context) error {
	model, err := models.New(cCtx.String("dburl"))
	if err != nil {
		return fmt.Errorf("could not connect to database, reason: %s", err.Error())
	}
	log.Printf("... connected to database")

	serial, err := strconv.ParseInt("0x"+cCtx.String("serial"), 0, 64)
	if err != nil {
		return fmt.Errorf("could not parse the certificate serial number, reason: %s", err.Error())
	}
	log.Printf("... certificate serial number parsed successfully")

	reason := cCtx.Int("reason")
	if reason < 0 || reason == 7 || reason > 10 {
		return fmt.Errorf("invalid reason")
	}

	if err := model.AddRevocation(serial, reason, cCtx.String("info")); err != nil {
		return fmt.Errorf("could not save the revoked certificate in the database, reason: %s", err.Error())
	}
	log.Printf("... saving revocation information to the database")

	model.Close()
	log.Printf("✅ Done! Your certificate has been revoked and its serial number has been added to a new CRL file\n\n")
	return nil
}
