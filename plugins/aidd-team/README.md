# aidd-team

An optional Claude Code plugin that runs the [AIDD](https://github.com/thaithienvanid/aidd#readme) loop as a delivery team. <!-- aidd:gen count:roles -->17<!-- aidd:end --> agent roles, each with a standard industry name, apply their discipline's standards and write only their own files. It needs the core `aidd` plugin (the skill, the MCP server, and the guard hook).

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd
/plugin install aidd-team@aidd
```

<!-- aidd:gen roles -->
| Role | Loop steps | Industry name | May write | Hands off |
| --- | --- | --- | --- | --- |
| `product-manager` | Plan, Learn (spec lane) | product manager; product management (SAFe), head of product | the work items, its analytics docs, its explorations, the proposals folder, and `docs/feedback/**` once a Task's scope covers them, after Spec approval | An Initiative, Epics, and INVEST Spec stubs that a human agrees to before any Spec is filled in. After launch: suggested Spec drafts for a person to triage, and feedback entries for a person to confirm. |
| `delivery-manager` | Plan, Ship (fast, spec lanes) | delivery manager; engagement manager, project manager, technical program manager, delivery lead | the proposals folder, its acceptance docs, and `specs/INIT-*.md`, `docs/vendors.md` once a Task's scope covers them, after Spec approval | The qualification, questions, RAID log, milestones, and Delivery section. The contract base and change orders, for a person to price and sign. The Handover lists, for the client's sign-off. |
| `architect` | Plan, Specify, Implement (spec lane) | software architect; tech lead | the active Spec, its tech-spec, adr, and api docs, its walking-skeleton Tasks, its explorations, the proposals folder, and `docs/adr/**`, `docs/decisions/**`, `docs/architecture/**`, `AGENTS.md` once a Task's scope covers them, after Spec approval | A Spec with scope, Tasks, risk, rollback, and design decided; Acceptance and tests left to the tester. |
| `product-designer` | Plan, Specify, Review (spec lane) | product designer; UX designer, interaction designer | the active Spec, its design files, its design-spec docs, its explorations, the proposals folder | The prototype, the flow diagram, and the accessibility notes in `design.files`, and the design review of the built UI. Product code never imports the prototype: the developer builds the real thing, and the tester writes the tests. |
| `security-engineer` | Plan, Specify, Implement, Review (spec, emergency lanes) | application security engineer (OWASP) | its threat-model and authz docs, the proposals folder, and `docs/security/**` once a Task's scope covers them, after Spec approval | A threat model and the ASVS requirements in the security return template, for the architect to link and fold into the Spec. Security tests for the tester, and findings for the security pool's reviewer. |
| `compliance-analyst` | Plan, Specify, Implement, Ship (spec, emergency lanes) | GRC analyst; privacy engineer, compliance analyst | its compliance docs, the proposals folder, and `docs/data-map.md`, `docs/compliance/**` once a Task's scope covers them, after Spec approval | Obligations and controls in the compliance return template, for the architect to fold into the Spec. A DPIA when required, and an evidence map for the audit. The human reviewer from the compliance or privacy pool decides. |
| `domain-expert` | Plan, Specify, Review (spec lane) | subject-matter expert (SME); domain analyst, business analyst | nothing (read-only) | A perspective card for the role that asked: Assessment, Rules that apply (each with its source), Missed cases, Change (to which stubs, Acceptance lines, or findings, and why). |
| `tester` | Specify (spec lane) | tester (ISTQB); QA engineer, SDET | the active Spec, its test files, its test-plan docs | Test files and the Spec's Acceptance and `tests`, each new-behavior test seen failing on base; `aidd validate` reports 0 errors. |
| `developer` | Implement (fast, spec, emergency lanes) | software engineer; developer | its Tasks' scope | Small Conventional Commits on the same PR/MR, and green `aidd test` output. |
| `ml-engineer` | Implement (spec, emergency lanes) | machine learning engineer; AI engineer | its Tasks' scope | The AI change and its eval results against the Spec's thresholds, in small commits on the same PR/MR, and green `aidd test` output. |
| `data-engineer` | Implement (fast, spec, emergency lanes) | data engineer; database engineer, analytics engineer | the scope of its Tasks, its migration docs, `docs/data-map.md` inside the change's scope | Migrations, pipelines, and events in small commits on the same PR/MR, with the migration's rollback tested, and green `aidd test` output. |
| `platform-engineer` | Implement, Ship (fast, spec, emergency lanes) | platform engineer; DevOps engineer, infrastructure engineer | its Tasks' scope | Small commits on the same PR/MR, a plan or dry-run for the Approver, and green `aidd test` output. |
| `tech-writer` | Plan, Implement (fast, spec, emergency lanes) | technical writer; developer advocate | `docs/**`, `README.md`, `CHANGELOG.md` inside the change's scope, and the proposals folder | Documentation, changelog, and migration notes inside the Task's scope. |
| `verifier` | Verify (fast, spec, emergency lanes) | verification engineer; acceptance tester, QA engineer, SDET | nothing (read-only) | A verification report, for the author to post and the reviewer to read. It starts with the harness and model the verifier ran on and the head SHA it checked. It lists each command run, what was seen, each mismatch with an Acceptance line, and the preview files under `.aidd/evidence/preview/<head-sha>/`. |
| `reviewer` | Review (fast, spec, emergency lanes) | code reviewer; QA engineer, SDET | nothing (read-only) | Ranked findings with evidence, starting with the harness and model it ran on, for the author to post and the Approver to weigh. |
| `sre` | Plan, Specify, Implement, Ship, Learn (fast, spec, emergency lanes) | site reliability engineer (Google SRE) | its runbook and slo docs, the proposals folder, and `docs/runbooks/**`, `docs/postmortems/**` once a Task's scope covers them, after Spec approval | An observe block with an SLO-based rollback trigger, in the SRE return template, for the architect to fold into the Spec. A runbook. Observe results and the postmortem link, for the author to record in the Spec's `outcome`. |
| `agile-coach` | Learn (fast, spec, emergency lanes) | agile coach; developer-experience lead, flow coach | the work items, and `docs/retros/**`, `docs/rfcs/**` inside the change's scope | A retrospective in `docs/retros/`, improvement Spec stubs for the repository, and RFC drafts for changes to the method; humans choose what to adopt. |
<!-- aidd:end -->

Humans keep every decision: who approves a Spec and a change, who reviews high-risk work, who runs an incident, and who directs the team.

<!-- aidd:gen roles:commands -->
- **Commands:** `/aidd-team:plan`, `/aidd-team:refine`, `/aidd-team:mvp`, `/aidd-team:propose`, `/aidd-team:onboard`, `/aidd-team:explore`, `/aidd-team:specify`, `/aidd-team:implement`, `/aidd-team:verify`, `/aidd-team:review`, `/aidd-team:sweep`, `/aidd-team:fix`, `/aidd-team:secure`, `/aidd-team:ship`, `/aidd-team:handover`, `/aidd-team:postmortem`, `/aidd-team:retro`, `/aidd-team:maintain`; one per flow in the registry, each running its roles in order and stopping where a person decides. `/aidd-team:autopilot` runs those flows between your decisions, one `aidd autopilot next` action at a time.
<!-- aidd:end -->
- **Know-how:** each role carries its discipline's standards. It loads a pack for every domain the change touches, and a playbook for the kind of work in a Task (up to two, named in its `skills`). Everything carries a checked date. `aidd eval standards` fails on a standard nobody re-checked within its review cadence: 90 days for an emerging one, a year otherwise ([docs/TEAM.md](https://github.com/thaithienvanid/aidd/blob/main/docs/TEAM.md)).
- **Extensions:** each role names the skills, plugins, and MCP servers that extend it. Any other one is added the same way, verified and pinned, through a change.
- **Guard, not a control:** the aidd plugin's hook reads each subagent's `agent_type`. It denies these:
  - an edit outside that role's area (the developer cannot edit a spec-lane test file)
  - any edit from a subagent that is not a role
  - `gh pr review --approve`, `gh pr merge`, and `glab mr approve|merge`
  - a command that carries `/aidd approve`

  The hook also holds a role's obvious shell writes (redirects, `tee`, `sed -i`, `cp`, `mv`, `git apply`, `patch`) to the same area, and denies a role's command that runs code it cannot read. It does not see a write by a program that writes by itself, such as an interpreter, a build tool, or a package manager. The gate's scope rule on the real diff is what decides. Without the aidd plugin (or `aidd init --agent-hooks`) there is no hook, and the roles only follow their instructions.
- **Without the plugin:** `aidd init --team` installs the roles, packs, practice skills, and commands as Claude Code project files. Each file is named `aidd-<name>` (`.claude/agents/aidd-developer.md`, `/aidd-implement`), so none collides with a built-in agent or your own. `aidd init --team` also installs the roles reference that each role file points to for its standards (`.aidd/team-roles.md`). For Codex, GitHub Copilot, Google Antigravity, Grok Build, OpenCode, and Kiro, it also writes each role as that agent's own agent file. `AGENTS.md` gets a short section that points at those files. In Grok Build and OpenCode, aidd's guard also keeps each role to its area. Elsewhere the team is advisory: no hook checks a role's writes, and the gate decides.
- **Model tiers:** each role carries a harness-neutral `tier` that follows the cost of its mistakes. Its agent file gives the reason.
  - `execution` is the default, on a mid-size model, because the tests, the gate, or a human catch the role's mistakes. The verifier is in it too.
  - `reasoning`, the strongest model, is only for the roles whose judgment no test checks, such as the architect and the reviewer.

  There are no other tiers. A role moves between tiers only on eval evidence. The Claude Code plugin derives `model:` from the tier (`team_registry.tier_model`, a model alias). For a copied team, `agents.models` can set `inherit` (the session's model) or any model by name, per tier or per role. On any other harness, read the tier and pick your own model.

Roles are defined once, in `schemas/roles.json`; the tables here and each agent's role block are generated from it.
