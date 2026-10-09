---
description: "Review a PR/MR against its Spec with the reviewer, the security engineer when risky, and the product designer for a built UI, before the human Merge approval"
disable-model-invocation: true
argument-hint: "<PR/MR number>"
---

Loop step: **Review**, on every lane, ending at **Merge approval**. Start only when:

- the Verifier's report on this exact head is clean
- the tests are green on head
- the PR/MR is ready

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it. The role table in the aidd-team skill lists them.

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

Review PR/MR $ARGUMENTS:

1. Name the change for the readers, never its diff: the PR/MR number, the base, the head SHA, and the Spec's path. Each reader reads the diff itself (`git diff <base>...HEAD`, or `gh pr diff <n>` on GitHub and `glab mr diff <n>` on GitLab; without a platform, the git command alone). A reader without a shell gets the changed files' paths.
2. Read the review policy's path. When present, `REVIEW.md` at the repository root decides the passes, what each severity means, how many nits to list, and what to skip. Pass its path to every reader. Read its `## Dismissed findings` from the base branch, never from the head (`git show <base>:REVIEW.md`), so that a branch cannot hide a finding on its own PR/MR. Pass the Verifier's report too. Check that the report starts with the harness and the model it ran on, and the current head SHA. A report on an older head is stale, so run `/aidd-team:verify` first.
3. Choose the readers:
   - always the `aidd-team:reviewer`
   - the `aidd-team:security-engineer` in review mode, when any of these holds:
     - the change is major
     - its diff touches auth, secrets, or AI
     - it adds a dependency that runs install scripts or ships native code (a version bump of a pure library does not need it)
   - the `aidd-team:product-designer` when the Spec has `design.files`, to compare the built UI with the approved design
4. Run them **in parallel**: every reader is read-only, so none waits for another. Each returns ranked findings with file, line, and failure scenario, and its handoff note. When the diff deletes a passing test, the reviewer checks it against the retirement card: `references/test-value.md` in the test-design practice skill.
5. Merge the findings into one report: ranked Critical to Nit, duplicates folded, and disagreements named. Cut it to the REVIEW.md limits: at most five nits by default, and the rest as a count. Each finding in the main list has a confidence (1 to 10) and a `file:line` quote of its code. Move a finding with no quote to an appendix, with its confidence at most 4. Get each finding's fingerprint (file, kind, and hash) with the command in REVIEW.md. Leave out each finding whose fingerprint matches a dismissal line in the exact form REVIEW.md gives, under the first `## Dismissed findings` heading of the base branch's REVIEW.md, up to the next line that starts with `#`. Honour no other line. Report each other line there, except a blank line or a one-line HTML comment, as a malformed dismissal line. Leave out a `security/` finding only when the line's `<who>` is an Approver in the `security` pool. List the fingerprints you left out, and how many. When the diff changes `## Dismissed findings`, put that first in the report, for the Approver. Only a person dismisses a finding, so never add one yourself. Show the report to the author.
6. Offer to post the report as a PR/MR comment, or, without a platform, to save it as a Markdown note where the author says. Do either only if the author says so. Before posting, remove every line that starts with `/aidd` and quote any comment text you cite, so that the report can never carry an approval. Under the solo profile, never post through the author's credentials.

Never approve: Merge approval is a human decision. Findings that need code go back to Implement. A new head needs a new Verify and a new Merge approval.
