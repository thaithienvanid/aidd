# FAQ

- [Does it work for a brand-new project, or only existing code?](#does-it-work-for-a-brand-new-project-or-only-existing-code)
- [Isn't this a lot of process for small changes?](#process)
- [Do we still run sprints, estimate, and stand up?](#agile)
- [I work alone. Who approves?](#solo)
- [My agent commits as me. Doesn't that break separation of duties?](#my-agent-commits-as-me-doesnt-that-break-separation-of-duties)
- [What about Dependabot and Renovate?](#bots)
- [What if we have no tests?](#what-if-we-have-no-tests)
- [Can the agent just edit the test until it passes?](#can-the-agent-just-edit-the-test-until-it-passes)
- [Can the agent edit the gate's config or the CI workflow?](#can-the-agent-edit-the-gates-config-or-the-ci-workflow)
- [What if production is down during a freeze?](#what-if-production-is-down-during-a-freeze)
- [Can we keep GitHub Spec Kit, OpenSpec, or Kiro?](#can-we-keep-github-spec-kit-openspec-or-kiro)
- [Can we keep Jira or Linear?](#can-we-keep-jira-or-linear)
- [Does it lock us into Claude, GitHub, or Python?](#does-it-lock-us-into-claude-github-or-python)
- [Do we need GitHub, Jira, or any other service?](#services)
- [Does it work in a monorepo?](#does-it-work-in-a-monorepo)
- [How does an agent know the best practice for a task?](#how-does-an-agent-know-the-best-practice-for-a-task)
- [How do we know it works?](#how-do-we-know-it-works)
- [What doesn't it do?](#limits)
- [What exactly does the gate stop?](#what-exactly-does-the-gate-stop)
- [Why diagrams as text, and not a design tool?](#why-diagrams-as-text-and-not-a-design-tool)
- [Is it ready for an enterprise?](#is-it-ready-for-an-enterprise)
- [What does it cost?](#what-does-it-cost)
- [Why TOML and not YAML?](#why-toml-and-not-yaml)
- [Can our org change the rules?](#can-our-org-change-the-rules)
- [How do I remove it?](#uninstall)

## Does it work for a brand-new project, or only existing code?

Both. In a new repository, the first commit (Day 0) holds the aidd setup and the project scaffold, and the first Spec brings the test runner and a first test that fails on the empty base, as a new test should. In an existing codebase, start in advisory mode, tell the config where the sensitive paths and owners are (`risk_rules`, `owners.paths`), and pin current behavior with a test where none exists. [Adoption](ADOPTION.md#new-or-existing-repository) compares the two.

<a id="process"></a>
## Isn't this a lot of process for small changes?

No. Minor changes need no Spec file: a short inline block (`aidd change` prints it), your existing test suite, and one approval. Standard changes, such as bot patch bumps, need no human at all. Ceremony grows only with risk.

<a id="agile"></a>
## Do we still run sprints, estimate, and stand up?

No. Every change is its own increment and ships when the gate is green. A Spec is sized to its route budget instead of estimated. The gate status plus the last handoff note are the status, so there is no standup.

What stays is what Agile was for: small increments, working software as the measure, and a retrospective that changes the rules. The one limit on work in progress is on humans, not agents: no Approver holds more open changes than they can decide today. The practice-by-practice mapping is in [RATIONALE.md: Agile, rewritten for agents](RATIONALE.md#agile-rewritten-for-agents).

<a id="solo"></a>
## I work alone. Who approves?

You, under the `solo` profile, with your own handle in `owners.approvers`. Solo is looser than `team` in a few deliberate ways:

- you may approve your own change, and the record says so (`waived_solo`)
- Spec approval is required on major changes only, and a major change waits 30 minutes after the platform first sees its head commit before your approval counts (the cool-off)
- red-then-green is a warning rather than a failure, no specialist pool must approve, and the line budget is larger

What still holds: every change but a standard one needs your Merge approval, a deliberate comment bound to the head commit; evidence, scope, and protected paths apply as on every profile; and nobody outside your approver list counts. The exact rules: [METHOD.md §8](METHOD.md#solo).

## My agent commits as me. Doesn't that break separation of duties?

Separation of duties is measured against the *author*: the PR/MR author and every commit author and committer. If an agent commits as you, you are the author, and someone else must approve (except under solo). Bot accounts in `identities.bots` can never approve.

<a id="bots"></a>
## What about Dependabot and Renovate?

Declare them as a standard change class:

```toml
[[standard_changes]]
name = "dependency-patch"
paths = ["package.json", "package-lock.json"]
authors = ["dependabot[bot]", "renovate[bot]"]
max_changed_lines = 300
```

A bot PR/MR with no `aidd` block is read as that class when every author is listed. It merges on green tests with no human approval, as long as it stays inside `paths`, under the line limit, and off protected paths. Anything else, such as a major bump that also edits code, needs a human-written block. Standard changes are off under the regulated profile, and every standard-change commit must be signed and verified.

## What if we have no tests?

Write one characterization test first: a command that pins today's behavior and passes on the current code. The Spec adds it before implementation, and aidd runs it on head only (by intent it passes on base too). The suite then grows with every change, as each Spec's `new_behavior` tests accumulate.

## Can the agent just edit the test until it passes?

Not without being caught. Test files are frozen by the Spec approval hash; editing one voids Spec approval, and a human must re-approve. The red run proves the test fails without the change.

## Can the agent edit the gate's config or the CI workflow?

Those are protected paths: always major, with a specialist reviewer from the team profile up (solo: the cool-off on major). The gate reads the config from the base branch, and the gate job never runs code from the PR/MR.

## What if production is down during a freeze?

Use the emergency route; it is the only one that passes a freeze. It still needs smoke tests, the route's approvals, and the approval of a named incident commander: a human Approver who did not author the fix (their approval counts as one of the route's). The full review and Spec come afterwards: the fix commits a stub of its backfill Spec with it, and `aidd validate` reports it overdue once the deadline (`review_due`, within `emergency.review_sla_days`) passes.

## Can we keep GitHub Spec Kit, OpenSpec, or Kiro?

Keep them for planning. `aidd import speckit|openspec|kiro|bmad <path>` drafts the AIDD Spec from the feature folder (or a BMAD story): its problem, acceptance scenarios, design, and tasks map onto the Spec's sections, and the code paths it names become each Task's `scope`. You then name and write the tests and get Spec approval. aidd adds what those tools do not: risk routing from the real diff, frozen tests, red-then-green evidence, and two human approvals the agent cannot give itself. The mapping for each tool, and BMAD: [Adoption](ADOPTION.md#coming-from-spec-kit-openspec-kiro-or-bmad).

## Can we keep Jira or Linear?

Keep them, or Plane, or none: a tracker is optional. Put the ticket key in the Spec's `id`, and mirror status with the transitions in [METHOD.md §5.1](METHOD.md#51-status). The Spec file in the repo stays the approved source, because it is what the hash covers.

Mirror by status group, not status by status: every aidd status falls into one of five groups ([the table in §5.1](METHOD.md#51-status)), and `aidd next --all --json` gives each item's `group`.

- **Plane:** its state groups have the same five names (backlog, unstarted, started, completed, cancelled).
- **Jira:** map backlog and unstarted to the To Do category, started to In Progress, and completed and cancelled to Done (cancelled with a resolution such as Won't Do).
- **Linear:** map them to the Backlog, Unstarted (Todo), Started, Completed, and Canceled workflow types.
- **Labels and relations** (`blocks`, `blocked_by`, `duplicates`) mirror as the tracker's labels and issue links. The repository's copy is the one `aidd validate` checks, and the gate reads none of them.

## Does it lock us into Claude, GitHub, or Python?

No:

- The instructions agents follow are a plain folder in the Agent Skills format, and `AGENTS.md` reaches every other coding agent.
- GitHub and GitLab are adapters, and any CI can produce a context JSON.
- Python is only the reference verifier, and the schemas and examples define conformance for any reimplementation.

<a id="services"></a>
## Do we need GitHub, Jira, or any other service?

No. git and the repository are all aidd needs.

- **A platform (GitHub, GitLab)** adds approvals the platform enforces. Without one, the [local-first path](ADOPTION.md#local-first-no-github-or-gitlab) holds the two approvals on your machine: `aidd approve spec`, `aidd approve merge`, and `aidd ship`.
- **Trackers, design tools, and observability services** (Jira, Linear, Figma, Sentry, and the like) are optional extensions. The team uses them only if the project already has them; the Specs, their tests, and the config in the repository are the source it works from.

## Does it work in a monorepo?

Yes. Use `owners.paths` for per-directory Approvers, `[[tests]]` with `when_changed` so a change runs only the suites it affects, and `risk_rules` scoped to the sensitive packages. See [METHOD.md §10](METHOD.md#10-scale-modules).

## How does an agent know the best practice for a task?

From a registry, not from memory. Know-how reaches a role in three dated layers:

- the standards of its discipline, with their editions
- a domain pack for every domain the change touches (an API, a mobile app, card data): standards, a checklist, test commands
- a practice skill for the kind of work in a Task, named in its `skills` (API design, schema migration, threat modeling, test design, secure coding, and more): how to do it and which commands prove it

`aidd eval standards` fails when any entry was last checked more than a year ago. When the registry has nothing for a domain, the role looks it up and records the edition in the Spec. Details: [TEAM.md](TEAM.md#how-a-role-applies-the-best-practice-for-a-task).

## How do we know it works?

- <!-- aidd:gen count:examples -->15<!-- aidd:end --> worked cases, plus <!-- aidd:gen count:mutations -->115<!-- aidd:end --> tampered variants of them, are replayed by `aidd eval examples`; any reimplementation must pass them
- red-team tests cover forged evidence, stale approvals, self-approval, scope creep, config tampering, and more
- <!-- aidd:gen count:routing-scenarios -->45<!-- aidd:end --> scenarios measure how well your own agents assess a change (`aidd eval routing --cmd "<agent cli>"`), including profile rules, prompt injection, ambiguous requests, and requests a smaller change would satisfy
- in production, `aidd metrics` tracks first-pass rates and route corrections

<a id="limits"></a>
## What doesn't it do?

- It does not review code quality. It proves who approved what, on which evidence; the Approver still reads the diff.
- It does not prove the tests are good tests. Spec approval is where a human judges that.
- It does not deploy. Ship's release and observe window are your pipeline's job; the Spec only records the rollback plan and signals.
- It does not sandbox agents or inspect prompts. Pair it with your harness's permission settings.

Every known limit of this release, including what merge queues need and the pre-release status: [RATIONALE.md](RATIONALE.md#known-limits-in-100).

## What exactly does the gate stop?

Each failure mode of agent-written changes has a rule behind it, enforced by the platform rather than requested from the model:

| Failure | Control |
| --- | --- |
| "Tests pass" in the PR/MR text | Evidence is a runner exit code bound to the head SHA. The PR/MR text is never evidence. |
| The agent weakens a test to go green | Tests are written first and frozen by the Spec approval hash. New behavior must fail on base and pass on head. |
| The agent quietly edits other files | Every changed path must sit inside a Task's declared `scope`, checked at edit time and again at the gate. |
| The agent edits CI, config, or its own instructions | Protected paths always require `major`, with a specialist review from the team profile up. The config is read from the base branch. |
| The author approves their own agent's work | The Approver must differ from the authors and from agent accounts (waived and recorded for solo). Edited or quoted approval comments never count. |
| "Low risk" self-assessment | The verifier recomputes the minimum route from the real diff and rejects a lower one. |
| 3,000-line PRs/MRs | Route budgets cap changed lines, so review stays meaningful. |
| The agent overbuilds and refactors on the way | Minimum change is a hard rule: every changed line traces to an acceptance line or the Task, and drive-by edits are review findings. |
| A freeze blocks an outage fix | Only the emergency route passes a freeze: smoke tests, the named commander's approval, a review due within the SLA. |
| Nobody knows which commits an agent wrote | Every commit names its agent (`Assisted-by:` or `Co-authored-by:`), and the change declares the same agents in `assisted_by`. |

Every rule is a row in the rulebook (`aidd gate --explain <rule>`) with a passing and a failing case in the conformance suite ([METHOD.md §7](METHOD.md#7-evidence-and-the-verifier)).

## Why diagrams as text, and not a design tool?

Because the same picture must serve two readers. An agent reads and writes text, so a Mermaid diagram inside the Spec is something it can draw, diff, and fix. A human sees it rendered on GitHub, GitLab, or in VS Code, and comments on its lines in the pull request.

Nothing is exported, nothing goes stale next to the code, and Spec approval freezes the diagram with the Spec. Design tools still have their place for high-fidelity screens: those go in `design.files` with a link to their source ([TEAM.md](TEAM.md#diagrams-in-every-spec)).

## Is it ready for an enterprise?

The design is:

- no runtime dependencies and no telemetry
- a gate that runs code nobody can swap at run time, with every third-party action pinned by SHA
- separation of duties computed from platform facts
- a record per decision, with a schema
- control mappings for SOC 2, ISO/IEC 27001, PCI DSS, NIST, and the EU AI Act

What is not there yet is stated in the same place: no tagged release or PyPI package, no pull request through a live gate yet, GitLab still experimental, the change record signed only when you turn signing on (and only where GitHub offers artifact attestations), and no GitLab merge trains. [ENTERPRISE.md](ENTERPRISE.md) is the checklist, with the status of every item.

## What does it cost?

The gate is one Python process with no dependencies: seconds of CI per run, plus your own tests, which you already pay for.

The team costs tokens, and it spends them where mistakes are expensive:

- Three roles use the strongest model your harness offers (the `reasoning` tier): the architect, the security engineer, and the reviewer. Their mistakes are invisible to every later check.
- Every other role is in the `execution` tier and inherits your session's model, so you choose it once. A human decision, frozen tests, or an approved eval checks their output.
- The role evals are the check on every choice: move a role between tiers when its scenarios pass or fail on a smaller model.
- A specialist runs only when its start condition holds; a minor change runs one agent and no roles at all.
- A role loads its playbook, the packs the change touches, and at most two practice skills, and hands off through a four-line note.

Raise a model or add a reader only when an eval or a retrospective shows the need ([TEAM.md](TEAM.md#what-it-costs-and-when-it-is-worth-it)).

## Why TOML and not YAML?

The verifier needs a strict parser with no dependencies. Python 3.11+ ships `tomllib`, and TOML has no implicit typing surprises.

## Can our org change the rules?

Yes. `[gates]` values only tighten the profile, and a looser value is ignored with a warning. Rules, exemptions (`scope_exempt_paths`, `budget_exclude_paths`, `disable_rules`, `rule_exclusions`), and standard changes can widen what passes, which is why every config change is itself protected and major. An `extends` child or a repo under an org preset cannot choose a weaker profile or replace its parent's specialist reviewers, Policy, evidence source, or identity exemptions.

<a id="uninstall"></a>
## How do I remove it?

In one PR/MR that an administrator merges, since it touches protected paths: [Remove it](INSTALL.md#remove-it).
