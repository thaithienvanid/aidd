---
description: "Hire the team into a repository: map the codebase read-only, fit aidd to it, and pick the first changes"
disable-model-invocation: true
argument-hint: "[what the team will work on here]"
---

Loop step: **Plan**, once per repository, before the team's first change in it: the team learns the codebase before it changes anything.

Lanes: spec.

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

Onboarding is read-only, so it runs even before the repository has `.aidd/config.yaml`. Every role here only reads and reports, and nothing is written before the person's yes in the chat. So here a role returns its findings as text in its reply, not in `.aidd/returns/` as the lead's rule 2 says for other commands.

1. Run `aidd init --dry-run` and read what it found:
   - the stacks and test commands
   - sensitive areas the baseline rules miss
   - generated code, owners, CI, and untested code
   - the agent instructions and planning tools already here

   The dry run writes nothing.
2. Run these subagents in parallel, each returning its findings as text, with file paths:
   - `aidd-team:architect`: the components and their boundaries, how data flows, a context diagram, where the tests are thin, and the domain packs the code needs. It also returns a draft architecture overview in the shape of `aidd new architecture`, a draft glossary in the shape of `aidd new glossary`: the domain's terms as the code and the docs use them, one meaning each. And a draft of the project's AGENTS.md guide in the shape of `aidd new agents`: what the project is, how it builds and tests, its layout, its conventions, and its rules, from the repository as it is.
   - `aidd-team:product-designer`, when the product has a user interface: a draft `DESIGN.md` and design tokens, in the shape of `aidd new design-system`. It reads them from the product as it is: its colors, type, spacing, components, and their states.
   - `aidd-team:security-engineer`: where authentication, secrets, personal data, and payments live, and the risk rules and owners each needs
   - `aidd-team:sre`: how the code builds, deploys, and is watched, which existing CI checks can serve as evidence, and what a runbook or rollback is missing
3. Give the author one onboarding brief with:
   - the config the setup change should hold (the dry run's proposal, corrected by the specialists)
   - the draft architecture overview, glossary, AGENTS.md guide, and design system, for a person to accept and add as the first documentation changes. Nothing is written here. The design system is a normal change, and AGENTS.md a major one, since it steers every agent.
   - the areas that need a characterization test before anyone changes them
   - three small, low-risk first changes to prove the loop here

   Include what the team will work on, if given: $ARGUMENTS. End the brief with one question: "Set up aidd here?", with the exact `aidd init` command and its flags, what it writes, and that it works on its own branch. Never send the person to a terminal.

Then stop. On their yes, create the branch `chore/adopt-aidd`, run the command and `aidd doctor`, and commit the setup there. Pass on each `Restart ...` line it printed. A person reviews and merges the setup change. The setup change steers every agent, so review it as a major change. Tune the risk rules once the team sees which asks help.
