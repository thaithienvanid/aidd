---
name: dependency-upgrade
description: "Practice skill: upgrade one dependency at a time. Use in an aidd repository when a Task bumps a package, runtime, image, or lockfile, a bot PR arrives, or a CVE lands."
metadata:
  checked: "2026-10-22"
---

# Dependency upgrade

**Use it when** a change moves a third-party package, a runtime, a toolchain, or a container base image to another version.

**Do not use when** you are adding a dependency for the first time; that is a design choice the Spec must allow and `aidd-team:secure-coding` checks. A vendored copy you maintain yourself is your code, not an upgrade.

## Standards

<!-- aidd:gen practice:dependency-upgrade -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Semantic Versioning | 2.0.0 | 2026-10-16 | <https://semver.org/> |
| OSV, the open vulnerability database and schema, for known vulnerabilities in the old and new versions | — | 2026-10-16 (reviewed) | <https://osv.dev/list> |
| OpenSSF Scorecard | v5.5.0 | 2026-10-16 | <https://github.com/ossf/scorecard> |
| SLSA | v1.2, 2025 | 2026-10-16 | <https://slsa.dev/> |
| Release-age cooldown: a new version is adopted only after it has been public for a set time (emerging) | — | 2026-10-16 | <https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference> |
| CVSS (Common Vulnerability Scoring System) for a vulnerability's severity | v4.0 | 2026-10-16 | <https://www.first.org/cvss/v4-0/> |
| CISA Known Exploited Vulnerabilities (KEV) catalog: an entry counts as Critical | — | 2026-10-16 | <https://www.cisa.gov/known-exploited-vulnerabilities-catalog> |
| Coordinated vulnerability disclosure: security.txt, then ISO/IEC 29147 and 30111 | RFC 9116 | 2026-10-22 | <https://www.rfc-editor.org/rfc/rfc9116> |
<!-- aidd:end -->

## Specify

- One package per change, or one group that must move together (a framework and its official plugins, a monorepo's packages released in lockstep, a library with its type package). Never mix an upgrade with a feature or a refactor.
- A major version gets its own change, with a Spec when the route needs one. It also gets a deprecation plan, as in [references/sizing.md](references/sizing.md). A pre-1.0 package promises nothing.
- A release cooldown holds a new version back for days after a patch, and a week or more after a minor or a major. A hijacked or broken release is then usually pulled before you take it. Set it in the update bot or the package manager, such as `minimumReleaseAge`. A security fix skips the cooldown. A tool a library standard pins moves only through that standard, after its `cooldown_until`.
- A bot's patch or minor update of a well-tested package can be a standard change (`standard_changes`), merging on green tests with no human. Majors, runtimes, and protected paths never are. Route by change type: [references/sizing.md](references/sizing.md).

## Implement

### Before you change the lockfile

- Read the changelog and the migration guide for every version you cross, not only the last one. Find the breaking changes, the deprecations, and the changed defaults that touch your code.
- Check advisories on the lockfile before and after; a new advisory in the target version is a reason to pick another. Run the Dependency scan and the License check of `aidd-team:enterprise-controls` on your machine before the handoff, because CI runs them only where the security workflow is on.
- Check provenance. The package comes from the official registry under the expected name (no look-alike). A person looks at a Scorecard below the team's stated score, or a new install script, maintainer, or license. Where available, a published SLSA provenance or registry attestation verifies (`npm audit signatures`, `cosign verify-attestation`). Note every transitive package the lockfile diff moves.

### Upgrade

- Run the full suite, the type checker, the linter, and the build, not a subset, and the app's smoke path where the dependency sits on it. Remove workarounds and pins the new version makes unnecessary, and say so.
- The rollback is reverting the manifest and lockfile change; a data or configuration migration the new version forces goes in its own step, with `aidd-team:schema-migration`.
- A vulnerability you find in a dependency goes to its maintainers privately, by their `security.txt` or security policy, never in a public issue.

### Codemods

Apply the official codemod first, and commit its output apart from hand edits. Make any other repeated edit with a codemod, never by hand or a regular expression, as [references/codemods.md](references/codemods.md) says.

## Review

- One package or one coherent group. Each of the changelog's breaking changes is addressed or shown irrelevant. No new advisory. The lockfile diff is explained. The codemod and hand edits are separable. The rollback is one revert.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Deprecation-warning check | the upgrade adds no new deprecation warning | the suite with warnings as errors where the runtime supports it (`-W error::DeprecationWarning`, `--throw-deprecation`) |
| Codemod fixture test | a transform you keep still rewrites as intended | its before-and-after fixture, run by the transform's own runner |
| Dependency hygiene | the manifest lists every package the code imports, and no unused one | `uvx deptry==0.25.1 .` (Python), `npx knip@6.42.1 --dependencies` (JS, TS), `cargo machete` 0.9.2 (Rust), `go mod tidy -diff` (Go), as `tests.commands` entries, `when_changed` on the manifests |

- From `aidd-team:enterprise-controls`: Dependency scan, on the base and on the head.

## Stop if

- The change bumps unrelated packages, or mixes an upgrade with a feature.
- You have not read the changelog for every version crossed.
- The target version has an open advisory, or the package name or publisher does not match the one you expect.
- Tests were skipped or pinned to pass, or rollback needs more than reverting the change.

## Hand off

- Done: the upgrade, the breaking changes handled, the advisory and provenance check, and the deprecation plan for a major. Next: the reviewer; the security engineer when an advisory drove the upgrade. Needs: a decision when the only safe version breaks an API you rely on. Stopped at: none, or the stop rule that fired.
