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
| Solo founder, agency MVP | spec-short, the Intent, and for design only the prototype and the design spec's light variant. On solo, `aidd new spec` and `aidd new design-spec` write these on every route, and `--full` writes the full ones | every doc the Spec's route and risk trigger, as `aidd new spec` prints and `aidd validate` warns (`references/spec.md`, Linked docs) |
| Team | the above, a tech spec with its Test strategy and a runbook on major, a design spec for a user-facing feat with its flows, a component in DESIGN.md for a new or changed one, ADRs | a test plan (compliance, device matrix, `uat`), a migration plan, a tracking plan, an API doc, an SLO, the Intent's journey map in discovery, the design spec's usability test for a risky flow |
| A regulated product, or a client's UAT | the above, the test plan (regulated or agency variant), a threat model, compliance with a DPIA, an acceptance record, change orders | none: each is expected |

## The product's living documents

A team that outgrows one person's memory keeps a few documents for the whole product. Each has one file, one owner, and a document inside a Spec that folds into it. A change that alters the Spec's document brings the product's file in line in the same change. Start one when its trigger fires, never before.

| Document | Written by | Home | Folds in |
| --- | --- | --- | --- |
| Product brief | `aidd new product-brief` | `docs/product/brief.md` | each Intent |
| Metrics dictionary | `aidd new metrics-dictionary` | `docs/product/metrics.md` | each tracking plan; `aidd validate` warns about an event it lacks |
| Service card | `aidd new service-card <name>` | `docs/services/<name>.md` | each `slo` doc |
| Control register | `aidd new control-register` | `docs/compliance/control-register.md` | each `compliance` doc |
| Improvement log | `aidd new improvement-log` | `docs/retros/improvement-log.md` | each retrospective, and a finding class that repeats across reviews as a proposed rule or lint; `aidd validate` warns about a check date with no result |
| Threat models | `aidd new threat-model <component> --spec <ID>` | `docs/security/threat-models/`, with a generated `README.md` index | each threat delta; `aidd validate` warns about a component with no model |

`aidd new srs <INTENT-ID>` writes the Intent's software requirements specification (ISO/IEC/IEEE 29148) to `.aidd/views/`. Each requirement is an Acceptance item of a Spec at or past Spec approval, and it links its test command and its newest commit. Never hand-edit it: change a Spec, then run the command again. `aidd new srs product` covers every Spec, which is the product's trace from each Acceptance id to its tests.
