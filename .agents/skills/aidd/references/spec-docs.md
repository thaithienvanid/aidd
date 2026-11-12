# Linked docs (`docs`)

The rest of the Spec's fields: `references/spec.md`.

The Spec is the contract: intent, Acceptance ids, Tasks, route, risk, rollback, tests, and approvals. The detail a reader needs to judge the Spec lives in documents it links, one `docs` entry each, in its work item folder: `specs/SPEC-220.md` keeps its documents in `specs/SPEC-220/`. `aidd new <type> <topic> --spec <ID>` writes one from its template in `assets/`, with the Spec's id in its header, and adds the entry. The types are in the table below; `--prototype` writes the design spec's `prototype.html` in `specs/<ID>/design/`. Acceptance links as a living doc. So do the component's test plan (below) and the repository's data map and vendor register (`aidd new data-map`, `aidd new vendors`) when a Spec changes what they record. An slo doc is a frozen delta to the service card's objectives. Work bigger than one Spec, a solo founder's MVP too, starts from an Intent (`aidd new intent`).

<!-- aidd:gen fields:doc -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | `tech-spec` \| `test-plan` \| `design-spec` \| `design-files` \| `adr` \| `threat-model` \| `authz-matrix` \| `api` \| `runbook` \| `slo` \| `compliance-record` \| `tracking-plan` \| `migration-plan` \| `acceptance` \| `data-map` \| `vendors` \| `other` | yes | What the document is. It names the role that writes it (architect: tech-spec, adr, api, migration-plan; verifier: test-plan; product designer: design-spec (with its context of use, flows, and usability test) or its HTML prototype, and design-files (the mockups, wireframes, and flows a person approves with the Spec, such as `specs/SPEC-220/design/**`: always frozen, and never implementation scope); security engineer: threat-model, authz-matrix; SRE: runbook, slo; compliance analyst: compliance-record, data-map (the repository's living inventory and records of processing); product manager: tracking-plan; delivery manager: acceptance, and vendors (the repository's vendor register)) and the required-docs matrix `aidd validate` warns from (`docs.disabled`). |
| `path` | string | yes | Repo-relative path of the document, or a glob for a folder of files (a prototype with its assets), such as `specs/SPEC-220/tech-spec-limits.md`. It must match a file (`aidd validate`; a `design-files` entry may match none yet), and a frozen one is never a catch-all and never inside a Task's scope. |
| `frozen` | boolean | no | Default true: approved with the Spec, like a design file, so an edit after Spec approval is `spec.revise`; a drift found while implementing goes in the verification report and a later docs-only change. False for a living document several Specs revise (a runbook, an area's architecture page): only checked to exist, and a Task that changes it names it in its scope. A `design-files` entry is always frozen: `frozen: false` on it is an error. |
<!-- aidd:end -->

- **Frozen** (the default) is never in a Task's scope. Only its owner writes it, and only before approval.
- **Living** (`frozen: false`): `aidd validate` checks it exists.
- **Test plan.** One type, the verifier's, at two scopes. A Spec's plan, `specs/<ID>/test-plan-<topic>.md`, is frozen with it, and its `## Test approach` has a row per Acceptance id. The component's plan (`aidd new test-plan <component> --living --spec <ID>`) is one living file, `docs/testing/test-plans/<component>.md`: its strategy, risks, and test catalog, with the generated trace (`aidd new srs product`). A test-only change adds its cases there. An Intent links no docs, so it has no plan.
- **When.** Nothing on minor. Testing lives in the Spec's Acceptance and its `tests`, and in a test plan when asked. `aidd validate` warns, never errors, when a major Spec links:
  - no tech-spec and no runbook (its own `## Alternatives considered` and `## Pre-mortem`, or a `## Rollout` from `references/spec-release.md`, count). Any reason for major counts: `availability`, a dimension that forces major, an irreversible change, or a service or deploy path (IaC, a container, a release file)
  - no threat-model when a risk dimension is security, privacy, or data, or, with `project.compliance` on, a Task touches an authentication, secrets, or cryptography path (on normal too)
  - no `authz-matrix` doc when a Task touches an authentication or authorization path and the risk names security or `project.compliance` is on (on normal too)
  - no `compliance-record` doc on a privacy dimension (on normal too), with the data map suggested beside it
  - no design-spec doc or `design-files` doc on a feat with a user-facing path
  - no test-plan (on normal too with a compliance dimension, or `project.compliance` on); no living plan only with `project.compliance` on
  - no `migration-plan` doc on a data dimension, or an irreversible change
  - no `tracking-plan` doc when the Spec has a `hypothesis` (on normal too)

  On normal the others, and any test plan, are suggestions `aidd new spec` prints. `docs.disabled` turns a type's rule off, with a reason. Which docs a team of your size writes: `profiles.md`, Ceremony by team size.
- **Checks.** A doc or a local `adrs` path that does not exist is an error. So is a frozen doc that is a catch-all or sits in a Task's scope. These are warnings:
  - a doc that still holds a placeholder (TODO, YYYY-MM-DD, an id such as SPEC-?), or a frozen doc that does not name its Spec
  - a test plan whose Test approach ids differ from the Spec's, or that no command covers
