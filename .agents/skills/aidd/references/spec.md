# Spec fields

What you write: the Spec, its Tasks and tests, and the Change Request block. Epics, Initiatives, and Proposals: `references/containers.md`. `aidd gen-docs` generates the tables from the schemas that ship with the CLI. `aidd validate` is the authority.

## Spec (`specs/<ID>.md` front matter)

<!-- aidd:gen fields:spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `kind` | `"spec"` | yes | Object kind. Always `spec`. |
| `id` | string | yes | Spec key, such as SPEC-220. |
| `parent` | string | no | Optional Epic id. |
| `title` | string | yes | One line. `locale` may apply. |
| `owner_team` | string | yes | Team accountable for the change. |
| `approvers` | list of string | no | Eligible Approvers for this Spec. Can only narrow the config's `owners.approvers`. |
| `type` | `type` | yes | What kind of change this is, in Conventional Commits vocabulary. `data`, `security`, and `compliance` are always major. |
| `route` | `normal` \| `major` \| `emergency` | yes | normal (the gate raises it to major when the diff demands it), major, or emergency for a backfill Spec. Minor and standard changes have no Spec file. |
| `confidence` | `confidence` | yes | Confidence in the assessment. `low` stops the run. |
| `open_questions` | list of string | no | Facts still unknown at assessment. Empty when confidence is high. |
| `trace_id` | string | no | Joins the Specs and changes of one piece of work across repositories. Defaults to the id. |
| `status` | `status` | no | Optional cache of the derived status; `aidd validate` warns when it disagrees. Record only what nobody can observe: `cancelled` (a person stopped it) or `rolled_back`. |
| `blocked_on` | string | no | Role, person, or interface the Spec waits on. While it is set, the Spec is blocked: a flag `aidd assess` and `aidd list` show, not a status. |
| `labels` | list of string | no | Up to 8 labels, lowercase letters, digits, `:` and `-`, such as `area:billing` or `customer-ask`, for filtering (`aidd list --label`). They never change the route or the gate, and the Spec hash ignores them. |
| `relations` | list of table (`relation`) | no | Typed links to other Specs, Epics, or Initiatives: blocks, blocked_by, duplicates, relates_to, implements. Bookkeeping: the gate never reads them and the Spec hash ignores them. |
| `priority` | `priority` | no | How soon the work matters, for sorting `aidd list` and filtering it (`--priority LEVEL`: this level or higher). Unset, it is inherited from the parent Epic or Initiative, else medium; an emergency is always urgent. Bookkeeping: the Spec hash ignores it and the gate never reads it. |
| `owner` | string | no | The person driving the work: `aidd list --mine` finds it, and `aidd list` names them as who acts. A person, never an agent or an agent account (`aidd validate` fails one). Bookkeeping: the Spec hash ignores it, and it approves nothing. |
| `suggested_by` | string | no | Who suggested work nobody asked for: `agent:<role>` for an agent in `[agents] proactive_roles` (or an agent account). Such a Spec stays a draft until a person records `triage`. |
| `triage` | table (`triage`) | no | A person's decision on suggested work. Required, by a person, before a Spec whose suggested_by is an agent moves past draft. |
| `risk` | table (`risk`) | yes | Blast radius: what changes, which dimensions it touches, and whether a revert restores the prior state. |
| `rollback` | string | yes | How to undo. Name the steps on major and emergency. |
| `hypothesis` | string | no | The measurable result the change should produce after Ship, written before Spec approval and frozen by the Spec hash: a metric, its baseline, the expected move, and by when. Learn records `outcome.result` against it. |
| `experiment` | table (`experiment`) | no | An A/B test that decides the `hypothesis`, planned before launch: its variants, one primary metric, the guardrails, how long it runs, and the decision rule. Optional; the product manager writes it with the tracking plan, and the flag that serves the variants is a `[[flags]]` entry. Approved content: the Spec hash covers it. `aidd validate` warns when it names no guardrail or the Spec has no hypothesis. |
| `uat` | boolean | no | True when people accept this change by hand: a client's user acceptance test, a QA owner's manual or exploratory pass, or a device lab run. The required-docs matrix then asks for a test plan (`aidd validate` warns on major, `aidd new spec` suggests it on normal). Approved content: the Spec hash covers it. |
| `residual_risk` | string | no | What stays true after release. `none` when nothing remains. |
| `assisted_by` | list of string | yes | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `decisions` | list of string | no | ADR paths or links this Spec depends on, and does not change. A repository path must exist (`aidd validate`); an ADR this Spec writes is a `[[docs]]` entry of kind `adr` instead. |
| `tasks` | list of table (`task`) | yes | Slices of the change. Parallel only when their scope is disjoint. |
| `tests` | table (`tests`) | yes | How the change is proven: the test files and the commands that run them. |
| `design` | table | no | The approved look and flow of a user-facing change. Optional; the product designer writes it before Spec approval. |
| `docs` | list of table (`doc`) | no | The documents that hold the detail this Spec links instead of carrying: a tech spec, a test plan, a prototype or design spec, an ADR, a threat model, an API contract, a migration or tracking plan, a runbook. `aidd new <kind> <topic> --spec <ID>` writes one from its template and adds the entry. A frozen doc is approved with the Spec by hash, like a design file; a living one is only checked to exist. |
| `observe` | table (`observe`) | when route is `major` | Post-release check. Required on the profile's observe_required_routes: major, and normal under regulated. |
| `flags` | list of table (`flag`) | no | Feature flags this change ships behind, so release is separate from deploy: the architect adds one on a normal or major user-facing change that should reach users later than its code reaches production. Optional; a minor change never needs one. Approved content: the Spec hash covers it. `aidd validate` warns, and `aidd list` shows the cleanup as work, once a flag's `cleanup_due` has passed and no Spec lists it in `removes_flags`; a later Spec that declares the same flag with a later date extends it. |
| `removes_flags` | list of string | no | Flags this change deletes from the code, by name: the cleanup Spec for an earlier Spec's `[[flags]]` entry. Once a Spec lists a flag here, `aidd validate` and `aidd list` stop reporting it as overdue. |
| `emergency` | table (`emergency`) | when route is `emergency` | Required when route is emergency. |
| `outcome` | table (`outcome`) | no | What happened after Ship. Written during the observe window and in Learn. |
<!-- aidd:end -->

