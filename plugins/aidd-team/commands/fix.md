---
description: "Fix a small bug on the quick path: one developer writes the regression test and the fix and checks its own head; the reviewer reads a diff over 20 changed lines; stops at the human Merge approval"
disable-model-invocation: true
argument-hint: "<the bug, an issue, or a failing test>"
---

Loop steps: **Implement**, **Verify** by the developer on its own head, and **Review** when the diff needs it, ending at **Merge approval**.

Lanes: fast. A fix that needs a Spec is not a quick fix: use `/aidd-team:specify`, then `/aidd-team:implement`.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route; you never edit an artifact yourself. Send a change to a Spec, a test, a proposal, or code to the role that owns the file. Pass on that role's handoff note.
2. Hand over file paths, not pasted facts: "read specs/SPEC-1.md and its latest handoff note", never a restatement of what a file already says.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
<!-- aidd:end -->

Fix $ARGUMENTS:

1. Run `aidd assess --paths <the paths the fix will touch> --type fix`. A route above minor needs a Spec: stop, and say to run `/aidd-team:specify`.
2. Run one `aidd-team:developer` subagent with the bug and the Change Request block's scope (its paths, not a pasted diagnosis). Its prompt holds the line "Load the aidd-team:debugging skill with the Skill tool before your first edit." Add one such line for the domain pack of each surface the fix touches. The developer:
   1. reproduces the bug as a regression test
   2. sees the test red on base
   3. makes the smallest fix
   4. runs the repository's tests and `aidd test` until green, retrying at most 3 times
   5. checks its own head against the bug as a user would hit it
   6. puts the commands and what it saw on its handoff note

   If an advisor is configured (optional and experimental), the developer consults it after a second failed attempt, and again before it reports the fix done. aidd never requires one.

   There is no separate verifier run on this path.
3. Run `aidd assess` on the branch. The minor route allows at most 50 changed lines, and no risk dimension or protected path.
   - If the route is no longer minor, the fix grew past the minor route and is not a quick fix. Stop, and hand it to `/aidd-team:specify` with the branch as it is.
   - Otherwise, count the diff (`git diff --stat <base>...HEAD`). Run the `aidd-team:reviewer` subagent when the diff has more than 20 changed lines. Cut its report to the REVIEW.md limits: at most five nits by default, and the rest as a count. Keep in the main list only the findings with a confidence (1 to 10) and a `file:line` quote. Move the others to an appendix, each with its confidence at most 4. Leave out the findings whose fingerprint matches a dismissal line in the exact form, under the first `## Dismissed findings` heading of REVIEW.md on the base branch (`git show <base>:REVIEW.md`), never the head. Report any other line there as a malformed dismissal line. A `security/` finding stays unless an Approver in the `security` pool dismissed it. List the fingerprints you left out, and how many. Flag a diff that changes that section, first in the report. Only a person dismisses a finding, so never add one yourself. A smaller fix goes to the human's Merge approval as its review.
4. Open or update the PR/MR with the Change Request block (`aidd describe`; without a platform, `aidd describe --commit` records it on the branch). The block declares `route = "minor"`, so the gate asks for one Merge approval. Never declare a lower route. Report the head SHA and what `aidd gate` still waits for, and stop.

Never approve and never merge: Merge approval is a human decision on this exact head.
