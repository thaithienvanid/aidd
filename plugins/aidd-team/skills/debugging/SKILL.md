---
name: debugging
description: "Practice skill: find the cause of a failure by experiment before changing any code. Use when a test fails, a build goes red, a bug is reported, a result is wrong, something is flaky or intermittent, a crash or a stack trace arrives, or someone says it broke, it used to work, it works on my machine, why does this happen, or this makes no sense: reproduce it as a failing command first, shrink the case, rank falsifiable hypotheses, change one variable at a time, put the regression test at the seam that reproduces the real bug, and stop to question the design after three failed fixes."
metadata:
  checked: "2026-09-28"
---

# Debugging

**Use it when** something behaves differently from what the Spec, a test, or a person expects, and the cause is not yet known: a red test, a bug report, a flaky check, a crash, a wrong number.

**Do not use when** the cause is already known and shown by a failing test (go straight to the fix), or when production is burning right now: mitigate first with `aidd-team:incident-response`, and debug the copy of the failure afterwards.

## Standards

- Scientific debugging (Andreas Zeller, *Why Programs Fail*, 2nd edition, 2009): observe, hypothesize, predict, experiment, conclude; keep a written log of each step; shrink the failing input (delta debugging).
- The nine rules of David Agans, *Debugging* (2002): understand the system, make it fail, quit thinking and look, divide and conquer, change one thing at a time, keep an audit trail, check the plug, get a fresh view, and if you did not fix it, it is not fixed.

## Reproduce, before any theory

- Write down the exact symptom: the message, the wrong value, the exit code, the environment. "It is slow" or "it fails sometimes" is not yet a symptom.
- Find one command that goes red on that exact symptom, and only on it. A test that fails for another reason proves nothing. Record the command, the commit, and the seed or time it needs.
- Flaky? Run it in a loop (`for i in $(seq 50); do <cmd> || break; done`) until you know its failure rate; fix the seed, the clock, the order, or the concurrency until it fails every time, or say you could not.
- Minimise: remove input, steps, configuration, and code until removing anything more makes the failure go away. The smallest case usually names the cause.

## Hypothesize and experiment

- Rank three to five hypotheses, each falsifiable: what you expect to see if it is true, and the one experiment that would show it false. Start with the cheapest to check, not the most interesting. Worked example and log format: [references/hypotheses.md](references/hypotheses.md).
- Change one variable per experiment and predict the result before you run it. A result you did not predict is information; a result you explain after the fact is not.
- Look before you reason: read the actual values (a debugger, a print, the log line) instead of the code you think runs. Check the plug: the right binary, branch, configuration, and data.
- Bisect when the bug is a regression: `git bisect run <the red command>` finds the commit faster than reading diffs.
- Tag every temporary print, log line, or flag with one marker (`DEBUG-<ID>`) and remove all of them before handing off; `git grep DEBUG-<ID>` must come back empty.

## Fix and prove

- The regression test goes at the seam that reproduces the real bug: the unit, the query, the HTTP call, or the queue message where the failing command showed it. A test that mocks away the faulty part passes against the bug and proves nothing.
- If no seam in the code can reproduce the failure without the whole system, that is a finding for the architect, not a reason to skip the test: record it, and test at the nearest seam that does fail.
- The fix makes the red command green and the full suite stays green; explain the cause in one sentence in the commit or the Spec's `outcome`.
- Who writes the test: the tester before Spec approval on the spec lane; the developer with the fix on the fast and emergency lanes.

## Test commands

- The single red command from Reproduce, now green; the flake loop above at its measured rate, green every time; the repository suite; `git grep DEBUG-<ID>` empty.

## Review

- The test fails on the parent commit and passes on the fix; it exercises the real faulty code, not a stub; the cause stated matches the diff; no debug output is left behind.

## Hand off

- Done: the red command, the cause in one sentence, the regression test, and the fix. Next: the reviewer; the architect when no seam could reproduce the bug. Needs: access to the environment or data where the failure happens, when you could not reproduce it. Stopped at: none, or the stop rule that fired.

## Stop if

- You are about to change code and have no command that fails on the exact symptom.
- You are changing two things at once, or you cannot say what result you predict.
- The regression test passes on the unfixed code.
- Three fixes have failed: stop, set the Task `blocked`, and question the design instead of trying a fourth; the loop sends it to Learn, as it does after three failed retries.
