# Releasing

Maintainers only. A release is one tag; everything else follows from it.

## One version

`src/aidd/__init__.py` holds the version. `tests/test_version.py` fails when any pin differs from it:

- the workflow and action refs `@vX.Y.Z` in `templates/` and the docs, including the `aidd-pin` line in `templates/gitlab/aidd.gitlab-ci.yml` and the `ref: vX.Y.Z` checkout lines in `templates/github/aidd-observe.yml` and `templates/github/aidd-notify.yml`
- `AIDD_REF` in `install.sh`
- `aidd_version` in the skill assets and `.aidd/config.yaml`
- `metadata.version` in `SKILL.md`. The Claude Code plugins set no `version`, so Claude Code versions them by commit. Never add one, or users stop getting updates

Schema `$id`s carry only the major version, as in `urn:aidd:1:<name>`.

## Steps

1. Open a release PR:
   - bump `__version__`, then update every pin until `python3 -m unittest discover -s tests` passes
   - on the first release only, change the `Development Status` classifier in `pyproject.toml` from `4 - Beta` to `5 - Production/Stable`. `tests/test_release_surface.py` requires Stable once `CHANGELOG.md` dates a 1.x version, and Beta before
   - date the version's `CHANGELOG.md` heading in the Keep a Changelog form, `## [X.Y.Z] - YYYY-MM-DD`. Move the entries from `## [Unreleased]`, or put the date in place of `Unreleased` in `## [X.Y.Z] - Unreleased`. For the first release, that's `## [1.0.0] - YYYY-MM-DD`. The release refuses a version without a dated heading
   - for the first release, drop the draft note from the version line of `docs/METHOD.md`
   - `aidd eval standards` passes, and the routing and role evals have a recorded score for the release's reference harness in `evals/*/README.md`
2. Merge it through the gate like any other change. It touches protected paths, so it is major.
   Then run `ci` by hand on `main`, under Actions, ci, Run workflow. A pull request and a push run Linux only, and the weekly schedule adds the Linux matrix. Only the manual run adds macOS and Windows. It runs the full matrix on Linux, macOS, and Windows with Python 3.11 to 3.15, then the sdist's own tests, and the wheel on every OS. Tag only once it is green, because the release refuses a commit without a successful manual run.
3. Tag the merge commit with a signed, annotated tag and push it:

   ```sh
   git tag -s vX.Y.Z -m "vX.Y.Z" <merge commit>
   git push origin vX.Y.Z
   ```

4. `.github/workflows/release.yml` then runs one release at a time, with `concurrency: release`:
   - **verify**:
     - first, the repository is public. It stops a private repository before any other check, since the attest job would fail there after the build
     - the tag is annotated, signed, and shown as verified by GitHub, and matches the version
     - `CHANGELOG.md` dates the version
     - the commit is an ancestor of `main` and passed `ci` there, in the push run. A newer push to `main` cancels an older run, so re-run a cancelled one before tagging. The full matrix also passed on the commit, in a manual `ci` run, since the schedule runs Linux only
     - the commit is the merge commit of a pull request whose head passed `aidd/gate`, and the gate App posted that status. The latest `aidd/gate` on the head must come from a bot, never a person or `github-actions[bot]`, because anyone with write access can use GITHUB_TOKEN. The App ID lives on the `aidd-gate` environment, which the release cannot read. To require exactly that App, set the `AIDD_GATE_APP_LOGIN` repository variable to the App's bot login, `<app-slug>[bot]`
   - **build** runs the tests and builds once, with the pinned uv, the hash-locked backend in `.github/requirements/build.txt`, and `SOURCE_DATE_EPOCH` from the tag commit. It also builds `aidd.pyz`, the CLI as one zipapp that runs as `python -m aidd.pyz` with the standard library only and the same `SOURCE_DATE_EPOCH`. It writes a CycloneDX SBOM of the wheel and `SHA256SUMS` of the dists and `aidd.pyz`.
   - **rebuild** builds the tagged commit again on a fresh runner, with the same pinned tools and `SOURCE_DATE_EPOCH`. The release stops unless every dist and `aidd.pyz` matches `SHA256SUMS` byte for byte, and a mismatch uploads the rebuilt files to compare with diffoscope.
   - **attest** runs only after rebuild passes. It makes Sigstore attestations of the build provenance and the SBOM, each for the dists and `aidd.pyz`. They are mandatory, so a failed attestation stops the release before the GitHub Release is made.
   - **release** makes the GitHub Release, with the dists, `aidd.pyz`, the SBOM, `SHA256SUMS`, and both attestation bundles. It's the only place aidd is distributed, because aidd is not on PyPI.
