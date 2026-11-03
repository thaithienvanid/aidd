# Profiles

A profile says who decides and on which routes you ask for Spec approval. Pick the one that fits who directs the work. A profile is a set of rules on top of the built-in ones (`references/risk.md`), and the config's own `risks.rules` replace a profile's rules with the same selector.

- **solo**: one person directs the agents and decides. Ask for Spec approval on major only. On normal, write the Spec, say that you go on, and go on. Ask for Merge approval in the chat, on a local trunk or on a platform.
- **team**: one or a few teams on one repository. Ask for Spec approval on normal and major. On a platform, the Merge approval is the platform's PR/MR review, so open the PR/MR and stop there. On a local trunk, ask in the chat.

**Many teams and repositories** share one org preset through `extends`. A preset may mark a rule `locked: true`, so a project keeps the preset's level, and `aidd risk` reports the project's own rule as ignored.

<!-- aidd:gen profiles -->
| Profile | What it is for | Spec approval asked on | Risk rules |
| --- | --- | --- | --- |
| `solo` | One person directs the agents and decides. The agent writes a Spec for a normal or major change, asks for Spec approval on major only, and asks before anything reaches the default branch. | major | the built-in ones |
| `team` | One or a few teams on one repository. The agent asks for Spec approval on normal and major changes, and a person merges through the platform's review: the agent opens the PR/MR and stops there. | normal, major | the built-in ones |
<!-- aidd:end -->

## Ceremony by team size

Write only what the team's size needs. Every other doc waits for its trigger: `aidd validate` warns, never fails.

| Team | Writes by default | Only when its trigger fires |
| --- | --- | --- |
| Solo founder, agency MVP | spec-short, the Initiative's brief, and for design only the prototype and the design spec's light variant | everything else: a tech spec on major, a threat model on security, privacy, or data, a migration plan on data, a tracking plan with a hypothesis |
| Team | the above, a tech spec with its Test strategy and a runbook on major, a design spec for a user-facing feat with its flows, a component in DESIGN.md for a new or changed one, ADRs | a test plan (compliance, device matrix, `uat`, 10 or more Acceptance items), a migration plan, a tracking plan, an API doc, an SLO, the brief's journey in discovery, the design spec's usability test for a risky flow |
| A regulated product, or a client's UAT | the above, the test plan (regulated or agency variant), a threat model, compliance with a DPIA, an acceptance record, change orders | none: each is expected |
