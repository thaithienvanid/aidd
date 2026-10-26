# Design rationale

Why aidd works the way it does. Each row pairs a failure mode of agent-driven development with the decision that closes it. The requirements themselves are in [METHOD.md](METHOD.md). This page explains them and owns the list of [known limits](#known-limits-in-100). Regression tests back the security rows (`tests/test_redteam.py`, `tests/test_security_hardening.py`, `tests/test_security_integrity.py`, `tests/test_gate_rules.py`). A mutation in `examples/` also backs each security row, and another implementation of the gate can replay it.

## Who decides

| Failure mode | Decision |
| --- | --- |
| Rules written as prose that the controlled agent is asked to follow, with the agent reporting its own results. | The agent proposes; the gate decides. The Change Request block only *declares* scope and intent. Diff, evidence, identities, approvals, and Policy are *derived* from the platform by a function of those facts alone. That function posts a required status. |
| The only human approval is after the build, when the code already exists and review becomes rubber-stamping. | Spec approval happens before implementation on normal and major (on major only, under solo). It binds the exact Spec and tests that land by a hash of their content, so an edit to either voids the approval. |
| Agents commit as the person who runs them, so author-based separation of duties is meaningless, and solo developers can never pass. | Separation of duties is measured against the *authors* (PR/MR author, commit authors, committers) and agent accounts. The solo profile waives that rule for one person. It also loosens a few others: Spec approval on major only, and red-then-green as a warning. But the Approver must still be in `owners.approvers`, the waiver is recorded ([METHOD.md §8](METHOD.md#solo)). |
| One "security reviewer" role has to judge data, privacy, money, and compliance changes it knows nothing about. | Specialist Approver pools. Each major dimension names the pool that reviews it (`data`, `security`, `privacy`, `finance`, `compliance`), and a risk rule can name its own. An unbound pool falls back to `security`, so the smallest team still has one specialist pool. Outside solo, nobody approves their own change, so each pool names at least two humans. `aidd doctor` warns about a pool of one. |
| A delivery team of agents taken for the whole organization, people decisions included. | Engineering management, hiring, and people management are human-only and not modelled: no role, command, or check stands in for them. aidd models the delivery work and the decisions on it, never the careers of the people who do it. |
| Every change needs a human, even bot patch bumps. | Standard changes: configured classes merge on green tests, never on protected paths, never under audited, and only with verified signatures. |

## What counts as proof

| Failure mode | Decision |
| --- | --- |
| The implementer writes and edits the test that grades it. | Tests are written in Specify, and the Spec hash freezes them. A Task's `scope` may not cover a test file. New behavior must be red on base and green on head. |
| Evidence not bound to a commit or a change, or produced by a workflow the PR controls. | Evidence records the head and base SHAs. The gate reads evidence only from the configured test workflow's runs of the change's own branch. It refuses the evidence while another PR from that branch at that commit targets a different base. The test action runs aidd from its pinned ref, and changing that ref is a protected change. |
| A change edits the gate's config, CI, CODEOWNERS, agent instructions, or hooks. | The built-in protected paths, plus every file a bound Policy or Observe command runs, are always major and cannot be disabled. The config is read from the base branch. The gate job never runs PR code. |
| Nothing checks that the diff stayed in scope. | The `scope` rule compares every changed path, including rename sources, and route budgets bound diff size. A scope can never be a catch-all glob. |
| Anyone with push access can write a commit status, including a same-repository PR workflow that grants itself `statuses: write`. And a status belongs to a commit, not a PR. | Post from a dedicated GitHub App whose key lives only in the `aidd-gate` environment. Pin the required check to that App. Post only for protected bases. When several protected-base PRs share a head, post the worst decision. Post `error` when the gate cannot finish. |
| The trusted gate installs itself at run time, so a moved tag or a compromised build dependency runs with the App token. | The reusable workflow runs aidd from its own commit (`job.workflow_sha`), with no build and nothing from a package index. It mints the App token just before the one step that uses it. |
| Commit authors that the platform cannot map to accounts hide who wrote the change. | Unlinked commit emails warn, or fail under audited, unless the platform itself blocks committers from approving. |
| Approvals can be forged or replayed: edited comments, quoted commands, short SHAs, stale reviews. | The gate ignores edited comments, and strips quotes, code blocks, and HTML comments. It requires full SHAs, and a review counts only on the head commit. Any Approver, specialist Approver, or path owner can block with a change request. |
| Nobody can tell which commits an agent wrote once it commits as a person. | Provenance reads three signals: the `Assisted-by:` trailer aidd asks for, the `Co-authored-by:` trailer most harnesses already add, and bot author accounts. aidd recognizes them from a baseline list: Claude, Copilot, Codex, Cursor, Gemini, and others. `assisted_by` must declare them all. |

## Risk and routing

| Failure mode | Decision |
| --- | --- |
| Routing by the agent's judgment alone. | Baseline path rules plus <!-- aidd:gen count:dimensions -->9<!-- aidd:end --> risk dimensions. The gate raises the route and requires the implied dimensions to be declared. `aidd gate --paths` shows the route before the first edit. |
| Route names nobody outside the tool understands. | The routes follow ITIL 4's three change types (standard, normal, emergency), with normal split by impact into minor, normal, and major. Change types are Conventional Commits types. Dimensions are plain words (data, security, privacy, financial, compliance, availability, third_party, cost, performance). A product manager, a change manager, and an engineer read the same Spec. |
| A freeze with no override, so an outage during a freeze cannot be fixed. | Only the emergency route passes a freeze. It needs a named commander who is a human Approver and not an author, smoke tests, and a review due within the SLA. |
| An unset or unreachable Policy fails open. | Profiles decide where Policy is required. An unreachable Policy, or `allow` with a non-zero exit, is deny. |
| Small changes drown in ceremony, so people route around the gate. | A minor change needs only a short Change Request block: `route`, `type`, `scope`, and `assisted_by`. `aidd describe` prints it. The changed paths are its scope, the repository suite is its evidence, and one approval merges it. |
| One activity under two names: autopilot's `spec.rework` ran Implement, while a separate `sweep` command answered review comments. | `/aidd-team:rework` is the one home of a rework, for Verify's and Review's failed reports, a listed person's requested changes, review comments, and failing checks, and `spec.rework` runs it. A command named by a metaphor never ships. |

## Scale

| Need | Decision |
| --- | --- |
| One-line fixes should not need planning documents. | Containers are optional. Minor and standard need no Spec file. |
| Many repositories must share a baseline that teams cannot quietly weaken. | `extends` presets pinned by sha256, or an org preset injected by the reusable workflow. Children only tighten, and reviewer pools, Policy, evidence source, and identity exemptions are locked. |
| Monorepos have many owners and many suites. | `owners.paths` per directory and `when_changed` tests. |
| Rollouts need a trial period. | Advisory mode reports on a separate status that never blocks. |
| Docs drift from code. | JSON Schemas and data files are the single source. Every table is generated and checked in CI (`aidd gen-docs --check`). |
| Product people, founders, and engineers need one method, not three. | The loop, the roles, and the vocabulary are the same for everyone. The profile and the team plugin change who does the work and who approves, never the steps. |

## Working style

| Failure mode | Decision |
| --- | --- |
| Agents assume instead of asking, and silently pick one reading of an ambiguous request. They never push back on a request that a smaller change would satisfy. | Clarify before the lane is chosen. Open questions go to the author. A question that could change the route keeps confidence low and stops the agent. The agent presents the readings of an ambiguous request, and names a simpler approach before a Spec exists. |
| Agents overbuild: speculative features, abstractions for single-use code, configurability nobody asked for, and drive-by edits to code they did not need to touch. So reviews grow, and diffs stop tracing to the request. | Minimum change is a hard rule of the skill and a review criterion. Every changed line traces to an Acceptance line or the Task. Refactors are their own change. Unrelated dead code is reported, not deleted. The scope and budget rules bound the where and the size; the rule and the reviewer bound the what. |
| Agent teams get expensive by default: the strongest model everywhere, every specialist on every change, transcripts as handoffs. | Priced to value is a principle and a contract rule. Each role carries a harness-neutral model tier that follows the cost of its mistakes. A specialist runs only when its start condition holds. A short note is the handoff, and a minor change runs one agent. Any extra cost needs a stated reason ([TEAM.md](TEAM.md#what-it-costs-and-when-it-is-worth-it)). |
| Agent tooling chases the newest technique, and a draft standard or a community skill gets applied as if it were settled. | Proven over new. Every registry entry carries a maturity, and the tables and packs show the emerging ones. The contract lets a role apply an emerging one only when the change clearly needs it, said in the Spec. Trendy restatements are attributed to their roots (YAGNI, KISS, small diffs, requirements clarification). |
| Standards lists go stale silently, and no static list covers every domain a team meets. | Every standard carries an edition and a checked date with the evidence read. An unversioned practice carries a reviewed date. `aidd eval standards` fails on a standard past its review cadence: emerging entries every 90 days, established ones every year, or its `review_due`. It also fails on one it cannot confirm: no source, no evidence, a bulk-edited date, a moved control ID. Each domain is a generated pack with executable checks. The loop contract's research-first rule covers a domain with no pack. |

The minimum-change rule is adapted from the Karpathy-inspired guidelines (MIT), which the `aidd-team` developer and reviewer cite.

## The loop, compared

How the loop in [METHOD.md §5](METHOD.md#5-the-loop) relates to Agile, why it is fast, and where it sits in the frameworks you already use.

### Agile, rewritten for agents

Agile assumed that writing code was the slow part and that people needed a cadence to stay in step. With agents, code takes minutes. What is slow is deciding what to build, proving it, and the human decisions in between. AIDD keeps Agile's principles (working software, small increments, continuous improvement, people over process) and drops every ceremony that would make an agent wait:

| Agile practice | In AIDD | Why it is faster with agents |
| --- | --- | --- |
| Fixed cadence | none: every change is its own increment, released when `aidd/gate` is green; the only cadence is Learn's retrospective | nothing waits for the end of a period |
| Estimation, story points, velocity | none: a Spec is sliced to its route's changed-line limit or split (INVEST Small); forecasts come from lead time and throughput in `aidd metrics` | sizes are cheap to measure and pointless to guess |
| Status meetings and reports | none: state is derived from the gate status and the last role's handoff note; `aidd metrics` shows what waits where | no meeting is faster than a status the gate already posts |
| Backlog refinement | Plan, only when the work is bigger than one Spec: an Initiative, Epics, and Spec stubs a human agrees to | just enough, just in time |
| Definition of Ready and Done | Spec approval (a validated Spec and its tests, approved by hash) and the end of Roll out (released and observed) | machine-checked, not a checklist in a wiki |
| Review of the increment | Merge approval on a ranked review report, then the observe window and the hypothesis result | the human reads findings, not a raw diff |
| Retrospective | Learn: on every signal and on a cadence, at most three measured improvements, through the same loop and the same gate | improvements become rules agents follow, not sticky notes |
| WIP limit | on human decisions, not on agents. Agents run every Task and change whose scope is disjoint. No Approver holds more open changes than they can decide today (three is a good default) | agents parallelize; human attention is the constraint |
| Pull system | an agent takes the next Task only when its dependencies have landed and its scope is free. When a human's queue is full, agents finish, split, or park instead of opening more | short queues mean short waits |
| Classes of service | the routes. Standard flows with no human, and minor with one Merge approval. Normal needs two decisions (Spec approval and Merge approval). Major needs the same two and, from the team profile up, a specialist Approver. Emergency expedites through a freeze | control proportional to risk, never uniform |

The measures that show a slowdown are in `aidd metrics`:

- the wait per approval (median and 90th percentile)
- the open changes waiting per approval
- time to first feedback
- flow efficiency
- the median time to a pass
- throughput

`aidd metrics --target-wait 1440` names the approvals whose median wait exceeds a day. An approval above target is the retrospective's first item. The usual fixes are a smaller Spec, a second Approver, or a standard-change class.

### Why it is fast

- **A change's route is a property of the change, not a step.** aidd computes the minimum from what it touches, the author may declare higher, and the gate enforces the higher of the two. The lane follows from the route. Asking the gate for the route before the first edit (`aidd gate --paths`) takes seconds and needs no meeting. The fast lane is the default, and the gate corrects a wrong route from the real diff. Which change to work on is a person's choice. `aidd list` shows the open work and who holds each step.
- **Humans decide twice, where it is cheapest.** The intent before any code (Spec approval) and the exact commit before merge (Merge approval). The fast lane skips Spec approval.
- **Verification is continuous, then explicit.** The guard checks scope at every edit made through the agent's edit tools. Tests run locally and in CI, and red-then-green proves the tests before anyone reviews code. Verify then re-runs the Spec's tests on the exact head a human will approve, so Review never reads a head nobody checked.
- **Batches stay small.** Route budgets keep a review to minutes, and Tasks with disjoint scope build in parallel. Branches stay short-lived: merge within a day, incomplete features behind flags, no more open changes per Approver than they can decide today. That is the small-batch practice DORA ties to delivery performance.
- **Status is the gate's report.** Pass, pending, or fail with the fix, so nobody asks where a change is.
- **Learning runs on a signal and on a cadence.** It lands as a change to the rules agents follow, through the same loop and the same gate as any other change.

### The same loop in the frameworks you know

| AIDD | DevOps loop | SDLC (ISO/IEC/IEEE 12207) | ITIL 4 change enablement | PDCA |
| --- | --- | --- | --- | --- |
| Plan, with the change's route from `aidd gate --paths` | Plan | Requirements | Request, assess (change type) | Plan |
| Specify + Spec approval | Plan | Requirements, design, test design | Assess, authorize the plan | Plan |
| Implement | Code, Build | Implementation | Implement | Do |
| Verify | Test | Verification | Test | Check |
| Review + Merge approval | Release approval | Verification sign-off | Authorize | Check |
| Publish + Roll out | Release, Deploy, Operate, Monitor | Deployment, maintenance | Implement, review | Do, Check |
| Learn | back to Plan, as a new change | Maintenance | Review and close | Act |

If a team already uses a Definition of Ready and a Definition of Done, Spec approval is the first. It means a Spec whose acceptance and tests exist and are approved. The end of Roll out is the second: released and observed. These two points give both definitions a machine-checked form instead of a checklist nobody re-reads.

## Notes on the method

The reasons behind some rules in [METHOD.md](METHOD.md), by the section they explain. METHOD.md links each one where it applies.

### Spec and its documents

From [METHOD.md §4.2](METHOD.md#42-spec):

- **The diagram first.** The Design section opens with one diagram of the change. With the diagram first, a human reads the change's shape before the words at Spec approval.
- **The Intent.** The body opens with the originator's own words. A reviewer can then check the Spec's reading of the request against the request itself.
- **No separate test plan by default.** Testing lives in the Spec's Acceptance and the tech spec's Test strategy. ISO/IEC/IEEE 29119-3 names information items, not files.

### Routes

From [METHOD.md §6](METHOD.md#6-routes). Why the route names follow ITIL 4: [Risk and routing](#risk-and-routing).

- `standard_changes` and `risk_rules` are ITIL change models: pre-assessed classes of change with a known route and known reviewers.
- A risk rule that names `dependencies` also matches each dependency the diff adds to a manifest. So a payment SDK or an auth library raises the route wherever the code that uses it sits.
- The minor route trusts its declaration: [Inherent to the model](#inherent-to-the-model).

### Evidence

From [METHOD.md §7](METHOD.md#7-evidence-and-the-gate) and [§14](METHOD.md#14-platform-bindings-and-trust):

- **A red run is never retried.** Red runs once, so a flaky test cannot pass for proof of new behavior.
- **A merge-queue entry is judged by its tree.** Its tree must be exactly the approved head merged into the entry's parent. So an entry can carry nothing that nobody approved, and lack nothing that they did.
- **The queue branch's name needs no trust.** The adapter reads the pull request and the entry's parent from it. Neither needs to be trusted: a wrong pull request or parent makes the trees differ, and the gate fails.
- **One head, one base.** The adapter refuses evidence while another pull request from the same branch at the same commit targets a different base. The reason: its runs would be indistinguishable.

### Approvals

From [METHOD.md §8](METHOD.md#8-approvals-and-separation-of-duties):

- **The Spec hash is over canonical JSON.** Because JSON escapes every character, no field can absorb another.
- **Two-party review under team.** One second person can be the Spec approval Approver, the Merge approval Approver, and the specialist Approver. That is by design: team is two-party review, not three. Use org or audited for more.
- **An agent's platform approval warns.** The gate never counts it, and warns when an agent or an unnamed bot approves on the platform. The reason: a branch rule's own review count may take that approval.

### Goals and trunk-based flow

From [METHOD.md §10.3](METHOD.md#103-goals-big-small-and-how-each-reaches-users) and [§10.4](METHOD.md#104-trunk-based-flow):

- **The person's four decisions.** What gets built and when users see it stay the person's; whether it is built right can be handed to a standing approval, and the gate still proves every change.
- **Trunk-based.** aidd follows DORA's trunk-based development capability: three or fewer active branches, each living hours rather than days and merged at least daily, with no code freezes and the tests run before each commit. A Spec branch is a small trunk of its own for its Tasks. That is spec-driven: the Spec is the contract, and the code reaches the trunk in small, tested steps.

### Learn

From [METHOD.md §12](METHOD.md#12-roll-out-and-learn):

- **A regression test for each incident.** After an emergency or a rollback, the lesson is a regression test that reproduces the failure. So every incident becomes a permanent check.
- **Agent evals are young.** Agent evals (`aidd eval routing`, `aidd eval roles`) are a young practice. Treat their scores as a trend to watch across releases, never as a certificate. Record them per model in the evals READMEs.

### Platform bindings

From [METHOD.md §14](METHOD.md#14-platform-bindings-and-trust):

- **A dedicated App posts the status.** Anyone with push access can write a commit status: [What counts as proof](#what-counts-as-proof).
- **The attest job is a caller job.** It is not part of the reusable workflow, because GitHub checks a reusable workflow's permissions even for the jobs it skips.

### Distribution

From [METHOD.md §15](METHOD.md#15-distribution-and-versioning): MCP tools, hooks, and skill folders are young formats (2024 and 2025). So the CLI, `AGENTS.md`, and the vendored skill are the stable path, and the agent tools are conveniences on top of it.

## Trade-offs

- **Python and YAML, with no dependencies.** A gate must install anywhere quickly and be auditable. aidd reads a strict YAML subset that every YAML reader reads the same way, with its own small reader, and a small JSON Schema subset validator keeps the package dependency-free. Reimplementations are welcome: the schemas and `examples/` define conformance.
- **A home-grown schema validator, held to the official test suite.** The mature library (`jsonschema`) needs a compiled dependency. So the validator is instead held to the official JSON Schema Test Suite for every keyword it supports. The glob matcher is held to a reference implementation under property tests. Both found real bugs when first run.
- **Not TypeScript.** Considered for the gate and rejected. The gate runs from a pinned commit with no build step, and a runtime with no package install is the point. Agent-side tooling in other languages can consume the same schemas.
- **Computed major.** Authors guessed the route and failed when they guessed low. Now they choose only whether a change needs a Spec. The gate raises a Spec to major from the real diff, the way CODEOWNERS routing works.
- **Tests, not "Checks".** An earlier draft called the proving commands Checks to distinguish them from a repository's test suite. Every reader already had a word for a command whose exit code proves behavior, and the invented one cost more than it clarified. The Spec's `tests` are tests. The repository suite is `tests` in the config. GitHub's check runs are `status_checks`.
- **Guide at edit time, decide at merge.** The MCP tools and the edit hook catch scope mistakes while the agent works, where they are cheapest. They run locally, so they guide; the gate still decides.
- **Reuse before reinvent.** aidd borrows CODEOWNERS, existing CI check runs, rulesets, required workflows, artifact attestations, Conventional Commits, and ITIL 4's change types (standard, normal, emergency). aidd adds what platforms lack: Spec-hash approval, red-then-green, scope, and assessment. It imports plans from Spec Kit, OpenSpec, and Kiro instead of competing with them.
- **Spec approval is enforced by hash, not by time.** Commit timestamps are forgeable, so the gate guarantees that what was approved is what lands. That the approval came *before* implementation is proven when the approval names its commit. The skill guides that order with a Spec-first draft PR, and the PR timeline shows it.
- **Test jobs stay untrusted.** Running tests means running the change's code. The design contains that risk instead of pretending it away. It uses a read-only token, no secrets, and evidence bound to the SHA. Any change to how the tests run needs human specialist approval.
- **Commit-author emails are not identities on GitLab.** Its commit API has no usernames. The adapter relies on MR-author separation of duties plus GitLab's own "prevent approvals by users who add commits" setting.
- **One developer for application, AI, and data work.** An ML engineer and a data engineer were each the developer plus a preloaded pack and a few done lines. A specialty is the context a Task loads in its `skills`, not a separate accountability, so fewer roles pass (priced to value). When a Task loads `ai-evals`, `ai-features`, `schema-migration`, or a data pack, the developer's done line adds the measured evals, the reversible migration, and the idempotent backfill. The SRE stays apart from the developer because CI and infrastructure are protected paths and its write area is a least-privilege control. The verifier and the reviewer stay apart because they are two checks: one runs the change against its Acceptance, and one reads the diff against the Spec. 1.0.0 carries no compatibility shim for the removed roles.
- **One QA role: the verifier writes the tests and runs the change.** The owner chose one QA-shaped role over two. The tester and the verifier shared the Acceptance, the test commands, and the same skills, and a second role cost its own agent file and preload. The tests freeze at Spec approval, so in Verify the guard already denies a change to them. The verifier's write area is the old tester's test paths plus its own git-ignored preview files under `.aidd/evidence/preview/`, with no step switch. The trade-off is that the Verify check is no longer independent of the tests' author. What stays apart is this. The verifier never writes the code, and the developer never writes the spec-lane tests. The Verify run is a fresh session that reads the Acceptance and runs the built change, not only its own tests. The reviewer stays the separate check of the code.
- **One SRE for delivery infrastructure and reliability.** In many teams one SRE or operations function owns both the pipelines and the infrastructure and the reliability of what runs on them. The platform engineer's CI, infrastructure, and rollout work now sits with the SRE, who already planned observe and rollback and ran the incidents. The merge loses no independent check, because the reviewer, the verifier, and Merge approval still read every change. The least-privilege split from the developer stays: the developer cannot write CI or infrastructure, and the SRE writes them only inside a Task's scope, with a person's specialist approval on protected paths.

## Known limits in 1.0.0

Each limit sits in one of four groups:

- what no tool in aidd's place could close
- what the platform decides
- what has not yet run for real
- what aidd holds back from on purpose

### Inherent to the model

- Evidence is as honest as the code under test. A malicious change to tests, build scripts, or dependencies can make its own tests lie. Code that leaves the test's process group can rewrite evidence. Killing each test's process group when the test exits is hygiene, not containment: the job runs the change's code, which can write anything the job can, including its own evidence. The human reviews at Spec approval and Merge approval are the control for these risks.
  - Spec approval freezes only the files under `tests.files`. When a Spec-backed change edits a file that configures or runs the tests, and `tests.files` leaves that file out, the gate warns `tests.setup_unfrozen`. Such files include a `conftest.py`, `pytest.ini`, a jest or vitest config, and a script a test command names. The gate cannot see settings inside `pyproject.toml` or `package.json`.
- Inline Change Request blocks (minor, standard, emergency) declare their own scope, or take their changed paths. Their scope and tests are the agent's word: nothing approves that scope before the diff. The assessment from the real paths and the Merge approval review are the controls.
- The guard checks the editor tools (Edit, Write) and the shell writes it can read, such as redirects, `tee`, `sed -i`, `cp`, `mv`, `git apply`, and `patch`. For a writer it holds, it denies a command that runs code it cannot read. It follows `sh -c`, `eval`, reserved words, and the programs that run commands, such as `xargs` and `find -exec`, and denies a command substitution where a command starts. It reads a substitution anywhere else as a command run in a folder it does not know. It keeps each word's quoting from the line's own text, never a child shell's, so a quoted word is exact. Where it cannot be exact, it fails closed, and SECURITY.md lists the plain forms that work.
  - Two kinds of write are out of its reach. A program that writes by itself, such as a Python script, an interpreter, a build tool, or a package manager, writes what the guard never sees. A command that the guard's parser reads differently from bash can also hide a write.
  - A program the agent runs can still change the always-on rules' files and refs on this machine. aidd shows each change with your next decision, which takes it in. A dialog lists it before you answer, and aidd's note after a typed decision lists it, with how to put each back. Claude Code shows you that list directly. A change that weakens the guard waits for a dialog that shows it exactly, so typed words never loosen the guard. An agent's `aidd land`, `aidd approve`, or `aidd publish` after a change stops until you say your words again. aidd never asks about a change on its own, since that question is one more stop with no more safety. A program that also rewrites aidd's state in the git directory can still hide its change, so the gate in CI, on a clean checkout, and signed approvals are the controls.
  - When the agent stops, the stop hook replays the guard over every path the branch changed. Once Spec approval holds, the hook names each path that the guard would have denied. Such a path is a frozen test, design file, or doc, a path outside the scope, or a protected path. The stop hook reminds at the default hook level, and blocks the stop once at strict.
  - So the guard shortens the time to the failure without making it a boundary: the gate's scope rule, on the real diff, still decides.
- Autopilot trusts the local machine. Its checks resist edits to the working tree and to the branch's content. A local writer of git refs or `.git/config` is out of their scope, such as one that moves the local base branch, and the trusted base config with it. An agent with a shell can already do that, so the gate in CI, on a clean checkout, is the control for merges ([SECURITY.md](../SECURITY.md#data-handling)).
  - An agent runs as the same user as the person, so a local approval is only as strong as that person's terminal. `aidd approve spec` asks for the person at a terminal, and signing narrows it further.
- Carrying approvals on GitLab is experimental. `aidd publish` posts the person's recorded Spec approvals on the pull request or merge request, as them, with their own token. On GitLab that's built against a faked API, not yet run against a production instance. Merge approval stays the person's own approval there.
- A protected base with a local trunk publishes as one pull request (`aidd publish --pr`). The platform's gate judges that batch as one change, so a team on a protected base does better with a platform trunk: publish each branch.
- `stop approving` can't turn off an auto-merge while GitHub is unreachable, or one another account turned on. It names each one it couldn't, and you turn it off on the pull request.
- Local-first approvals (`aidd approve`, `aidd land`) are weaker than a platform's. The agent runs as the same user as the person, so the terminal check, the guard hook, and commit signing are friction, not a boundary. Push to a platform when the work matters to other people ([METHOD.md §8](METHOD.md#local-approvals)).
  - With `gates.local_approvals: signed`, a local approval counts only with an SSH signature from a key in the signers file that `gates.local_signers` names. aidd reads the file from the base branch's tip, never from the working tree or this machine's git config. An agent that holds the person's key still defeats the signature check.
  - The confirmation is one yes or no question. An earlier version asked the person to type back a one-time code, which an agent that drives a terminal cannot type ahead of time. It cost every person a step on every decision, and it stopped only an agent that already got past the guard, which could write the decision record itself. So the question is plain, and other controls hold. The guard denies the known ways to start or type into another terminal, even through quoting: tmux, screen, zellij, Orca, `osascript`, `xdotool`, terminal emulators. A signing key that asks for the person's presence makes an approval theirs alone.
  - In Claude Code, the `aidd-mods` plugin takes a Spec approval from a prompt the person typed (`approve SPEC-1`) and a choice in Claude Code's own dialog. The engine stamps a prompt typed at the terminal, so a prompt a plugin or an agent sent never counts, and the model sees neither the prompt nor the answer. The record names where it was confirmed.
- Under solo, an agent holding the author's own credentials (a personal `gh` token) can post `/aidd approve-merge <sha>` as the author. An approval line that an App posts on a person's behalf never counts. GitHub marks it `performed_via_github_app`, and the gate warns `merge_approval.via_app` or `spec_approval.via_app`. In Claude Code, the aidd plugin's Bash hook denies approve and merge commands, and comment bodies holding `/aidd approve`. Give agents their own bot account (listed in `identities.bots`, which never approves). Keep a manual "ready for review" as friction.
- Observe blocks are recorded and required, and aidd never rolls back. `aidd observe specs/<ID>.md --window spec` polls the observe command until the window ends. It exits 1 as soon as the rollback trigger fires, and 2 on a usage error. So the rollback is one line of your release script: `aidd observe specs/<ID>.md --window spec; [ $? -ne 1 ] || <your rollback>`.
- The gate proves what a repository can prove. Work that never becomes a commit (a strategy, a campaign, a contract) can run the same loop with the same human approvals. But no `aidd/gate` decides it.

### Depends on the platform

- The gate blocks nothing by itself. It blocks a merge only in enforce mode, as a check the platform requires, from a status source pinned to its App. A private repository on GitHub Free cannot require the check, so there the gate stays advisory ([PLATFORMS.md](PLATFORMS.md#what-holds-without-the-full-setup)).
- Gate runs queue per head commit. The reusable workflow's concurrency group is the commit the run judges. So two runs for one head never post out of order. Two such runs come, for example, from pull requests that share the head, or from a push and a review. GitHub keeps one waiting run per group, and a newer event replaces it. That is safe, because every run reads the current state.
- On GitLab, an approval is a system note that names no commit, so it binds to a head by time. It counts only when it came after the pipeline for that head was created. Keep "Remove all approvals when commits are added" on. The gate reads the project setting, and warns `merge_approval.survives_push` when the setting is off. A new target branch, set by a person or by GitLab, voids every approval given before it, as a retarget does on GitHub.
- Merge queues work on GitHub, with limits ([PLATFORMS.md](PLATFORMS.md#merge-queues)):
  - An entry passes only when its commit's tree equals what `git merge-tree` makes of the approved head and the entry's parent. So a queue whose merge differs from git's fails closed and needs a re-queue, as with a rename that git detects differently.
  - An entry stacked on another passes only once the gate reads, from rulesets, that the queue merges all-green groups. So a queue configured outside a ruleset builds one entry at a time, or fails its stacked entries.
- GitLab merge trains are experimental, and judged as queue entries are ([PLATFORMS.md](PLATFORMS.md#merge-trains)). An entry's first-parent chain holds the commit it was built on, so the gate takes the newest commit on it whose merge with the approved head gives the entry's tree. Newest first, an entry names the same parent before and after the entry ahead merges. A train whose merge differs from git's fails closed, and the person adds the merge request to the train again. In a train pipeline, an approval binds to the head by the head's diff version, because the pipeline starts after the approvals.
- GitHub offers artifact attestations on public repositories, and on private or internal ones only with GitHub Enterprise Cloud. Elsewhere leave the change record's `attest` job off: the record stays unsigned, and the commit status and the run log remain the anchors.
- Red runs need the test tooling available at the base commit. The CI templates run red in place to reuse installed dependencies.

### Not yet exercised

- The GitHub flow, merge queues included, has not yet run on a live repository. [Release status](ENTERPRISE.md#1-release-status-and-maturity) says what the 1.0.0 tag waits on.
- The GitLab adapter is experimental. It is tested end to end against a real git repository and a faked GitLab API, not yet against a production instance.
- Autopilot's real runs were in Claude Code, Codex, and OpenCode, each on one small repository ([Real runs](AUTOPILOT.md#real-runs)). In OpenCode, the guard denies the run's start until aidd's plugin passes the session to its shell hook. Grok Build and Google Antigravity run it as `/aidd-autopilot`, not yet tried with real models. Its tests drive fixture repositories with scripted notes in place of agents. Another agent runs its steps by hand with `aidd autopilot next`.
- The role evals were not run again with real models after the agent files changed.
- No eval baselines are published. The routing and role evals come with scenarios and scorers. The scheduled workflow runs them only where an API key is set. Run them against your own agents, and keep your own scores.
- No release is signed or published yet. The release workflow refuses a private repository, because artifact attestations need a public one or GitHub Enterprise Cloud ([RELEASING.md](../RELEASING.md#the-first-public-release)).

### Bounded on purpose

- A red run proves new behavior only when a test failed. For pytest, exits 3 to 5 (an internal error, a usage error, no tests collected) are no proof (`red_green.red_not_assertion`). Exit 2, a collection error such as importing a module that does not exist yet, stays red. Other runners keep every non-zero exit except 126 and 127.
- An App-posted approval never counts, even when the person really did use an App to post it: they post the line again themselves.
- Test configuration outside `tests.files` only warns. The list of files that configure tests is a guess by name, and a false alarm must not block a merge.
- The stop hook names forbidden changes only after Spec approval, and reads at most 500 changed paths to stay inside a hook's time limit. At strict it blocks a stop once, never again while a stop hook keeps the agent going. So it cannot trap an agent in a loop.
- A glob pattern longer than 512 characters is refused: the gate errors on it and fails closed. Matching is linear in the pattern and the path, so no pattern can stall the gate.
