# Specialist returns (fixed templates)

The Spec's `## Concerns` lists each concern by area, with its owner, or `none`. A specialist starts only for a concern in its area, or for a document the risk requires.

With the development team, a specialist writes the rows its own area holds in place: the threat model, the `authz-matrix` doc, the `compliance-record` doc. It writes only what another role folds to `.aidd/returns/<ID>/<role>.md`, which git ignores: Acceptance lines, the tech spec's delta by id, the observe block. It names that file on its handoff note, and the architect folds it into the section the template names. A row the specialist cannot fill goes on the handoff note's Needs line instead of a guess. A fixed shape lets the architect fold without re-deriving, and the verifier turn each row into a test. Each fact has one home, and every other document links it by id. Acceptance ids come from the Spec: cite one, or write `new: <behavior>` in the cell for the Spec's writer to number, never a new id (`aidd validate` warns).

**Security engineer** → the rows in the component's living threat model, which the Spec links (`aidd new threat-model <component> --spec <ID> --no-link`), the one home of each threat. The tech spec's `### Security and privacy` links the model and lists this Spec's delta by id: the threats it adds, changes, or retires. Name each threat `T-<COMPONENT>-NN`, so `aidd validate` can find its model: it warns when the component has none, and, once the Spec asks for approval, when the model does not list the id. One row per threat, in the threat-model template's shape. Every row names the Acceptance id that proves its mitigation, and the mitigation's owner or the person who accepted the risk. Risk is the likelihood (remote, possible, probable) times the severity (minimal, significant, severe), as low, medium, or high, the ICO's DPIA scale: the highest rows are mitigated and tested first.

| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Risk | Mitigation | Acceptance id | Owner |
| --- | --- | --- | --- | --- | --- |
| Spoofing: a replayed session token | browser → API | high (probable × significant) | bind the token to the device, expire in 15 min | A4 | @security-lead |
| Linking: two exports joined on the email column | export → analytics | medium (possible × significant) | export a per-export pseudonym, never the email | A5 | @privacy-lead |

Then the ASVS level and the requirements it names, and the data-flow diagram as Mermaid.

**SRE** → the tech spec's `### Observability`, the Spec's `observe` and `rollback`, and the Spec's `## Rollout`. One row per signal that shows the change working or failing.

| SLI (golden signal, RED or USE) | SLO | Observe signal (dashboard, query, or `observe.command`) | Window | Rollback trigger |
| --- | --- | --- | --- | --- |
| checkout p99 latency | 99% under 400 ms over 28 days | `checkout_latency_seconds` p99 panel | 24h | error-budget burn above 14.4x for 5 min |

Then the runbook path for each new failure mode, and on major the pre-mortem's causes and the `## Rollout` rings. When nothing runs after release (a library, a CLI, docs), return one line instead: `observe: {not_applicable: "<reason>"}` (`references/spec-release.md`), with no rollout.

**Compliance analyst** → one row per obligation in the `compliance-record` doc the Spec links, or else in the tech spec's `### Compliance`, never both. A risk to people is a LINDDUN row in the threat model, which the DPIA cites by id. The evidence is something the repository already holds, such as a test or the `aidd test` evidence. The control id is the enterprise-controls pack's `EC-01` to `EC-19`, or the team's own.

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or `aidd test` evidence) | Owner |
| --- | --- | --- | --- | --- |
| EC-10 | GDPR Art. 25 data minimization | drop the date of birth from the export | the test that asserts the export's columns; the `aidd test` evidence for the head | the privacy pool |

Then whether a DPIA is required and why.
