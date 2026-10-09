+++
id = "go/golangci-lint"
type = "opinionated"
fills = ["ci-pipeline:linter", "ci-pipeline:formatter"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.go", "go.mod", "go.sum", ".golangci.yml", ".golangci.yaml", ".golangci.toml"]
why = "golangci-lint brings go vet, staticcheck, gosec, and over a hundred more linters into one run, and its gofmt and goimports formatters check the layout while skipping vendor/ and testdata/, all from one configuration file."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "golangci-lint", registry = "github", package = "golangci/golangci-lint" }
version_policy = "current_stable"
checked_version = "v2.14.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "v2.14.0"
source = "https://golangci-lint.run/docs/welcome/install/local/"
evidence = "We recommend using binary installation."
alternatives = ["staticcheck with gofmt", "go vet with gofmt"]
status = "active"
enforced_by = [
  { name = "lint", command = ["golangci-lint", "run"] },
  { name = "format", command = ["golangci-lint", "fmt", "--diff"] },
]
+++

# golangci-lint lints the Go code and checks its layout

It answers the linter and formatter choices of `aidd-team:ci-pipeline`.

## What the team does

- Keep one `.golangci.yml` in the version 2 format (`version: "2"`) at the repository root.
- Start from the `standard` linter set and add linters on purpose, such as `gosec`, `errorlint`, `bodyclose`, and `revive`. Write the reason beside each one you disable.
- Under `formatters`, enable `gofmt` and `goimports`, and set `goimports.local-prefixes` to the module path, so the module's own imports sit after third-party ones.
- Run `golangci-lint fmt` in the pre-commit hook. Never align code or sort imports by hand.
- Install the release binary at `pin`, in CI with the official GitHub Action or install script. The project advises against `go install` and `go tool` for it.
- Turn on `nolintlint` with `require-explanation` and `require-specific`, so each `//nolint` names its linter and says why.

## What the gate runs

Two `[[tests]]` entries from the binary at `pin`: `golangci-lint run`, where any issue fails the change, and `golangci-lint fmt --diff`, which prints the diff and exits 1 when a file's layout differs.
