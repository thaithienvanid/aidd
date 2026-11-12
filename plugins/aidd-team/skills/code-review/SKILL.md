---
name: code-review
description: "Practice skill: review a diff against its Spec. Use in an aidd repository when reading a PR/MR as a reviewer, or someone asks to review a diff or whether it is ready to merge."
metadata:
  checked: "2026-10-22"
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

- Read the Spec, then the diff, then the checks on the head (`aidd test` evidence, or the platform's checks).
- Judge design, functionality, complexity, tests, naming, comments, style, and docs. Say what would improve code health, not what you would have written. "This name made me guess wrong" is a valid blocking comment (`aidd-team:naming`). A diff's shape and its comments follow `aidd-team:maintainable-code`.
- Spec conformance: every Acceptance line has a test that would catch a regression. Nothing is outside the scope. Rollback, observe, and decisions match what landed.
- Diff discipline: a speculative feature, a single-use abstraction, unrequested configurability, handling an impossible case, or a drive-by edit is a finding, and so is deleting pre-existing dead code unasked.
- Security trace: follow untrusted input to its sinks. Check authorization on every new path, secrets, injection, deserialization, and rate limits. Shape each security finding, its severity, and its outcome as [references/security-findings.md](references/security-findings.md) says. Escalate a major-route change to the security engineer.
- Ask which test compares a changed reader, parser, or decider's new answers with the old over a generated set, and which shows that the honest work a new control could block still passes.
- Run the passes in [references/passes.md](references/passes.md), over the artifact, a stated rule, untrusted text, AI-generated code, silent failures, test strength, and operability.

### Report

- Report as [references/review-output.md](references/review-output.md) says: both questions, and the verdict first. Rank findings Critical, High, Medium, Low, Nit. Give each its file, line, failure scenario, and suggested fix, quote the line it is about, and give a confidence from 1 to 10 (REVIEW.md sets both rules). When a finding feels vague or its severity unclear, compare it with the worked examples there. Label each with Conventional Comments (issue, suggestion, question, nitpick), `blocking` or `non-blocking`. Fold duplicates. Name disagreements.
- Never approve, merge, or edit. Run only commands that read.

## Test commands

The reviewer adds no test commands. It runs the touched tests and reads the rest in the evidence.

- From `aidd-team:test-design`: Mutation run.

## Stop if

- The diff is too large to review line by line: ask for a split rather than skim it.
- A finding needs a judgment only the person who decides Merge approval can make.
- You are about to edit the change, approve it, or merge it.

## Hand off

- Done: the ranked report. Next role: the author posts it and a person decides Merge approval. Findings needing code return to Implement. Needs: a judgment only that person can make. Stopped at: none, or the stop rule's code.
