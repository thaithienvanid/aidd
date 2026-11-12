# Test value, strength, and retirement

Load this in any of these cases:

- You add a test whose purpose is not plain from its name.
- You write or review a test of a control, an invariant, or a cost.
- A suite is slow.
- A change deletes or weakens a passing test.

A test has a value and a cost. The value card says why the test exists. The retirement card says what evidence a person needs before a passing test goes. Write each card in the test's docstring or comment, or in the handoff note. Keep each one to a few lines. The sections between them say how to know a test has value, and how to hold its cost.

## Test value card

| Field | What it says |
| --- | --- |
| Test | The test's name, as the runner reports it. |
| Protects | The failure it prevents: the Acceptance line, the bug, or the invariant. Name the user or caller who would see the failure. |
| Fails today when | How it fails today: the change to the code that turns it red. Show it once, by a revert, a mutant, or the red run on base. |
| Cost | Its run time, its flaky rate (`aidd test` marks late passes), and how often it changed while the behavior did not. |

- A test with no failure it prevents is a candidate for retirement, not a safe test.
- A test that never failed is not a test without value. It can guard a path that nobody broke yet.
- Fix a flaky test, or quarantine it with an owner and a date. A retry that hides the flake is not a fix. A timing flake's usual fix is to wait for the condition itself, with a timeout, never for a fixed time.

## Prove the test can fail

A test that passes on a broken implementation protects nothing. A feature or a fix has its red run on the base commit. A test of a control, an invariant, or a cost often has none, because the base already holds. A refactor's guard, a new check, and a cost test are examples. Before you trust such a test, seed its fault and watch it fail:

1. Pick the fault from the table below.
2. Run the test. It fails with its own assertion message, for the reason its name gives. A crash that your seeded change caused proves nothing.
3. Restore the code and run the test again: it passes.
4. List the result in the value card's "Fails today when" field or in the handoff note. Never commit the seeded fault.

| The test guards | Seed this |
| --- | --- |
| A fix | the fix, reverted |
| A rule that refuses, such as a permission, a validation, or a limit | the check, removed |
| An invariant, such as sorted, unique, or balanced | the invariant, broken the simplest way: return a constant, skip the sort, drop the filter |
| A cost | a costly implementation: the query inside the loop, the whole file read for each line, the process started for each input |

The review reads that list, because a green run is not proof that a test can fail. A mutation tool seeds many faults at once. This is the same idea, done by hand for one test. No standard sets it. It is aidd's practice, with mutation testing as its basis.

## Keep the clock out of the assertion

A test that asserts a duration fails by the load on the machine, not by a defect. The same code passes on a quiet laptop and fails on a busy runner. To hold a cost, count the work the code does at two or three sizes, and assert how the count grows. This keeps the test repeatable, the R in FIRST.

| The product | Count | At sizes | Assert |
| --- | --- | --- | --- |
| A web service | queries for one request | 10, 100, and 1,000 items | the count is the same at every size |
| A command-line tool | files read, or processes started | 1, 10, and 100 inputs | the count grows by at most the input count |
| A mobile app | network calls to open a screen | 5 and 50 list rows | the count is the same at both sizes |
| A data pipeline | rows read for each row written | 1,000, 10,000, and 100,000 rows | the ratio is the same at every size |

Put a counter at the boundary that the cost crosses: a database driver that counts statements, an HTTP client that counts calls, or a file wrapper that counts reads. The test passes the code a size, runs it, and compares the counts. It reads no timer. Seed a costly implementation, as the table above says, so the count test shows it can fail.

A real timeout is the exception. Where the clock is the thing under test, such as a call that must give up after five seconds, the test says so in its name. It uses the smallest limit that still shows the behavior, with a fake clock where the runtime has one. A latency budget is a measurement, never a unit assertion. The performance harness takes it, base against head on one machine (`aidd-team:performance`).

## When a suite is slow, measure first

Do not delete, skip, or weaken a test for speed: the retirement card below says what evidence that needs. Do not parallelize before you know where the time goes.

1. Read the runner's own timing report, such as pytest's `--durations`, for the slowest tests and setups. Then profile one slow test.
2. Ask what the time is spent on. Common causes are a setup repeated for each test, a fixed wait, and I/O, such as a process started, a network call, or a disk read. Sometimes it is the product's own repeated work. Examples are the same query for each item, the same configuration file read many times, the same process started for each call, and the same asset decoded on each screen.
3. Fix the cause where it lives. A repeated setup is shared between tests, and a fixed wait gives way to the event it waits for. Repeated work in the product is fixed in the product. That fix also serves the person who runs it, so it pays twice. `aidd-team:performance` says how to measure a change and keep it.
4. Only then run files in parallel. A shared setup and a parallel run never let one test see another's data.

A mock that hides the repeated work makes the suite fast and keeps the defect. Count the work first, as the section above says, so the repeat shows.

## Retirement card

Delete or weaken a passing test only with one of these evidence items in the change:

1. **The behavior is gone.** The same change deletes the code it tests, or an approved Spec removed the Acceptance line it proves.
2. **Another test covers it.** Name the other test. A mutation run or a revert shows that the other test fails on each mutant this test kills.
3. **The cost is over the value.** Its cost is measured: a run time, or a flaky rate over the limit after a fix was tried. A test at a lower level that proves the same failure replaces it in the same change.

"It is slow", "it never fails", and "it is in the way" are not evidence.

**Who decides.** A person decides, never an agent:

- A test that an approved Spec froze changes only through `spec.revise`.
- Any other passing test goes at Merge approval. The person reads the retirement card in the PR/MR.
- The verifier or the developer writes the card. The reviewer checks the evidence and reports a deletion without a card as a finding.
