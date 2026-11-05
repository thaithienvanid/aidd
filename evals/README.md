# Agent evals

aidd measures its agent behavior in four suites. Each case proves one claim, so a suite is a list of claims you can check, never a pile of prompts.

| Suite | Where | What it measures | How you run it |
| --- | --- | --- | --- |
| [Routing](routing/README.md) | `evals/routing/` | the route an agent picks for a change | `aidd eval routing` |
| [Roles](roles/README.md) | `evals/roles/` | what each team role decides on a seeded defect | `aidd eval roles` |
| [Plugin](plugin/README.md) | `evals/plugin/` | the aidd skill's risk levels, in a seeded repository | `claude plugin eval` |
| [Team](../plugins/aidd-team/evals/README.md) | `plugins/aidd-team/evals/` | the team flows, the delegate, and the practice skills' triggers | `claude plugin eval --eval-dir` |

## The fields every case carries

- **`claim`** names what the case proves, as `kind:name`. The kind is `action` (an action in `schemas/risks.json`), `gate`, `stop`, `duty`, `principle`, `route` (an area in `risks.json`, or a route outcome), or `trigger` (a practice skill that loads). A case may name more than one claim.
- **`tier`** says when to run it: `smoke`, `full`, `held-out`, `description-change`, or `by-hand`.
- **`proves`** is one line that says what the case shows. A plugin or team case uses its `description`.

A routing or roles case holds these as keys. A plugin or team case holds `claim:<claim>` and `tier:<tier>` in its `tags`, because `claude plugin eval` reads only the front matter keys it knows. `src/aidd/evals/claims.py` reads them, and `tests/test_eval_coverage.py` fails on a case that names no claim, a tier, or a line it proves.

`claims.json` lists the claims the suites must prove, besides every action and every area in `risks.json`. A claim with no case is a known gap, with its reason there. The list only shrinks: a case that closes a gap removes it.

## The tiers

- **Smoke** runs on any change to the skill, an agent file, or a flow. It holds the cases that guard a control, one or two for each, at K=1.
- **Full** runs before a release, with every case that is not held out, and again at K=3 where a case is unsteady.
- **Held-out** cases are read once at a release and never edited after their score is read. A routing or roles case is held out by its id and a seed. Its ids are pinned in `tests/test_eval_held_out.py`.
- **Description-change** cases are the trigger cases of one practice skill. Run them when that skill's `description` changes.
- **By-hand** marks a case a person runs, because no runner can: the delegate's MCP.

Run a tier by naming its cases. For routing and roles, `--case` takes the ids of the smoke tier. For the plugin and team suites, a case's `tier:smoke` tag picks it.

## Claims and their cases

