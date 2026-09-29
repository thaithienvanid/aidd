---
description: "Hire the team into a repository: map the codebase read-only, fit aidd to it, and pick the first changes"
argument-hint: "[what the team will work on here]"
---

Loop step: **Plan**, once per repository, before the team's first change in it: the team learns the codebase before it changes anything.

Lanes: spec.

Onboarding is read-only, so it runs even before the repository has `.aidd/config.toml`: every role here only reads and reports, and nothing is written. A person runs `aidd init` and merges the setup change afterwards.

1. Run `aidd init --dry-run` and read what it found: the stacks and test commands, sensitive areas the baseline rules miss, generated code, owners, CI, untested code, and the agent instructions and planning tools already here. The dry run writes nothing.
2. Run these subagents in parallel, each returning its findings as text, with file paths:
   - `aidd-team:architect`: the components and their boundaries, how data flows, a context diagram, where the tests are thin, and the domain packs the code needs
   - `aidd-team:security-engineer`: where authentication, secrets, personal data, and payments live, and the risk rules and owners each needs
   - `aidd-team:sre`: how the code builds, deploys, and is watched, which existing CI checks can serve as evidence, and what a runbook or rollback is missing
3. Give the author one onboarding brief: the config the setup change should hold (the dry run's proposal, corrected by the specialists), the architecture overview to add as the first documentation change, the areas that need a characterization test before anyone changes them, and three small, low-risk first changes to prove the loop here. Include what the team will work on, if given: $ARGUMENTS. End the brief with the exact `aidd init` command, with its flags, for a person to run.

Then stop. A person runs that command, reviews, and merges the setup change; it touches `.aidd/`, so the gate treats it as major. Start in advisory mode, and enforce once the gate's findings match the team's judgment.
