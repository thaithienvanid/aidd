---
description: "Fix a small bug on the quick path: one developer writes the regression test and the fix and checks its own head; the reviewer reads a diff over 20 changed lines; stops at the human Merge approval"
disable-model-invocation: true
argument-hint: "<the bug, an issue, or a failing test>"
---

Loop steps: **Implement**, **Verify** by the developer on its own head, and **Review** when the diff needs it, ending at **Merge approval**.

Lanes: fast. A fix that needs a Spec is not a quick fix: use `/aidd-team:specify`, then `/aidd-team:implement`.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Take its pack with `aidd context <ID> --role <role> --play --session ${CLAUDE_SESSION_ID}`, so the guard holds you to its files, and run `--stop-playing` when the step ends, before you start a role. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Under autopilot, start every role. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary. With a Spec, that is its context pack, `aidd context <ID> --role <role>`, else the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never an approval: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Fix $ARGUMENTS:

1. Run `aidd gate --paths <the paths the fix will touch> --type fix`. A route above minor needs a Spec: stop, and say to run `/aidd-team:specify`.
2. Run one `aidd-team:developer` subagent with the bug and the paths step 1 routed (not a pasted diagnosis). Its prompt holds the line "Load the aidd-team:debugging skill with the Skill tool before your first edit." Add one such line for the domain pack of each surface the fix touches. The developer:
   1. reproduces the bug as a regression test
   2. sees the test red on base
   3. makes the smallest fix
   4. runs the repository's tests and `aidd test` until green, retrying at most 3 times
   5. checks its own head against the bug as a user would hit it
   6. puts the commands and what it saw on its handoff note

   If an advisor is configured (optional and experimental), the developer consults it after a second failed attempt, and again before it reports the fix done. aidd never requires one.

   There is no separate verifier run on this path.
3. Run `aidd gate` on the branch: it computes the route again from the diff. The minor route allows at most 50 changed lines, and no risk dimension or protected path.
   - If the route is no longer minor, the fix grew past the minor route and is not a quick fix. Stop, and hand it to `/aidd-team:specify` with the branch as it is.
   - Otherwise, count the diff (`git diff --stat <base>...HEAD`). Run the `aidd-team:reviewer` subagent when the diff has more than 20 changed lines. Cut its report to the REVIEW.md limits: at most five nits by default, and the rest as a count. Keep in the main list only the findings with a confidence (1 to 10) and a `file:line` quote. Move the others to an appendix, each with its confidence at most 4. Leave out the findings whose fingerprint matches a dismissal line in the exact form, under the first `## Dismissed findings` heading of REVIEW.md on the base branch (`git show <base>:REVIEW.md`), never the head. Report any other line there as a malformed dismissal line. A `security/` finding stays unless an Approver in the `security` pool dismissed it. List the fingerprints you left out, and how many. Flag a diff that changes that section, first in the report. Only a person dismisses a finding, so never add one yourself. A smaller fix goes to the human's Merge approval as its review.
4. Under `publish: agents`, open or update the PR/MR. Otherwise ask the person to type `land it` (a local trunk) or `publish` (a platform trunk). The change needs no Change Request block: the gate takes `route: minor` from the diff, so it asks for one Merge approval. Add a block (`aidd describe`) only for a risk the paths hide, and never declare a lower route. Report the head SHA and what `aidd gate` still waits for, and stop.

Never approve and never merge: Merge approval is a human decision on this exact head.