### Task (`[[tasks]]`)

<!-- aidd:gen fields:task -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line describing the slice. |
| `scope` | list of string | yes | Globs this Task's diff may change. Never a test or design file, never a catch-all. |
| `depends_on` | list of string | no | Task ids that must finish first. Required between Tasks whose scope overlaps. |
| `assignee` | string | no | Implementer: `agent:<role>` or a person. |
| `skills` | list of string | no | Skills loaded only for this Task, by directory name: a practice skill such as `api-design` or a stack skill, at most two. Domain packs are named in Context instead. |
| `risk` | string | no | What this Task could break, and how it guards against it. Approved content: frozen by the Spec hash. |
| `proof` | string | no | How this Task is shown to work: the test command, screenshot, or check a reviewer reads. Approved content: frozen by the Spec hash. |
| `retry_count` | integer | no | Implementation retries used. At 3 the Task stops and the Spec is blocked until a person re-plans it. |
| `done` | boolean | no | True when the Task is finished and the evidence cannot show it (a changed scope with every command green on head shows it by itself). Bookkeeping: the Spec hash ignores it. |
<!-- aidd:end -->

A Task is a plan in four parts: its files (`scope`), its order (`depends_on`), its `risk`, and its `proof`. Write `risk` as what could break and the guard ("the cache key changes shape; the migration test reads records written before"). Write `proof` as the named check a reviewer can open ("tests.commands `acceptance`", "screenshot in docs/design/checkout/after.png"). Both are approved content, so Spec approval freezes them.

### Risk (`[risk]`)

<!-- aidd:gen fields:risk -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `summary` | string | yes | Blast radius in one or two sentences: who or what changes behavior. |
| `dimensions` | list of `dimension` | yes | Every dimension the change touches. Empty means none. |
| `reversible` | boolean | yes | False when a revert does not restore the prior state, such as a destructive migration or an external side effect. False forces major. |
<!-- aidd:end -->

### Tests (`[tests]` and `[[tests.commands]]`)

<!-- aidd:gen fields:tests -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `files` | list of string | yes | The test files, and the configuration they run through. Frozen by the Spec hash and never inside a Task's scope. |
| `commands` | list of table (`test_command`) | yes | Commands the runner executes. Exit 0 is the only pass. |
<!-- aidd:end -->

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `smoke` | boolean | no | In the config's [[tests]]: part of the smoke set, the only repository commands an emergency change runs (with its own). When no command is marked, an emergency runs the whole suite. |
| `retries` | integer | no | How many more times a failing run on head is tried (default 0). Every attempt is kept in the evidence; a pass after a failure passes, marked flaky, and metrics count it. A red run on the base commit is never retried. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. The gate never reads it. |
<!-- aidd:end -->

