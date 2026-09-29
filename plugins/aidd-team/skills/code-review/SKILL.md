---
name: code-review
description: "Practice skill: review a diff against its Spec. Use when reading a pull request or merge request as the reviewer or a second reader, or when someone asks to review this, look over my diff, is this ready to merge, what did I miss, or check this PR: the Spec first, then design, functionality, complexity, tests, naming, comments, style, and docs, diff discipline, a security trace, a silent-failure pass, test strength, and ranked findings with evidence."
metadata:
  checked: "2026-09-28"
---

# Code review

**Use it when** you read a pull request as the reviewer or as a second reader for the security engineer or the product designer.

**Do not use when** you are writing the change rather than reading someone else's; a self-review before handing off is Implement's own verification, not this.

## Standards

- Google Engineering Practices, the code review standard.
- Conventional Comments.
- Diff discipline (every changed line traces to the Spec).
- The OWASP Code Review Guide.

## Review

- Read the Spec first, then the diff, then the local gate view (`aidd gate --spec specs/<ID>.md`, advisory, blind to approvals).
- Judge design, functionality, complexity, tests, naming, comments, style, and documentation; say what would improve code health, not what you would have written.
- Spec conformance: every Acceptance line has a test that would catch a regression; nothing outside the scope; rollback and observe match what shipped; decisions match the code.
- Diff discipline: a speculative feature, a single-use abstraction, unrequested configurability, handling of an impossible case, or a drive-by edit is a finding; so is deleted pre-existing dead code nobody asked for.
- Security trace: follow untrusted input to its sinks; check authorization on every new path; check secrets, injection, deserialization, and rate limits; escalate to the security engineer on major.
- Test strength: would the tests fail if the change were reverted or subtly wrong? Run the mutation command the tester named and report surviving mutants.
- Silent-failure pass, over every new or changed error path: an exception caught and dropped, or only logged, where the caller needed to know; a broad catch (`except Exception`, `catch (e)`, `rescue => e`) that also swallows bugs; a fallback or default value that hides a failure from the user or the metrics (an empty list for "the service is down"); an error that is not propagated or returned (an ignored return code, an unawaited promise, a discarded `err`); and leftover debug output (prints, `console.log`, commented-out code, a `DEBUG-` marker). Each is a finding unless the Spec or a comment at the site records the decision to drop the failure.

## Report

- Findings ranked Critical, High, Medium, Low, Nit, each with file, line, the failure scenario, and a suggested fix, labeled with Conventional Comments (issue, suggestion, question, nitpick); duplicates folded, disagreements named.
- Never approve, never edit, never post an `/aidd` command; Bash reads only.

## Hand off

- Done: the ranked report. Next: the author posts it and the Approver decides Merge approval; findings that need code return to Implement. Needs: a judgment only the Approver can make. Stopped at: none, or the stop rule that fired.
