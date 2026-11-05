# Spec fields

What you write: the Spec and its Tasks. Its tests: `references/spec-tests.md`. Its linked docs: `references/spec-docs.md`. Its release blocks (`observe`, `flags`, `deprecations`, `emergency`, `outcome`): `references/spec-release.md`. A specialist's return: `references/spec-returns.md`. Intents: `references/intents.md`. Proposals: `references/proposal.md`. `aidd gen-docs` generates the tables from the CLI's schemas. `aidd validate` is the authority.

## Spec (`specs/<ID>.md` front matter)

<!-- aidd:gen fields:spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | `"spec"` | yes | Object type. Always `spec`. |
| `id` | string | yes | Spec key, such as SPEC-220. |
| `parent` | string | no | Optional: the Intent whose slice this Spec delivers. `aidd validate` warns when it lists no such slice. |
| `title` | string | yes | One line, an imperative summary of the change, such as "Rate-limit authenticated checkout": the merge commit's subject, `<change_type>: <title> (<ID>)`. `aidd validate` warns when that subject passes 72 characters. The language in the project's AGENTS.md may apply. |
| `delivery_team` | string | no | The delivery team that owns the change: a key of the config's `delivery_teams`, which `aidd validate` checks. Unset, the change is its Intent's team's, or the work of the team whose areas its Tasks touch. |
| `approvers` | list of string | no | The people to ask for this Spec's decisions, first to last. Missing, the agent asks the config's `owners.approvers`. |
| `change_type` | `change_type` | yes | What kind of change this is, in Conventional Commits vocabulary. The type never raises the route: a risk dimension does, as `risk.dimensions` holds it and `aidd risk --dimension` declares it. |
| `route` | `normal` \| `major` \| `emergency` | yes | normal, major (an area or the risk can raise a normal change to major), or emergency for a backfill Spec. A minor change has no Spec file. |
| `confidence` | `confidence` | no | Confidence in the assessment. Write it only as `low`, which stops the run. Unset, it is `high` while `open_questions` is empty and `medium` while it lists facts. |
| `open_questions` | list of string | no | Facts still unknown at assessment. Leave it out when none is. |
| `trace_id` | string | no | Joins the Specs and changes of one piece of work across repositories. Unset, it is the lower-cased id; write it only to join work across repositories. |
| `tracker` | list of mapping | no | The tracker's story this Spec delivers, such as `{type: story, id: PORT-32}`. |
| `status` | `status` | no | The Spec's status, stored here. The agent sets it as the work moves: `ready` when it asks for Spec approval, `approved` on the person's yes, and `done` once the change merged. Missing means `draft`. |
| `approved_by` | string | no | The person who said yes, in git's trailer form, like `Co-authored-by`: `Name <email>`, from their `git config user.name` and `git config user.email`. When that identity is a bot's or missing, it is the `Name <email>` or `@handle` the person gives. An Approver's `@handle`, `@org/team`, or `email:<address>` holds too. It names only who: the head, the action, or a delegation goes in the commit body or the decision record (`aidd records add`). `aidd validate` warns about another form, and about an agent or a bot. |
| `approved_at` | string | no | When the person said yes to Spec approval (RFC 3339), such as `2026-11-03T14:20:00Z`. On the yes in the chat, the agent sets it, `approved_by`, and `status: approved`, and commits with an `Approved-by:` trailer of the same value as `approved_by`. Both are a note the agent wrote, not proof. |
| `delegate_answer` | string | no | On a delegated Spec approval, the id of the `delegate_answer` record that accepted it, with `approved_at` and `status: approved`, and no `approved_by`. The commit carries the `Decided-by`, `On-behalf-of`, and `Delegation` trailers, never `Approved-by`, which stays a person's own yes. |
| `waiting_on` | string | no | Role, person, or interface the Spec waits on. While `waiting_on` names one, the Spec is blocked: a flag `aidd status` shows, not a status. |
| `blocked_by` | list of string | no | The work items (Specs or Intents) that must finish before Implement starts, by id. A draft or ready Spec waits only at Implement, and `aidd status` names what it waits for. Bookkeeping: it never changes the route, and on a Spec editing it needs no `spec.revise`. A Task's `depends_on`, which orders Tasks inside one Spec, is unrelated. |
| `provides` | list of string | no | The interfaces this Spec provides, by stable name, such as `orders-api` or `order.created`: an API, an event, or a schema that other Specs consume. When it is revised (`spec.revise`), `aidd status` names the open Specs that `consumes` each one, so the question to the person names them and their owners hear first. Advice only: nothing blocks. Bookkeeping: it never changes the route, and on a Spec editing it needs no `spec.revise`. |
| `consumes` | list of string | no | The interfaces this Spec consumes, by the stable name another Spec lists in `provides`. `aidd validate` warns when no Spec provides one. Bookkeeping: it never changes the route, and on a Spec editing it needs no `spec.revise`. |
| `priority` | `priority` | no | How soon the work matters, for sorting the open work. Unset, it is inherited from the parent Intent, else medium; an emergency is always urgent. Bookkeeping: it never changes the route, and editing it needs no `spec.revise`. |
| `owner` | string | no | The person driving the work, whom `aidd status` names as who acts. A person, never an agent or an agent account (`aidd validate` fails one). Bookkeeping: editing it needs no `spec.revise`, and it approves nothing. |
| `suggested_by` | string | no | Who suggested work nobody asked for: `role:<role>` for a role in `agents.proactive_roles` (or an agent account). Such a Spec stays a draft until a person decides its `triage`. |
| `triage` | mapping (`triage`) | no | A person's decision on suggested work. Required, by a person, before a Spec whose suggested_by is an agent moves past draft. |
| `risk` | mapping (`risk`) | yes | Blast radius: what changes, which dimensions it touches, whether a revert restores the prior state, what stays true after release, and what it costs to run. |
| `rollback` | string | yes | How to undo. Name the steps on major and emergency. |
| `hypothesis` | string | no | The measurable result the change should produce after Roll out, written before Spec approval, which covers it: a metric, its baseline, the expected move, and by when. Learn writes `outcome.result` against it. |
| `manual_acceptance` | boolean | no | True when humans accept this change by hand: a client's user acceptance test, a product or QA owner's pass, or a device lab run. A test plan is expected on major and suggested on normal (`aidd new spec` prints it); the acceptance record (`aidd new acceptance`) lists who accepted each id and holds the sign-offs. Approved content: Spec approval covers it. |
| `adrs` | list of string | no | ADR paths or links this Spec depends on, and does not change. A repository path must exist (`aidd validate`); an ADR this Spec writes is a `docs` entry of type `adr` instead. |
| `tasks` | list of mapping (`task`) | yes | Slices of the change. Parallel only when their scope is disjoint. |
| `tests` | mapping (`tests`) | yes | How the change is proven: the test files and the commands that run them. |
| `design` | mapping | no | The approved look and flow of a user-facing change. Optional; the product designer writes it before Spec approval. |
| `docs` | list of mapping (`doc`) | no | The documents that hold the detail this Spec links instead of carrying: a tech spec, a test plan, a prototype or design spec, an ADR, a threat model, an API contract, a migration or tracking plan, a runbook. `aidd new <type> <topic> --spec <ID>` writes one from its template and adds the entry. A frozen doc is approved with the Spec, like a design file; a living one is only checked to exist. |
| `observe` | mapping (`observe`) | when route is `major` | Post-release check: what to watch, for how long, and when to roll back. Required on major. |
| `flags` | list of mapping (`flag`) | no | Feature flags this change ships behind, so release is separate from deploy: the architect adds one on a normal or major user-facing change that should reach users later than its code reaches production. Optional; a minor change never needs one. Approved content: Spec approval covers it. `aidd validate` warns, and `aidd status` shows the cleanup as work, once a flag's `cleanup_due` has passed and no merged Spec lists it in `removes_flags`; a later Spec that declares the same flag with a later date extends it once that Spec merges. |
| `removes_flags` | list of string | no | Flags this change deletes from the code, by name: the cleanup Spec for an earlier Spec's `flags` entry. Once this Spec merges, `aidd validate` and `aidd status` stop reporting the flag as overdue; while it is a draft, they name it as the pending removal. |
| `deprecations` | list of mapping (`deprecation`) | no | What this change deprecates: an endpoint, a field, an event, a config key, or a command its consumers still use. The architect adds one when a removal or a changed meaning goes through expand and contract. The running API announces it with the `Deprecation` header (RFC 9745) and, once dated, the `Sunset` header (RFC 8594), with the same dates. Approved content: Spec approval covers it. `aidd validate` warns, and `aidd status` shows the removal as work, once its `sunset` has passed and no merged Spec lists it in `removes_deprecations`. A later Spec that declares the same `what` with a later `sunset` extends it once that Spec merges. |
| `removes_deprecations` | list of string | no | Deprecations this change removes from the code, by their `what`: the removal Spec for an earlier Spec's `deprecations` entry. Once this Spec merges, `aidd validate` and `aidd status` stop reporting it; while it is a draft, they name it as the pending removal. |
| `emergency` | mapping (`emergency`) | when route is `emergency` | Required when route is emergency. |
| `revisions` | list of mapping | no | Each reopening of an approved Spec, newest last: what was wrong, when, and who said yes to the revision. On a person's yes to `spec.revise`, the agent adds one and sets the Spec back to `draft`, so Spec approval is asked again. The approval question names the latest one and, when the Spec `provides` an interface, the open Specs that consume it. |
| `outcome` | mapping (`outcome`) | no | What happened after Roll out. Written during the observe window and in Learn. |
<!-- aidd:end -->

