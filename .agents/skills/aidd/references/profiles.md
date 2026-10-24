# Profiles

A profile sets how strict the gates are. Pick the weakest one that fits who approves. `gates` values may only tighten the profile. aidd ignores a looser value and warns. A config that extends another cannot pick a weaker profile: it is an error.

- **solo**: one person directs agents and approves their work. The solo profile waives separation of duties, and the gate record shows `waived_solo`. Compensating controls apply: SHA-bound tests, protected paths, a deliberate Merge approval of the exact head. A Spec approval recorded on a route where solo makes it optional still binds. A changed Spec or test fails `spec_approval.voided`, and red-then-green fails for that Spec. You never pass that flag.

- **team**: one or a few teams on a repo. Spec approval before implementation, an Approver who is not the author, and a specialist Approver on major.
- **org**: many teams and repos. Team plus a bound Policy on major and emergency.
- **audited**: finance, health, and public sector. Two Approvers plus each specialist pool on major (and on the Spec hash), a Policy on every route, an `Assisted-by` trailer on every commit, Observe on normal, and no standard changes.

**A standing approval** works under any profile. When the person types `approve all` (`but major` keeps major changes for them), you record each decision it covers. Run the command `aidd list` names, such as `aidd approve spec`, `aidd land`, or `aidd publish`, and the record cites it. It lasts until they type `stop approving`. Only the person starts one; the guard denies your `aidd approve all`.

<!-- aidd:gen profiles -->
| Gate | solo | team | org | audited |
| --- | --- | --- | --- | --- |
| Mode while the config names none: advisory (the guard and the gate report; no agent decides for a person) or enforce (they block) | advisory | advisory | enforce | enforce |
| Approvers must differ from the authors | no | yes | yes | yes |
| Spec approval on routes | major | normal, major | normal, major | normal, major |
| Specialist pools also approve the Spec on major | no | no | no | yes |
| Merge approvals per route | standard 0, minor 1, normal 1, major 1, emergency 1 | standard 0, minor 1, normal 1, major 1, emergency 1 | standard 0, minor 1, normal 1, major 1, emergency 1 | standard 0, minor 1, normal 1, major 2, emergency 1 |
| Approvals from each specialist pool on major | 0 | 1 | 1 | 1 |
| Bound Policy required on routes | none | none | major, emergency | minor, normal, major, emergency |
| AI provenance | declare | declare | declare | every_commit |
| Red-then-green proof for new behavior | warn | require | require | require |
| Standard changes allowed | yes | yes | yes | no |
| Observe block required on routes | major | major | major | normal, major |
| Changed-line limit per route (standard: its class's own limit; emergency: none) | minor 50, normal 800, major 800 | minor 50, normal 400, major 400 | minor 50, normal 400, major 400 | minor 50, normal 400, major 300 |
| Commit authors with no platform account | warn | warn | warn | fail |
| Spec approval proven before implementation | optional | optional | optional | require |
| A Merge approval carries across a trivial rebase | trivial_rebase | trivial_rebase | trivial_rebase | none |
| Routes on which it carries (never emergency) | minor, normal, major | minor, normal, major | minor, normal | none |
| `limits`: open waits per Approver before `aidd list` warns (0: off; never gated) | 0 | 3 | 3 | 3 |
| `limits`: minutes before `aidd list` escalates a wait (0: off; never gated) | 0 | 0 | 0 | 0 |
| `limits`: Specs in progress per owner before `aidd list` warns (0: off; never gated) | unset (off) | unset (off) | unset (off) | unset (off) |
| `limits`: days in progress before `aidd list` flags a Spec as aging (0: off; never gated) | unset (10) | unset (10) | unset (10) | unset (10) |
| `limits`: days a goal branch lives before `aidd list` and `aidd doctor` warn (0: off; never gated) | unset (7) | unset (7) | unset (7) | unset (7) |
| `limits`: days a branch with unmerged work lives before `aidd list` and `aidd doctor` warn (0: off; never gated) | unset (2) | unset (2) | unset (2) | unset (2) |
| `limits`: branches with unmerged work before `aidd list` and `aidd doctor` warn (0: off; never gated) | unset (3) | unset (3) | unset (3) | unset (3) |
<!-- aidd:end -->

## Ceremony by team size

Write only what the team's size needs. Every other doc waits for its trigger: `aidd validate` warns, never fails.

| Team | Writes by default | Only when its trigger fires |
| --- | --- | --- |
| Solo founder, agency MVP | spec-short, the Initiative's brief, and for design only the prototype and the design spec's light variant | everything else: a tech spec on major, a threat model on security, privacy, or data, a migration plan on data, a tracking plan with a hypothesis |
| Team | the above, a tech spec with its Test strategy and a runbook on major (not for a protected path alone), a design spec for a user-facing feat with its flows, a component in DESIGN.md for a new or changed one, ADRs | a test plan (compliance, device matrix, `uat`, 10 or more Acceptance items), a migration plan, a tracking plan, an API doc, an SLO, the brief's journey in discovery, the design spec's usability test for a risky flow |
| Audited, or a client's UAT | the above, the test plan (audited or agency variant), a threat model, compliance with a DPIA, an acceptance record, change orders | none: each is expected |