5. Install the release as an adopter would, with `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh | sh`. It installs the tag's wheel from the GitHub Release, once the wheel matches the release's `SHA256SUMS`, and with `gh` on PATH, once `gh attestation verify` accepts it. `aidd --version` must name the release.

Until the first tag, nothing above has run:

- `CHANGELOG.md` keeps `## [1.0.0] - Unreleased`. The release PR of step 1 dates it, and the release refuses a version without a dated entry.
- the `vX.Y.Z` pins in `templates/` are placeholders that `aidd init` replaces with a commit SHA
- the installer installs only from a commit, given as `AIDD_REF=<sha>`

The first release is [The first public release](#the-first-public-release), then steps 1 to 5 in order.

Until then, adopters pin a commit. `aidd init --ref <sha>` writes that SHA into every template pin. Take a commit of `main` from `git ls-remote https://github.com/thaithienvanid/aidd refs/heads/main`. `aidd doctor` says so when a pin names a tag the repository does not have yet.

## The first public release

The release refuses a private repository in its first step, because artifact attestations need a public repository or GitHub Enterprise Cloud, and every release carries them.

Until the first tag, a person may squash `main` again and push it with `git push --force-with-lease=main:<the commit it replaces> origin main`. The lease names the commit you replace, so the push fails if anyone pushed since. Only a person does this, never an agent, and the guard denies an agent's force push. From the tag on, `main` only moves forward. So step 5 imports `.github/rulesets/main.json`, which forbids a push that is not a fast-forward and requires `aidd/gate`.

Before tagging 1.0.0:

aidd is not on PyPI, and other projects use the AIDD name. So the README and the install guide say that a package named `aidd` on PyPI is not this one, and the GitHub Release is where aidd comes from.

1. Make the repository public. Private vulnerability reporting, which `SECURITY.md` describes, and the `codeql` and `scorecard` workflows need that too.
2. On GitHub, finish the one-time setup below. That's the `v*` tag ruleset, each maintainer's signing key, the gate App, the `AIDD_GATE_APP_LOGIN` repository variable, and immutable releases.
3. Run [the first live run](#the-first-live-run). Every case must give the outcome it names, and the release PR links the record.
4. In the release PR from step 1 above, date `CHANGELOG.md` as `## [1.0.0] - YYYY-MM-DD`, and change the classifier to `Development Status :: 5 - Production/Stable`.
5. Make any last squash of `main` now. Then import `.github/rulesets/main.json` under Settings → Rules → Rulesets → Import a ruleset, and set the expected source of `aidd/gate` to the gate App. From here on, `main` only moves forward.
6. Run `ci` by hand on the release commit, then tag it, as steps 2 and 3 say.
7. Once the tag is public, offer the editor schema to [SchemaStore](https://github.com/SchemaStore/schemastore), so an editor finds it for a config with no modeline too. Add this entry to its `src/api/json/catalog.json` in a pull request; each later release moves `url` to its tag and adds a line to `versions`:

   ```json
   {
     "name": "aidd config",
     "description": "aidd's repository config: the profile, the gates, the tests, and the team",
     "fileMatch": [".aidd/config.yaml"],
     "url": "https://raw.githubusercontent.com/thaithienvanid/aidd/v1.0.0/schemas/editor/config.json",
     "versions": { "1.0.0": "https://raw.githubusercontent.com/thaithienvanid/aidd/v1.0.0/schemas/editor/config.json" }
   }
   ```

## The first live run

The gate has been proven on recorded contexts, in fixture repositories, and in CI on itself, but never on a live pull request. Before the first tag, run each case on this repository, with the gate App as the status source and a ruleset that requires `aidd/gate` and `ci passed` on `main`. Write each result, with the pull request's URL, into the release PR.

| Case | What you do | The outcome it must give |
| --- | --- | --- |
| A green change | a docs-only pull request, route minor, with its Change Request block | `aidd/gate` passes once a maintainer's Merge approval names the head; the merge button stays locked before it |
| Out of scope | a pull request whose diff touches a path outside its Change Request block's `scope` | `aidd/gate` fails on `scope`, and the pull request cannot merge |
| Nobody's approval | an approving review from an account that is not an Approver, and from `github-actions[bot]` | neither counts: the gate still waits for a Merge approval |
| A stale approval | approve the head, then push one more commit | the approval stops counting; the gate waits for a new one, on the new head |
| A typed `merge it` | in a Claude Code session on the published branch, type `merge it` | the person's approving review of the head is posted, and auto-merge turns on only because `aidd/gate` is required |
| The merge queue | with a merge queue on `main`, queue a green pull request | the gate judges the queued commit, and the queue merges it only when it passes |
| A fork | a pull request from a fork | the gate job never runs the fork's code, and the pull request cannot merge on its own status |
| GitLab | the same green and out-of-scope cases on a GitLab project with the pipeline execution policy | the same outcomes, from the injected gate job |

A case that gives another outcome is a release blocker. Fix it, then run that case again.

## One-time setup

- **GitHub**:
  - add a tag ruleset that protects `v*` from deletion and update, so a released tag never moves, and lets only maintainers create `v*` tags
  - add each maintainer's GPG or SSH signing key to their GitHub account, so GitHub verifies the release tag
  - require the `ci passed` check and `aidd/gate` on `main`. `ci passed` is the ci workflow's summary job. A pull request runs only its checks and test jobs, so name no other job. Never require `agent-evals`, as the header of `.github/workflows/evals.yml` explains, nor the `codeql` analyze checks. The `codeql` analyze checks run weekly and by hand, never on pull requests, and only while the repository is public. So does `scorecard`, because code scanning on a private repository needs GitHub Code Security
  - set the `AIDD_GATE_APP_LOGIN` repository variable to the gate App's bot login, `<app-slug>[bot]`, so the release checks who posted `aidd/gate`
  - turn on immutable releases
  - keep the repository public, or on Enterprise Cloud, since the release requires artifact attestations
  - optionally, add the `ANTHROPIC_API_KEY` secret, so the scheduled `evals` workflow and a maintainer's manual run measure the agents. Put it on an `evals` environment with required reviewers where the plan offers environment secrets, and otherwise as a repository secret. No pull request run reads it. On a pull request that changes the agents' configuration, a maintainer reads the diff, then runs the evals by hand on the branch

## Toolchain pins

Dependabot bumps these monthly, one grouped pull request per ecosystem, with a seven-day cooldown:

- actions, by commit SHA in `.github/workflows/` and the root `action.yml`. Mirror a bump into `templates/github/`, since `tests/test_version.py` fails until they agree
- Python tools, hash-locked in `.github/requirements/*.txt` and compiled from the `.in` file next to each
- Node tools in `tools/mermaid/package-lock.json`, installed with `npm ci`, including the Claude Code CLI. They sit outside `.github/`, where Dependabot's npm updates cannot write

Dependabot doesn't see these, so update them by hand:

- uv, the `version:` input of `astral-sh/setup-uv` in `ci.yml` and `release.yml`. Dependabot bumps the action, not its inputs
- the Claude Code CLI in `templates/github/aidd-diagnose.yml`, with its version and the `sha512-` integrity of the `@anthropic-ai/claude-code-linux-x64` package. Copy both from `tools/mermaid/package-lock.json` after Dependabot bumps it; `tests/test_version.py` fails until they agree
- the GitLab image `python:<tag>@sha256:<digest>` in `templates/gitlab/aidd.gitlab-ci.yml`
- the `overrides` in `tools/mermaid/package.json`, which pin `lodash-es`, since Mermaid 12's `chevrotain ~11.1.2` pins it to a version with advisories. Drop the override once Mermaid depends on a fixed release and `npm audit` in `tools/mermaid` stays clean without it

## What adopters pin

- Templates reference `thaithienvanid/aidd@vX.Y.Z` on the line after an `aidd-pin:` comment. That tag is a placeholder, and `aidd init` writes the release commit SHA in its place. Anyone who copies a template by hand replaces it with the SHA and keeps the tag in a comment. `aidd init` writes that comment only for the release's own commit, and `# aidd <short sha>` for any other.
- `templates/github/aidd-observe.yml` and `templates/github/aidd-notify.yml` check aidd's source out and run it, with `ref: vX.Y.Z` on the line after `repository: thaithienvanid/aidd`. That tag is a placeholder too. `aidd init` doesn't write these two workflows. Once you copy one into `.github/workflows/`, `aidd upgrade --ref <sha> --yes` writes the commit SHA in its place as `ref: <sha> # vX.Y.Z`. Or set that SHA to the release commit by hand.
- `install.sh` installs a release tag's wheel from its GitHub Release, once the wheel matches the release's `SHA256SUMS`, and `AIDD_SHA256` when you set one from a source you trust. With `gh` on PATH, it also verifies the wheel's build provenance. `AIDD_RELEASE_URL` points it at a mirror of the releases, which also needs `AIDD_SHA256` or `gh`.
- Verify a downloaded artifact with `gh attestation verify <file> --repo thaithienvanid/aidd`. Add `--predicate-type https://cyclonedx.org/bom` to verify the SBOM attestation.