### Task (`tasks`)

<!-- aidd:gen fields:task -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line describing the slice. |
| `scope` | list of string | yes | Globs this Task's diff may change: the module's folder (`src/billing/`), the folder of the unit tests written with its code, and a single file only where an area names it. Never a frozen test or design file, never a catch-all. |
| `skeleton` | boolean | no | Part of the walking skeleton: the thinnest version of a new system that runs end to end, with its structure, contracts, test runner, CI, and one smoke test, which every later slice builds on. The architect or the SRE implements it (`{skeleton}` in their write area), before the feature slices fan out. Default false. |
| `depends_on` | list of string | no | Task ids that must finish first. Required between Tasks whose scope overlaps. |
| `assignee` | string | no | Builder: `role:<role>` for a role of the team, or a person. |
| `skills` | list of string | no | Skills loaded only for this Task, by directory name: a practice skill such as `schema-migration` or a stack skill, at most two. Domain packs are named in Context instead. |
| `risk` | string | no | What this Task could break, and how it guards against it. Approved content: Spec approval covers it. |
| `proof` | string | no | How this Task is shown to work: the test command, screenshot, or check a reviewer reads. Approved content: Spec approval covers it. |
| `retry_count` | integer | no | Implementation retries used. At 3 the Task stops and the Spec is blocked until a person re-plans it. |
| `done` | boolean | no | True when the Task is finished. The agent sets it. Bookkeeping: editing it needs no `spec.revise`. |
<!-- aidd:end -->

