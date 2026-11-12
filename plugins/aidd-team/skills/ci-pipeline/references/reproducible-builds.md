# Reproducible builds, and checks that mean the same everywhere

Read the first part in Implement, when a change adds or touches a build that makes a release artifact: a package, a binary, an image, or an archive. Read [the same checks on every machine](#the-same-checks-on-every-machine) when a change adds or changes a check, a matrix entry, or a runner. A build is reproducible when the same source, environment, and instructions give the same bytes (reproducible-builds.org). Then anyone can check that the artifact came from the commit it claims, and a tampered runner shows up as a mismatch.

## Prove it in CI

1. Build twice, in two clean jobs on fresh runners, from the same commit. Each job sets the clock the build writes into its files from the commit, not from the runner:

   ```sh
   SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
   export SOURCE_DATE_EPOCH
   ```

2. The first job writes `SHA256SUMS` of its artifacts (`sha256sum -- *`). The second job builds again and compares its own list with `diff -u`, so a missing, extra, or changed file fails the job.
3. On a mismatch, nothing is signed or published. Compare each differing pair with diffoscope (`diffoscope <first> <second>`), which shows where two archives, binaries, or images differ, down to the file and the byte. Fix the cause, and never publish the first build alone.
4. Build once with the network off. Fetch the locked dependencies in one step, then build in the next with no network, such as `docker build --network=none` or `unshare --net`. A build that reaches out then fails, instead of quietly taking whatever the network served that day.

Give the comparison job only `contents: read`. It needs no token and no secret.

## Per stack

| Stack | What makes the output differ | Fix |
| --- | --- | --- |
| Any | timestamps, file order, the build path, the locale, the time zone | `SOURCE_DATE_EPOCH`, sorted inputs, `TZ=UTC`, `LC_ALL=C` |
| Go | the build path embedded in the binary | `go build -trimpath`, with the toolchain version pinned in `go.mod` |
| Container images (BuildKit) | the image's `created` time and each file's time | pass `SOURCE_DATE_EPOCH` as a build arg, and export with `rewrite-timestamp=true` (BuildKit v0.13 and later): `--output type=image,name=<image>,rewrite-timestamp=true` |
| Maven | the time each plugin writes into the JAR | the `project.build.outputTimestamp` property in `pom.xml`, which the release plugin updates |
| Python | the archive times of the wheel and the sdist | `SOURCE_DATE_EPOCH`, with the build backend pinned by hash (`uv build --build-constraint <file> --require-hashes`) |
| npm | a build script that stamps the date or the runner into the output | `npm ci` from the committed lockfile, and the date from `SOURCE_DATE_EPOCH`, never from the clock |

## The test command

The Reproducible build row in SKILL.md is the second job above. It builds the same commit with the same `SOURCE_DATE_EPOCH`, runs `diff -u SHA256SUMS <its own list>`, and runs diffoscope on a mismatch.

## The same checks on every machine

A check that passes on a laptop and fails in the pipeline wastes a push, and one that fails only after the merge costs more. Make four things equal. Twelve-Factor's dev/prod parity (12factor.net/dev-prod-parity) is the standard behind this.

1. **The commands.** Each pipeline job calls the command a person runs: a project script or task, such as `make check`, `npm test`, or `aidd test`. It never holds a copy of that command's lines. A change to a check then changes both places at once.
2. **One command for every check.** Every check the pipeline runs on a change runs on the working tree with one command, the secret scan included, so a person learns of a failure before the push. `aidd-packs:enterprise-controls` gives the secret scan as `gitleaks dir --redact .` over the tree and `gitleaks git --redact .` over the history. A check that needs the platform or a secret, such as a deploy or a signing step, has a dry run. If it has none, name it as a gap. A check that needs a second clean runner or the built image, such as the build-once digest check and the second reproducible-build job, runs only in the pipeline, and the reason is named. The check that shows it: each workflow step either sets up the job or calls that command.
3. **The versions.** Test the oldest and the newest runtime version the project supports, which its manifest declares. A person runs the oldest and the newest locally with a version manager or an image. The versions between them run on a schedule ([ci-cost.md](ci-cost.md)).
4. **The platform.** Platforms differ in fonts and text widths, in the path separator, in whether file names are case-sensitive, in line endings, in system libraries, in the locale and time zone, and in the default shell. A defect that shows only on one fails after the merge. Run each platform the release builds on before the release job:
   - On Linux, run the check in a container of the pipeline's image: `docker run --rm -v "$PWD":/work -w /work <the pipeline's image> <the check command>`.
   - On macOS or Windows, a person cannot run the hosted runner locally. Run that job in the pipeline before the release, and list the gap on the handoff note until then.
   - For a mobile app, test the oldest and the newest operating system it supports, on a simulator or an emulator. For a data pipeline, test the oldest and newest engine version it runs on.

## A failing test with no defect behind it

A test that fails for a reason that is not a defect is a finding with an owner. Timing, test order, a shared resource, and a network call are common reasons. Never re-run it until it passes: hard rule 7 of the aidd skill says so, and `aidd-team:test-design` says how to fix or quarantine it.

- The runner's `reruns` is the only re-run. Its count is data in the test command (0 to 5, default 0), and every attempt stays in the evidence. A pass after a failure counts green but is marked flaky, so a person quarantines the test.
- A retry in the workflow hides that report. A retry action, a `retry:` keyword on a test job, and a shell loop around a test are findings.
- A job the platform lost, such as a runner that vanished before the test ran, has no test result. It may start again.

