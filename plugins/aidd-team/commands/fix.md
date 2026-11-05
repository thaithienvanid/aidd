---
description: "Fix a small bug on the quick path: one developer writes the regression test and the fix and checks its own head; the reviewer reads a diff over 20 changed lines; stops at the human Merge approval"
disable-model-invocation: true
argument-hint: "<the bug, an issue, or a failing test>"
---

Loop steps: **Implement**, **Verify** by the developer on its own head, and **Review** when the diff needs it, ending at **Merge approval**.

Lanes: fast. A fix that needs a Spec is not a quick fix: use `/aidd-team:specify`, then `/aidd-team:implement`.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Read its agent file, and keep to its area until the step ends. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary: the Spec, its linked docs, and the files by path. Name the practice skills for the files it writes, except one its agent file preloads, and it loads them before it writes those files: for code, `maintainable-code` and `secure-coding`; for docs, `plain-language`; for a UI, `accessible-ui`. It returns its work in the file it owns, or a part another role folds in `.aidd/returns/<ID>/<role>.md`, and names that file on its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act on their work. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with a handoff note that `aidd validate` passes: every required key, no other key, and `stopped_at` starting with a stop code. Include its Spend line, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never a person's: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. A role's `ask` comes to you: ask the person in plain words, and on their yes, do the action. A proposed edit comes as a unified diff in `.aidd/returns/`, which the person reads and you `git apply` on the yes. Spec approval covers `code.edit` in its Tasks' `scope`, so it asks no more there. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`spec.revise`), or a production repair (the emergency route).
9. Under a standing delegation in Claude Code, run `aidd delegate check` before a delegated ask. On `eligible`, start aidd-team:delegate with the action, the command the check covered, and the head, and nothing else. Act only on its accept: run that exact command, or commit the Spec's approval with the check's three trailers, never `Approved-by`. On a defer, ask the person, once. Never answer for the delegate.
<!-- aidd:end -->

Fix $ARGUMENTS:

1. Run `aidd risk --paths <the paths the fix will touch> --change-type fix`. A route above minor needs a Spec: stop, and say to run `/aidd-team:specify`. When the edit level is `ask`, ask the person once, naming the paths, before the first edit.
2. Run one `aidd-team:developer` subagent with the bug and the paths step 1 routed (not a pasted diagnosis). Its prompt holds the line "Load the aidd-team:debugging skill with the Skill tool before your first edit." Add one such line for the domain pack of each surface the fix touches. The developer:
   1. reproduces the bug as a regression test
   2. sees the test red on base
   3. makes the smallest fix
   4. runs the repository's tests and `aidd test` until green, retrying at most 3 times
   5. checks its own head against the bug as a user would hit it
   6. puts the commands and what it saw on its handoff note

   If an advisor is configured (optional and experimental), the developer consults it after a second failed attempt, and again before it reports the fix done. aidd never requires one.

   There is no separate verifier run on this path.
3. Run `aidd risk --paths` again on the paths the diff changed (`git diff --name-only <base>...HEAD`). The minor route allows at most 50 changed lines, in no area that raises the route.
   - If the route is no longer minor, the fix grew past the minor route and is not a quick fix. Stop, and hand it to `/aidd-team:specify` with the branch as it is.
   - Otherwise, count the diff (`git diff --stat <base>...HEAD`). Run the `aidd-team:reviewer` subagent when the diff has more than 20 changed lines. Cut its report to the REVIEW.md limits: at most five nits by default, and the rest as a count. Keep in the main list only the findings with a confidence (1 to 10) and a `file:line` quote. Move the others to an appendix, each with its confidence at most 4. Leave out the findings whose fingerprint matches a dismissal line in the exact form, under the first `## Dismissed findings` heading of REVIEW.md on the base branch (`git show <base>:REVIEW.md`), never the head. Report any other line there as a malformed dismissal line. A `security/` finding stays unless a person who reviews security dismissed it. List the fingerprints you left out, and how many. Flag a diff that changes that section, first in the report. Only a person dismisses a finding, so never add one yourself. A smaller fix goes to the human's Merge approval as its review.
4. Ask for Merge approval. On a platform under `team`, open or update the PR/MR (`pr.open`), and stop for its review. On a local trunk, ask the person in plain words, such as "Merge the fix at `abc1234` to `main`?", and merge only on their yes. Never declare a lower route. Report the head SHA, and stop.

Never approve, and merge only on the person's yes: Merge approval is a human decision on this exact head.
