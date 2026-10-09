---
description: "Hire the team into a repository: map the codebase read-only, fit aidd to it, and pick the first changes"
disable-model-invocation: true
argument-hint: "[what the team will work on here]"
---

Loop step: **Plan**, once per repository, before the team's first change in it: the team learns the codebase before it changes anything.

Lanes: spec.

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

Onboarding is read-only, so it runs even before the repository has `.aidd/config.toml`. Every role here only reads and reports, and nothing is written. A person runs `aidd init` and merges the setup change afterwards.

1. Run `aidd init --dry-run` and read what it found:
   - the stacks and test commands
   - sensitive areas the baseline rules miss
   - generated code, owners, CI, and untested code
   - the agent instructions and planning tools already here

   The dry run writes nothing.
2. Run these subagents in parallel, each returning its findings as text, with file paths:
   - `aidd-team:architect`: the components and their boundaries, how data flows, a context diagram, where the tests are thin, and the domain packs the code needs. It also returns a draft architecture overview in the shape of `aidd new architecture`, and a draft glossary in the shape of `aidd new glossary`: the domain's terms as the code and the docs use them, one meaning each.
   - `aidd-team:product-designer`, when the product has a user interface: a draft `DESIGN.md` and design tokens, in the shape of `aidd new design-system`. It reads them from the product as it is: its colours, type, spacing, components, and their states.
   - `aidd-team:security-engineer`: where authentication, secrets, personal data, and payments live, and the risk rules and owners each needs
   - `aidd-team:sre`: how the code builds, deploys, and is watched, which existing CI checks can serve as evidence, and what a runbook or rollback is missing
3. Give the author one onboarding brief with:
   - the config the setup change should hold (the dry run's proposal, corrected by the specialists)
   - the draft architecture overview, glossary, and design system, for a person to accept and add as the first documentation changes. Nothing is written here, and the design system is a normal change.
   - the areas that need a characterization test before anyone changes them
   - three small, low-risk first changes to prove the loop here

   Include what the team will work on, if given: $ARGUMENTS. End the brief with the exact `aidd init` command, with its flags, for a person to run.

Then stop. A person runs that command, reviews, and merges the setup change. The setup change touches `.aidd/`, so the gate treats it as major. Start in advisory mode, and enforce once the gate's findings match the team's judgment.
