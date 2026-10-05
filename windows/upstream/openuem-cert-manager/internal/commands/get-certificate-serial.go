package commands

import (
	"encoding/hex"
	"fmt"

	"github.com/open-uem/utils"
	"github.com/urfave/cli/v2"
)

func GetCertificateSerial() *cli.Command {
	return &cli.Command{
		Name:   "get-certificate-serial",
		Usage:  "Get a certificate serial number",
		Action: getCertificateSerial,
		Flags:  getCertificateSerialFlags(),
	}
}

func getCertificateSerialFlags() []cli.Flag {
	return []cli.Flag{
		&cli.StringFlag{
			Name:     "path",
			Usage:    "the path to the certificate",
			Required: true,
		},
	}
}

func getCertificateSerial(cCtx *cli.Context) error {
	cert, err := utils.ReadPEMCertificate(cCtx.String("path"))
	if err != nil {
		return err
	}

	fmt.Println(hex.EncodeToString(cert.SerialNumber.Bytes()))
	return nil
}
