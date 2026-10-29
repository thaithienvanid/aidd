# Reproducible builds

Read in Implement, when a change adds or touches a build that makes a release artifact: a package, a binary, an image, or an archive. A build is reproducible when the same source, environment, and instructions give the same bytes (reproducible-builds.org). Then anyone can check that the artifact came from the commit it claims, and a tampered runner shows up as a mismatch.

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
