---
name: dependency-upgrade
description: "Practice skill: upgrade one dependency at a time. Use in an aidd repository when a Task bumps a package, runtime, image, or lockfile, a bot PR arrives, or a CVE lands."
metadata:
  checked: "2026-09-30"
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
<!-- aidd:end -->

## Specify

- One package per change, or one group that must move together (a framework and its official plugins, a monorepo's packages released in lockstep, `react` with `react-dom`). Never mix an upgrade with a feature or a refactor.
- A major version gets its own change, with a Spec when the route needs one. It also gets a deprecation plan: the deprecated APIs you use, the codemod or edit that replaces each, and the version that removes the old one. A pre-1.0 package promises nothing.
- A release-age cooldown holds a new version back for a set time after it goes public. That time is days for a patch, and a week or more for a minor or a major. A hijacked or broken release is then usually pulled before you take it. Set it with Dependabot `cooldown`, Renovate `minimumReleaseAge`, pnpm `minimumReleaseAge`, or uv `--exclude-newer`. A security fix skips the cooldown.
- A bot's patch or minor update of a well-tested package can be a standard change (`standard_changes` in `.aidd/config.yaml`: the lockfile and manifest paths, the bot as author, a line limit), merging on green tests with no human. Majors, runtimes, and anything on a protected path never are. Route by change type: [references/sizing.md](references/sizing.md).

## Implement

### Before you change the lockfile

- Read the changelog and the migration guide for every version you cross, not only the last one. Find the breaking changes, the deprecations, and the changed defaults that touch your code.
- Check advisories on the lockfile before and after; a new advisory in the target version is a reason to pick another.
- Check provenance. The package comes from the official registry under the expected name (no look-alike), and its Scorecard is not alarming. Where available, a published SLSA provenance or registry attestation verifies (`npm audit signatures`, `cosign verify-attestation`). Note every transitive package the lockfile diff moves.

### Upgrade

- Apply the official codemod or migration tool first, then fix what it missed by hand; commit the codemod output separately from hand edits.
- Run the full suite, the type checker, the linter, and the build, not a subset, and the app's smoke path where the dependency sits on it. Remove workarounds and pins the new version makes unnecessary, and say so.
- The rollback is reverting the manifest and lockfile change; a data or configuration migration the new version forces goes in its own step, with `aidd-team:schema-migration`.

### Codemods

The same edit across many files (a renamed API, a framework's migration, a deprecated call) is a codemod. Never make hand edits file by file, and never run a regular expression over source: it matches text, not syntax, so it also changes comments, strings, and look-alike names. Dry run, review the diff, apply, then run the tests, as in [references/codemods.md](references/codemods.md).

## Review

- One package or one coherent group. Each of the changelog's breaking changes is addressed or shown irrelevant. No new advisory. The lockfile diff is explained. The codemod and hand edits are separable. The rollback is one revert.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Deprecation-warning check | the upgrade adds no new deprecation warning | the suite with warnings as errors where the runtime supports it (`-W error::DeprecationWarning`, `--throw-deprecation`) |
| Codemod fixture test | a transform you keep still rewrites as intended | its before-and-after fixture, run by the transform's own runner |

- From `aidd-team:enterprise-controls`: Dependency scan, on the base and on the head.

## Stop if

- The change bumps unrelated packages, or mixes an upgrade with a feature.
- You have not read the changelog for every version crossed.
- The target version has an open advisory, or the package name or publisher does not match the one you expect.
- Tests were skipped or pinned to pass, or rollback needs more than reverting the change.

## Hand off

- Done: the upgrade, the breaking changes handled, the advisory and provenance check, and the deprecation plan for a major. Next: the reviewer; the security engineer when an advisory drove the upgrade. Needs: a decision when the only safe version breaks an API you rely on. Stopped at: none, or the stop rule that fired.
