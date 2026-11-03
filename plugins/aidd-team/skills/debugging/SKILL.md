---
name: debugging
description: "Practice skill: find a failure's cause by experiment first. Use in an aidd repository when a test fails, a bug is reported, something is flaky, or someone says it broke."
metadata:
  checked: "2026-10-22"
---

# Debugging

**Use it when** something behaves differently from what the Spec, a test, or a person expects, and the cause is not yet known. It can be a red test, a bug report, a flaky check, a crash, or a wrong number.

**Do not use when** the cause is already known and shown by a failing test (go straight to the fix). Do not use it when production is burning right now: mitigate first with `aidd-team:incident-response`, and debug the copy of the failure afterwards.

## Standards

<!-- aidd:gen practice:debugging -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Scientific debugging: observe, hypothesize, predict, experiment, and conclude, with a written log and delta debugging to shrink the failing input | — | 2026-10-16 (reviewed) | — |
| The nine debugging rules: understand the system, make it fail, quit thinking and look, divide and conquer, change one thing at a time, keep an audit trail, check the plug, get a fresh view, and if you did not fix it, it is not fixed | — | 2026-10-16 (reviewed) | — |
<!-- aidd:end -->

## Implement

### Reproduce, before any theory

1. Write down the exact symptom: the message, the wrong value, the exit code, the environment. "It is slow" or "it fails sometimes" is not yet a symptom.
2. Find one command that goes red on that exact symptom, and only on it. A test that fails for another reason proves nothing. Record the command, the commit, and the seed or time it needs.
3. If flaky, run it in a loop (`for i in $(seq 50); do <cmd> || break; done`) until you know its failure rate p. Fix the seed, the clock, the order, or the concurrency until it fails every time, or say you could not. A fix needs 3 ÷ p green runs, such as 60 for 1 in 20, to show with 95% confidence that the failure is gone.
4. Minimise: remove input, steps, configuration, and code until removing anything more makes the failure go away. The smallest case usually names the cause.
5. A symptom that grows with time or load (memory, open files, a pool that runs dry) is a slope: measure it per round. The causes and the test: [references/memory-and-resources.md](references/memory-and-resources.md).

### Hypothesize and experiment

- Rank three to five hypotheses, each falsifiable: what you expect to see if it is true, and the one experiment that would show it false. Start with the cheapest to check, not the most interesting. Worked example and log format: [references/hypotheses.md](references/hypotheses.md).
- Change one variable per experiment. Predict the result before you run it. A result you did not predict is information. A result you explain after the fact is not. An experiment that needs throwaway code goes on an explore branch, which only a person starts.
- Look before you reason. Read the actual values (a debugger, a print, the log line), not the code you think runs. Check the plug: the right binary, branch, configuration, and data.
- Bisect when the bug is a regression: `git bisect run <the red command>` finds the commit faster than reading diffs. The command exits 125 to skip a commit that cannot build.
- Tag every temporary print, log line, or flag with one marker (`DEBUG-<ID>`). Remove all of them before handing off.

### Fix and prove

- The regression test goes at the seam that reproduces the real bug: the unit, the query, the HTTP call, or the queue message where the failing command showed it. A test that mocks away the faulty part passes against the bug and proves nothing.
- If no seam in the code can reproduce the failure without the whole system, that is a finding for the architect. Record the finding. Test at the nearest seam that does fail. Never skip the test.
- The fix makes the red command green and the full suite stays green. Explain the cause in one sentence in the commit or the Spec's `outcome`.
- Who writes the test: the verifier before Spec approval on the spec lane; the developer with the fix on the fast and emergency lanes.

## Review

- The test fails on the parent commit and passes on the fix. It exercises the real faulty code, not a stub. The stated cause matches the diff. No debug output is left behind.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Red command | the exact symptom is reproduced, then fixed | the single command from Reproduce, red on the parent and green on the fix |
| Flake loop | a flaky failure is gone, not hidden | the loop above, run 3 ÷ p times for the measured failure rate p, green every time |
| Debug marker check | no temporary debug output is left | `! git grep -q DEBUG-<ID>`, which exits 0 only when no marker is left |

## Stop if

- You are about to change code and have no command that fails on the exact symptom.
- You are changing two things at once, or you cannot say what result you predict.
- The regression test passes on the unfixed code.
- You are about to change the failing test instead of the code. A wrong test goes back to Specify for a new Spec approval.
- Three fixes have failed. Stop, and record `blockers` as [references/hypotheses.md](references/hypotheses.md) says. The Task stays stopped until a person re-plans it. Question the design instead of trying a fourth.

## Hand off

- Done: the red command, the cause in one sentence, the regression test, and the fix. Next: the reviewer; the architect when no seam could reproduce the bug. Needs: access to the environment or data where the failure happens, when you could not reproduce it. Stopped at: none, or the stop rule that fired.
