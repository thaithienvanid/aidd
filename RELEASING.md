# Releasing

Maintainers only. A release is one tag; everything else follows from it.

## One version

`src/aidd/__init__.py` holds the version. `tests/test_version.py` fails when any pin differs from it:

- the workflow and action refs in `templates/` and the docs (`@vX.Y.Z`), including the `aidd-pin` line in `templates/gitlab/aidd.gitlab-ci.yml` and the `ref: vX.Y.Z` checkout lines in `templates/github/aidd-watch.yml` and `templates/github/aidd-notify.yml`
- `AIDD_REF` in `install.sh`
- `aidd_version` in the skill assets and `.aidd/config.toml`
- `metadata.version` in `SKILL.md`, and the versions in `.claude-plugin/`

Schema `$id`s carry only the major version (`urn:aidd:1:<name>`).

## Steps

1. Open a release PR:
   - bump `__version__`, then update every pin until `python3 -m unittest discover -s tests` passes
   - move the `CHANGELOG.md` entries from `## [Unreleased]` to a dated heading in the Keep a Changelog form, `## [X.Y.Z] - YYYY-MM-DD` (for the first release, `## [1.0.0] - YYYY-MM-DD`); the release refuses a version without one
   - `aidd eval standards` passes, and the routing and role evals have a recorded score for the release's reference harness (`evals/*/README.md`)
2. Merge it through the gate like any other change. It touches protected paths, so it is major.
   Then run `ci` by hand on `main` (Actions, ci, Run workflow): a pull request and a push run Linux only, and the manual run adds the full matrix (Linux, macOS, and Windows on Python 3.11 to 3.15), the sdist's own tests, and the wheel on every OS. Tag only once it is green: the release refuses a commit without a successful manual or scheduled run.
3. Tag the merge commit with a signed, annotated tag and push it:

   ```sh
   git tag -s vX.Y.Z -m "vX.Y.Z" <merge commit>
   git push origin vX.Y.Z
   ```

4. `.github/workflows/release.yml` then runs one release at a time (`concurrency: release`):
   - **verify**:
     - the tag is annotated, signed, and shown as verified by GitHub, and matches the version
     - `CHANGELOG.md` dates the version
     - the commit is an ancestor of `main` and passed `ci` there (the push run: a newer push to `main` cancels an older run, so re-run a cancelled one before tagging), and the full matrix passed on it (a manual or scheduled `ci` run)
     - the commit is the merge commit of a pull request whose head passed `aidd/gate`, and the gate App posted that status: the latest `aidd/gate` on the head must come from a bot, never a person or `github-actions[bot]` (GITHUB_TOKEN, which anyone with write access can use). The App ID lives on the `aidd-gate` environment, which the release cannot read; set the `AIDD_GATE_APP_LOGIN` repository variable to the App's bot login (`<app-slug>[bot]`) to require exactly that App
   - **build**: runs the tests and builds once, with the pinned uv, the hash-locked backend in `.github/requirements/build.txt`, and `SOURCE_DATE_EPOCH` from the tag commit. It also builds `aidd.pyz`, the CLI as one zipapp (`python -m aidd.pyz`, standard library only, with the same `SOURCE_DATE_EPOCH`), outside `dist/` so PyPI never sees it. It writes a CycloneDX SBOM of the wheel and `SHA256SUMS` of the dists and `aidd.pyz`.
   - **attest**: build provenance and the SBOM, each for the dists and `aidd.pyz`, as Sigstore attestations. They are mandatory: a failed attestation stops the release before anything is published.
   - **publish**: PyPI through trusted publishing; this job holds only `id-token: write`
   - **release**: the GitHub Release, with the dists, `aidd.pyz`, the SBOM, `SHA256SUMS`, and both attestation bundles
5. After the first release is on PyPI, set `PUBLISHED="yes"` in `install.sh`, through the gate like any change. Until then the one-line installer refuses a release tag without `AIDD_SHA256`, since the name on PyPI proves nothing before aidd holds it.