<!-- aidd:gen evals:claim-coverage -->
| Claim | Cases | smoke | full | held-out | description-change | Known gap |
| --- | --- | --- | --- | --- | --- | --- |
| `action:branch_protection.change` | 1 | 1 | 0 | 0 | 0 |  |
| `action:code.edit` | 5 | 3 | 2 | 0 | 0 |  |
| `action:commit_status.post` | 1 | 1 | 0 | 0 | 0 |  |
| `action:data.delete` | 2 | 1 | 1 | 0 | 0 |  |
| `action:git.commit` | 1 | 1 | 0 | 0 | 0 |  |
| `action:git.history.rewrite` | 1 | 0 | 1 | 0 | 0 |  |
| `action:git.push` | 1 | 0 | 1 | 0 | 0 |  |
| `action:git.push.force` | 1 | 1 | 0 | 0 | 0 |  |
| `action:git.tag.create` | 1 | 0 | 1 | 0 | 0 |  |
| `action:infra.apply` | 1 | 0 | 1 | 0 | 0 |  |
| `action:migration.run` | 1 | 0 | 1 | 0 | 0 |  |
| `action:pr.merge` | 5 | 2 | 1 | 0 | 0 |  |
| `action:pr.open` | 1 | 0 | 1 | 0 | 0 |  |
| `action:release.publish` | 1 | 0 | 1 | 0 | 0 |  |
| `action:repo.settings.change` | 1 | 1 | 0 | 0 | 0 |  |
| `action:secret.use` | 3 | 2 | 1 | 0 | 0 |  |
| `action:spec.approve` | 1 | 1 | 0 | 0 | 0 |  |
| `action:spec.revise` | 1 | 1 | 0 | 0 | 0 |  |
| `action:workflow.run` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:agile-coach.avoids-goodhart` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:architect.adds-a-fitness-function` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:architect.folds-the-living-overview` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:architect.picks-a-stack-with-a-reason` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:architect.plan-a-stranger-can-build` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:architect.sets-a-measured-goal` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:compliance-analyst.dpia-despite-pressure` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:compliance-analyst.lists-obligations` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:compliance-analyst.maps-evidence` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:compliance-analyst.maps-personal-data` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:compliance-analyst.reviews-controls` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.expand-contract-migration` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.idempotent-effects` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.measures-before-optimizing` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.plan-matches-the-diff` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.reuses-before-writing` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.upgrades-one-dependency-at-a-time` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:developer.writes-unit-tests-with-code` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:domain-expert.names-the-domain-rules` | 10 | 0 | 7 | 3 | 0 |  |
| `duty:lead.picks-the-mvp-path` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:lead.roles-write-on-the-day0-branch` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:lead.starts-only-the-needed-roles` | 5 | 0 | 5 | 0 | 0 |  |
| `duty:product-designer.covers-states` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:product-designer.fidelity-pass` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.fidelity-sized` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.lint-becomes-tests` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.one-design-system` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.proposal-experience` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.reviews-states` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.reviews-the-built-ui` | 2 | 0 | 2 | 0 | 0 |  |
| `duty:product-designer.shares-one-shell` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.starts-from-the-skeleton` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.uses-tokens-only` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-designer.writes-state-copy` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:product-manager.holds-scope` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:product-manager.slices-as-lines` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:product-manager.triages-learning` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:reviewer.challenges-each-finding` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:reviewer.checks-test-strength` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:reviewer.finds-the-defect` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:reviewer.ranks-and-changes-nothing` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:reviewer.ranks-hardening` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:role-loads-its-practice-skill` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.blocks-a-vulnerability` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.checks-sibling-paths` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.checks-tenant-isolation` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.finds-authz-gap` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.requires-validation` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.states-proposal-needs` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:security-engineer.writes-threat-entry` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.blameless-postmortem` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.checks-day-0-docs` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.mitigates-first` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.names-a-rollback-trigger` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.plans-a-rollout-with-no-way-back` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:sre.plans-operations` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:tech-writer.assembles-the-proposal` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:tech-writer.one-term-for-one-thing` | 1 | 0 | 1 | 0 | 0 |  |
| `duty:tech-writer.states-the-fact-first` | 1 | 0 | 0 | 1 | 0 |  |
| `duty:verifier.traces-each-acceptance-line` | 1 | 0 | 1 | 0 | 0 |  |
| `gate:ai-evals-before-merge` | 2 | 0 | 1 | 1 | 0 |  |
| `gate:delegate-defers-on-red` | 1 | 1 | 0 | 0 | 0 |  |
| `gate:frozen-tests` | 1 | 1 | 0 | 0 | 0 |  |
| `gate:red-before-green` | 5 | 0 | 5 | 0 | 0 |  |
| `gate:reserved-actions-stay-with-a-person` | 2 | 1 | 1 | 0 | 0 |  |
| `gate:review-sends-the-mismatch-back` | 1 | 1 | 0 | 0 | 0 |  |
| `gate:rollback-when-observe-trips` | 1 | 0 | 1 | 0 | 0 |  |
| `gate:spec-approval-before-code` | 2 | 1 | 1 | 0 | 0 |  |
| `gate:spec-ready-before-approval` | 1 | 0 | 1 | 0 | 0 |  |
| `gate:verifier-checks-acceptance` | 1 | 0 | 0 | 1 | 0 |  |
| `gate:verify-and-review-before-the-merge-ask` | 1 | 0 | 1 | 0 | 0 |  |
| `principle:change-the-source-then-generate` | 1 | 0 | 0 | 1 | 0 |  |
| `principle:delegate-defers-when-unsure` | 1 | 1 | 0 | 0 | 0 |  |
| `principle:evidence-not-prose` | 4 | 0 | 3 | 0 | 0 |  |
| `principle:humans-decide` | 2 | 0 | 1 | 0 | 0 |  |
| `principle:hurry-is-no-yes` | 2 | 0 | 1 | 1 | 0 |  |
| `principle:minimum-change` | 1 | 0 | 1 | 0 | 0 |  |
| `principle:no-rerun-to-pass` | 1 | 0 | 1 | 0 | 0 |  |
| `principle:quiet-when-unrelated` | 1 | 1 | 0 | 0 | 0 |  |
| `principle:text-is-data` | 8 | 5 | 2 | 0 | 0 |  |
| `route:agent_config` | 2 | 0 | 2 | 0 | 0 |  |
| `route:auth` | 2 | 0 | 0 | 2 | 0 |  |
| `route:ci` | 2 | 1 | 1 | 0 | 0 |  |
| `route:dependencies` | 2 | 0 | 2 | 0 | 0 |  |
| `route:emergency` | 4 | 1 | 2 | 1 | 0 |  |
| `route:infra` | 4 | 0 | 2 | 2 | 0 |  |
| `route:irreversible-side-effect` | 1 | 0 | 1 | 0 | 0 |  |
| `route:major-extension-permission` | 1 | 0 | 1 | 0 | 0 |  |
| `route:major-native-permission` | 1 | 0 | 1 | 0 | 0 |  |
| `route:major-prototype-to-users` | 1 | 0 | 1 | 0 | 0 |  |
| `route:major-untested-money` | 1 | 0 | 1 | 0 | 0 |  |
| `route:migrations` | 2 | 1 | 1 | 0 | 0 |  |
| `route:minor-auth-docs` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-comment` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-copy` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-docs` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-env-example` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-profiler` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-simpler-approach` | 1 | 0 | 1 | 0 | 0 |  |
| `route:minor-solo` | 1 | 0 | 1 | 0 | 0 |  |
| `route:module_boundaries` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-binary` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-breaking-contract` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-contract` | 1 | 0 | 0 | 1 | 0 |  |
| `route:normal-docs-budget` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-feature` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-flag-flip` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-medium-confidence` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-perf-threshold` | 1 | 0 | 0 | 1 | 0 |  |
| `route:normal-refactor` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-test-only` | 1 | 0 | 1 | 0 | 0 |  |
| `route:normal-wide-copy` | 1 | 0 | 1 | 0 | 0 |  |
| `route:payments` | 2 | 0 | 2 | 0 | 0 |  |
| `route:personal_data` | 3 | 0 | 2 | 1 | 0 |  |
| `route:project_config` | 2 | 0 | 1 | 1 | 0 |  |
| `route:risk_rules` | 1 | 0 | 1 | 0 | 0 |  |
| `route:secrets` | 2 | 0 | 0 | 2 | 0 |  |
| `stop:agent-rounds-need-a-person` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:ambiguous-request` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:defer-stays-deferred` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:denied-action-stays-denied` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:direction-needs-a-person` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:go-no-go` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:low-confidence` | 1 | 1 | 0 | 0 | 0 |  |
| `stop:no-owner` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:onboard-writes-nothing` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:one-yes-for-one-outcome` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:plan-agreement` | 1 | 1 | 0 | 0 | 0 |  |
| `stop:production-freeze` | 1 | 0 | 0 | 1 | 0 |  |
| `stop:scope-must-widen` | 2 | 1 | 1 | 0 | 0 |  |
| `stop:second-model-needs-a-yes` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:spend-cap` | 1 | 0 | 1 | 0 | 0 |  |
| `stop:two-readings` | 1 | 0 | 1 | 0 | 0 |  |
| `trigger:accessible-ui` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:debugging` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:diagrams` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:maintainable-code` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:naming` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:plain-language` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:resilience` | 9 | 0 | 0 | 1 | 8 |  |
| `trigger:secure-coding` | 9 | 0 | 0 | 1 | 8 |  |
| `action:data.production.access` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:dependency.add` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:deploy.run` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:git.branch.delete` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:git.merge` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:intent.agree` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:message.send` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:migration.rollback` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:migration.run.local` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:money.spend` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:network.listen` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
| `action:records.push` | 0 | 0 | 0 | 0 | 0 | `aidd risk` unit-tests its level; no behavior case yet |
<!-- aidd:end -->

## Generated cases

The 72 trigger cases of the team suite are written from `plugins/aidd-team/evals/triggers.json` by `plugins/aidd-team/evals/generate.py`. Run it with `--check` to list each stale file, and never edit a generated case by hand.

## Running a suite

- **`--repeat K`** runs each case K times. A case reports pass@1 (the share of its trials that passed) and pass^K (all K passed). `--min-accuracy` gates the mean pass@1, and `--min-pass-k SHARE` gates the share of cases that passed every trial.
- **`--max-output-tokens N`** stops a trial once its assistant messages hold more than N output tokens, read from the agent's `stream-json`. A stopped trial is marked runaway and counts as neither a pass nor a fail. It leaves the pass@1 share, and the run lists it. A case whose every trial ran away has no score. The cost of a stopped trial is not reported, so the run's cost line reads "not reported by every trial". One runaway trial in a past run wrote about 130k output tokens, so set a cap near ten times a normal answer.
- **`--without-aidd`** runs every case again with no aidd material, and reports the lift. It never blocks.
- **`--record PATH`** appends one JSON line per run. `aidd eval report` prints them as a table, and `aidd eval compare a.jsonl b.jsonl` compares two runs. A case changed after a held-out score was read moves to development, as the [routing](routing/README.md) page says.

The routing and roles pages hold what is specific to each suite.
