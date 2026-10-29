# Review policy

How code review works in this repository, for every reviewer: a person, the aidd-team `reviewer`, a harness's review command, or a review bot. It starts from `templates/REVIEW.md`, the template `aidd init` writes for adopters, with this repository's notes at the end. A change to it is a change to how every pull request is reviewed, so it goes through review like any other.

Findings inform the human Approver; they never approve. Merge approval is a person's decision on the exact head commit. No reviewer, agent or bot, approves, merges, or posts an `/aidd` command.

## Passes

Review every change in three passes, in this order, and say which pass each finding comes from.

1. **Bugs.** Does the change do what it claims, on every path? Look for wrong logic, off-by-one and boundary errors, unhandled errors and empty inputs, races, resource leaks, and behavior that changed without a test noticing. Would the tests fail if the change were reverted or subtly wrong?
2. **Security.** Trace untrusted input to every sink. Check injection, authorization on each new path, secrets in code or logs, unsafe deserialization, new dependencies, and personal data that leaves where it should stay.
3. **Conformance.** The change matches its Spec (or, on the fast lane, its Change Request):
   - each Acceptance line is implemented and has a test that would catch a regression
   - nothing lands outside the declared scope
   - the frozen tests were not edited after approval
   - a user-visible change updates the tutorial, how-to, or reference page its reader uses, and the changelog, or says why not
   - public names (types, responses, events, fields, error codes) follow the standard the Spec cites and the language's convention. An RFC 9457 body is `ProblemDetails`, an exception `<Domain>Error`, and a response is named by its meaning, never its status code

   A changed line that traces to nothing in the Spec is a finding.

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

### Security findings

A security finding names who has less trust than the code assumes, what input they control, the control it gets past, the boundary it crosses, the impact, and the proof, each with its `file:line`. A note that misses one of them is a hardening note: list it after the findings, with no severity. Rank by the impact the proof shows, never the impact the bug class could have. When the deciding fact is outside the repository, such as a proxy rule, a cloud permission, or a deployed header, mark the finding "needs validation" and name that fact and its check, with no severity. After a Critical or High finding, check the sibling paths for the same root cause. End the report with what you read and what you skipped, and never call a change "secure".

## Confidence and quotes

Give every finding a confidence from 1 to 10: how sure you are that the finding is real. Quote the code it is about, as `file:line` and the line itself. A finding with no quote has a confidence of at most 4. List it in an appendix after the main list, "Findings without a quote", and never in the main list. A confidence never changes a severity. It tells the Approver how much to check.

## Nits

List at most 5 nits. Summarize the rest as a count ("and 12 more nits of the same kind"), so the findings that matter stay on the first screen.

## Out of scope

- Generated files (blocks between `aidd:gen` markers, lockfiles, build output, vendored code): review the source they come from instead.
- Anything CI already enforces (formatting, lint, type checks, the test run, the `aidd/gate` rules): do not repeat a check that already runs. Say so only when it failed or is missing.
- Changes the Spec does not ask for: report them as scope findings, do not review them as if they belonged.

## Dismissing a finding

A person who dismisses a finding records it in the list under `## Dismissed findings`, so that the review of a later head does not raise it again. An agent never adds or changes a dismissal. A review reads the list from the base branch (`git show <base>:REVIEW.md`), never from the head, so a branch cannot hide a finding on its own pull request.

Each dismissal is one line in this exact form:

`- <file> | <kind> | <hash> | <who> | <date> | <why>`

| Part | What it is |
| --- | --- |
| `<file>` | The file's path, from the repository root. A renamed file has a new fingerprint, so the finding comes back. |
| `<kind>` | The rule or the kind of the finding, in a few words, such as `missing-test`. A finding from the Security pass has a kind that starts with `security/`, such as `security/sql-injection`. |
| `<hash>` | 16 lowercase hex characters: the start of the SHA-256 of the quoted line and the line before it. Each of the two lines loses its leading and trailing spaces first, and each run of spaces in it becomes one space. |
| `<who>` | The person who dismissed it, as the config names Approvers, such as `@name`. |
| `<date>` | The date of the dismissal, as YYYY-MM-DD. |
| `<why>` | Why the finding does not apply. It can quote the code. |

The line starts with `- `. A space, a `|`, and a space separate the six parts. No part is empty, starts or ends with a space, or holds a `|`. The first three parts are the finding's fingerprint, `<file> | <kind> | <hash>`.

The hash has no line number, because a line number changes when the code above it changes. It covers the whole line and the line before it, so a different line, or the same line in another place, does not match. When the quoted code changes, the line no longer matches, and a reviewer can raise the finding again.

To get the hash of line `<n>` of `<file>`, run this command:

```sh
python3 -c 'import hashlib,sys; f,n=sys.argv[1],int(sys.argv[2]); n>0 or sys.exit("<n> is a line number: 1 or more"); L=[" ".join(x.split()) for x in open(f,encoding="utf-8").read().splitlines()]; n<=len(L) or sys.exit(f"{f} has only {len(L)} lines"); print(hashlib.sha256(((L[n-2] if n>1 else "")+"\n"+L[n-1]).encode()).hexdigest()[:16])' <file> <n>
```

A review honors only the lines in this exact form under the first line that reads exactly `## Dismissed findings` in the base branch's REVIEW.md, up to the next line that starts with `#`. It ignores every other line there, except a blank line and a one-line HTML comment, and reports it as a malformed dismissal line. The guard denies an agent's edit that adds or changes a line that looks like a dismissal anywhere in the file, or that moves one under the heading.

A finding whose kind starts with `security/` needs more. The `<who>` must be an Approver in the `security` pool (`owners.specialists` in `.aidd/config.yaml` on the base branch). Otherwise, the review raises the finding again.

## Dismissed findings

<!-- One line per dismissed finding, in the form "Dismissing a finding" gives. -->

## Repository notes

- **The gate decides what may merge everywhere aidd runs.** So a bug in any of these is a bug in every adopter's change control:
  - its rules, in `src/aidd/gate/rules/`, `gate/routing.py`, and `gate/rulebook.py`, with the secret patterns in `gate/rules/safety.py`
  - the platform adapters that feed it facts, in `platforms/github.py`, `platforms/gitlab.py`, `platforms/local_context.py`, `platforms/local_land.py`, and `workitems/decision_records.py`
  - the evidence path, in `gate/test_runner.py` and `gate/engine.py`
  - the guard in `guard/`, with its edit, command, and MCP checks, `guard/pre_tool.py`, `guard/session_hooks.py`, and `guard/hook_settings.py`
  - the derived status, in `workitems/derived_status.py`

  These need a second reader, and every changed rule needs a passing and a failing case in `examples/` that pins its finding code.
- **Fail closed.** A missing input, an API error, or an unparsable file must make the gate fail or stay pending, never pass. A new `try` that turns an error into a pass is Critical.
- **The base branch decides.** The gate reads its config, Policy, and CODEOWNERS from the base commit, never from the change. A change that reads any of them from head is Critical.
- **`schemas/*.json` are the source of truth.** Review the schema and `src/aidd/docsgen/`, not the generated blocks; `aidd gen-docs --check` proves the blocks match.
- **Zero dependencies, Python 3.11+.** A new import outside the standard library is a finding.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` links outside it.
- **Agents never approve.** A change that lets an agent account, a bot, or a hook approve, merge, or post an `/aidd` command is Critical.
