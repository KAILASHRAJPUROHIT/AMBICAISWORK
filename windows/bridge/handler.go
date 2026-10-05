package main

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"sort"
	"strings"
	"time"
)

func newHandler(store Store, cmd Commander, token string) http.Handler {
	mux := http.NewServeMux()

	writeJSON := func(w http.ResponseWriter, status int, v any) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(status)
		json.NewEncoder(w).Encode(v)
	}
	fail := func(w http.ResponseWriter, status int, msg string) {
		writeJSON(w, status, map[string]string{"error": msg})
	}

	mux.HandleFunc("GET /v1/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]any{"ok": true, "commands": cmd != nil})
	})

	mux.HandleFunc("GET /v1/devices", func(w http.ResponseWriter, r *http.Request) {
		list, err := store.List(r.Context())
		if err != nil {
			log.Printf("list: %v", err)
			fail(w, 502, "the Windows database could not be read")
			return
		}
		writeJSON(w, 200, map[string]any{"devices": list, "commands": actionsOf(cmd)})
	})

	mux.HandleFunc("GET /v1/devices/{id}", func(w http.ResponseWriter, r *http.Request) {
		d, err := store.Get(r.Context(), r.PathValue("id"))
		if errors.Is(err, ErrNotFound) {
			fail(w, 404, "no such Windows PC")
			return
		}
		if err != nil {
			log.Printf("get: %v", err)
			fail(w, 502, "the Windows database could not be read")
			return
		}
		writeJSON(w, 200, map[string]any{"device": d, "commands": actionsOf(cmd)})
	})

	mux.HandleFunc("POST /v1/devices/{id}/commands/{action}", func(w http.ResponseWriter, r *http.Request) {
		if cmd == nil {
			fail(w, 501, "commands are not configured on the Windows bridge")
			return
		}
		id, action := r.PathValue("id"), r.PathValue("action")
		if _, err := store.Get(r.Context(), id); err != nil { // only ever act on a PC we know about
			if errors.Is(err, ErrNotFound) {
				fail(w, 404, "no such Windows PC")
				return
			}
			fail(w, 502, "the Windows database could not be read")
			return
		}
		known := false
		for _, a := range cmd.Actions() {
			if a == action {
				known = true
			}
		}
		if !known {
			fail(w, 400, "unknown action")
			return
		}
		if err := cmd.Do(r.Context(), id, action); err != nil {
			log.Printf("command %s on %s: %v", action, id, err)
			fail(w, 502, err.Error())
			return
		}
		log.Printf("command %s sent to %s", action, id)
		writeJSON(w, 200, map[string]any{"ok": true, "action": action, "at": time.Now().UnixMilli()})
	})

	return authenticate(token, mux)
}

func actionsOf(c Commander) []string {
	if c == nil {
		return []string{}
	}
	a := c.Actions()
	sort.Strings(a)
	return a
}

// authenticate requires the shared secret on every route except health. The comparison is constant-time.
func authenticate(token string, next http.Handler) http.Handler {
	want := []byte(token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/health" {
			next.ServeHTTP(w, r)
			return
		}
		got := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		if subtle.ConstantTimeCompare([]byte(got), want) != 1 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(`{"error":"unauthorized"}`))
			return
		}
		next.ServeHTTP(w, r)
	})
}