## One-time setup

- **PyPI**: add a trusted publisher for this repository, workflow `release.yml`, environment `pypi`.
- **GitHub**:
  - create the `pypi` environment with required reviewers, and deployment tags limited to `v*`
  - add a tag ruleset that protects `v*` from deletion and update, so a released tag never moves, and lets only maintainers create `v*` tags
  - add each maintainer's signing key (GPG or SSH) to their GitHub account, so GitHub verifies the release tag
  - require the `ci passed` check (the ci workflow's summary job: a pull request runs only its checks and test jobs, so name no other job) and `aidd/gate` on `main`; never `agent-evals` (see the header of `.github/workflows/evals.yml`) nor the `codeql` analyze checks, which run weekly and by hand, never on pull requests, and only while the repository is public (as does `scorecard`: code scanning on a private repository needs GitHub Code Security)
  - set the `AIDD_GATE_APP_LOGIN` repository variable to the gate App's bot login (`<app-slug>[bot]`), so the release checks who posted `aidd/gate`
  - turn on immutable releases
  - keep the repository public (or on Enterprise Cloud): the release requires artifact attestations
  - optional: create the `evals` environment with required reviewers, deployment branches `main` plus `refs/pull/*/merge` (what a pull request's run is evaluated against), and the `ANTHROPIC_API_KEY` secret, so the scheduled `evals` workflow and pull requests that change the agents' configuration run the agent evals. The reviewers approve each run before it spends the key

## Toolchain pins

Dependabot bumps these monthly, one grouped pull request per ecosystem, with a seven-day cooldown:

- actions: by commit SHA in `.github/workflows/` and the root `action.yml`; mirror a bump into `templates/github/` (`tests/test_version.py` fails until they agree)
- Python tools: hash-locked in `.github/requirements/*.txt`, compiled from the `.in` file next to each
- Node tools: `tools/mermaid/package-lock.json`, installed with `npm ci`, including the Claude Code CLI (outside `.github/`, where Dependabot's npm updates cannot write)

Dependabot does not see these; update them by hand:

- uv: the `version:` input of `astral-sh/setup-uv` in `ci.yml` and `release.yml` (Dependabot bumps the action, not its inputs)
- the Claude Code CLI in `templates/github/aidd-triage.yml`: its version and the `sha512-` integrity of the `@anthropic-ai/claude-code-linux-x64` package. Copy both from `tools/mermaid/package-lock.json` after Dependabot bumps it; `tests/test_version.py` fails until they agree
- the GitLab image: `python:<tag>@sha256:<digest>` in `templates/gitlab/aidd.gitlab-ci.yml`

## What adopters pin

- Templates reference `thaithienvanid/aidd@vX.Y.Z` on the line after an `aidd-pin:` comment. That tag is a placeholder: `aidd init` writes the release commit SHA in its place. Anyone who copies a template by hand replaces it with the SHA and keeps the tag in a comment; `aidd init` writes that comment only for the release's own commit, and `# aidd <short sha>` for any other.
- `templates/github/aidd-watch.yml` and `templates/github/aidd-notify.yml` check aidd's source out and run it, with `ref: vX.Y.Z` on the line after `repository: thaithienvanid/aidd`. That tag is a placeholder too. `aidd init` does not write these two workflows; once you copy one into `.github/workflows/`, `aidd upgrade --ref <sha> --yes` writes the commit SHA in its place (`ref: <sha> # vX.Y.Z`), or set that SHA to the release commit by hand.
- `install.sh` installs the release wheel from PyPI. With `AIDD_SHA256` set to the wheel's line in the release's `SHA256SUMS`, it checks the wheel before installing it; until `PUBLISHED="yes"` (step 5), it installs a release tag only that way.
- Verify a downloaded artifact with `gh attestation verify <file> --repo thaithienvanid/aidd`. Add `--predicate-type https://cyclonedx.org/bom` to verify the SBOM attestation.
