// ambic-windows-bridge: the link between AMBIC Digital MDM and the Windows (OpenUEM) side.
//
// It lets the AMBIC server show Windows PCs next to tablets and send them commands, without the AMBIC server knowing OpenUEM's database.
//
//	GET  /v1/health
//	GET  /v1/devices                         list of Windows PCs
//	GET  /v1/devices/{id}                    one PC with its drives
//	POST /v1/devices/{id}/commands/{action}  report | admit | restart-agent
//
// Every call except /v1/health needs `Authorization: Bearer <BRIDGE_TOKEN>`. Without a token the bridge refuses to start.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"time"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	token := os.Getenv("BRIDGE_TOKEN")
	if len(token) < 16 {
		log.Fatal("BRIDGE_TOKEN must be set to at least 16 characters")
	}
	dbURL := os.Getenv("OPENUEM_DB_URL")
	if dbURL == "" {
		log.Fatal("OPENUEM_DB_URL is required (read-only access to OpenUEM's database is enough)")
	}
	mins, _ := strconv.Atoi(env("BRIDGE_ONLINE_MINUTES", "15"))
	store, err := newPGStore(dbURL, time.Duration(mins)*time.Minute)
	if err != nil {
		log.Fatalf("database: %v", err)
	}

	var cmd Commander
	if os.Getenv("OPENUEM_CONSOLE_URL") != "" {
		c, err := newConsoleCommander(os.Getenv("OPENUEM_CONSOLE_URL"), env("OPENUEM_TENANT", "1"),
			os.Getenv("OPENUEM_ADMIN_PFX"), env("OPENUEM_ADMIN_PFX_PASSWORD", "changeit"), os.Getenv("OPENUEM_CA_CERT"))
		if err != nil {
			log.Fatalf("commands: %v", err)
		}
		cmd = c
	} else {
		log.Println("OPENUEM_CONSOLE_URL is not set: the bridge is read-only (no commands)")
	}

	srv := &http.Server{Addr: env("BRIDGE_LISTEN", "127.0.0.1:8470"), Handler: newHandler(store, cmd, token), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		log.Printf("ambic-windows-bridge listening on %s (online window %d min)", srv.Addr, mins)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	srv.Shutdown(ctx)
}
