---
description: "Verify and review a PR/MR against its Spec side by side: the verifier, the reviewer, the security engineer when risky, and the product designer for a built UI, before the human Merge approval"
disable-model-invocation: true
argument-hint: "<PR/MR number>"
---

Loop steps: **Verify** and **Review**, side by side on the same head, on every lane, ending at **Merge approval**. Start once the builders' `aidd test --changed` is green on head. The review counts only with a clean verifier report on that head.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it. The role table in the aidd-team skill lists them.

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

Review PR/MR $ARGUMENTS:

1. Name the change for the readers, never its diff: the PR/MR number, the base, the head SHA, and the Spec's path. Each reader reads the diff itself (`git diff <base>...HEAD`, or `gh pr diff <n>` on GitHub and `glab mr diff <n>` on GitLab; without a platform, the git command alone). A reader without a shell gets the changed files' paths.
2. Read the review policy's path. When present, `REVIEW.md` at the repository root decides the passes, what each severity means, how many nits to list, and what to skip. Pass its path to every reader. Read its `## Dismissed findings` from the base branch, never from the head (`git show <base>:REVIEW.md`), so that a branch cannot hide a finding on its own PR/MR. When a verifier report on this head is already posted, pass it too. It starts with the harness, the model it ran on, and the current head SHA. A report on an older head is stale, so the verifier runs again in step 4.
3. Choose the readers:
   - the `aidd-team:verifier`, unless a clean report on this exact head is already posted. It runs its own `aidd test` and each Acceptance line, as `/aidd-team:verify` says
   - always the `aidd-team:reviewer`
   - the `aidd-team:security-engineer` in review mode, when any of these holds:
     - the change is major, or has a security, data, privacy, compliance, or third_party risk dimension
     - its diff touches auth, secrets, or AI
     - it adds a dependency that runs install scripts or includes native code (a version bump of a pure library does not need it)
   - the `aidd-team:product-designer` when the Spec has `design.files`, to compare the built UI with the approved design
   - the `aidd-team:domain-expert` when the Spec's Context names a domain pack, to check the change against the domain's rules
   - the `aidd-team:compliance-analyst` when the change has a compliance, privacy, or data dimension, or the profile is audited, to check the diff against the Spec's controls
4. Run them **in parallel**: every reader is read-only, so none waits for another, and the verifier runs beside them. Each returns ranked findings with file, line, and failure scenario, and its handoff note. When the diff deletes a passing test, the reviewer checks it against the retirement card: `references/test-value.md` in the test-design practice skill.
5. A failed command or a mismatch in the verifier's report sends the head back to `/aidd-team:implement` with the findings, in one pass, and the review does not count. Otherwise merge the findings into one report: ranked Critical to Nit, duplicates folded, and disagreements named. Cut it to the REVIEW.md limits: at most five nits by default, and the rest as a count. Each finding in the main list has a confidence (1 to 10) and a `file:line` quote of its code. Move a finding with no quote to an appendix, with its confidence at most 4. Get each finding's fingerprint (file, kind, and hash) with the command in REVIEW.md. Leave out each finding whose fingerprint matches a dismissal line in the exact form REVIEW.md gives. Read those lines under the first `## Dismissed findings` heading of the base branch's REVIEW.md, up to the next line that starts with `#`. Honor no other line. Report each other line there, except a blank line or a one-line HTML comment, as a malformed dismissal line. Leave out a `security/` finding only when the line's `<who>` is an Approver in the `security` pool. List the fingerprints you left out, and how many. When the diff changes `## Dismissed findings`, put that first in the report, for the Approver. Only a person dismisses a finding, so never add one yourself. Show the report to the author.
6. Offer to post the report as a PR/MR comment, or, without a platform, to save it as a Markdown note where the author says. Do either only if the author says so. Before posting, remove every line that starts with `/aidd` and quote any comment text you cite, so that the report can never carry an approval. Under the solo profile, never post through the author's credentials.

Never approve: Merge approval is a human decision. Findings that need code go back to Implement. A new head needs a new Verify and a new Merge approval.
