# The delivery team (aidd-team)

The delivery team is an optional way to run the loop: <!-- aidd:gen count:roles -->14<!-- aidd:end --> agent roles, from product manager to SRE. Each has a standard industry name, the standards of its discipline, and its own files to write. Humans lead it and make every decision. aidd works the same with a single agent. Add the team when a change needs a Spec, and you want product, design, security, and testing eyes on it, not just a builder.

## Contents

- [Why roles](#why-roles), [the roles](#roles), and [running the team](#running-the-team)
- [The loop, by role](#the-loop-by-role), and [handoffs](#handoffs)
- Know-how, in [how a role applies the best practice](#how-a-role-applies-the-best-practice-for-a-task), [domain packs](#domain-packs), [practice skills](#practice-skills), [keeping the knowledge current](#keeping-the-knowledge-current), and [extensions per role](#extensions-per-role)
- Ways of working, in [living architecture docs](#living-architecture-docs), [diagrams in every Spec](#diagrams-in-every-spec), [how the team stays fast](#how-the-team-stays-fast), and [subagents inside a role](#subagents-inside-a-role)
- [Who is responsible](#who-is-responsible-raci), [what the team covers](#what-the-team-covers), and [commands and flows](#commands-and-flows)
- [Startup default team](#startup-default-team), [at scale](#at-scale), [what it costs](#what-it-costs-and-when-it-is-worth-it), and [mixing harnesses and models](#mixing-harnesses-and-models)

## Why roles

- **The verifier is not the builder.** The verifier writes the acceptance tests before any code, and never the code, so whoever writes them never makes them pass. The developer writes the unit tests with the code, and never edits a frozen test. The Verify run is a fresh session that runs the built change against the Acceptance, not only its own tests, and the reviewer stays the separate check of the code. It is the main reason to use a team.
- **Independent eyes.** The security engineer threat-models before code exists. The verifier runs the built change against the Spec's Acceptance without touching it. The reviewer reads the diff against the Spec and the repository's `REVIEW.md`. So the Approver sees findings, not just a diff.
- **Smaller contexts.** Each role reads what its step needs, so the planning context does not crowd the build.
- **Own areas.** Each role's agent file names the files it writes, so the developer does not edit a frozen acceptance test, and the reviewer edits nothing. The developer and the tech writer stay inside the Spec's scope. A risk rule with a `role` can make one role ask before an action. The reviewer and the Merge approval check the diff.
- **The loop improves itself.** The agile coach runs a retrospective on a cadence and after every Learn signal, from the delivery results and the postmortems. Its improvements go through the same loop, and a person decides each one, as [METHOD.md](METHOD.md#9-roll-out-and-learn) explains.

## Roles

Roles are defined once, in `schemas/roles.json`, and the agent files, `aidd init --team`, and the tables here all come from it.

<!-- aidd:gen roles -->
| Role | Loop steps | Industry name | May write | Hands off |
| --- | --- | --- | --- | --- |
| `product-manager` | Plan, Learn (no Spec, Spec first, repair first) | product manager; product management (SAFe), head of product | the work items, its analytics docs, its explorations, the proposals folder, and `docs/feedback/**`, `docs/product/**` once a Task's scope covers them, after Spec approval | An Intent of INVEST slices that a human agrees to before any Spec is written. After launch: suggested Spec drafts for a person to triage, and feedback entries for a person to confirm. |
| `delivery-manager` | Plan, Roll out (no Spec, Spec first) | delivery manager; engagement manager, project manager, technical program manager, delivery lead | the proposals folder, its acceptance docs, and `specs/INTENT-*.md`, `docs/vendors.md` once a Task's scope covers them, after Spec approval | The qualification, questions, RAID log, phases, and Delivery section. The contract base and change orders, for a person to price and sign. The Handover lists, for the client's sign-off. |
| `architect` | Plan, Specify, Implement (Spec first) | software architect; tech lead | the active Spec, its tech-spec, adr, api, and migration docs, its product-level work (`loop.documents`), its walking-skeleton Tasks, its explorations, the proposals folder, and `docs/adr/**`, `docs/decisions/**`, `AGENTS.md` once a Task's scope covers them, after Spec approval | A Spec with its design, Concerns, and Tasks decided; Acceptance and tests left to the verifier. |
| `product-designer` | Plan, Specify, Implement, Review (no Spec, Spec first) | product designer; UX designer, interaction designer | the active Spec, its design files, its design-spec docs, its product-level work (`loop.documents`), the scope of the Tasks assigned to it by name, its explorations, the proposals folder | The prototype, the flow diagram, and the accessibility notes in `design.files`, and the design review of the built UI. Product code never imports the prototype: the developer builds the real thing, and the verifier writes the acceptance tests. |
| `security-engineer` | Plan, Specify, Implement, Review (no Spec, Spec first, repair first) | application security engineer (OWASP) | its threat-model and authz docs, the proposals folder, and `docs/security/**` once a Task's scope covers them, after Spec approval | A threat model and the ASVS requirements in the security return template, for the architect to link and fold into the Spec. Security tests for the verifier, and findings for a security reviewer. |
| `compliance-analyst` | Plan, Specify, Implement, Review, Roll out (Spec first, repair first) | GRC analyst; privacy engineer, compliance analyst | its compliance docs, the proposals folder, and `docs/data-map.md`, `docs/compliance/**` once a Task's scope covers them, after Spec approval | Obligations and controls in the compliance return template, for the architect to fold into the Spec. A DPIA when required, and an evidence map for the audit. A person who reviews compliance or privacy decides. |
| `domain-expert` | Plan, Specify, Review (Spec first) | subject-matter expert (SME); domain analyst, business analyst | nothing (read-only) | A perspective card for the role that asked: Assessment, Rules that apply (each with its source), Missed cases, Change (to which slices, Acceptance lines, or findings, and why). |
| `developer` | Implement (no Spec, Spec first, repair first) | software engineer; developer, machine learning engineer, data engineer | its Tasks' scope | Small commits in the project's convention on the same PR/MR, and green `aidd test` output, with the eval results or the tested rollback a specialty needs. |
| `tech-writer` | Plan, Specify, Implement (no Spec, Spec first, repair first) | technical writer; developer advocate | `docs/**`, `README.md`, `CHANGELOG.md` inside the change's scope, and the proposals folder | Documentation, changelog, and migration notes inside the Task's scope. |
| `verifier` | Specify, Verify (no Spec, Spec first, repair first) | test engineer; verification engineer; QA engineer, SDET, acceptance tester | the active Spec, its test files, its test-plan docs | Specify: the test files and the Spec's Acceptance and `tests`, each new-behavior test seen failing on base. Verify: a verification report for the author to post and the reviewer to read. It starts with the harness, the model, and the head SHA, and lists each command run, what was seen, each mismatch with an Acceptance line, and the preview files in `.aidd/evidence/preview/<head-sha>/`. |
| `reviewer` | Review (no Spec, Spec first, repair first) | code reviewer; QA engineer, SDET | nothing (read-only) | Ranked findings with evidence, starting with the harness and model it ran on, for the author to post and the person to weigh. |
| `delegate` | Specify, Review (no Spec, Spec first) | change approver for standard changes (ITIL 4 change enablement); a release manager's delegate | nothing (read-only) | One `delegate_answer` record, accept or defer, which the lead acts on. On accept, it runs the exact command the check covered, or commits the Spec's approval with the three trailers. On defer, it asks the person, with the reason. |
| `sre` | Plan, Specify, Implement, Roll out, Learn (no Spec, Spec first, repair first) | site reliability engineer (Google SRE); platform engineer, DevOps engineer, infrastructure engineer | the scope of its Tasks, its runbook and slo docs, `docs/runbooks/**`, `docs/postmortems/**`, `docs/services/**` inside the change's scope, and the proposals folder | An observe block with an SLO-based rollback trigger, in the SRE return template, for the architect to fold into the Spec. A runbook. Observe results and the postmortem link, for the author to record in the Spec's `outcome`. |
| `agile-coach` | Learn (no Spec, Spec first, repair first) | agile coach; developer-experience lead, flow coach | the work items, and `docs/retros/**`, `docs/rfcs/**` inside the change's scope | A retrospective in `docs/retros/`, improvement Spec drafts for the repository, and RFC drafts for changes to the method; humans choose what to adopt. |
<!-- aidd:end -->

## Running the team

| Harness | How |
| --- | --- |
| Claude Code, plugin | `/plugin install aidd-team@aidd` (after `aidd`); then <!-- aidd:gen list:team-commands -->`/aidd-team:plan`, `refine`, `mvp`, `propose`, `onboard`, `explore`, `specify`, `implement`, `review`, `rework`, `fix`, `rollout`, `handover`, `postmortem`, `retro`, `maintain`, `autopilot`<!-- aidd:end --> |
| Claude Code, no plugin | `aidd init --team`: project agents in `.claude/agents/`, commands as `.claude/commands/aidd-<name>.md` (run as `/aidd-<name>`, not the plugin's `/aidd-team:<name>`), the domain packs in `.claude/skills/`, and the MCP server, wired when Claude Code is detected |
| Codex, GitHub Copilot, Kiro | `aidd init --team` writes each role as a native agent file (`.codex/agents/aidd-<role>.toml`, `.github/agents/aidd-<role>.agent.md`, `.kiro/agents/aidd-<role>.json`) and adds a "Team roles" section to `AGENTS.md`. Codex and Copilot also get each flow as a skill in `.agents/skills/aidd-<flow>/`, run as `$aidd-<flow>` in Codex. Kiro reads no `.agents/skills/`, so there you pick the role's agent, one role per session |
| OpenCode | `aidd init --team` writes each role as `.opencode/agents/aidd-<role>.md` and each team command as `.opencode/commands/aidd-<flow>.md`, run as `/aidd-<flow>`. Pick the role's agent, one role per session |
| Google Antigravity | `aidd init --team` writes each role as `.agents/agents/aidd-<role>.md`, a subagent the lead starts with `invoke_subagent`, and each team command as a skill in `.agents/skills/aidd-<flow>/`, run as `/aidd-<flow>`; `.agents/skills.json` names the domain packs in `.claude/skills/` |
| Grok Build | `aidd init --team` writes each role as `.grok/agents/aidd-<role>.md`, a subagent the lead starts with `spawn_subagent`, and each team command as a skill in `.grok/skills/aidd-<flow>/`, run as `/aidd-<flow>`; the domain packs stay in `.claude/skills/` |
| Any other agent that loads skills from `.agents/skills/` (Cursor, Junie, Qwen Code, Trae, Mistral Vibe) | `aidd init --team` writes each flow as a skill in `.agents/skills/aidd-<flow>/`, and each role as `.agents/roles/aidd-<role>.md`, which the lead hands its subagent |
| An agent that reads no skills (the rest of the table in [GUIDE.md](GUIDE.md#every-coding-agent)) | `aidd init --team` adds a "Team roles" section to `AGENTS.md`; ask the agent to act as a role, one role per session |

The whole team shares one config, one skill, and one set of roles, and `aidd doctor` checks that the team is ready.

## The loop, by role

The loop in [METHOD.md](METHOD.md#3-the-loop) belongs to the change, never to a role, so no role runs a loop of its own. Each role takes only its steps of the inner loop, in its lanes. It starts only when its condition holds, and hands off at its done condition. Its agent file carries the same data.

<!-- aidd:gen roles:loops -->
*Loop contract version 1.0.0: a change that adds, removes, or reorders a step, an approval, or a lane bumps its major number.*

**The way in.** A change's route is a property of the change. aidd advises the minimum from the paths it touches, and the author may declare higher. The lane follows from the route. Before the first edit, get the route: `aidd risk --paths <planned paths>` gives the route, the lane, the areas hit, and the edit level. Which change to work on is a person's choice; `aidd status` shows the open work and each item's next step. No Spec is the default: a change starts there unless its route needs a Spec. Clarify first: ask the author at most five questions, each with a recommended answer and why, and never one a lookup answers. A question whose answer could change the route keeps confidence low, which stops the agent.

**Outer loop — human strategy and governance.** It decides what is worth doing at all (Plan), and whether the Spec an agent drafted may be built (Spec approval). It decides whether the built head may merge to the default branch (Merge approval), and how it rolls out (Roll out). Where the default branch lives on a platform, Merge approval is the review of the pull or merge request. It decides what the change and the process teach (Learn). An agent drafts for every one of these and decides none: no role approves, merges, or adopts. Where the outer loop needs a specialist, such as security, data, privacy, finance, or compliance, or an incident commander, that is a person too.

**Inner loop — autonomous agentic execution.** An agent drafts the contract, then builds against it. In Specify, it writes the Spec and its tests, which Spec approval then freezes. In Implement and Verify, repeated until green, it builds inside that frozen contract. Then the verifier runs the Spec's tests once on the green head, beside Review. In Review, on the same head, the agent reads what it built adversarially. The inner loop is bounded, not free. The Task's scope is the write area, and a failing test returns to Implement rather than being weakened. Three retries make it blocked, and the stop list hands it back.

**What crosses between them.** Two artifacts cross. Inward: the Spec approval note in the Spec, at the commit that records it. After it, an edit to the Spec's tests or Acceptance is `spec.revise`, which asks, so the inner loop does not move the target it is graded against. Outward: the runner's exit codes bound to a head commit (`aidd test`), and the checks the platform ran on that head. Prose is never evidence: not a summary, a claim that tests pass, or a chat handoff. Humans do read the ranked review report and the handoff note's Needs line, and Merge approval and the stop list are for that.

| Loop | Who decides | Steps |
| --- | --- | --- |
| Outer | a human: by approval at Spec approval and Merge approval, by recorded agreement for Plan, Merge, Roll out, and Learn | Plan, Intent agreement, Spec approval, Merge approval, Merge, Production release, Roll out, Learn |
| Inner | the agent: it drafts the contract in Specify, then works inside it once Spec approval freezes it | Specify, Implement ⟲ Verify, Review |

Control passes at the two approvals on machine-checkable evidence, and at Plan, Merge, Roll out, and Learn on a recorded human decision:

- Spec approval: a person says yes to the Spec and its tests, which freezes them
- Merge approval: a person says yes to the head commit, on its evidence

**Human feedback.** A person sends work back on these paths, drawn dashed in the loop diagram; each is a normal part of the loop, not a failure:

- **Spec approval → Specify** (changes requested): the person asks for a different Spec, tests, or design. The Specify roles revise them and ask for a new Spec approval.
- **Merge approval → Implement** (changes requested): the person does not say yes to the head. Its review comments, a person's or an agent reviewer's, go back to Implement the same way. The new head needs a new Verify and a new Merge approval.
- **Roll out → Learn** (incident, rollback, missed hypothesis): what production showed goes to Learn, never straight back into code.
- **Learn → Plan** (a new change): a lesson becomes a new change, whose route `aidd risk --paths` gives before the first edit. Also, a missed hypothesis is a product decision, taken at Plan (keep, change, or remove the feature), not a fix an agent starts by itself.
<!-- aidd:end -->

<!-- aidd:gen roles:loop:diagram -->
```mermaid
flowchart TD
  subgraph before["Before any code: with no Spec, go to Implement"]
    direction LR
    Plan["Plan<br/><i>product-manager,<br/>delivery-manager,<br/>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>domain-expert, tech-writer,<br/>sre</i>"]
    IA{{"Intent agreement"}}
    Specify["Specify<br/><i>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>domain-expert, tech-writer,<br/>verifier, delegate, sre</i>"]
    SA{{"Spec approval"}}
    Plan --> IA --> Specify --> SA
    SA -.->|"changes requested"| Specify
  end
  subgraph build["Build and prove"]
    direction LR
    Implement["Implement<br/><i>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>developer, tech-writer,<br/>sre</i>"]
    Verify["Verify<br/><i>verifier</i>"]
    Review["Review<br/><i>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>domain-expert, reviewer,<br/>delegate</i>"]
    MA{{"Merge approval"}}
    Implement --> Verify --> Review --> MA
    Verify -->|"red, or a mismatch"| Implement
    Review -->|"a finding"| Implement
    MA -.->|"changes requested"| Implement
  end
  subgraph run["Merge, roll out, and learn"]
    direction LR
    Merge["Merge<br/><i>a person</i>"]
    PR{{"Production release"}}
    Roll_out["Roll out<br/><i>delivery-manager,<br/>compliance-analyst, sre</i>"]
    Learn["Learn<br/><i>product-manager, sre,<br/>agile-coach</i>"]
    Merge --> PR --> Roll_out
    Roll_out -.->|"incident, rollback,<br/>missed hypothesis"| Learn
    Plan_again(["back to Plan"])
    Learn -.->|"a new change"| Plan_again
  end
  before --> build
  build --> run
  classDef human fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#1c1917
  class IA,SA,MA,PR human
  linkStyle 3,9,12,13 stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4
```
<!-- aidd:end -->

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#the-loop-by-role) says who decides what, and which roles work in each step.

## Handoffs

Roles cooperate through files and one note, never through chat alone. The file is the deliverable the next role reads. The note is the lines the loop contract requires of every run:

- **Done** says what changed, in which files
- **Next** names the role, or the person's approval, that follows
- **Needs** asks for a decision or fact only a human can give, or says none
- **Stopped at** names the stop rule that fired, or says none
- **Spend** copies the harness's count for the run, or says `unknown`

The next role reads the note first, then the file, so nothing is re-derived and every open question reaches a human on the Needs line.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#handoffs) draws every handoff and lists what each one passes.

Two habits keep handoffs quick.

- **One writer per file.** The architect holds the Spec during Specify, while the specialists return their parts in fixed templates. Each Task's assignee holds its scope during Implement. Disjoint Tasks build in parallel worktrees after the first Task lands green.
- **Readers in parallel.** The review readers start together, and so do the rollout readers. The review readers are the reviewer, the security engineer, and the product designer. The rollout readers are the SRE and the compliance analyst. The command merges their reports, so a reader never waits for another.

## How a role applies the best practice for a task

Know-how reaches a role in three layers, all from one registry and all dated:

1. **Standards, per role.** The role's playbook names the standards of its discipline with their editions, as [the list](TEAM-REFERENCE.md#standards-each-role-applies) shows. Its agent file turns them into steps, a Definition of Done, and stop rules.
2. **Domain packs, per change.** For every domain the change touches, such as an API, a mobile app, or card data, a generated pack adds the domain's standards. It also adds a checklist per loop step, and test commands that `aidd test` runs.
3. **Practice skills, per Task.** A Task is one kind of work, such as designing an API, migrating a schema, threat-modeling a change, writing the tests, or rolling out a release. For each kind, a hand-written skill says how to do it well and which test commands prove it.
   - Each role lists the ones for its own work, and the architect names at most two for each Task in its `skills`.
   - The files a role writes call for their own skills, whatever the Task, such as `secure-coding` for code. The lead names them in the role's brief, from the registry's `file_practices`, so they cost the agent file no bytes.
   - A role loads a skill by name with the `Skill` tool. Through its agent file's `skills:` list, the registry's `preload`, it preloads the aidd skill and the one or two it uses on most runs. So the rest cost nothing until a Task names them.

So a developer building an endpoint works from:

- its own standards, such as TDD, secure coding, and Conventional Commits
- the `aidd-team:apis-and-services` pack, with OpenAPI 3.2, the OWASP API Security Top 10, contract first, idempotency, pagination, and versioning, and `spectral lint` and `oasdiff breaking` in the Spec's tests
- the `aidd-team:naming` practice skill, for the error codes and public names the contract freezes

A role can also extend itself with any skill, plugin, MCP server, or tool, as [Extensions per role](#extensions-per-role) explains. When the registry has nothing for a domain or a kind of work, the research-first rule applies. The role looks it up and records the edition in the Spec.

## Domain packs

Each domain is a pack, a skill named `aidd-team:<pack>` generated from `schemas/packs.json`, and [TEAM-REFERENCE.md](TEAM-REFERENCE.md#domain-packs) lists them all. So a best practice becomes a red or green exit code on the head commit. Every pack has one template, in this order:

- **Scope**, when it applies, when it doesn't, and its neighbours
- **Standards**, at most ten, each cited by a checklist row or a test, with only the bare edition, since its history stays in the registry's `notes`
- **Dated obligations**, for a regulated or platform pack, the dates a duty applies from
- **Checklist by loop step**, one to four rows a step, each citing its standard, with the product defaults as one row that points to `aidd-team:product-defaults`
- **Test commands**, at most eight of its own, each name unique across every pack and practice skill. Pointers lead to the tests that another skill owns, and the shared scanners are `aidd-team:enterprise-controls`'s
- **Owned elsewhere**, **References** with at most two decision guides, and one line on keeping it current

`aidd eval packs` fails on a pack or practice skill that breaks its template or its size cap. The cap is 2,200 estimated tokens a pack, 1,700 a practice skill, and 1,600 a reference. Every session lists each skill's description, so a description has at most 250 characters. The aidd-team router names every role and command, so it gets 460. The command prints the total.

How the packs stay current:

- **Dated.** Every standard carries the date it was last checked against its source, with the page read and the line seen, in `evidence`. A practice with no versioned document or canonical page has no `evidence`, because there's nothing to check it against. Five whys and test-driven development are examples. Its date says an agent last re-read the practice.
- **Checked.** `aidd eval standards` fails on any of six things. The first is a checked date past its review cadence or its `review_due`. The cadence is its own `review_every_days`, else 90 days for an emerging entry or a year for an established one. The second is many entries sharing one checked date without evidence that confirms each, because one bulk edit isn't that many checks. The third and fourth are a control ID that its source records as moved, and an edition with no source to check it against. The fifth and sixth are an edition with no evidence, and an extension with no license or no pin. The agile coach re-checks them at every retrospective. A passing run proves that each edition names a source and a sentence read from it on that date. It doesn't prove that the practice matches the edition, because it isn't that many independent verifications.
- **Missing a pack?** A domain with no pack triggers the research-first rule, so the role looks the standard up and records its edition in the Spec.
- **Without the plugin**, `aidd init --team` copies the packs into `.claude/skills/`.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#domain-packs) lists every pack, when it applies, and the standards it adds.

## Practice skills

A practice skill is the how-to for one kind of work, hand-written in `plugins/aidd-team/skills/<name>/SKILL.md` in one template:

- **Use it when** and **Do not use when**
- **Standards**, as registry ids in `schemas/roles.json` `practices`, rendered by `aidd gen-docs`, so `aidd eval standards` checks every edition it names
- the loop steps it works in, in loop order, from Plan, Specify, Implement, Verify, Review, Roll out, and Learn
- **Test commands**, its own by a unique name, and pointers to the ones another skill owns
- **Stop if** and **Hand off**

It is loaded per Task, named in the Task's `skills`, and installed with the packs by `aidd init --team`. Its front matter carries a checked date too. Add one by writing the folder and listing it in a role's `practices` in `schemas/roles.json`, as [plugins/README.md](../plugins/README.md) explains.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#practice-skills) lists every practice skill, what it does, and the roles that load it.

## Keeping the knowledge current

A standard goes stale in three ways. Its source moves or changes edition, nobody re-reads it, or an incident shows a pack missed something. Each has a check, and a person decides every change. An agent checks every entry against its source and records the sentence it read as `evidence`.

| What keeps it current | How | Who acts |
| --- | --- | --- |
| The review cadence | Every entry in `schemas/industry-standards.json` carries the date it was last checked against its source (for a practice with no source, the date an agent re-read it). It is due again after `review_every_days`, or by default 90 days for an emerging entry and 365 for an established one, less a stable offset of up to a quarter from its id. So entries checked on one day come due across weeks, never all at once. A dated obligation on a known calendar (a store's yearly minimum SDK, a target API level) also carries `review_due`. `aidd eval standards` fails on an entry past either, and counts what comes due within 90 days; `--due DAYS` lists them. | An agent re-reads the source and updates the date and the evidence. |
| The standards check | `aidd eval standards --online` fetches each entry's `evidence.url` again. It reports whether the quoted sentence is still there: `ok`, `moved`, `missing`, or `unreachable`. `moved` means the address no longer serves it, and `missing` that the page no longer says it. `unreachable` means no answer to judge, never a finding. It is bounded: a timeout per request, a cap on the run, and a byte limit per page. It sends at most two requests at once, and one per host. It prints text or `--json` (`schemas/knowledge.schema.json`), and exits 1 only with `--strict` on a moved or missing quote. It reads the registry and never edits it; offline is the default. | Whoever reads the report raises the fix as a change to the registry. |
| The weekly workflow | The `standards` job of `.github/workflows/ci.yml` runs the online standards check every Monday and by hand, writes the report to the job summary, and turns red on a moved or missing quote. It opens an issue only when the `open_issue` input or the `AIDD_STANDARDS_ISSUES` variable asks, and only that job can write issues; it never commits. Adopters copy `templates/github/aidd-standards.yml`. | The maintainers triage the run. |
| A person approves each change | A change to `schemas/industry-standards.json` is a change like any other, and a person reviews it before it merges. | the Approvers |
| Learn feeds knowledge | A postmortem action may carry `target: pack:<slug>` or `"skill:<name>"` when its lesson belongs in the team's knowledge. `aidd validate` refuses an id the registry does not know, and `/aidd-team:postmortem` and `/aidd-team:retro` raise a suggested Spec for each one. | A person triages the suggested Spec, and an Approver approves it. |

[CONTRIBUTING.md](../CONTRIBUTING.md#update-a-standard) shows how to change a standard, step by step.

## Living architecture docs

Each document type has one owner, the role that writes it and keeps it current. Spec approval freezes a frozen one with the Spec; a living one changes with later work.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#documents-and-their-owners) lists each document type, its owner, whether it is frozen or living, and its home.

A Spec's Design describes one change, and it freezes when the Spec is approved. The documents it links as frozen in `docs` freeze with it, such as the tech spec, the test plan, the prototype, and the ADRs. A threat model is the component's, not the Spec's. It's one living file per component in `docs/security/threat-models/`, and the Spec freezes only its delta. Each role writes its document before Spec approval, with `aidd new <type> <topic> --spec <ID>`. The system's shape lives in `docs/architecture/`, and it stays current through an optional follow-up after the merge:

- **Frozen or living.** A document that records what one change decided is frozen with that Spec and never edited after. A drift found while implementing goes in the verification report and a later docs-only change. A document that several changes revise over time is living, such as an area's architecture page, a component's threat model, a runbook, or an SLO. The Spec links it with `frozen: false`, and `aidd validate` checks only that it exists. The Task that revises it names it in its scope, in that Spec's own diff.
- **When.** At Roll out, after a clean observe window, or at Learn, the author may open a change that folds the merged Spec's Design into those pages. The change updates the C4 diagram in place, and links each decision to its ADR and to the Spec.
- **Who.** The tech writer does it as a docs-only change with no Spec. When the fold needs design judgment, the architect does it as an architecture-document Task in the next Spec.
- **Never the Spec.** The merged Spec and its frozen docs are never edited, because they stay the record of what was approved.
- **One of each.** The overview and the design system exist once per repository. `aidd new architecture` writes the overview, `docs/architecture/README.md`. `aidd new design-system` writes the design system, `DESIGN.md` and `design/tokens.json`. The architect keeps the first and writes a fitness function for each layer it declares. The product designer keeps the second, and a Spec uses both and copies neither.

## Diagrams in every Spec

A person deciding at Spec approval or Merge approval reads a picture faster than a page, and an agent writes a picture as text. So the loop contract has the team explain visually, as Mermaid inside the Markdown file:

- in a Spec's Design, one diagram of the change
- in a threat model, its data-flow diagram
- in an Intent, its map of phases and slices
- in a runbook, its decision flow

The feedback loop stays in the file:

1. GitHub, GitLab, and VS Code render the diagram.
2. The reviewer comments on its lines in the pull request.
3. The author changes the source.
4. The Spec changes, so a person approves it again.

Minutes, no meeting.

`aidd validate` warns when a major Spec has no diagram, and the `aidd-team:diagrams` practice skill says which diagram answers which question. The diagrams on this page and in the team skill are generated from the roles registry, like the tables.

## How the team stays fast

A team of agents is slowed by waiting, not by typing. Five rules keep it moving, and the agile coach owns them at every retrospective:

1. **Parallel by scope.** Tasks with disjoint scope build at the same time in separate worktrees, after the first Task lands green. Specialists and reviewers run as parallel readers. One writer holds each file.
2. **WIP limits on humans, not on agents.** No Approver holds more open changes than they can decide today, and three is a good default. When a queue is full, the team finishes, splits, or parks a change instead of opening another.
3. **Decide in minutes.** Spec approval is a read of intent and acceptance, because `aidd validate` already checked the form and the verifier already wrote the tests. Merge approval is a read of the reviewer's ranked report. An approval that waits more than a day is the retrospective's first item.
4. **No status meeting.** `aidd status` and the handoff notes are the status, so nobody meets to learn it.
5. **Right-size, don't estimate.** The product manager slices each Spec small enough for one review; nobody assigns points; the coach forecasts from lead time and throughput.

## Extensions per role

Extensions are optional. The team works from the repository alone, with the Specs, the tests, the config, and the handoff notes. A role uses an extension only when the project already has the service behind it, and nothing in the loop waits for one.

A role can load any skill, plugin, MCP server, or tool its agent can run, on top of its domain packs. Each agent file names starting points, as [the list](TEAM-REFERENCE.md#extensions-per-role) shows:

- Linear or Jira for the product manager
- a design-craft skill such as Impeccable for the product designer
- Semgrep for the security engineer
- Playwright for the verifier
- Terraform, cloud servers, Sentry, and Grafana for the SRE

The lists are short on purpose, with one tool per job and the most trusted source first. Every extension has a **tier** that says who stands behind it:

| Tier | Who stands behind it | Examples | Prefer it when |
| --- | --- | --- | --- |
| `official` | the harness vendor, which made it: its source is in the vendor's own repository | Anthropic's `pr-review-toolkit`, `security-guidance`, `frontend-design` | always, when it does the job |
| `vendor` | the company behind the service it connects to | Playwright MCP, Sentry MCP, PagerDuty | you already use that service |
| `maintainer` | the maintainers of an established open-source tool | Semgrep CLI, Renovate, OSV-Scanner, knip | the tool is already in your stack |
| `community` | an individual or small group; newer and less proven | Impeccable, CodeGraph, Superpowers, Plane MCP | nothing above does the job; it is marked *emerging*, needs a permissive license, and is pinned to an exact version |

A listing in the vendor's official directory is not the same as being made by the vendor. A third-party entry listed there, such as Superpowers or the PagerDuty plugin, keeps its maker's tier. It records the listing in `listed_in`, with the commit that the directory pins.

Every tool, plugin, and skill names its **license** and its **pin**, and `aidd eval standards` fails when one lacks either. A license says what a team may do with it. A note flags terms such as the Semgrep Registry rules' internal-use license, or the document skills' ban on redistribution. A pin says exactly what it installs, a tag resolved to its commit. A server that only its vendor hosts is pinned as `vendor-hosted <URL>`.

A team adds its own in `schemas/roles.json` or straight in the harness, with a tier like any other.

Each entry also says what the extension can touch, in the **Can** column of [the list](TEAM-REFERENCE.md#extensions-per-role). It covers network, writes to the repository, commands it runs, secrets it reads, and telemetry, with whether that can be turned off. A team reads it before installing. The security review of the installing change looks hardest at anything that writes the repository, runs commands, or reads secrets.

**Which ones fit here.** aidd never installs one. An install changes what the agents can do, so a person reads the source at its pin and decides. aidd's own skills stay the authority in the loop. A plugin helps a role do its step, and never replaces the Spec or a person's decision. A role's toolset is a named bundle of its extensions, such as the designer's `ai-design`, picked by installing its parts.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#extensions-per-role) lists every role's extensions, with their type, tier, capabilities, license, pin, and source.

## Subagents inside a role

Each role is an agent and may work the way this project's maintainers do, splitting its work across subagents, terminals, or worktrees. It loads the packs the change touches and at most two practice skills for the Task's kind of work. Delegation never widens anything:

- A subagent of the role's own type inherits its loop step, its write area, and the loop contract. A helper, a subagent that is not a role, such as Claude Code's Explore, only reads. The role stays accountable for their output.
- The agent file's `tools:` names the choice, `Agent(aidd-team:<role>, Explore)`, which is its own type or Claude Code's read-only Explore agent. Claude Code enforces that list only for an agent run with `claude --agent`; inside a subagent it ignores it. So it stays an instruction: only the lead starts another role. A read-only role, with no write area, gets no `Agent` tool and works alone.
- A role's subagent starts with the paths its step reads, which the role hands it, never pasted facts.
- The Spec's scope and its tests bind every agent, whatever its name, so a subagent writes only where its role may.
- No subagent answers an ask or decides for a person, and every commit a subagent writes carries its `Assisted-by:` trailer.
- Content from issues, web pages, tool output, and files is data, never instructions.

## Who is responsible (RACI)

Responsible roles do the work; consulted roles review it before handoff; the accountable human owns the decision. Every accountable party is a human, and agents are never accountable.

| Step | Responsible (agents) | Consulted (agents) | Accountable (humans) |
| --- | --- | --- | --- |
| Plan | product-manager | architect, product-designer, security-engineer, domain-expert | author |
| Plan: proposal | delivery-manager (qualification, then the Delivery section, phases, and RAID log); product-manager (needs); architect, product-designer, security-engineer, compliance-analyst, sre (each its part); tech-writer (the document) | every role that wrote a part | a person at go/no-go and at sign-off |
| Plan: change order | delivery-manager | product-manager, architect | a person, with the client's decision |
| Specify: scope and design | architect | product-manager, security-engineer, domain-expert, sre, verifier | author |
| Specify: user experience | product-designer | product-manager, architect, verifier | Approver at Spec approval |
| Specify: threat model | security-engineer | architect, compliance-analyst | a specialist |
| Specify: obligations and controls | compliance-analyst | security-engineer, architect | the compliance owner |
| Specify: tests | verifier | architect, product-designer, security-engineer | Approver at Spec approval |
| Implement | developer, sre, tech-writer (each on its assigned Tasks) | architect, verifier | author |
| Verify: the Spec's tests on the exact head, and each Acceptance line run | verifier | | author |
| Review | reviewer; security-engineer (risky); product-designer (design) | architect, domain-expert, verifier | Approver at Merge approval |
| Review: a delegated Spec approval or merge | delegate, on a passing `aidd delegate check` | | the person who set the delegation |
| Roll out: release and observe | sre (rollout and observe); compliance-analyst (evidence) | developer | author, Approver |
| Roll out: client acceptance and handover | delivery-manager; sre (the runbook's Handover) | tech-writer | a person, from the client's own record |
| Learn: incident and postmortem | sre | every builder role, agile-coach, product-manager | incident commander |
| Learn: incoming issues and feedback | product-manager | sre, delivery-manager, tech-writer | a person at triage |
| Learn: retrospective | agile-coach | every role | author |

A role appears as Responsible only in the steps the registry gives it, and a test holds this table to `schemas/roles.json`. The product-manager owns Plan, so a postmortem's follow-ups reach it as a consultation. They become slices at the next Plan, not work at Learn.

Humans keep the decisions:

- the **Author** directs the team and answers its asks
- **Approvers** answer Spec approval and Merge approval
- **specialists** review a change whose risk names their pool
- the **incident commander** runs an incident

No agent role answers an ask for a person, or declares a route below the one `aidd risk` computes, whatever its name.

The names are functional and come from widely used references, such as SAFe, ISTQB, ISO/IEC/IEEE 12207, ITIL 4, and Google SRE, so teams recognize them. A role name carries no authority: only a person's yes answers an ask.

## What the team covers

[The process-by-process table](TEAM-REFERENCE.md#what-the-team-covers) maps each software life cycle process of ISO/IEC/IEEE 12207 to what covers it here, says who acts, and how speed and quality are measured.

## Commands and flows

Each command runs the roles its flow names, in order. The roles of one group run in parallel, and every flow stops where a human decides. The flows are data in `schemas/roles.json`, next to the roles and the handoffs, and a test holds each command to its flow.

No command runs Verify alone: `/aidd-team:review` runs the verifier beside the readers, and `/aidd-team:rework` runs it on each new head.

Not sure which? Start with `/aidd-team:autopilot` and say what you want, because it picks the flow for you. Otherwise, pick a command by the situation you are in:

<!-- aidd:gen roles:flows:when -->
| Command | When | Stops at |
| --- | --- | --- |
| `/aidd-team:plan` | You have a goal and want it planned as an Intent: phases of slices | a human agrees to the plan |
| `/aidd-team:refine` | The backlog has more than about 20 open items, and you are about to plan new work | a person accepts or rejects every proposed change in one table; the roles prepare only the accepted lines, and the person commits them |
| `/aidd-team:mvp` | You have a brief and want a launched MVP, built as a walking skeleton and then vertical slices | the launch: a person agrees to the plan, says yes to the Day-0 baseline, approves each slice's Spec and its merge, and decides the launch after the launch review. The baseline comes with its one-command local preview and the product defaults `project.defaults` leaves on |
| `/aidd-team:propose` | A client or the company's decision makers need a proposal, with options and an estimate, before any code | sign-off: a person signs the proposal off before it is sent |
| `/aidd-team:onboard` | The team starts in a repository: it maps the codebase, fits aidd to it, and picks the first changes | the author has the onboarding brief, ending with one question to run the exact `aidd init` command, which the lead runs on their yes |
| `/aidd-team:explore` | A question has two or three good answers, and a person must pick a direction before anyone builds | a person picks one of two or three directions on the comparison page; the owning role records the pick and why |
| `/aidd-team:specify` | A change needs a Spec: its route is above minor, or it needs product, design, or security eyes | Spec approval: the person approves the Spec, its tests, and its design |
| `/aidd-team:implement` | A Spec is approved, or a change with no Spec other than a bug fix is ready to build, then Verify and Review | `aidd test --changed` is green on the head, which goes to Verify and Review |
| `/aidd-team:review` | A built head needs Verify and review, side by side, with a security review when it is risky, before the human Merge approval | Merge approval: the person's yes to the head, or its PR/MR review, once Verify is clean |
| `/aidd-team:rework` | A built head came back with a failed Verify or Review report, an open review comment, or a failing check, to fix on its branch | only Merge approval remains: every report item and comment answered, the checks green, and the new head ready for a yes |
| `/aidd-team:fix` | You have a small bug fix on the minor route: within 50 changed lines, in no area that raises the route | Merge approval: the person's yes to the fix's head (the reviewer reads a diff over 20 changed lines) |
| `/aidd-team:rollout` | A person merged an approved change, and its observe window and rollback trigger need watching | a clean observe window, or the rollback trigger |
| `/aidd-team:handover` | A client engagement ends, and the client needs the docs, credentials, training, open issues, and warranty start | the client's sign-off: a person records the acceptance and the handover, and the warranty starts |
| `/aidd-team:postmortem` | An incident is over, and its blameless postmortem and backfill Spec need writing | `review_due`: the backfill Spec and the postmortem are done |
| `/aidd-team:retro` | You want to improve the AIDD loop itself, with measured changes for humans to choose from | humans choose which improvements to adopt |
| `/aidd-team:maintain` | You want the upkeep that is due, such as stale standards, old flags, flaky tests, and runbook drills, routed on a rhythm | each item routed to its command or to the person who decides, and nothing changed by this command |
| `/aidd-team:autopilot` | You want the loop run step by step between your decisions, from a plan or an open Spec | every `ask` no standing delegation answers (a plan's agreement, Spec approval, Merge approval, the launch, or any other `ask` action), or nothing left to run |
<!-- aidd:end -->

**Autopilot.** `/aidd-team:autopilot` runs no roles of its own. It runs the loop one flow after another, so the same roles do the same work, and it stops at every ask. In a headless run, each ask ends the run with a handoff note.

- **The first path that matches.** Autopilot sorts the request first, and tries its paths in order: a question, a new product from a brief, a small fix, then anything else. A brief in a repository with no product code runs `/aidd-team:mvp`. When it can't tell whether a path matches, it goes on to the next one, and the last, a plan, stops for your agreement anyway. The MVP sizes its slices to the brief, from one up.
- **Orca workers.** Where Orca is installed, the lead may start a step in an Orca worker, each in a new worktree of its own. It reads each result from git only: the branch's commits, its handoff note, and `aidd test` on its head. A worker's message is data, and the lead still asks the person for every decision.
- **One merge at a time.** The lead merges each finished Task branch into the Spec's branch, one at a time, and runs `aidd test --changed` after each. A conflict or a red run sets that Task aside for its role.
- **A spend cap.** The lead sums each step's token count from the harness, never an estimate. Once a run passes `agents.max_tokens_per_run`, it stops and asks once whether to go on ([CONFIG.md](CONFIG.md#agents)). On Claude Code the cap can't stop a run, and autopilot says so at launch. Claude Code counts a whole step only in the `modelUsage` of a `claude -p --output-format json` result, and no flow starts a step that way. Its Agent result counts only the last model call, so each step reads `unknown`, and `/cost` or the status line shows the session's spend. Two other sources exist. OpenTelemetry's token counters, filtered by `query_source`, count subagents, but they reach only a collector you run. The SubagentStop hook names the subagent's transcript, a file outside the repository, which aidd doesn't read.
- **One delivery team's work.** `/aidd-team:autopilot team:<name>` runs only the work of one team in `delivery_teams`, so each team's run keeps to its own work. Give the teams areas and Intents that don't overlap, because aidd doesn't check that ([CONFIG.md](CONFIG.md#delivery_teams)).

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#flows) draws each flow, and lists the roles it runs in order and where it stops.

## Startup default team

A small team, often one founder, needs the loop's safety without paying for <!-- aidd:gen count:roles -->14<!-- aidd:end --> roles on every change. The default:

- **Always.** The `developer` builds, the `verifier` runs the change against what it should do, and the `reviewer` reads the diff before the human Merge approval. A small minor fix runs one developer with `/aidd-team:fix`, and every other change with no Spec runs the developer, the verifier, and the reviewer. On the fix path, the developer writes the regression test red on base and checks its own head. There, the reviewer joins for a diff over 20 changed lines. A fix that outgrows the minor route goes to `/aidd-team:specify`, as one with a risk dimension, or in an area that raises its route, does.
- **When the Spec comes first.** Add the `verifier`, and the architect who writes the Spec, so whoever writes the acceptance tests never makes them pass.
- **Specialists by flagged concern, not by habit.** The architect writes the Spec in one session and lists each concern in `## Concerns`. `aidd risk --paths` names the areas and the risk dimensions. Only the specialist for a flagged concern, a named area, or a document the risk requires joins:
  - the security engineer for security, privacy, or an AI feature
  - the compliance analyst for compliance or data
  - the SRE for availability, and on major
  - the product designer for a user-facing flow
- **The founder decides.** Under the `solo` profile, the agent asks the founder at each ask. When no specialist pool is named, the product manager records the founder as the domain expert. No role ever approves.
- **A new product.** `/aidd-team:mvp` takes a brief to a one-screen plan, a Day-0 baseline, and a walking skeleton. Then come the other slices, two or three at a time in their own worktrees, and a launch review. The founder decides at each stop.

## At scale

The same roles serve a solo founder and a large organization; only the humans change. The founder answers every ask and runs an incident. A team adds Approvers and specialists, and many teams run one delivery team per area. Roles never reach across a repository or a company.

## What it costs, and when it is worth it

A team of agents costs tokens, and the CI test job costs minutes; both are priced to value, and extra cost needs a reason:

- **Model tiers.** Each role carries a harness-neutral tier, not a vendor's model name, because the team ships to <!-- aidd:gen count:harnesses -->14<!-- aidd:end --> harnesses and only one of them is Anthropic's. There are two tiers. The registry records the tier and the reason ([per role](TEAM-REFERENCE.md#model-tiers)). To pick the model per tier or per role, see [Mixing harnesses and models](#mixing-harnesses-and-models).
  - `execution`, the default — the role's output is checked by something other than itself. The check is a human decision at Spec approval or Merge approval, tests written before it builds, or evals approved at Spec approval. It runs on a mid-size model, not the session's, because on a top-tier session the roles meant to be cheap would otherwise cost the most. It also holds the verifier. The verifier runs the Spec's commands and compares the results with each Acceptance line, and the reviewer and Merge approval read its report.
  - `reasoning` — only where a mistake is invisible to every later check. It holds the architect, whose route, scope, and design every later step inherits, and the security engineer, who finds threats tests never see. It also holds the reviewer, the last reader before Merge approval. The compliance analyst, the product manager, and the product designer are in it too, because a person reviews what they list, never what they miss. The strongest model your harness offers.
  - Each tier also sets how hard its roles think in Claude Code: `xhigh` effort for reasoning and `high` for execution. Higher effort spends more tokens, so `agents.effort` lowers or raises it per tier or role.
  - `inherit`, the session's model, is an opt-in. Set it for a tier or a role in `agents.models`, as [Mixing harnesses and models](#mixing-harnesses-and-models) explains.
  - A role can also run on any model by name. Give it its own entry in `agents.models`, such as `verifier: openai/gpt-6-sol`.
  - The role evals are the check. Move a role to a smaller tier when its scenarios still pass there, and back when they fail.
  - <a id="the-claude-code-advisor"></a>The Claude Code advisor is an optional middle ground for the `execution` roles. It is experimental, on the Anthropic API only, and off when feature-flag fetching is off. Set `advisorModel` to an Opus model in Claude Code's settings, or use `/advisor`. A role on Sonnet then asks Opus before an approach, on a recurring error, and before it says it's done. It applies to the whole session and subagents inherit it, so the `reasoning` roles get an Opus-reviews-Opus pairing at extra cost. It reads the same conversation as the role. So the advisor is a second opinion inside one role's session, never a substitute for the verifier, the reviewer, or independent review. aidd never sets it. Its tokens bill at the advisor model's rates, so count them in the handoff note's Spend line.

<!-- aidd:gen roles:tiers -->
| Tier | For | Claude Code | Codex |
| --- | --- | --- | --- |
| `reasoning` | decides, designs, or judges where a mistake, or a missing option, is invisible to every later check; the strongest model | `opus` | `gpt-6-astra` |
| `execution` | builds, proposes, or runs checks where the tests, the reviewer, or a person catch the mistake; a mid-size model | `sonnet` | `gpt-6-sol` |
<!-- aidd:end -->

- **Roles per route.** A small minor fix runs one developer, and the reviewer past 20 changed lines (`/aidd-team:fix`); every other change with no Spec runs the developer, the verifier, and the reviewer. A normal change runs the architect and the verifier before Spec approval, one builder per Task, the verifier, and the reviewer. A specialist, such as the designer, security, compliance, or the SRE, runs only for a concern the architect flags in its area, or a document the risk requires. Parallel readers cost the same tokens as serial ones and save wall-clock time.
- **Context.** A role starts with its playbook and the contract rules that bind it. Only a role that writes a Spec or tests preloads the aidd skill. A role loads the packs the change touches and at most two practice skills. A subagent inherits nothing more. A handoff is a short note plus a file, never a transcript.
- **The lead.** The session that runs a command places each role, its role placement. It plays only a role that adds a view to its own work, never one that checks, tests, or reviews it. It starts the rest, and every role under autopilot. It hands each role it starts its context pack or its files by path, never pasted facts. It launches a group in one message and waits for all of it. It names each role's model, starts each command fresh, and revises in one write. Each command carries these rules. It ends with a handoff note that `aidd validate` passes, with a Spend line and a stop code.
- **aidd itself.** One Python process with no dependencies, seconds per run; the tests it runs are your own. The evals against a real agent run by hand, on your own quota.

[TEAM-REFERENCE.md](TEAM-REFERENCE.md#model-tiers) gives each role's tier, the model it maps to per harness, and the reason.

Use `/aidd-team:fix` for a small minor fix and one agent for small Specs. Use the team for Specs with several Tasks, for major work where independent tests matter most, and for planning an Intent. Measure it before you make it the default. Run the routing and role evals with `aidd eval routing` and `aidd eval roles`. Compare how often the tests pass on the first try, with and without the team.

## Mixing harnesses and models

A team does not have to run on one vendor's agent. People can use different harnesses, such as Claude Code, Codex, and Cursor, and each role can run on a different model. aidd never cares which, and `assisted_by` records which `harness/model` wrote each change.

**Pick a model per tier or per role** in `.aidd/config.yaml`, as `provider/model`. A role's own entry wins over its tier:

```yaml
agents:
  models:
    reasoning: anthropic/claude-opus-5-5  # the six deciders, such as the architect and the reviewer
    execution: inherit  # the session's model for every other role (opt-in)
    reviewer: openai/gpt-6-astra  # one role, by name: review on another model family
    verifier: openai/gpt-6-sol  # any role can run on any model by name
```

`aidd init --team` and `aidd upgrade` write the choice into each harness's own agent model field:

| Harness | Takes |
| --- | --- |
| Claude Code | an `anthropic/` model, as `model:` |
| Codex | an `openai/` model, as `model` |
| In OpenCode | the whole `provider/model` |
| Kiro, GitHub Copilot | the model name |

Where a harness cannot run the model you named, the generated file says so and the harness's default runs. Without `agents.models`, each tier keeps its default per harness. The Claude Code plugin derives `model:` from the tier. On any other harness, you read the tier and pick your own model.

**Ask for review on another model.** A reviewer on the same model as the developer tends to miss what the developer missed. So give the reviewer and the verifier their own entries in `agents.models`, on another model family. The Reviewer and the Verifier start every report with the harness and the model they ran on, so the Approver can see it.

Mixing is a choice, not a requirement, and one harness and one model is a fine start. Measure before you switch, with the role evals in `aidd eval roles` and the first-pass rate of the tests, as [What it costs](#what-it-costs-and-when-it-is-worth-it) explains.
