# Spec fields

What you write: the Spec, its Tasks, and its tests. Epics, Initiatives, and Proposals: `references/containers.md`. `aidd gen-docs` generates the tables from the schemas that ship with the CLI. `aidd validate` is the authority.

**Contents**

<!-- aidd:gen toc -->
- [Spec (`specs/<ID>.md` front matter)](#spec-specsidmd-front-matter)
- [Exemplar Specs](#exemplar-specs)
- [Measurable words](#measurable-words)
- [Specialist returns (fixed templates)](#specialist-returns-fixed-templates)
<!-- aidd:end -->

## Spec (`specs/<ID>.md` front matter)

<!-- aidd:gen fields:spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `type` | `"spec"` | yes | Object type. Always `spec`. |
| `id` | string | yes | Spec key, such as SPEC-220. |
| `parent` | string | no | Optional Epic id. |
| `title` | string | yes | One line, an imperative summary of the change, such as "Rate-limit authenticated checkout": the merge commit's subject, `<change_type>: <title> (<ID>)`. `aidd validate` warns when that subject passes 72 characters. The language in the project's AGENTS.md may apply. |
| `owner_team` | string | yes | Team accountable for the change. |
| `approvers` | list of string | no | The people to ask for this Spec's decisions, first to last. Missing, the agent asks the config's `owners.approvers`. |
| `change_type` | `change_type` | yes | What kind of change this is, in Conventional Commits vocabulary. `data`, `security`, and `compliance` are always major. |
| `route` | `normal` \| `major` \| `emergency` | yes | normal, major (an area or the risk can raise a normal change to major), or emergency for a backfill Spec. A minor change has no Spec file. |
| `confidence` | `confidence` | yes | Confidence in the assessment. `low` stops the run. |
| `open_questions` | list of string | no | Facts still unknown at assessment. Empty when confidence is high. |
| `trace_id` | string | no | Joins the Specs and changes of one piece of work across repositories. Defaults to the id. |
| `status` | `status` | no | The Spec's status, stored here. The agent sets it as the work moves: `ready` when it asks for Spec approval, `approved` on the person's yes, and `done` once the change merged. Missing means `draft`. |
| `approved_by` | string | no | Who said yes to Spec approval, in their own words in the chat. The agent writes it on that yes, with `approved_at` and `status: approved`, and commits it with an `Approved-by:` trailer. It is a note the agent wrote, not proof. |
| `approved_at` | string | no | When the person said yes to Spec approval (RFC 3339), such as `2026-11-03T14:20:00Z`. The agent writes it with `approved_by`. |
| `blockers` | string | no | Role, person, or interface the Spec waits on. While it is set, the Spec is blocked: a flag `aidd status` shows, not a status. |
| `labels` | list of string | no | Up to 8 labels, lowercase letters, digits, `:` and `-`, such as `area:billing` or `customer-ask`, for filtering on a board or a tracker. They never change the route, and on a Spec editing them needs no `spec.revise`. |
| `relations` | list of mapping (`relation`) | no | Typed links to other Specs, Epics, or Initiatives: blocks, blocked_by, duplicates, relates_to, implements. Bookkeeping: they never change the route, and on a Spec editing them needs no `spec.revise`. |
| `priority` | `priority` | no | How soon the work matters, for sorting the open work. Unset, it is inherited from the parent Epic or Initiative, else medium; an emergency is always urgent. Bookkeeping: it never changes the route, and editing it needs no `spec.revise`. |
| `owner` | string | no | The person driving the work: `aidd status --mine` finds it, and `aidd status` names them as who acts. A person, never an agent or an agent account (`aidd validate` fails one). Bookkeeping: editing it needs no `spec.revise`, and it approves nothing. |
| `suggested_by` | string | no | Who suggested work nobody asked for: `agent:<role>` for an agent in `agents.proactive_roles` (or an agent account). Such a Spec stays a draft until a person decides its `triage`. |
| `triage` | mapping (`triage`) | no | A person's decision on suggested work. Required, by a person, before a Spec whose suggested_by is an agent moves past draft. |
| `risk` | mapping (`risk`) | yes | Blast radius: what changes, which dimensions it touches, and whether a revert restores the prior state. |
| `rollback` | string | yes | How to undo. Name the steps on major and emergency. |
| `hypothesis` | string | no | The measurable result the change should produce after Roll out, written before Spec approval, which covers it: a metric, its baseline, the expected move, and by when. Learn writes `outcome.result` against it. |
| `experiment` | mapping (`experiment`) | no | An A/B test that decides the `hypothesis`, planned before launch: its variants, one primary metric, the guardrails, how long it runs, and the decision rule. Optional; the product manager writes it with the tracking plan, and the flag that serves the variants is a `flags` entry. Approved content: Spec approval covers it. `aidd validate` warns when it names no guardrail or the Spec has no hypothesis. |
| `uat` | boolean | no | True when humans accept this change by hand: a client's user acceptance test, a QA owner's manual or exploratory pass, or a device lab run. The required-docs matrix then asks for a test plan (`aidd validate` warns on major, `aidd new spec` suggests it on normal). Approved content: Spec approval covers it. |
| `residual_risk` | string | no | What stays true after release. `none` when nothing remains. |
| `assisted_by` | list of string | yes | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `adrs` | list of string | no | ADR paths or links this Spec depends on, and does not change. A repository path must exist (`aidd validate`); an ADR this Spec writes is a `docs` entry of kind `adr` instead. |
| `tasks` | list of mapping (`task`) | yes | Slices of the change. Parallel only when their scope is disjoint. |
| `tests` | mapping (`tests`) | yes | How the change is proven: the test files and the commands that run them. |
| `design` | mapping | no | The approved look and flow of a user-facing change. Optional; the product designer writes it before Spec approval. |
| `docs` | list of mapping (`doc`) | no | The documents that hold the detail this Spec links instead of carrying: a tech spec, a test plan, a prototype or design spec, an ADR, a threat model, an API contract, a migration or tracking plan, a runbook. `aidd new <kind> <topic> --spec <ID>` writes one from its template and adds the entry. A frozen doc is approved with the Spec, like a design file; a living one is only checked to exist. |
| `observe` | mapping (`observe`) | when route is `major` | Post-release check: what to watch, for how long, and when to roll back. Required on major. |
| `cost_estimate` | mapping | no | What the change will cost to run, which the architect estimates in Specify: the one place for it. `aidd validate` warns on a Spec that changes infrastructure code, or whose risk names `cost`, and gives none. It also warns on a monthly estimate above `project.budget.max_infra_per_month`, the person's ceiling. Latency and availability belong in the SLO and `observe`. |
| `flags` | list of mapping (`flag`) | no | Feature flags this change ships behind, so release is separate from deploy: the architect adds one on a normal or major user-facing change that should reach users later than its code reaches production. Optional; a minor change never needs one. Approved content: Spec approval covers it. `aidd validate` warns, and `aidd status` shows the cleanup as work, once a flag's `cleanup_due` has passed and no merged Spec lists it in `removes_flags`; a later Spec that declares the same flag with a later date extends it once that Spec merges. |
| `removes_flags` | list of string | no | Flags this change deletes from the code, by name: the cleanup Spec for an earlier Spec's `flags` entry. Once this Spec merges, `aidd validate` and `aidd status` stop reporting the flag as overdue; while it is a draft, they name it as the pending removal. |
| `deprecations` | list of mapping (`deprecation`) | no | What this change deprecates: an endpoint, a field, an event, a config key, or a command its consumers still use. The architect adds one when a removal or a changed meaning goes through expand and contract. The running API announces it with the `Deprecation` header (RFC 9745) and, once dated, the `Sunset` header (RFC 8594), with the same dates. Approved content: Spec approval covers it. `aidd validate` warns, and `aidd status` shows the removal as work, once its `sunset` has passed and no merged Spec lists it in `removes_deprecations`. A later Spec that declares the same `what` with a later `sunset` extends it once that Spec merges. |
| `removes_deprecations` | list of string | no | Deprecations this change removes from the code, by their `what`: the removal Spec for an earlier Spec's `deprecations` entry. Once this Spec merges, `aidd validate` and `aidd status` stop reporting it; while it is a draft, they name it as the pending removal. |
| `emergency` | mapping (`emergency`) | when route is `emergency` | Required when route is emergency. |
| `revisions` | list of mapping | no | Each reopening of an approved Spec, newest last: what was wrong, when, and who said yes to the revision. On a person's yes to `spec.revise`, the agent adds one and sets the Spec back to `draft`, so Spec approval is asked again. The approval question names the latest one. |
| `outcome` | mapping (`outcome`) | no | What happened after Roll out. Written during the observe window and in Learn. |
<!-- aidd:end -->

### Task (`tasks`)

<!-- aidd:gen fields:task -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line describing the slice. |
| `scope` | list of string | yes | Globs this Task's diff may change: the module's folder (`src/billing/`), and a single file only where an area names it. Never a test or design file, never a catch-all. |
| `skeleton` | boolean | no | Part of the walking skeleton: the thinnest version of a new system that runs end to end, with its structure, contracts, test runner, CI, and one smoke test, which every later slice builds on. The architect or the SRE implements it (`{skeleton}` in their write area), before the feature slices fan out. Default false. |
| `depends_on` | list of string | no | Task ids that must finish first. Required between Tasks whose scope overlaps. |
| `assignee` | string | no | Builder: `agent:<role>` or a person. |
| `skills` | list of string | no | Skills loaded only for this Task, by directory name: a practice skill such as `api-design` or a stack skill, at most two. Domain packs are named in Context instead. |
| `risk` | string | no | What this Task could break, and how it guards against it. Approved content: Spec approval covers it. |
| `proof` | string | no | How this Task is shown to work: the test command, screenshot, or check a reviewer reads. Approved content: Spec approval covers it. |
| `retry_count` | integer | no | Implementation retries used. At 3 the Task stops and the Spec is blocked until a person re-plans it. |
| `done` | boolean | no | True when the Task is finished. The agent sets it. Bookkeeping: editing it needs no `spec.revise`. |
<!-- aidd:end -->

A Task is a plan in four parts: its area (`scope`), its order (`depends_on`), its `risk`, and its `proof`. Scope the module, not the file: write `src/billing/`, so a helper you add beside a file stays in scope. Name a single file only where an area matches it; `aidd new spec --paths` writes the scope that way. Write `risk` as what could break and the guard ("the cache key changes shape; the migration test reads records written before"). Write `proof` as the named check a reviewer can open ("tests.commands `acceptance`", "screenshot in docs/design/checkout/after.png"). Both are approved content, so a change to them after approval is `spec.revise`.

### Risk (`risk`)

<!-- aidd:gen fields:risk -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `summary` | string | yes | Blast radius in one or two sentences: who or what changes behavior. |
| `dimensions` | list of `dimension` | yes | Every dimension the change touches. Empty means none. |
| `reversible` | boolean | yes | False when a revert does not restore the prior state, such as a destructive migration or an external side effect. False forces major. |
<!-- aidd:end -->

### Tests (`tests` and `tests.commands`)

<!-- aidd:gen fields:tests -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `files` | list of string | yes | The test files, and the configuration they run through. Frozen at Spec approval: changing them after is `spec.revise`, which asks (unless `mode` is `with_code`). Never inside a Task's scope. A test section of `pyproject.toml` or `package.json` is frozen by itself as `<path>#<dotted key>`, such as `pyproject.toml#tool.pytest` or `package.json#scripts.test`, so a dependency bump is not a change to the tests. |
| `commands` | list of mapping (`test_command`) | yes | Commands the runner executes. Exit 0 is the only pass. |
| `mode` | `first` \| `with_code` | no | A Spec's only. `first` (the default): the tests are written before the code and frozen at Spec approval. `with_code`: for new code with nothing to break (change type feat, no risk dimension, never major), the tests are written with the code in the same Task. Spec approval then covers the Spec, its commands, and their `covers`, but not the test files: the review and Merge approval check those. Every Acceptance item needs a command that `covers` it, and red on base still holds. |
<!-- aidd:end -->

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `smoke` | boolean | no | In the config's `tests`: part of the smoke set, the only repository commands an emergency change runs (with its own). When no command is marked, an emergency runs the whole suite. |
| `retries` | integer | no | How many more times a failing run on head is tried (default 0). Every attempt is kept in the evidence; a pass after a failure passes, marked flaky, and the flaky test is a finding. A red run on the base commit is never retried. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. Under `tests.mode: with_code` every item must be covered, or the Spec is invalid. |
<!-- aidd:end -->

### Linked docs (`docs`)

The Spec is the contract: intent, Acceptance ids, Tasks, route, risk, rollback, tests, and approvals. The detail a reader needs to judge the Spec lives in documents it links, one `docs` entry each, in the Spec's own folder beside it: `specs/SPEC-220.md` keeps its documents in `specs/SPEC-220/`. `aidd new <kind> <topic> --spec <ID>` writes one from its template in `assets/`, with the Spec's id in its header, and adds the entry. Kinds: tech-spec, test-plan, design-spec for `design-spec.md` or, with `--prototype`, `prototype.html` in the design folder (`specs/<ID>/design/`), adr, threat-model, authz for `authz-matrix.md`, api, slo, compliance, analytics for `tracking-plan.md`, migration for `migration-plan.md`, acceptance. slo and acceptance link as living docs. So do the repository's data map and vendor register (`aidd new data-map`, `aidd new vendors`) when a Spec changes what they record. The one-page pitch is the Initiative's `## Brief` (`aidd new initiative`), for an Initiative or a solo founder's MVP.

<!-- aidd:gen fields:doc -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `kind` | `tech-spec` \| `test-plan` \| `design-spec` \| `adr` \| `threat-model` \| `authz` \| `api` \| `runbook` \| `slo` \| `compliance` \| `analytics` \| `migration` \| `acceptance` \| `data-map` \| `vendors` \| `other` | yes | What the document is. It names the role that writes it (architect: tech-spec, adr, api, migration; verifier: test-plan; product designer: design-spec (with its flows and usability test) or its HTML prototype; security engineer: threat-model, authz (the authorization matrix); SRE: runbook, slo; compliance analyst: compliance, data-map (the repository's living inventory and records of processing); product manager: analytics; delivery manager: acceptance, and vendors (the repository's vendor register)) and the required-docs matrix `aidd validate` warns from (`docs.required`). |
| `path` | string | yes | Repo-relative path of the document, or a glob for a folder of files (a prototype with its assets), such as `specs/SPEC-220/tech-spec-limits.md`. It must match a file (`aidd validate`), and a frozen one is never a catch-all and never inside a Task's scope. |
| `frozen` | boolean | no | Default true: approved with the Spec, like a design file, so an edit after Spec approval is `spec.revise`; a drift found while implementing goes in the verification report and a later docs-only change. False for a living document several Specs revise (a runbook, an SLO, an area's architecture page): only checked to exist, and a Task that changes it names it in its scope. |
<!-- aidd:end -->

- **Frozen** (the default): approved with the Spec, like a design file, so an edit after Spec approval is `spec.revise`. It is never in a Task's scope. Only its owner writes it, and only before approval. A drift found while implementing goes in the verification report and a later docs-only change, never an edit in place.
- **Living** (`frozen: false`): a runbook, an SLO, or an area document several Specs revise. `aidd validate` checks it exists. A Task that changes it names it in its scope, like any other file.
- **When.** Nothing on minor. Testing lives in the Spec's Acceptance and the tech spec's `## Test strategy`. `aidd validate` warns, never errors, when a major Spec links:
  - no tech-spec and no runbook (its own `## Alternatives considered` and `## Pre-mortem`, or `## Rollout`, count). Any reason for major counts: a dimension that forces major or `availability`, a type that forces major, an irreversible change, or a service or deploy path (IaC, a container, a deploy or release file)
  - no threat-model when a risk dimension is security, privacy, or data (on normal too)
  - no design-spec doc or `design.files` on a feat with a user-facing path
  - no test-plan when a trigger fires: a compliance dimension or type, a device path, `uat: true`, or 10 or more Acceptance items
  - no migration doc on a data dimension or type, or an irreversible change
  - no analytics doc (a tracking plan) when the Spec has a `hypothesis` (on normal too)

  On normal the others are suggestions `aidd new spec` prints. `docs.required` in the config only turns a kind's rule off. Which docs a team of your size writes by default: `profiles.md`, Ceremony by team size.
- **Checks.** A doc or a local `decisions` path that does not exist is an error. So is a frozen doc that is a catch-all or sits in a Task's scope. These are warnings:
  - a frozen doc that still holds TODO or does not name its Spec
  - a test plan whose Acceptance ids differ from the Spec's, or that no command covers
  - a tech spec's Test strategy that lists an id the Spec lacks or no command covers

### Observe (`observe`)

<!-- aidd:gen fields:observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `not_applicable` | string | no | Why nothing runs to watch after release, such as "a CLI and its docs: no running service". It takes the place of the other fields, so the person asked for approval sees the reason. |
| `command` | list of string | no | Post-release check. Exit 0 means healthy. |
| `signals` | string | no | Dashboards, SLOs, or queries a human watches. |
| `window` | string | no | How long to watch, such as 30m, 24h, or 7d. |
| `rollback_trigger` | string | no | The condition that starts the rollback. |
<!-- aidd:end -->

### Feature flags (`flags`)

Optional, on a normal or major user-facing change whose release should come after its deploy. Never on minor. A person owns each flag and flips it in production, never an agent. The cleanup is a later Spec that lists the flag in `removes_flags`. After `cleanup_due`, `aidd validate` warns and `aidd status` shows it as work.

```yaml
flags:
  - name: checkout-v2
    default: "off"
    owner: "@alice"
    cleanup_due: "2026-12-01"
    purpose: release toggle for the new checkout
```

<!-- aidd:gen fields:flag -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | A flag key in lowercase, with `-`, `.`, or `_` between words, such as `checkout-v2`: the key the code evaluates. |
| `default` | `on` \| `off` | yes | The value the code falls back to when the flag system cannot answer. `off` for a new feature; `on` only for a kill switch that guards existing behavior. |
| `owner` | string | yes | The person who decides when the flag flips and sees it removed: never an agent or an agent account (`aidd validate` fails one). |
| `cleanup_due` | string | yes | The date by which a later Spec removes the flag and its dead branch. After it, `aidd validate` warns and `aidd status` shows the cleanup as work. |
| `purpose` | string | no | Why the flag exists: a release toggle, an experiment, a kill switch, or an operational toggle. |
<!-- aidd:end -->

### Deprecations (`deprecations`)

Optional, when a change deprecates what its consumers use: an endpoint, a field, an event, a config key, or a command. The running API sends the same dates in the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers. The removal is a later Spec that lists the `what` in `removes_deprecations`. After `sunset`, `aidd validate` warns, and `aidd status` shows the removal as work.

```yaml
deprecations:
  - what: "GET /v1/orders"
    announced: "2026-10-01"
    sunset: "2027-04-01"
    replacement: "GET /v2/orders"
    consumers: ["mobile app"]
```

<!-- aidd:gen fields:deprecation -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `what` | string | yes | What is deprecated, as its consumers know it, such as `GET /v1/orders` or `order.total_cents`: the name a removal Spec lists in `removes_deprecations`. |
| `announced` | string | yes | The day consumers were told. The `Deprecation` header (RFC 9745) carries the day the deprecation takes effect. |
| `sunset` | string | yes | The day it stops working: the date the `Sunset` header (RFC 8594) carries, never before `announced` (`aidd validate` fails one). After it, a later Spec removes it, and until then `aidd validate` warns and `aidd status` shows the removal as work. |
| `replacement` | string | yes | What consumers use instead, such as `GET /v2/orders`, or `none` with the reason. |
| `consumers` | list of string | no | The known consumers that still use it, as the api doc's Consumers table names them: the people told before the sunset. |
<!-- aidd:end -->

### Experiment (`experiment`)

Optional: an A/B test that decides the Spec's `hypothesis`. Plan it before Spec approval with the tracking plan, which names its exposure event. A `flags` entry with `purpose` experiment serves it. `aidd validate` warns when the experiment names no guardrail or the Spec has no hypothesis. How to run it (the sample ratio check, the stop rule): the Experiments section of `aidd-team:release-rollout`.

```yaml
experiment:
  variants: [control, one-page]
  metric: checkout conversion
  guardrails: [payment error rate, p95 checkout latency]
  min_sample: 12000
  decision: ship one-page if conversion rises at p < 0.05 and no guardrail worsens; stop on a guardrail breach or a sample ratio mismatch
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

### Incident (`emergency`)

<!-- aidd:gen fields:emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `severity` | `sev1` \| `sev2` \| `sev3` | yes | Incident severity. |
| `kind` | `outage` \| `degradation` \| `security` \| `data` | yes | What is broken in production. |
| `commander` | string | yes | The incident commander, a human. Named before the repair starts. |
| `incident` | string | no | The incident's ticket or page id, such as INC-481: what the repair answers, and what the post-incident review and the backfill Spec link. Required on an emergency change. |
| `review_due` | string | yes | Date the postmortem and the Spec backfill are due. |
<!-- aidd:end -->

### Outcome (`outcome`)

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

`docs.exemplars` in `.aidd/config.yaml` names the project's best Specs. A person chooses them; aidd never does. Read them before you write a Spec. Follow their shape and depth, and never copy their content. `aidd validate` warns on an exemplar that does not exist.

## Measurable words

Write each Acceptance line as a target a test can check. "Search is fast" is not one; "p95 under 300 ms" is. `aidd validate` warns on an Acceptance line, or a line of `## Non-functional requirements`, that uses a vague word and holds no number, inline code, link, or file path. The word list is `schemas/vague-words.json` in the CLI. It is a warning, never an error. `aidd validate` also warns when Goals, Acceptance, or Design use a word from the Avoid column of the repository's glossary (`aidd new glossary`). Intent is never checked, because it quotes the originator.

## Specialist returns (fixed templates)

With the delivery team, a specialist that cannot write the Spec returns its part in the template below. The architect folds it into the section the template names. A row the specialist cannot fill goes on the handoff note's Needs line instead of a guess. A fixed shape lets the architect fold without re-deriving, and the verifier turn each row into a test.

**Security engineer** → this Spec's delta in the tech spec's `### Security and privacy`: the threat ids it adds, changes, or retires. Also the component's living threat model it links (`aidd new threat-model <component>`), kept in line with the delta in the same change, and Acceptance. One row per threat, in the same shape as the threat-model template and the compliance record's DPIA. Every row names the Acceptance id that proves its mitigation, and the mitigation's owner or the person who accepted the risk. Risk is the likelihood (remote, possible, probable) times the severity (minimal, significant, severe), as low, medium, or high, the ICO's DPIA scale: the highest rows are mitigated and tested first.

| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Risk | Mitigation | Acceptance id | Owner |
| --- | --- | --- | --- | --- | --- |
| Spoofing: a replayed session token | browser → API | high (probable × significant) | bind the token to the device, expire in 15 min | A4 | @security-lead |
| Linking: two exports joined on the email column | export → analytics | medium (possible × significant) | export a per-export pseudonym, never the email | A5 | @privacy-lead |

Then the ASVS level and the requirements it names, and the data-flow diagram as Mermaid.

**SRE** → the tech spec's `### Observability`, the Spec's `observe` and `rollback`, and the rollout runbook it links. One row per signal that shows the change working or failing.

| SLI (golden signal, RED or USE) | SLO | Observe signal (dashboard, query, or `observe.command`) | Window | Rollback trigger |
| --- | --- | --- | --- | --- |
| checkout p99 latency | 99% under 400 ms over 28 days | `checkout_latency_seconds` p99 panel | 24h | error-budget burn above 14.4x for 5 min |

Then the runbook path for each new failure mode, and on major the pre-mortem's causes. When nothing runs after release (a library, a CLI, docs), return one line instead: `observe: {not_applicable: "<reason>"}`, with no runbook.

**Compliance analyst** → the tech spec's `### Compliance` (Cross-cutting concerns), or a `compliance` doc the Spec links. One row per obligation. The evidence is something the repository already holds, such as a test or the `aidd test` evidence. The control id is the enterprise-controls pack's `EC-01` to `EC-19`, or the team's own.

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or `aidd test` evidence) | Owner |
| --- | --- | --- | --- | --- |
| EC-10 | GDPR Art. 25 data minimization | drop the date of birth from the export | the test that asserts the export's columns; the `aidd test` evidence for the head | the privacy pool |

Then whether a DPIA is required and why.