### Linked docs (`[[docs]]`)

The Spec is the contract: intent, Acceptance ids, Tasks, route, risk, rollback, tests, and approvals. The detail a reader needs to judge the Spec lives in documents it links, one `[[docs]]` entry each. `aidd new <kind> <topic> --spec <ID>` writes one from its template in `assets/`, with the Spec's id in its header, and adds the entry. Kinds: tech-spec, test-plan, ui for `design-spec.md` or, with `--prototype`, `prototype.html` in the design folder (`docs/design/<ID>/`), adr, threat-model, authz for `authz-matrix.md`, api, slo, compliance, analytics for `tracking-plan.md`, migration for `migration-plan.md`, acceptance. slo and acceptance link as living docs. So do the repository's data map and vendor register (`aidd new data-map`, `aidd new vendors`) when a Spec changes what they record. The one-page pitch is the Initiative's `## Brief` (`aidd new initiative`), for an Initiative or a solo founder's MVP.

<!-- aidd:gen fields:doc -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `kind` | `tech-spec` \| `test-plan` \| `design-spec` \| `adr` \| `threat-model` \| `authz` \| `api` \| `runbook` \| `slo` \| `compliance` \| `analytics` \| `migration` \| `acceptance` \| `data-map` \| `vendors` \| `other` | yes | What the document is. It names the role that writes it (architect: tech-spec, adr, api; tester: test-plan; product designer: ui, the design spec (with its flows and usability test) or its HTML prototype; security engineer: threat-model, authz (the authorization matrix); SRE: runbook, slo; compliance analyst: compliance; compliance analyst or data engineer: data-map (the repository's living inventory and records of processing); product manager: analytics; delivery manager: acceptance, and vendors (the repository's vendor register); data engineer: migration) and the required-docs matrix `aidd validate` warns from (`[docs.required]`). |
| `path` | string | yes | Repo-relative path of the document, or a glob for a folder of files (a prototype with its assets), such as `docs/specs/SPEC-220/tech-spec-limits.md`. It must match a file (`aidd validate`), and a frozen one is never a catch-all and never inside a Task's scope. |
| `frozen` | boolean | no | Default true: approved with the Spec, and part of the Spec hash like a design file, so any edit after Spec approval voids it; a drift found while implementing goes in the verification report and a later docs-only change. False for a living document several Specs revise (a runbook, an SLO, an area's architecture page): only checked to exist, and a Task that changes it names it in its scope. |
<!-- aidd:end -->

- **Frozen** (the default): approved with the Spec. The hash covers it like a design file, so an edit after Spec approval voids the approval. It is never in a Task's scope, and the gate never counts it against the budget. The guard lets only its owner write it, and only before approval. A drift found while implementing goes in the verification report and a later docs-only change, never an edit in place.
- **Living** (`frozen = false`): a runbook, an SLO, or an area document several Specs revise. `aidd validate` checks it exists. A Task that changes it names it in its scope, like any other file.
- **When.** Nothing on minor or standard. Testing lives in the Spec's Acceptance and the tech spec's `## Test strategy`. `aidd validate` warns (never errors, and the gate never reads it) when a major Spec links:
  - no tech-spec and no runbook (its own `## Alternatives considered` and `## Pre-mortem`, or `## Rollout`, count)
  - no threat-model when a risk dimension is security, privacy, or data (on normal too)
  - no design-spec doc or `design.files` on a feat with a user-facing path
  - no test-plan when a trigger fires: a compliance dimension or type, the regulated profile, a device path, `uat = true`, or 10 or more Acceptance items
  - no migration doc on a data dimension or type, or an irreversible change
  - no analytics doc (a tracking plan) when the Spec has a `hypothesis` (on normal too)

  On normal the others are suggestions `aidd new spec` prints. `[docs.required]` in the config changes any rule (`any_of` holds alternative triggers). Which docs a team of your size writes by default: `profiles.md`, Ceremony by team size.
- **Checks.** A doc or a local `decisions` path that does not exist is an error. So is a frozen doc that is a catch-all or sits in a Task's scope. These are warnings:
  - a frozen doc that still holds TODO or does not name its Spec
  - a test plan whose Acceptance ids differ from the Spec's, or that no command covers
  - a tech spec's Test strategy that lists an id the Spec lacks or no command covers

### Observe (`[observe]`)

<!-- aidd:gen fields:observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Post-release check. Exit 0 means healthy. |
| `signals` | string | no | Dashboards, SLOs, or queries a human watches. |
| `window` | string | yes | How long to watch, such as 30m, 24h, or 7d. |
| `rollback_trigger` | string | yes | The condition that starts the rollback. |
<!-- aidd:end -->

### Feature flags (`[[flags]]`)

Optional, on a normal or major user-facing change whose release should come after its deploy. Never on minor. A person owns each flag and flips it in production, never an agent. The cleanup is a later Spec that lists the flag in `removes_flags`. After `cleanup_due`, `aidd validate` warns and `aidd list` shows it as work.

```toml
[[flags]]
name = "checkout-v2"
default = "off"
owner = "@alice"
cleanup_due = "2026-12-01"
purpose = "release toggle for the new checkout"
```

<!-- aidd:gen fields:flag -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | A flag key in lowercase, with `-`, `.`, or `_` between words, such as `checkout-v2`: the key the code evaluates. |
| `default` | `on` \| `off` | yes | The value the code falls back to when the flag system cannot answer. `off` for a new feature; `on` only for a kill switch that guards existing behavior. |
| `owner` | string | yes | The person who decides when the flag flips and sees it removed: never an agent or an agent account (`aidd validate` fails one). |
| `cleanup_due` | string | yes | The date by which a later Spec removes the flag and its dead branch. After it, `aidd validate` warns and `aidd list` shows the cleanup as work. |
| `purpose` | string | no | Why the flag exists: a release toggle, an experiment, a kill switch, or an operational toggle. |
<!-- aidd:end -->

### Experiment (`[experiment]`)

Optional: an A/B test that decides the Spec's `hypothesis`. Plan it before Spec approval with the tracking plan, which names its exposure event. A `[[flags]]` entry with `purpose` experiment serves it. `aidd validate` warns when the experiment names no guardrail or the Spec has no hypothesis. How to run it (the sample ratio check, the stop rule): the Experiments section of `aidd-team:release-rollout`.

```toml
[experiment]
variants = ["control", "one-page"]
metric = "checkout conversion"
guardrails = ["payment error rate", "p95 checkout latency"]
min_sample = 12000
decision = "ship one-page if conversion rises at p < 0.05 and no guardrail worsens; stop on a guardrail breach or a sample ratio mismatch"
```

<!-- aidd:gen fields:experiment -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `variants` | list of string | yes | The arms by name, control first, such as `["control", "one-page"]`: the variants the experiment's flag serves. |
| `metric` | string | yes | The one primary metric that decides, the one the `hypothesis` names. Others are guardrails, or read after the decision. |
| `guardrails` | list of string | no | Metrics that must not get worse while the experiment runs (an error rate, a latency, refunds, unsubscribes); a breach stops it. |
| `min_sample` | integer | no | Units (users, accounts, sessions) per variant before anyone reads the result, from a power calculation on the primary metric's baseline and the smallest effect worth shipping. |
| `duration` | string | no | How long it runs, such as `14d` or `2w`: whole weeks, so weekday effects cancel. With `min_sample`, whichever is reached last. |
| `decision` | string | yes | The rule written before launch: when the result ships, when it stops early (a guardrail breach, a sample ratio mismatch), and what an inconclusive result means. |
<!-- aidd:end -->

### Incident (`[emergency]`)

<!-- aidd:gen fields:emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `severity` | `sev1` \| `sev2` \| `sev3` | yes | Incident severity. |
| `kind` | `outage` \| `degradation` \| `security` \| `data` | yes | What is broken in production. |
| `commander` | string | yes | The incident commander, a human. Named before the repair starts. |
| `incident` | string | no | The incident's ticket or page id, such as INC-481: what the repair answers, and what the post-incident review and the backfill Spec link. The gate requires it on an emergency change. |
| `review_due` | string | yes | Date the postmortem and the Spec backfill are due. The config sets the SLA. |
<!-- aidd:end -->

### Outcome (`[outcome]`)

<!-- aidd:gen fields:outcome -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `released_on` | string | no | Date the change reached production. |
| `observe_result` | `pass` \| `fail` | no | Result of the observe window. |
| `rolled_back` | boolean | no | True when the rollback ran. |
| `restored_on` | string | no | Date service was restored after a failed change (a rollback or a fix). With `released_on`, it gives the time to restore. |
| `learn_ref` | string | no | Link to the retro or the PR that fed lessons back into AGENTS.md, skills, or tests. |
| `result` | string | no | What the metric named in `hypothesis` did after the observe window: met, missed, or inconclusive, with the number. A missed hypothesis is a Learn signal for the author and the product-manager, not a rollback. |
<!-- aidd:end -->

## Exemplar Specs

`[docs] exemplars` in `.aidd/config.toml` names the project's best Specs. A person chooses them; aidd never does. Read them before you write a Spec: `aidd context <ID> --step spec.draft` lists them. Follow their shape and depth, and never copy their content. `aidd validate` warns on an exemplar that does not exist.

## Measurable words

Write each Acceptance line as a target a test can check. "Search is fast" is not one; "p95 under 300 ms" is. `aidd validate` warns on an Acceptance line, or a line of `## Non-functional requirements`, that uses a vague word and holds no number, inline code, link, or file path. The word list is `schemas/vague-words.json` in the CLI. It is a warning, never an error.

## Specialist returns (fixed templates)

With the delivery team, a specialist that cannot write the Spec returns its part in the template below. The architect folds it into the section the template names. A row the specialist cannot fill goes on the handoff note's Needs line instead of a guess. A fixed shape lets the architect fold without re-deriving, and the tester turn each row into a test.

**Security engineer** → the threat-model doc it links before Spec approval (`aidd new threat-model`), summarized in the tech spec's `### Security and privacy`, and Acceptance. One row per threat, in the same shape as the threat-model template and the compliance record's DPIA. Every row names the Acceptance id that proves its mitigation, and the mitigation's owner or the person who accepted the risk.

| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Mitigation | Acceptance id | Owner |
| --- | --- | --- | --- | --- |
| Spoofing: a replayed session token | browser → API | bind the token to the device, expire in 15 min | A4 | @security-lead |
| Linking: two exports joined on the email column | export → analytics | export a per-export pseudonym, never the email | A5 | @privacy-lead |

Then the ASVS level and the requirements it names, and the data-flow diagram as Mermaid.

**SRE** → the tech spec's `### Observability`, the Spec's `[observe]` and `rollback`, and the rollout runbook it links. One row per signal that shows the change working or failing.

| SLI (golden signal, RED or USE) | SLO | Observe signal (dashboard, query, or `observe.command`) | Window | Rollback trigger |
| --- | --- | --- | --- | --- |
| checkout p99 latency | 99% under 400 ms over 28 days | `checkout_latency_seconds` p99 panel | 24h | error-budget burn above 14.4x for 5 min |

Then the runbook path for each new failure mode, and on major the pre-mortem's causes.

**Compliance analyst** → the tech spec's `### Compliance` (Cross-cutting concerns), or a `compliance` doc the Spec links. One row per obligation. The evidence is something the gate or the repository already holds. `aidd record export records --by-control` groups the evidence by the control id: the enterprise-controls pack's `EC-01` to `EC-19`, or the team's own.

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or gate record) | Owner |
| --- | --- | --- | --- | --- |
| EC-10 | GDPR Art. 25 data minimization | drop the date of birth from the export | the test that asserts the export's columns; the gate record for the head | the privacy pool |

