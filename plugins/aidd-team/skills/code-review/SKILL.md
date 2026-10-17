---
name: code-review
description: "Practice skill: review a diff against its Spec. Use in an aidd repository when reading a PR/MR as a reviewer, or someone asks to review a diff or whether it is ready to merge."
metadata:
  checked: "2026-09-30"
---

# Code review

**Use it when** you read a pull request as the reviewer, or as second reader for the security engineer or the product designer.

**Do not use when** you are writing the change, not reading someone else's. A self-review before handoff is Implement's own verification.

## Standards

<!-- aidd:gen practice:code-review -->
| Standard | Edition |
| --- | --- |
| Google Engineering Practices: the code review standard | — |
| Conventional Comments labels (emerging) | — |
| Diff discipline: every changed line traces to the Spec, and speculative, single-use, unrequested, or drive-by code is a finding | — |
| The OWASP Code Review Guide | — |
| AI-assisted coding: verify every generated line, API, and package before relying on it, and keep secrets and personal data out of prompts | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:code-review`.
<!-- aidd:end -->

## Review

- Read the Spec, then the diff, then the local gate view (`aidd gate --spec specs/<ID>.md`, advisory, blind to approvals).
- Judge design, functionality, complexity, tests, naming, comments, style, and docs. Say what would improve code health, not what you would have written. "This name made me guess wrong" is a valid blocking comment (`aidd-team:naming`).
- Spec conformance: every Acceptance line has a test that would catch a regression. Nothing is outside the scope. Rollback, observe, and decisions match what shipped.
- Diff discipline: a speculative feature, a single-use abstraction, unrequested configurability, handling an impossible case, or a drive-by edit is a finding, and so is deleting pre-existing dead code unasked.
- Security trace: follow untrusted input to its sinks. Check authorization on every new path, secrets, injection, deserialization, and rate limits. Escalate to the security engineer on major.
- AI-generated code pass, when a commit names an agent:
  - each new package real, exactly named, and allowed (a hallucinated name invites a squatter)
  - each API and flag in the pinned version
  - no empty or loosened test
  - no duplicated helper
  - no code of unknown license
- Test strength: would the tests fail if the change were reverted or subtly wrong? Run the tester's mutation command and report surviving mutants.
- Silent-failure pass, over every new or changed error path. Each pattern below is a finding unless the Spec or a comment at the site records the decision:
  - an exception dropped or only logged where the caller needed it
  - a broad catch (`except Exception`, `catch (e)`) swallowing bugs
  - a default hiding a failure (an empty list for "the service is down")
  - an ignored return code, unawaited promise, or discarded `err`
  - leftover debug output

### Report

- Rank findings Critical, High, Medium, Low, Nit. Give each its file, line, failure scenario, and suggested fix. Label each with Conventional Comments (issue, suggestion, question, nitpick). Fold duplicates. Name disagreements.
- Never approve, never edit, never post an `/aidd` command. Bash reads only.

## Test commands

The reviewer adds no test commands. It runs the Spec's.

- From `aidd-team:test-design`: Mutation run.

## Stop if

- The diff is too large to review line by line: ask for a split rather than skim it.
- A finding needs a judgment only the Approver can make.
- You are about to edit the change, approve it, or post an `/aidd` command.

## Hand off

- Done: the ranked report. Next: the author posts it and the Approver decides Merge approval. Findings needing code return to Implement. Needs: a judgment only the Approver can make. Stopped at: none, or the stop rule that fired.
