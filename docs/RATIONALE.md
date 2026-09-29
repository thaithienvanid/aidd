# Design rationale

Why aidd works the way it does. Each row pairs a failure mode of agent-driven development with the decision that closes it. The requirements themselves are in [METHOD.md](METHOD.md); this page explains them and owns the list of [known limits](#known-limits-in-100). The security rows are backed by regression tests (`tests/test_redteam.py`, `tests/test_security_hardening.py`, `tests/test_security_integrity.py`, `tests/test_gate_rules.py`), and by a mutation in `examples/` where another verifier can replay the case.

## Who decides

| Failure mode | Decision |
| --- | --- |
| Rules written as prose that the controlled agent is asked to follow, with the agent reporting its own results. | The agent proposes; the verifier decides. The `toml aidd` block only *declares* scope and intent. Diff, evidence, identities, approvals, and Policy are *derived* from the platform by a function of those facts alone, which posts a required status. |
| The only human approval is after the build, when the code already exists and review becomes rubber-stamping. | Spec approval happens before implementation on normal and major (on major only, under solo). It binds the exact Spec and tests that ship by a hash of their content, so an edit to either voids the approval. |
| Agents commit as the person who runs them, so author-based separation of duties is meaningless, and solo developers can never pass. | Separation of duties is measured against the *authors* (PR/MR author, commit authors, committers) and agent accounts. The solo profile waives that rule for one person and loosens a few others (Spec approval on major only, red-then-green as a warning): the Approver must still be in `owners.approvers`, the waiver is recorded, and major changes get a cool-off ([METHOD.md §8](METHOD.md#solo)). |
| One "security reviewer" role has to judge data, privacy, money, and compliance changes it knows nothing about. | Specialist reviewer pools: each major dimension names the pool that reviews it (`data`, `security`, `privacy`, `finance`, `compliance`), a risk rule can name its own, and an unbound pool falls back to `security`, so the smallest team still has one specialist. |
| Every change needs a human, even bot patch bumps. | Standard changes: configured classes merge on green tests, never on protected paths, never under regulated, and only with verified signatures. |

## What counts as proof

| Failure mode | Decision |
| --- | --- |
| The implementer writes and edits the test that grades it. | Tests are written in Specify and frozen by the Spec hash. A Task's `scope` may not cover a test file. New behavior must be red on base and green on head. |
| Evidence not bound to a commit or a change, or produced by a workflow the PR controls. | Evidence records the head and base SHAs. The gate reads it only from the configured test workflow's runs of the change's own branch, and refuses it while another PR from that branch at that commit targets a different base. The test action runs aidd from its pinned ref, and changing that ref is a protected change. |
| A change edits the gate's config, CI, CODEOWNERS, agent instructions, or hooks. | The built-in protected paths, plus every file a bound Policy or Observe command runs, are always major and cannot be disabled. The config is read from the base branch. The gate job never runs PR code. |
| Nothing checks that the diff stayed in scope. | The `scope` rule compares every changed path, including rename sources, and route budgets bound diff size. A scope can never be a catch-all glob. |
| A commit status can be written by anyone with push access, and belongs to a commit, not a PR. | Post from a dedicated GitHub App whose key lives only in the `aidd-gate` environment, pin the required check to that App, post only for protected bases, post the worst decision when a head is shared by several protected-base PRs, and post `error` when the gate cannot finish. |
| The trusted gate installs itself at run time, so a moved tag or a compromised build dependency runs with the App token. | The reusable workflow runs aidd from its own commit (`job.workflow_sha`), with no build and nothing from a package index, and mints the App token just before the one step that uses it. |
| Commit authors that the platform cannot map to accounts hide who wrote the change. | Unlinked commit emails warn, or fail under regulated, unless the platform itself blocks committers from approving. |
| Approvals can be forged or replayed: edited comments, quoted commands, short SHAs, stale reviews. | Edited comments are ignored, quotes, code blocks, and HTML comments are stripped, full SHAs are required, a review counts only on the head commit, and any Approver, specialist reviewer, or path owner can block with a change request. |
| Nobody can tell which commits an agent wrote once it commits as a person. | Provenance reads three signals: the `Assisted-by:` trailer aidd asks for, the `Co-authored-by:` trailer most harnesses already add (Claude, Copilot, Codex, Cursor, Gemini, and others, from a baseline list), and bot author accounts. `assisted_by` must declare them all. |

## Risk and routing

| Failure mode | Decision |
| --- | --- |
| Routing by the agent's judgment alone. | Baseline path rules plus eight risk dimensions. The verifier raises the route and requires the implied dimensions to be declared; `aidd next` shows the minimum. |
| Route names nobody outside the tool understands. | The routes are ITIL change types (standard, minor, normal, major, emergency); change types are Conventional Commits types; dimensions are plain words (data, security, privacy, financial, compliance, availability, third_party, cost). A product manager, a change manager, and an engineer read the same Spec. |
| A freeze with no override, so an outage during a freeze cannot be fixed. | Only the emergency route passes a freeze, with a named commander who is a human Approver and not an author, smoke tests, and a review due within the SLA. |
| An unset or unreachable Policy fails open. | Profiles decide where Policy is required. An unreachable Policy, or `allow` with a non-zero exit, is deny. |
| Small changes drown in ceremony, so people route around the gate. | A minor change needs only a short `toml aidd` block (`aidd change` prints it: `route`, `type`, `scope`, and `assisted_by`); the changed paths are its scope, the repository suite is its evidence, and one approval ships it. |

## Scale

| Need | Decision |
| --- | --- |
| One-line fixes should not need planning documents. | Containers are optional. Minor and standard need no Spec file. |
| Many repositories must share a baseline that teams cannot quietly weaken. | `extends` presets pinned by sha256, or an org preset injected by the reusable workflow. Children only tighten, and reviewer pools, Policy, evidence source, and identity exemptions are locked. |
| Monorepos have many owners and many suites. | `owners.paths` per directory and `when_changed` tests. |
| Rollouts need a trial period. | Advisory mode reports on a separate status that never blocks. |
| Docs drift from code. | JSON Schemas and data files are the single source; every table is generated and checked in CI (`aidd gen-docs --check`). |
| Product people, founders, and engineers need one method, not three. | The loop, the roles, and the vocabulary are the same for everyone; the profile and the team plugin change who does the work and who approves, never the steps. |

## Working style

| Failure mode | Decision |
| --- | --- |
| Agents assume instead of asking, pick one reading of an ambiguous request silently, and never push back on a request that a smaller change would satisfy. | Clarify before the lane is chosen, as the entry rule's precondition: open questions go to the author, a question that could change the route keeps confidence low and stops the agent, the readings of an ambiguous request are presented, and a simpler approach is named before a Spec exists. |
| Agents overbuild: speculative features, abstractions for single-use code, configurability nobody asked for, and drive-by edits to code they did not need to touch, so reviews grow and diffs stop tracing to the request. | Minimum change is a hard rule of the skill and a review criterion: every changed line traces to an Acceptance line or the Task, refactors are their own change, and unrelated dead code is reported, not deleted. The scope and budget rules bound the where and the size; the rule and the reviewer bound the what. |
| Agent teams get expensive by default: the strongest model everywhere, every specialist on every change, transcripts as handoffs. | Priced to value is a principle and a contract rule: each role carries a harness-neutral model tier that follows the cost of its mistakes, a specialist runs only when its start condition holds, a four-line note is the handoff, a minor change runs one agent, and any extra cost needs a stated reason ([TEAM.md](TEAM.md#what-it-costs-and-when-it-is-worth-it)). |
| Agent tooling chases the newest technique, and a draft standard or a community skill gets applied as if it were settled. | Proven over new: every registry entry carries a maturity, the tables and packs show the emerging ones, and the contract lets a role apply one only when the change clearly needs it, said in the Spec. Trendy restatements are attributed to their roots (YAGNI, KISS, small diffs, requirements clarification). |
| Standards lists go stale silently, and no static list covers every domain a team meets. | Every standard carries an edition and a checked date with the evidence read (an unversioned practice a reviewed date), `aidd eval standards` fails on one older than a year, each domain is a generated pack with executable checks, and the loop contract's research-first rule covers a domain with no pack. |

The minimum-change rule is adapted from the Karpathy-inspired guidelines (MIT), which the `aidd-team` developer and reviewer cite.

## The loop, compared

How the loop in [METHOD.md §5](METHOD.md#5-the-loop) relates to Agile, why it is fast, and where it sits in the frameworks you already use.

### Agile, rewritten for agents

Agile assumed that writing code was the slow part and that people needed a cadence to stay in step. With agents, code takes minutes; what is slow is deciding what to build, proving it, and the human decisions in between. AIDD keeps Agile's principles (working software, small increments, continuous improvement, people over process) and drops every ceremony that would make an agent wait:

| Agile practice | In AIDD | Why it is faster with agents |
| --- | --- | --- |
| Sprint | none: every change is its own increment, released when `aidd/gate` is green; the only cadence is Learn's retrospective | nothing waits for a sprint boundary |
| Estimation, story points, velocity | none: a Spec is sliced to its route budget or split (INVEST Small); forecasts come from lead time and throughput in `aidd metrics` | sizes are cheap to measure and pointless to guess |
| Daily standup, status reports | none: state is derived from the gate status and the last role's handoff note; `aidd metrics` shows what waits where | no meeting is faster than a status the gate already posts |
| Backlog refinement | Plan, only when the work is bigger than one Spec: an Initiative, Epics, and Spec stubs a human agrees to | just enough, just in time |
| Definition of Ready and Done | Spec approval (a validated Spec and its tests, approved by hash) and the end of Ship (released and observed) | machine-checked, not a checklist in a wiki |
| Sprint review | Merge approval on a ranked review report, then the observe window and the hypothesis result | the human reads findings, not a raw diff |
| Retrospective | Learn: on every signal and on a cadence, at most three measured improvements, through the same loop and the same gate | improvements become rules agents follow, not sticky notes |
| WIP limit | on human decisions, not on agents: agents run every Task and change whose scope is disjoint; no Approver holds more open changes than they can decide today (three is a good default) | agents parallelize; human attention is the constraint |
| Pull system | an agent takes the next Task only when its dependencies have landed and its scope is free; when a human's queue is full, agents finish, split, or park instead of opening more | short queues mean short waits |
| Classes of service | the routes: standard flows with no human, minor with one Merge approval, normal with two decisions (Spec approval and Merge approval), major with the same two and a specialist reviewer, emergency expedites through a freeze | control proportional to risk, never uniform |

The measures that show a slowdown are in `aidd metrics`: the wait per approval (median and 90th percentile), the open changes waiting per approval, time to first feedback, flow efficiency, the median time to a pass, and throughput; `aidd metrics --target-wait 1440` names the approvals whose median wait exceeds a day. An approval above target is the retrospective's first item, and the usual fixes are a smaller Spec, a second Approver, or a standard-change class.

### Why it is fast

- **The route is computed, not a step.** Every change enters the loop through `aidd next`, which takes seconds and needs no meeting; the fast lane is the default, the lane is chosen once, and the gate corrects a wrong choice from the real diff.
- **Humans decide twice, where it is cheapest.** The intent before any code (Spec approval) and the exact commit before merge (Merge approval). The fast lane skips Spec approval.
- **Verification is continuous, then explicit.** The edit-time guard checks scope at every edit made through the agent's edit tools, tests run locally and in CI, and red-then-green proves the tests before anyone reviews code. Verify then re-runs the Spec's tests on the exact head a human will approve, so Review never reads a head nobody checked.
- **Batches stay small.** Route budgets keep a review to minutes, Tasks with disjoint scope build in parallel, and branches stay short-lived (merge within a day, incomplete features behind flags, no more open changes per Approver than they can decide today). That is the small-batch practice DORA ties to delivery performance.
- **Status is the gate's report.** Pass, pending, or fail with the fix, so nobody asks where a change is.
- **Learning runs on a signal and on a cadence.** It lands as a change to the rules agents follow, through the same loop and the same gate as any other change.

### The same loop in the frameworks you know

| AIDD | DevOps loop | SDLC (ISO/IEC/IEEE 12207) | ITIL 4 change enablement | PDCA |
| --- | --- | --- | --- | --- |
| Entry rule: `aidd next` (not a step) | Plan | Requirements | Assess (change type) | Plan |
| Plan | Plan | Requirements | Request | Plan |
| Specify + Spec approval | Plan | Requirements, design, test design | Assess, authorize the plan | Plan |
| Implement | Code, Build | Implementation | Implement | Do |
| Verify | Test | Verification | Test | Check |
| Review + Merge approval | Release approval | Verification sign-off | Authorize | Check |
| Ship | Release, Deploy, Operate, Monitor | Deployment, maintenance | Implement, review | Do, Check |
| Learn | back to Plan, as a new change | Maintenance | Review and close | Act |

Where a team already uses a Definition of Ready and a Definition of Done, Spec approval is the first — a Spec whose acceptance and tests exist and are approved — and the end of Ship is the second: released and observed. These two points give both definitions a machine-checked form instead of a checklist nobody re-reads.

## Trade-offs

- **Python and TOML, with no dependencies.** A gate must install anywhere quickly and be auditable. Python 3.11+ ships `tomllib`, and a small JSON Schema subset validator keeps the package dependency-free. Reimplementations are welcome: the schemas and `examples/` define conformance.
- **A home-grown schema validator, held to the official test suite.** The mature library (`jsonschema`) needs a compiled dependency, so the validator is instead held to the official JSON Schema Test Suite for every keyword it supports, and the glob matcher to a reference implementation under property tests. Both found real bugs when first run.
- **Not TypeScript.** Considered for the verifier and rejected: the gate runs from a pinned commit with no build step, and a runtime with no package install is the point; agent-side tooling in other languages can consume the same schemas.
- **Computed major.** Authors guessed the route and failed when they guessed low. Now they choose only whether a change needs a Spec; the gate raises a Spec to major from the real diff, the way CODEOWNERS routing works.
- **Tests, not "Checks".** An earlier draft called the proving commands Checks to distinguish them from a repository's test suite. Every reader already had a word for a command whose exit code proves behavior, and the invented one cost more than it clarified. The Spec's `tests` are tests; the repository suite is `[[tests]]` in the config; GitHub's check runs are `status_checks`.
- **Guide at edit time, decide at merge.** The MCP tools and the edit hook catch scope mistakes while the agent works, where they are cheapest. They run locally, so they guide; the gate still decides.
- **Reuse before reinvent.** CODEOWNERS, existing CI check runs, rulesets, required workflows, artifact attestations, Conventional Commits, and ITIL's change types are borrowed. aidd adds what platforms lack (Spec-hash approval, red-then-green, scope, assessment) and imports plans from Spec Kit, OpenSpec, and Kiro instead of competing with them.
- **Spec approval is enforced by hash, not by time.** Commit timestamps are forgeable, so the verifier guarantees that what was approved is what ships. That approval came *before* implementation is proven when the approval names its commit, guided by the skill (a Spec-first draft PR), and visible in the PR timeline.
- **Test jobs stay untrusted.** Running tests means running the change's code. The design contains that risk instead of pretending it away: a read-only token, no secrets, evidence bound to the SHA, and human specialist review for any change to how the tests run.
- **Commit-author emails are not identities on GitLab.** Its commit API has no usernames. The adapter relies on MR-author separation of duties plus GitLab's own "prevent approvals by users who add commits" setting.

## Known limits in 1.0.0

- Evidence is as honest as the code under test. A malicious change to tests, build scripts, or dependencies can make its own tests lie, and code that leaves the test's process group can rewrite evidence; the human reviews at Spec approval and Merge approval are the control for that. Only files under `tests.files` are frozen by Spec approval, so list the test configuration and scripts the tests run through there.
- Inline blocks (minor, standard, emergency) declare their own scope, or take their changed paths; nothing approves it before the diff. The assessment from the real paths and the Merge approval review are the controls.
- Merge queues work on GitHub, with limits ([PLATFORMS.md](PLATFORMS.md#merge-queues)):
  - An entry passes only when its commit's tree equals what `git merge-tree` makes of the approved head and the entry's parent, so a queue whose merge differs from git's (a rename git detects differently) fails closed and needs a re-queue.
  - An entry stacked on another passes only once the gate reads, from rulesets, that the queue merges all-green groups: a queue configured outside a ruleset builds one entry at a time or fails its stacked entries.
  - The queue flow, like the rest of the GitHub flow, has not yet run on a live repository.
  - GitLab merge trains are not supported: turn them off on gated branches.
- The solo cool-off is measured from the head commit's earliest check suite on the pull request's branch (the pipeline's creation on GitLab); on a platform, never from a commit date. Locally there is no platform time, so it starts at the head commit's committer date, which the committer sets: a reminder, not a control. A determined solo developer can still wait it out. It is a second look, not a control against yourself ([METHOD.md §8](METHOD.md#solo)).
- Observe blocks are recorded and required. `aidd observe --window` polls the observe command until the window ends and says when the rollback trigger fires, but it never rolls back: your release tooling, or a person, does.
- The GitLab adapter is experimental: tested end to end against a real git repository and a faked GitLab API, not yet exercised against a production instance.
- Under solo, an agent holding the author's credentials (a `gh` token) could post `/aidd approve <sha>` as the author. In Claude Code, the aidd plugin's Bash hook denies approve and merge commands and comment bodies holding `/aidd approve`; other harnesses have only the skill's instruction. Give agents their own bot account (listed in `identities.bots`, which never approves), and keep the cool-off and a manual "ready for review" as friction.
- Local-first approvals (`aidd approve`, `aidd ship`) are weaker than a platform's. The agent runs as the same user as the person, so the terminal check, the edit-time hook, and commit signing are friction, not a boundary. Push to a platform when the work matters to other people ([METHOD.md §8](METHOD.md#local-approvals)).
  - With `gates.local_approvals = "signed"`, only approvals with a good signature from a trusted key count; an agent that holds the person's keys still defeats it.
  - The confirmation asks for a one-time code the agent cannot know in advance, and the guard denies the known ways to start or type into another terminal (tmux, screen, zellij, Orca, `osascript`, `xdotool`, terminal emulators), even through quoting; an agent that can both read a terminal and type into it by some other means still defeats it.
- The edit-time guard checks the editor tools (Edit, Write) and, best-effort, obvious shell writes (redirects, `tee`, `sed -i`, `cp`, `mv`, `git apply`, `patch`). A write through an interpreter or a build tool is not seen, so per-role write areas and Task scopes guide an agent that edits that way rather than bind it. That only delays the failure: the gate's scope rule still sees the diff.
- On GitLab, an approval binds to the head by time (it must come after the pipeline for that head was created), not by the SHA the Approver saw, and retargeting a merge request to another branch does not yet void earlier approvals (GitHub does both).
- Two pull requests that share one head commit are evaluated by separate runs; if they race, the last run to post decides the shared status until the next event re-runs both.
- The GitHub flow has not yet run on a live repository; the first real pull request through this repository's own gate is the release criterion.
- The routing and role evals ship scenarios and scorers, but no published baseline per model; the scheduled workflow runs them only where an API key is set. Run them against your own agents and record the scores.
- A glob pattern longer than 512 characters is refused: the gate errors on it and fails closed. Matching is linear in the pattern and the path, so no pattern can stall the gate.
- Red runs need the test tooling available at the base commit. The CI templates run red in place to reuse installed dependencies.
- The gate proves what a repository can prove. Work that never becomes a commit (a strategy, a campaign, a contract) can run the same loop with the same human approvals, but no `aidd/gate` decides it.
