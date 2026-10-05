package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	pkcs12 "software.sslmate.com/src/go-pkcs12"
)

// Commander sends a management command for one PC. The real one drives OpenUEM's own console with its administrator certificate,
// so every action goes through the same checks and audit trail OpenUEM already has.
type Commander interface {
	Do(ctx context.Context, id, action string) error
	Actions() []string
}

var uuidRe = regexp.MustCompile(`^[0-9a-fA-F-]{8,64}$`)

// actionRoutes maps a bridge action to OpenUEM's console route (under /tenant/<tenant>/agents/<uuid>/).
var actionRoutes = map[string]string{
	"report":        "forcereport",  // collect and send a fresh inventory now
	"admit":         "admit",        // approve a new PC (it receives its own certificate)
	"restart-agent": "forcerestart", // restart the agent service on the PC
}

type consoleCommander struct {
	base   string // https://console.example:1323
	tenant string
	pfx    string
	pass   string
	ca     string

	mu     sync.Mutex
	client *http.Client
}

func newConsoleCommander(base, tenant, pfxPath, pass, caPath string) (*consoleCommander, error) {
	if base == "" || pfxPath == "" {
		return nil, errors.New("OPENUEM_CONSOLE_URL and OPENUEM_ADMIN_PFX are required for commands")
	}
	return &consoleCommander{base: strings.TrimRight(base, "/"), tenant: tenant, pfx: pfxPath, pass: pass, ca: caPath}, nil
}

func (c *consoleCommander) Actions() []string {
	out := make([]string, 0, len(actionRoutes))
	for k := range actionRoutes {
		out = append(out, k)
	}
	return out
}

func (c *consoleCommander) newClient() (*http.Client, error) {
	data, err := os.ReadFile(c.pfx)
	if err != nil {
		return nil, fmt.Errorf("read administrator certificate: %w", err)
	}
	key, cert, chain, err := pkcs12.DecodeChain(data, c.pass)
	if err != nil {
		return nil, fmt.Errorf("open administrator certificate: %w", err)
	}
	tlsCert := tls.Certificate{PrivateKey: key, Leaf: cert, Certificate: [][]byte{cert.Raw}}
	_ = chain // leaf only: OpenUEM's sign-in port rejects a presented chain
	// Always present the administrator certificate when asked, whatever list of authorities the server names (OpenUEM's sign-in port
	// issues its own certificates and Go would otherwise withhold it).
	cfg := &tls.Config{
		MinVersion:           tls.VersionTLS12,
		GetClientCertificate: func(*tls.CertificateRequestInfo) (*tls.Certificate, error) { return &tlsCert, nil },
	}
	if c.ca != "" {
		pem, err := os.ReadFile(c.ca)
		if err != nil {
			return nil, fmt.Errorf("read CA certificate: %w", err)
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(pem) {
			return nil, errors.New("the CA certificate file has no certificate")
		}
		cfg.RootCAs = pool
	}
	jar, _ := cookiejar.New(nil)
	return &http.Client{Jar: jar, Timeout: 30 * time.Second, Transport: &http.Transport{TLSClientConfig: cfg}}, nil
}

// login signs in with the certificate: /auth on the console port redirects to the certificate port, which sets the session cookie.
func (c *consoleCommander) login(ctx context.Context) error {
	cl, err := c.newClient()
	if err != nil {
		return err
	}
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, c.base+"/auth", nil)
	res, err := cl.Do(req)
	if err != nil {
		return fmt.Errorf("console sign-in: %w", err)
	}
	io.Copy(io.Discard, res.Body)
	res.Body.Close()
	u, _ := url.Parse(c.base)
	hasSession := false
	for _, ck := range cl.Jar.Cookies(u) {
		if ck.Name == "session" {
			hasSession = true
		}
	}
	if !hasSession {
		return errors.New("the console did not accept the administrator certificate")
	}
	c.client = cl
	return nil
}

func (c *consoleCommander) csrf() string {
	u, _ := url.Parse(c.base)
	for _, ck := range c.client.Jar.Cookies(u) {
		if ck.Name == "_csrf" {
			return ck.Value
		}
	}
	return ""
}

func (c *consoleCommander) Do(ctx context.Context, id, action string) error {
	route, ok := actionRoutes[action]
	if !ok {
		return fmt.Errorf("unknown action %q", action)
	}
	if !uuidRe.MatchString(id) {
		return errors.New("invalid device id")
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	for attempt := 0; attempt < 2; attempt++ {
		if c.client == nil || attempt > 0 {
			if err := c.login(ctx); err != nil {
				return err
			}
		}
		// A page request first, so the CSRF cookie exists and the session is proven live.
		warm, _ := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("%s/tenant/%s/site/1/dashboard", c.base, c.tenant), nil)
		if res, err := c.client.Do(warm); err == nil {
			io.Copy(io.Discard, res.Body)
			res.Body.Close()
		}
		req, _ := http.NewRequestWithContext(ctx, http.MethodPost, fmt.Sprintf("%s/tenant/%s/agents/%s/%s", c.base, c.tenant, id, route), nil)
		req.Header.Set("X-CSRF-Token", c.csrf())
		req.Header.Set("HX-Request", "true")
		res, err := c.client.Do(req)
		if err != nil {
			return fmt.Errorf("console request: %w", err)
		}
		body, _ := io.ReadAll(io.LimitReader(res.Body, 64<<10))
		res.Body.Close()
		finalPath := res.Request.URL.Path
		if res.StatusCode == http.StatusOK && !strings.Contains(finalPath, "/login") && !strings.Contains(string(body), "<title>OpenUEM | Login</title>") {
			return nil
		}
		// Signed out (session expired): sign in again and retry once.
		c.client = nil
	}
	return errors.New("the console refused the command")
}
