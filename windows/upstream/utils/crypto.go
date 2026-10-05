package utils

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"math"
	"math/big"
	"os"
)

func GenerateSerialNumber() (*big.Int, error) {
	serialNumber, err := rand.Int(rand.Reader, new(big.Int).SetInt64(math.MaxInt64))
	if err != nil {
		return nil, err
	}
	return serialNumber, nil
}

func ReadPEMCertificate(path string) (*x509.Certificate, error) {
	certBytes, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	certBlock, _ := pem.Decode(certBytes)
	if certBlock.Type != "CERTIFICATE" || certBlock.Bytes == nil {
		return nil, fmt.Errorf("file does not content a certificate")
	}

	cert, err := x509.ParseCertificate(certBlock.Bytes)
	if err != nil {
		return nil, err
	}

	return cert, nil
}

func ReadPEMPrivateKey(path string) (*rsa.PrivateKey, error) {
	privKeyBytes, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	privKeyBlock, _ := pem.Decode(privKeyBytes)
	if privKeyBlock.Type != "RSA PRIVATE KEY" || privKeyBlock.Bytes == nil {
		return nil, fmt.Errorf("file does not content a private key")
	}

	privKey, err := x509.ParsePKCS1PrivateKey(privKeyBlock.Bytes)
	if err != nil {
		return nil, err
	}
	return privKey, nil
}

func savePEM(buf *bytes.Buffer, path string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = f.Write(buf.Bytes())
	if err != nil {
		return err
	}

	return nil
}

func SavePFX(b []byte, path string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = f.Write(b)
	if err != nil {
		return err
	}

	return nil
}

func SaveCertificate(certBytes []byte, path string) error {
	certPEM := new(bytes.Buffer)
	if err := pem.Encode(certPEM, &pem.Block{
		Type:  "CERTIFICATE",
		Bytes: certBytes,
	}); err != nil {
		return err
	}

	if err := savePEM(certPEM, path); err != nil {
		return err
	}

	return nil
}

func SavePrivateKey(certPrivKey *rsa.PrivateKey, path string) error {
	certPrivKeyPEM := new(bytes.Buffer)
	if err := pem.Encode(certPrivKeyPEM, &pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(certPrivKey),
	}); err != nil {
		return err
	}

	if err := savePEM(certPrivKeyPEM, path); err != nil {
		return err
	}

	return nil
}

func GetSHA256Sum(filepath string) ([]byte, error) {
	f, err := os.Open(filepath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return nil, err
	}

	return h.Sum(nil), nil
}

// Ref: https://gist.github.com/dopey/c69559607800d2f2f90b1b1ed4e550fb
func GenerateRandomPIN(length int) (string, error) {
	const numbers = "0123456789"
	pin := make([]byte, length)

	for i := range length {
		num, err := rand.Int(rand.Reader, big.NewInt(int64(len(numbers))))
		if err != nil {
			return "", err
		}
		pin[i] = numbers[num.Int64()]
	}

	return string(pin), nil
}

// Reference: https://www.twilio.com/en-us/blog/developers/community/encrypt-and-decrypt-data-in-go-with-aes-256
func EncryptSensitiveField(plaintext string, key string) (string, error) {
	block, err := aes.NewCipher([]byte(key))
	if err != nil {
		log.Printf("[ERROR]: error creating aes block cipher, reason: %v", err)
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		log.Printf("[ERROR]: error setting gcm mode, reason: %v", err)
		return "", err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		log.Printf("[ERROR]: error  generating the nonce, reason: %v", err)
		return "", err
	}

	ciphertext := gcm.Seal(nonce, nonce, []byte(plaintext), nil)
	enc := hex.EncodeToString(ciphertext)

	return enc, nil
}

// Reference: https://www.twilio.com/en-us/blog/developers/community/encrypt-and-decrypt-data-in-go-with-aes-256
func DecryptSensitiveField(enc string, key string) (string, error) {
	block, err := aes.NewCipher([]byte(key))
	if err != nil {
		log.Printf("[ERROR]: error creating aes block cipher, reason: %v", err)
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		log.Printf("[ERROR]: error setting gcm mode, reason: %v", err)
		return "", err
	}

	decodedCipherText, err := hex.DecodeString(enc)
	if err != nil {
		log.Printf("[ERROR]: error decoding hex, reason: %v", err)
		return "", err
	}

	decryptedData, err := gcm.Open(nil, decodedCipherText[:gcm.NonceSize()], decodedCipherText[gcm.NonceSize():], nil)
	if err != nil {
		log.Printf("[ERROR]: error decrypting data, reason: %v", err)
		return "", err
	}

	return string(decryptedData), nil
}

// Reference: https://www.twilio.com/en-us/blog/developers/community/encrypt-and-decrypt-data-in-go-with-aes-256
func IsSensitiveFieldEncrypted(enc string, key string) (bool, error) {
	if enc == "" {
		return false, nil
	}

	block, err := aes.NewCipher([]byte(key))
	if err != nil {
		return false, err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return false, err
	}

	decodedCipherText, err := hex.DecodeString(enc)
	if err != nil {
		return false, nil
	}

	if _, err := gcm.Open(nil, decodedCipherText[:gcm.NonceSize()], decodedCipherText[gcm.NonceSize():], nil); err != nil {
		return false, nil
	}

	return true, nil
}
