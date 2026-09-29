---
name: dependency-upgrade
description: "Practice skill: upgrade a dependency one package at a time, with a rollback that is one revert. Use when a Task bumps a library, a framework, a runtime, a base image, or a lockfile, when a Dependabot or Renovate pull request arrives, or when someone says upgrade, bump, update the deps, a major version, end of life, deprecated, a CVE or security advisory in a package, npm audit or pip-audit failed, or the build broke after an update: one package or one coherent group per change, the changelog and migration guide read, advisories and provenance checked, codemods applied, the full suite run, majors with a deprecation plan, and bot patch updates as standard changes."
metadata:
  checked: "2026-09-28"
---

# Dependency upgrade

**Use it when** a change moves a third-party package, a runtime, a toolchain, or a container base image to another version.

**Do not use when** you are adding a dependency for the first time; that is a design choice the Spec must allow and `aidd-team:secure-coding` checks. A vendored copy you maintain yourself is your code, not an upgrade.

## Standards

- Semantic Versioning 2.0.0: what a major, minor, and patch number promise, and that a pre-1.0 package promises nothing.
- OSV (osv.dev) for known vulnerabilities in the old and new versions.
- OpenSSF Scorecard for the upstream project's security practices; SLSA provenance where the package publishes it.

## Size the change

- One package per change, or one group that must move together (a framework and its official plugins, a monorepo's packages released in lockstep, `react` with `react-dom`). Never mix an upgrade with a feature or a refactor.
- A major version gets its own change, with a Spec when the route needs one, and a deprecation plan: which deprecated APIs you use, the codemod or edit that replaces each, and the version where the old one is removed.
- A bot's patch or minor update of a well-tested package can be a standard change (`[[standard_changes]]` in `.aidd/config.toml`: the lockfile and manifest paths, the bot as author, a line limit), merging on green tests with no human. Majors, runtimes, and anything on a protected path never are. Route by change type: [references/sizing.md](references/sizing.md).

## Before you change the lockfile

- Read the changelog and the migration guide for every version you cross, not only the last one. List the breaking changes, the deprecations, and the changed defaults that touch your code.
- Check advisories: `osv-scanner` on the lockfile before and after; a new advisory in the target version is a reason to pick another.
- Check provenance: the package comes from the official registry under the expected name (no look-alike), its Scorecard is not alarming, and a published SLSA provenance or registry attestation verifies (`npm audit signatures`, `cosign verify-attestation`) where available.
- Note the transitive changes: the lockfile diff shows every package that moved with it.

## Upgrade

- Apply the official codemod or migration tool first, then fix what it missed by hand; commit the codemod output separately from hand edits so a reviewer can tell them apart.
- Run the full suite, the type checker, the linter, and the build, not a subset; run the app's smoke path where the dependency sits on it.
- Remove workarounds and pins that the new version makes unnecessary, and say so.

## Roll back

- The rollback is reverting the manifest and lockfile change; keep it that simple by keeping the change to the dependency. A data or configuration migration that the new version forces makes rollback harder: put it in its own step, with `aidd-team:schema-migration`.

## Test commands

- The full repository suite; `osv-scanner --lockfile <lockfile>` (or `npm audit`, `pip-audit`, `cargo audit`); the build; a deprecation-warning check that fails on new warnings where the runtime supports it (`-W error::DeprecationWarning`, `--throw-deprecation`).

## Review

- One package or one coherent group; the changelog's breaking changes are each addressed or shown irrelevant; no new advisory; the lockfile diff is explained; the codemod and hand edits are separable; the rollback is one revert.

## Hand off

- Done: the upgrade, the breaking changes handled, the advisory and provenance check, and the deprecation plan for a major. Next: the reviewer; the security engineer when an advisory drove the upgrade. Needs: a decision when the only safe version breaks an API you rely on. Stopped at: none, or the stop rule that fired.

## Stop if

- The change bumps unrelated packages, or mixes an upgrade with a feature.
- You have not read the changelog for every version crossed.
- The target version has an open advisory, or the package name or publisher does not match the one you expect.
- Tests were skipped or pinned to pass, or rollback needs more than reverting the change.
