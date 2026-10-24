---
id: go/net-http
type: opinionated
fills: [apis-and-services:api-framework]
default: true
implements: product-defaults:operability
roles: [architect, developer, reviewer]
when_changed: ["**/*.go"]
why: "Since Go 1.22 the standard ServeMux routes by method and path wildcard, so a Go service serves its API with no router dependency and upgrades with the toolchain."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pkg.go.dev/net/http
evidence: "Patterns can match the method, host and path of a request."
alternatives: [chi, Echo, Gin]
status: active
enforced_by:
  - name: server-timeouts
    command: [go, run, github.com/securego/gosec/v2/cmd/gosec@v2.29.0, "-include=G112,G114", "./..."]
---

# net/http serves the Go API

It answers the api-framework choice of `aidd-team:apis-and-services`. Its version is the Go toolchain's, which `go/go-version` pins.

## What the team does

- Route with `http.ServeMux` patterns such as `GET /items/{id}`, and read each wildcard with `r.PathValue`.
- Serve through an `http.Server` with `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, and `IdleTimeout` set. Never call `http.ListenAndServe`, which sets none.
- Cap each request body with `http.MaxBytesReader`.
- On SIGTERM, call `Server.Shutdown` with a deadline.
- Write middleware as a plain `func(http.Handler) http.Handler`.

## What the gate runs

One `tests` entry runs gosec, at the version its command pins, with only its rules G112 and G114, so it needs no linter set up. They flag a server that sets no header timeout, or that serves with no timeouts at all.
