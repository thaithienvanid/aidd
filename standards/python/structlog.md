+++
id = "python/structlog"
type = "opinionated"
fills = ["observability:logging-library"]
default = true
implements = "observability:Logs"
roles = ["developer", "sre", "reviewer"]
when_changed = ["**/*.py", "pyproject.toml"]
why = "structlog builds each log event as a dictionary that a chain of processors enriches and renders, so the service writes one JSON line per event, with the request's context bound once."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "structlog", registry = "pypi", package = "structlog" }
version_policy = "current_stable"
checked_version = "26.1.0"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pypi.org/pypi/structlog/json"
evidence = '"version":"26.1.0"'
alternatives = ["the Python `logging` module with a JSON formatter"]
status = "active"
enforced_by = [
  { name = "redaction", command = ["uv", "run", "pytest", "tests/test_logging.py"] },
]
+++

# structlog writes the Python service's logs

It answers the logging-library choice of `aidd-team:observability`. structlog is under your choice of the MIT licence or the Apache License 2.0.

## What the team does

- Call `structlog.configure()` once at start. In production, end the processor chain with `structlog.processors.JSONRenderer()` and write to standard out. Use `structlog.dev.ConsoleRenderer()` only when the output is a terminal.
- Put `structlog.contextvars.merge_contextvars` first in the chain. Clear the context at the start of each request, then bind the request id and trace id with `bind_contextvars`.
- Add a processor that masks secret and personal fields, before the renderer.
- Send the records of the standard `logging` module through the same processors with `structlog.stdlib.ProcessorFormatter`, so library logs have the same format.
- Keep `tests/test_logging.py`. It runs the production processors over a nested event with `token` and `email` fields, and checks the JSON line. `structlog.testing.capture_logs` turns the processors off unless the test passes them in.

## What the gate runs

One `[[tests]]` entry runs `tests/test_logging.py`. A field that comes out unmasked, or a line that is not JSON, fails the change.
