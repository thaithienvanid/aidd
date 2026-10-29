---
description: "Hire the team into a repository: map the codebase read-only, fit aidd to it, and pick the first changes"
disable-model-invocation: true
argument-hint: "[what the team will work on here]"
---

Loop step: **Plan**, once per repository, before the team's first change in it: the team learns the codebase before it changes anything.

Lanes: spec.

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

Onboarding is read-only, so it runs even before the repository has `.aidd/config.yaml`. Every role here only reads and reports, and nothing is written. A person runs `aidd init` and merges the setup change afterwards.

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

   Include what the team will work on, if given: $ARGUMENTS. End the brief with the exact `aidd init` command, with its flags, for a person to run.

Then stop. A person runs that command, reviews, and merges the setup change. The setup change touches `.aidd/`, so the gate treats it as major. Start in advisory mode, and enforce once the gate's findings match the team's judgment.
