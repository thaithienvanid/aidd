+++
id = "go/slog"
type = "opinionated"
fills = ["observability:logging-library"]
default = true
implements = "observability:Logs"
roles = ["developer", "sre", "reviewer"]
when_changed = ["**/*.go"]
why = "log/slog is Go's standard structured logger: its JSONHandler writes one JSON object per record, and every library can log through the same handler without a dependency."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pkg.go.dev/log/slog"
evidence = "Package slog provides structured logging, in which log records include a message, a severity level, and various other attributes expressed as key-value pairs."
alternatives = ["zap", "zerolog"]
status = "active"
enforced_by = [
  { name = "vet", command = ["go", "vet", "-slog", "./..."] },
]
+++

# slog writes the Go service's logs

It answers the logging-library choice of `aidd-team:observability`. Its version is the Go toolchain's, which `go/go-version` pins.

## What the team does

- At start, build one `slog.New(slog.NewJSONHandler(os.Stdout, opts))` and make it the default with `slog.SetDefault`.
- Set the level from config through a `slog.LevelVar`, so it can change without a restart.
- Prefer typed attributes (`slog.String`, `slog.Int`) or `LogAttrs`, so a key never goes without its value.
- Give each type that holds a secret a `LogValue` method that redacts it.
- Log with the `Context` methods, such as `InfoContext`, so the handler can add the trace id.

## What the gate runs

One `[[tests]]` entry runs `go vet -slog ./...`. It reports a slog call whose keys and values do not pair up.