Then whether a DPIA is required and why.

## Change Request block (`toml aidd` in the PR/MR description)

<!-- aidd:gen fields:change-request -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `spec` | string | no | Repo path of the Spec. Required on normal and major. When set, the Spec supplies every other field. |
| `trace_id` | string | no | Copy of the Spec trace_id. Child changes in other repos use the same value. |
| `route` | `minor` \| `standard` \| `emergency` | when spec is absent | Inline only: minor, standard, or emergency. Normal and major need a Spec. |
| `type` | `type` | no | Default chore. |
| `confidence` | `confidence` | no | Default high. |
| `risk` | table (`risk`) | no | Inline blast radius. Default: no dimensions, reversible. The gate fails when the paths imply a dimension the block omits. |
| `scope` | list of string | when route is `emergency` and spec is absent | Inline scope: globs the diff may change. Required on emergency. On minor it defaults to the changed paths and is recorded as undeclared. |
| `rollback` | string | no | How to undo. Default: revert the change. |
| `residual_risk` | string | no | What stays true after release. |
| `assisted_by` | list of string | when spec is absent | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `tests` | table (`tests`) | no | Inline tests, such as smoke tests on an emergency. They add to the repository suite, never replace it. |
| `emergency` | table (`emergency`) | when route is `emergency` and spec is absent | Required when route is emergency. |
| `backfill` | string | when route is `emergency` and spec is absent | Emergency only: the repo path of the backfill Spec, committed as a stub with the repair (`aidd new spec <ID> --title "<incident>" --route emergency`). `aidd validate` fails once its review_due passes without outcome.learn_ref. |
| `standard_change` | string | when route is `standard` and spec is absent | Name of the config standard_changes entry this change claims. |
<!-- aidd:end -->