A Task is a plan in four parts: its area (`scope`), its order (`depends_on`), its `risk`, and its `proof`. Scope the module, not the file, so a helper you add beside a file stays in scope; `aidd new spec --paths` writes the scope that way. Write `risk` as what could break and the guard ("the cache key changes shape; the migration test reads records written before"). Write `proof` as the named check a reviewer can open ("tests.commands `acceptance`", "screenshot in docs/design/checkout/after.png"). Both are approved content, so a change to them after approval is `spec.revise`. Once the Spec is approved, and its branch changes no other Spec, `aidd validate` warns of each file the change alters that no Task's scope, test, design file, or linked doc names. While the Spec asks for approval, each open question it still lists gets a warning too.

### Risk (`risk`)

<!-- aidd:gen fields:risk -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `summary` | string | yes | Blast radius in one or two sentences: who or what changes behavior. |
| `dimensions` | list of `dimension` | yes | Every dimension the change touches. Empty means none. |
| `irreversible` | boolean | yes | True when a revert does not restore the prior state, such as a destructive migration or an external side effect. True forces major. |
| `residual` | string | no | What stays true after release. `none` when nothing remains. A threat that stays is named by its id in the threat model, never restated. |
| `cost_estimate` | mapping | no | What the change will cost to run, which the architect estimates in Specify: the one place for it. `aidd validate` warns on a Spec that changes infrastructure code, or whose risk names `cost`, and gives none. It also warns on a monthly estimate above `project.budget.max_infra_per_month`, the person's ceiling. Latency and availability belong in the SLO and `observe`. |
<!-- aidd:end -->

## Exemplar Specs

`docs.exemplars` in `.aidd/config.yaml` names the project's best Specs. A person chooses them; aidd never does. Read them before you write a Spec. Follow their shape and depth, and never copy their content. `aidd validate` warns on an exemplar that does not exist.

## Measurable words

Write each Acceptance line, and each line of `## Non-functional requirements`, as a target a test can check. "Search is fast" is not one; "p95 under 300 ms" is. A word that names a quality but no target, such as fast, easy, or secure, needs its number, unit, threshold, or test, and the reviewer reads every line for one. `aidd validate` warns when Goals, Acceptance, or Design use a word from the Avoid column of the repository's glossary (`aidd new glossary`). Request is never checked, because it quotes the person.
