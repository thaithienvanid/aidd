# Governance

## Maintainers

One maintainer today: Van Hoang ([CODEOWNERS](.github/CODEOWNERS)). Every change to the method, the schemas, the gate, or the skill needs maintainer review. This repository will run its own gate on every pull request once the first live pull request has gone through it. Until then, that run is the release criterion ([ENTERPRISE.md](docs/ENTERPRISE.md#1-release-status-and-maturity)).

## Decisions

Changes to routes, profiles, gate rules, schemas, or the loop go through an RFC with a public comment period ([CONTRIBUTING.md](CONTRIBUTING.md#change-the-method)). Everything else is a pull request that a maintainer approves, and, once the gate runs live, that merges only when `aidd/gate` is green. Disagreements are settled in the pull request or the RFC, in writing.

## Becoming a maintainer

A contributor becomes a maintainer after sustained contributions (reviewed pull requests, RFCs, and triage) over a few months. Becoming a maintainer also takes an invitation by the existing maintainers, recorded in CODEOWNERS.

## Succession

The project is Apache-2.0 with no contributor agreement, so anyone may fork and continue it. If the maintainer is unreachable for 90 days, the most active contributor of the last year may do one of these:

- ask GitHub to transfer the repository
- announce a fork as the continuation

Releases keep the same version scheme.

## Releases

Maintainers publish through the release workflow ([RELEASING.md](RELEASING.md)). It verifies a signed tag, builds against a hash-locked backend, and writes a CycloneDX SBOM. It attests the build provenance and the SBOM before anything is published. No release has exercised it yet: nothing has been released. There is no fixed cadence. A release ships when the changelog has something worth shipping, and a security fix ships as a patch as soon as it is ready.

## Support

Community support through issues and pull requests, with no service level. Security reports follow [SECURITY.md](SECURITY.md).

## Money

No sponsor, no commercial edition, no paid support. Nothing in the project depends on a service the maintainer runs.
