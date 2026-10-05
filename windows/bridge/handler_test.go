package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

type fakeStore struct {
	devices []Device
	err     error
}

func (f fakeStore) List(context.Context) ([]Device, error) { return f.devices, f.err }
func (f fakeStore) Get(_ context.Context, id string) (Device, error) {
	if f.err != nil {
		return Device{}, f.err
	}
	for _, d := range f.devices {
		if d.ID == id {
			return d, nil
		}
	}
	return Device{}, ErrNotFound
}

type fakeCmd struct {
	calls []string
	err   error
}

func (f *fakeCmd) Do(_ context.Context, id, action string) error {
	f.calls = append(f.calls, id+":"+action)
	return f.err
}
func (f *fakeCmd) Actions() []string { return []string{"report", "admit", "restart-agent"} }

const tok = "0123456789abcdef-token"

func do(h http.Handler, method, path, auth string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, nil)
	if auth != "" {
		r.Header.Set("Authorization", "Bearer "+auth)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func sample() []Device {
	return []Device{{ID: "11111111-aaaa", Hostname: "BILLING-PC", Online: true, Status: "Enabled", OSEdition: "Professional"}}
}

func TestEveryRouteButHealthNeedsTheToken(t *testing.T) {
	h := newHandler(fakeStore{devices: sample()}, &fakeCmd{}, tok)
	for _, c := range []struct{ m, p string }{{"GET", "/v1/devices"}, {"GET", "/v1/devices/11111111-aaaa"}, {"POST", "/v1/devices/11111111-aaaa/commands/report"}} {
		if w := do(h, c.m, c.p, ""); w.Code != 401 {
			t.Errorf("%s %s without a token: %d", c.m, c.p, w.Code)
		}
		if w := do(h, c.m, c.p, "wrong-token-wrong-token"); w.Code != 401 {
			t.Errorf("%s %s with a wrong token: %d", c.m, c.p, w.Code)
		}
	}
	if w := do(h, "GET", "/v1/health", ""); w.Code != 200 {
		t.Errorf("health should be open, got %d", w.Code)
	}
}

func TestListAndDetail(t *testing.T) {
	h := newHandler(fakeStore{devices: sample()}, &fakeCmd{}, tok)
	w := do(h, "GET", "/v1/devices", tok)
	var out struct {
		Devices  []Device `json:"devices"`
		Commands []string `json:"commands"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil || w.Code != 200 {
		t.Fatalf("list: %d %v", w.Code, err)
	}
	if len(out.Devices) != 1 || out.Devices[0].Hostname != "BILLING-PC" {
		t.Errorf("unexpected list %+v", out.Devices)
	}
	if strings.Join(out.Commands, ",") != "admit,report,restart-agent" {
		t.Errorf("commands should be listed sorted: %v", out.Commands)
	}
	if w := do(h, "GET", "/v1/devices/11111111-aaaa", tok); w.Code != 200 {
		t.Errorf("detail: %d", w.Code)
	}
	if w := do(h, "GET", "/v1/devices/does-not-exist", tok); w.Code != 404 {
		t.Errorf("unknown device should be 404, got %d", w.Code)
	}
}

func TestDatabaseFailureIsAGatewayErrorWithoutLeakingDetail(t *testing.T) {
	h := newHandler(fakeStore{err: errors.New("password authentication failed for user openuem")}, &fakeCmd{}, tok)
	w := do(h, "GET", "/v1/devices", tok)
	if w.Code != 502 || strings.Contains(w.Body.String(), "openuem") {
		t.Errorf("want a plain 502, got %d %s", w.Code, w.Body.String())
	}
}

func TestCommandsOnlyForKnownDevicesAndActions(t *testing.T) {
	cmd := &fakeCmd{}
	h := newHandler(fakeStore{devices: sample()}, cmd, tok)
	if w := do(h, "POST", "/v1/devices/11111111-aaaa/commands/report", tok); w.Code != 200 {
		t.Fatalf("report: %d", w.Code)
	}
	if len(cmd.calls) != 1 || cmd.calls[0] != "11111111-aaaa:report" {
		t.Errorf("calls %v", cmd.calls)
	}
	if w := do(h, "POST", "/v1/devices/unknown-id/commands/report", tok); w.Code != 404 {
		t.Errorf("unknown device: %d", w.Code)
	}
	if w := do(h, "POST", "/v1/devices/11111111-aaaa/commands/format-disk", tok); w.Code != 400 {
		t.Errorf("unknown action must be refused, got %d", w.Code)
	}
	if len(cmd.calls) != 1 {
		t.Errorf("a refused request must not reach the console: %v", cmd.calls)
	}
}

func TestCommandFailureIsReported(t *testing.T) {
	h := newHandler(fakeStore{devices: sample()}, &fakeCmd{err: errors.New("the console refused the command")}, tok)
	w := do(h, "POST", "/v1/devices/11111111-aaaa/commands/admit", tok)
	if w.Code != 502 || !strings.Contains(w.Body.String(), "refused") {
		t.Errorf("got %d %s", w.Code, w.Body.String())
	}
}

func TestReadOnlyWhenNoCommander(t *testing.T) {
	h := newHandler(fakeStore{devices: sample()}, nil, tok)
	if w := do(h, "POST", "/v1/devices/11111111-aaaa/commands/report", tok); w.Code != 501 {
		t.Errorf("want 501, got %d", w.Code)
	}
	w := do(h, "GET", "/v1/devices", tok)
	if !strings.Contains(w.Body.String(), `"commands":[]`) {
		t.Errorf("no commands should be advertised: %s", w.Body.String())
	}
}

func TestCommanderRejectsBadIdsAndActionsBeforeAnyNetwork(t *testing.T) {
	c, err := newConsoleCommander("https://console.invalid:1323", "1", "none.pfx", "x", "")
	if err != nil {
		t.Fatal(err)
	}
	if err := c.Do(context.Background(), "../../etc/passwd", "report"); err == nil || !strings.Contains(err.Error(), "invalid device id") {
		t.Errorf("path-like id must be refused: %v", err)
	}
	if err := c.Do(context.Background(), "11111111-aaaa", "wipe"); err == nil || !strings.Contains(err.Error(), "unknown action") {
		t.Errorf("unknown action must be refused: %v", err)
	}
}

// Integration: set BRIDGE_TEST_DB to a read-only URL of an OpenUEM database that has at least one Windows PC.
func TestAgainstRealOpenUEMDatabase(t *testing.T) {
	url := os.Getenv("BRIDGE_TEST_DB")
	if url == "" {
		t.Skip("BRIDGE_TEST_DB not set")
	}
	s, err := newPGStore(url, 15*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	list, err := s.List(ctx)
	if err != nil || len(list) == 0 {
		t.Fatalf("list: %v (%d)", err, len(list))
	}
	d, err := s.Get(ctx, list[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("%s | %s %s | %s | %d MB | apps %d | disks %d | last %s", d.Hostname, d.OSDescription, d.OSVersion, d.Model, d.MemoryMB, d.AppCount, len(d.Disks), time.UnixMilli(d.LastContactMs).UTC())
	if d.Hostname == "" || d.OSVersion == "" || d.AppCount == 0 {
		t.Errorf("expected inventory to be present: %+v", d)
	}
}
