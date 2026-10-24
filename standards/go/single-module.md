---
id: go/single-module
type: opinionated
fills: [ci-pipeline:workspace]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [go.mod, "**/go.mod", go.work, "**/go.work", "**/*.go"]
why: "One Go module at the root holds every app, module, and package with one go.mod and one go.sum, and internal/ folders give the boundaries, so no workspace file is needed."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://go.dev/ref/mod
evidence: "It is generally inadvisable to commit go.work files into version control systems, for two reasons:"
alternatives: ["one module for each deployable, without a committed go.work"]
status: active
enforced_by:
  - name: one-module
    command:
      - sh
      - -c
      - "set -eu; work=$(git ls-files -- go.work '*/go.work'); test -z \"$work\" || {printf 'a committed go.work:\\n%s\\n' \"$work\"; exit 1;}; mods=$(git ls-files -- go.mod '*/go.mod' ':(exclude)*testdata/*'); test \"$mods\" = \"go.mod\" || {printf 'want one go.mod at the root; found:\\n%s\\n' \"${mods:-none}\"; exit 1;}"
  - name: build
    command: [go, build, "./..."]
---

# One Go module holds the apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for Go. Its tool is the Go toolchain, which `go/go-version` pins, under a BSD-style license.

## What the team does

- Keep one `go.mod` at the repository root. Put the apps under `apps/`, each with its own `main` package, and the modules under `modules/`.
- Never commit a `go.work` file. The Go docs advise against it. A developer may keep one locally, outside version control.
- Split a second module out only when it has its own release, such as a library for other repositories. Record that in an ADR.
- Put a test module under `testdata/`, where the check ignores it.

## What the gate runs

Two `tests` entries. The first fails when git tracks a `go.work` file, or a `go.mod` other than the root one. The second builds every package, so an import cycle or a use of another tree's `internal/` package fails the change.
