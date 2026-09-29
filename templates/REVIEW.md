# Review policy

How code review works in this repository, for every reviewer: a person, the aidd-team `reviewer`, a harness's review command, or a review bot. `aidd init` wrote this file once; it is yours now, so change it to fit the repository. A change to it is a change to how every pull request is reviewed, so it goes through review like any other.

Findings inform the human Approver; they never approve. Merge approval is a person's decision on the exact head commit, and no reviewer, agent or bot, approves, merges, or posts an `/aidd` command.

## Passes

Review every change in three passes, in this order, and say which pass each finding comes from.

1. **Bugs.** Does the change do what it claims, on every path? Look for wrong logic, off-by-one and boundary errors, unhandled errors and empty inputs, races, resource leaks, and behavior that changed without a test noticing. Would the tests fail if the change were reverted or subtly wrong?
2. **Security.** Trace untrusted input to every sink: injection, authorization on each new path, secrets in code or logs, unsafe deserialization, new dependencies, and personal data that leaves where it should stay.
3. **Conformance.** The change matches its Spec (or, on the fast lane, its Change Request): each Acceptance line is implemented and has a test that would catch a regression, nothing lands outside the declared scope, and the frozen tests were not edited after approval. A changed line that traces to nothing in the Spec is a finding.

## Severity

Rank every finding, and give each one the file, the line, the failure scenario, and a suggested fix.

| Severity | Meaning |
| --- | --- |
| Critical | Reserved for a finding that breaks behavior, leaks data, or breaches a policy (the Spec, the gate, a law, or a contract). Blocks the merge. |
| High | Wrong in a case users or callers will hit, or a missing test for an Acceptance line; fix before merge. |
| Medium | A real defect in a rare case, or a maintainability problem that will cause one; fix now or record why not. |
| Low | Worth fixing, safe to defer. |
| Nit | Style or taste; never blocks. |

Do not raise a finding to Critical to get attention: a report with one honest Critical is read, and a report of five is skimmed.

## Nits

List at most 5 nits. Summarize the rest as a count ("and 12 more nits of the same kind"), so the findings that matter stay on the first screen.

## Out of scope

- Generated files (blocks between `aidd:gen` markers, lockfiles, build output, vendored code): review the source they come from instead.
- Anything CI already enforces (formatting, lint, type checks, the test run, the `aidd/gate` rules): do not repeat a check that already runs; say so only when it failed or is missing.
- Changes the Spec does not ask for: report them as scope findings, do not review them as if they belonged.

## Repository notes

<!-- Add what a reviewer here must know: the modules that need a second reader, the invariants that are easy to break, the checks that are known to be flaky. -->
