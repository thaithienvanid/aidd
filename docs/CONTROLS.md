# Control mapping

How aidd's mechanisms support common frameworks. This is guidance for your auditors, not a certification. A mechanism listed against a control contributes evidence toward it. Each organization maps its own control IDs and decides what satisfies them. References are to `docs/METHOD.md`. [METHOD.md §11](METHOD.md#11-ai-era-security-controls) says which mechanisms the gate enforces and which are guidance.

A gate mechanism is evidence of a control only where the gate is enforced. That means enforce mode, a gate the platform requires, and a status pinned to the gate's App. In advisory mode, it's evidence of monitoring, not of prevention. [What holds without that setup](PLATFORMS.md#what-holds-without-the-full-setup) says what you still get.

AI-specific frameworks:

| Mechanism | NIST SSDF (SP 800-218 / 800-218A) | OWASP LLM Top 10 (2026) | ISO/IEC 42001 | EU AI Act |
| --- | --- | --- | --- | --- |
| Spec with executable acceptance, Spec approval by hash (§5, §8) | PW.1 (design to meet requirements), PO.1 | LLM03 Excessive Agency | A.6 AI system life cycle | Art. 14 human oversight |
| SHA-bound evidence, red-then-green (§7) | PW.8 (test executable code) | LLM07 Misinformation (claims without proof), LLM10 Improper Output Handling | A.6.2.4 verification and validation | Art. 15 accuracy, robustness |
| Scope via Task scope, route budgets (§4.2, §7) | supports PW.7 (review code) by keeping each human review small and bounded; the review itself is the Approver's | LLM03 Excessive Agency | A.6.2.3 | |
| Protected paths, base-branch config, trusted gate job (§6, §14) | PO.3 (secure toolchains), PS.1 (protect code) | LLM01 Prompt Injection (persistence), LLM03 | A.4.4 tooling resources | Art. 15 cybersecurity |
| SoD against the author, agents cannot approve (§8) | PO.2 (roles and responsibilities) | LLM03 | A.3 internal organization | Art. 14 |
| Policy and freeze with emergency break-glass (§13, §6) | PO.1 | | A.9 use of AI systems | |
| Supply-chain rule, registry verification (§11) | PW.4 (reuse well-secured software), PS.3 | LLM04 Supply Chain | A.10 third-party relationships | Art. 15 |
| Untrusted-input rule, secrets rule (§11) | PW.5, PS.1 | LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure | A.7 | |
| Provenance trailers and `assisted_by` (§11) | supports PS.3 (archive and protect releases) and 800-218A's record of AI involvement | | A.6.2.7 documentation | Art. 12 record-keeping (Art. 50 transparency, by analogy) |
| Roll out's observe window, rollback trigger, Learn (§12) | RV.2, RV.3 (analyze root causes) | | A.6.2.6 operation and monitoring | Art. 72 post-market monitoring |
| Gate events and records retained (§12, [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)) | PO.3.3 (audit trail), PS.3 | | Clause 9 performance evaluation, A.6.2.8 event logs | Art. 12, Art. 19 logs |

General frameworks:

| Mechanism | SOC 2 | SLSA / DORA metrics | ISO/IEC 27001:2022, PCI DSS v4.0.1, NIST SP 800-53r5 |
| --- | --- | --- | --- |
| Spec with executable acceptance, Spec approval by hash (§5, §8) | CC8.1 change authorization | | A.8.32 change management; PCI 6.5.1 (documented approval before the change); 800-53 CM-3 |
| SHA-bound evidence, red-then-green (§7) | CC8.1 testing | SLSA-style: evidence produced by a defined CI runner | A.8.29 security testing in development and acceptance; PCI 6.5.1 (testing before deployment); 800-53 SA-11 |
| Scope via Task scope, route budgets (§4.2, §7) | CC8.1 | | A.8.32; PCI 6.5.1; 800-53 CM-4 impact analysis |
| Protected paths, base-branch config, trusted gate job (§6, §14) | CC6.1, CC8.1 | SLSA: source and build integrity | A.8.9 configuration management, A.8.32; PCI 6.5.1; 800-53 CM-5 access restrictions for change |
| SoD against the author, agents cannot approve (§8) | CC8.1, CC1.3 | | A.5.3 segregation of duties; PCI 6.5.1 (approval by authorized parties); 800-53 AC-5 |
| Policy and freeze with emergency break-glass (§13, §6) | CC8.1, CC7.4 | DORA metrics: change fail rate, failed deployment recovery time | A.8.32 (emergency changes recorded and reviewed); PCI 6.5.1 (back-out procedures); 800-53 CM-3 |
| Supply-chain rule, registry verification (§11) | CC9.2 | pinned dependencies (lockfiles) | A.5.21 ICT supply chain, A.8.28 secure coding; PCI 6.3.2 (component inventory); 800-53 SR-3 |
| Untrusted-input rule, secrets rule (§11) | CC6.1 | | A.8.28 secure coding; PCI 6.2.4; 800-53 SI-10 input validation |
| Provenance trailers and `assisted_by` (§11) | CC2.1 | supports provenance: unsigned commit trailers record which agent wrote a change; they are not SLSA provenance, which is a signed build attestation | A.8.25 secure development life cycle; PCI 6.3.2; 800-53 SA-8 |
| Roll out's observe window, rollback trigger, Learn (§12) | CC7.2 to CC7.5 | DORA metrics: `aidd metrics --dora` reports proxies for the five metrics against `targets`, with `--specs` for change fail rate and recovery time | A.8.16 monitoring, A.5.27 learning from incidents; PCI 6.5.2 (confirmation after a significant change); 800-53 IR-4 |
| Gate events and records retained (§12, [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)) | CC4.1, CC7.2 | the source of the DORA proxies in `aidd metrics --dora` | A.8.15 logging, A.5.28 collection of evidence; PCI 10.5.1 (retention); 800-53 AU-3, AU-11 |

Notes:

- The OWASP LLM Top 10 column uses the 2026 edition, the one the standards registry records. It uses these IDs, LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Excessive Agency, LLM04 Supply Chain, LLM07 Misinformation, and LLM10 Improper Output Handling. The 2025 edition numbered several of these differently, so Excessive Agency was LLM06, Supply Chain LLM03, Misinformation LLM09, and Improper Output Handling LLM05. So check which edition a control ID in your own mapping uses.
- The untrusted-input rule and the secrets rule are process. They're agent guidance, not a gate.
- The observe window, the rollback trigger, and Learn are process, not tool. aidd records the plan, and `aidd observe` runs one check; your release tooling watches and rolls back.
- The EU AI Act mostly places obligations on AI system *providers* and *deployers*. aidd helps a software organization evidence human oversight and record-keeping for AI-assisted development; it does not classify your product under the Act.
- For NIST SP 800-218A, treat `assisted_by`, evidence, and gate records as the development-time artifacts for AI-generated code.
- DORA in the table above means the DORA software delivery metrics from Google Cloud's DevOps research. The EU regulation of the same name is in [EU cyber laws](#eu-cyber-laws-and-the-osps-baseline).

## OWASP Top 10 for Agentic Applications

The 2026 edition, published on December 9, 2025, names the risks of agents that plan and act on their own. The standards registry marks it emerging. Each row says what aidd does about one risk, and which files show it. **partial** means aidd narrows the risk and the rest is yours. **open** means aidd does nothing that holds against it yet. No row is fully covered, because aidd decides at the edges of a run and never inside the model.

| Risk | What aidd does | Evidence | Status |
| --- | --- | --- | --- |
| ASI01 Agent Goal Hijack | The engine that picks each autopilot step reads no free text as an instruction, so a Spec body, a handoff note, or a PR/MR comment never changes the next action. The gate reads the change as git objects and never runs it. An imported issue is quoted as data, and the skill tells agents to treat issue text, pages, and tool output as data. The agent itself can still be hijacked, so the always-on rules and the gate stay the controls. | `src/aidd/autopilot/__init__.py`, `src/aidd/setup/issue_import.py`, `.agents/skills/aidd/references/security.md` | partial |
| ASI02 Tool Misuse and Exploitation | The guard checks each tool call. It denies an agent's approval, land, merge, or publish, and an MCP tool that approves or merges. In enforce mode, it also denies an edit outside a role's area. A command that matches `guard.held_commands`, such as a deploy, waits for a person. The guard's known limits are in [SECURITY.md](../SECURITY.md#trust-model). | `src/aidd/guard/pre_tool.py`, `src/aidd/guard/held_commands.py`, `src/aidd/guard/mcp_tools.py`, `src/aidd/guard/role_areas.py`, `tests/test_guard_ref_oracle.py` | partial |
| ASI03 Identity and Privilege Abuse | aidd issues no agent identity and scopes no token. It counts no approval from an account in `identities.bots`. `aidd doctor --autopilot` names each credential in the environment, and warns on a long-lived classic GitHub token. An agent can still use any credential it holds. | `src/aidd/setup/autopilot_readiness.py`, [AUTOPILOT.md](AUTOPILOT.md#credentials-for-a-run) | open |
| ASI04 Agentic Supply Chain Vulnerabilities | Agent instructions, skills, hooks, and MCP config are protected paths, so a change to one is major and needs a specialist Approver. `aidd init` never shares the plugins when the project's settings name another source for the `aidd` marketplace. The managed settings template pins the marketplace, with auto-update off. aidd has no runtime dependency. A plugin or MCP server installed outside the repository is yours to vet. | `schemas/baseline.json`, `src/aidd/setup/claude_plugins.py`, `templates/claude/managed-settings.json` | partial |
| ASI05 Unexpected Code Execution | The gate never runs the change's code. The test job runs it with a read-only token and no secrets. For a writer it holds, the guard denies a command that runs code it cannot read, such as a pipe into `bash`. aidd sandboxes nothing, and its dev container is a starting point. | `src/aidd/guard/write_targets.py`, `.github/workflows/aidd-tests.yml`, `templates/devcontainer/init-firewall.sh` | partial |
| ASI06 Memory and Context Poisoning | The instruction files in the repository, such as `AGENTS.md` and the skills, are protected paths, so a person reviews each change to them. A harness's own memory, and what a tool returns during a session, are outside what aidd reads. | `schemas/baseline.json` | open |
| ASI07 Insecure Inter-Agent Communication | Roles hand work on through files in git, which the next role reads as data. The guard denies a decision that another agent sends into this session, in each way it can read. aidd authenticates no message between agents. | `src/aidd/guard/approval_commands.py`, `src/aidd/guard/tmux_commands.py` | partial |
| ASI08 Cascading Failures | In an autopilot run, a step that fails twice in a row sets its item aside, and six steps in a row that move nothing stop the run. A timebox, optional token and cost caps, and the Approver work in progress limit bound it. An error inside a gate check fails closed. The cost cap, and the token cap outside Claude Code, rest on the spend each step records. | `src/aidd/autopilot/engine.py`, `src/aidd/autopilot/lease.py` | partial |
| ASI09 Human-Agent Trust Exploitation | Evidence, not prose. The gate counts a runner's exit code on a known commit, never an agent's summary. Spec approval binds the Spec hash, and Merge approval binds the head commit, so a person approves exact content. No agent approves, and a journal line never counts as an approval. A person can still be persuaded, so the review stays theirs. | `src/aidd/gate/rules/approvals.py`, `src/aidd/gate/rules/evidence.py`, `schemas/record.schema.json` | partial |
| ASI10 Rogue Agents | A lease gives each piece of work one live run, and a timebox ends it. In every mode, the guard's always-on rules deny an agent's approval, land, merge, or publish, a change to a person's decision records, and a looser config. In enforce mode, roles write only their own area. An agent with a shell can still edit the journal, so the gate in CI stays the control. | `src/aidd/autopilot/lease.py`, `src/aidd/guard/decision_files.py`, `src/aidd/guard/role_areas.py` | partial |

Two risks are open. ASI03 needs short-lived, scoped credentials for each agent, which aidd can warn about but never issue. ASI06 needs checks on what a harness remembers between sessions, which aidd never reads.

## EU cyber laws and the OSPS Baseline

Four texts reach a software organization in the EU, or its customers:

- **The Cyber Resilience Act**, Regulation (EU) 2024/2847, Annex I. Part I sets what a product with digital elements must be, and Part II how its maker handles vulnerabilities.
- **NIS2**, Directive (EU) 2022/2555, Article 21(2). It lists the risk measures an essential or important entity takes.
- **DORA**, Regulation (EU) 2022/2554, Articles 8 to 11, for financial entities. They cover identification, protection and prevention, detection, and response and recovery.
- **The OpenSSF OSPS Baseline**, version v2026.08.28, a control catalog for open-source projects. The registry marks it emerging.

A cell names only what aidd does, and an empty cell means the control is the adopter's. aidd evidences how each change was specified, tested, approved, and recorded, so it serves the process controls. The product's own properties, such as its encryption or its access control, come from the product's code and tests.

| Mechanism | CRA Annex I | NIS2 Art. 21(2) | DORA (EU) 2022/2554 Arts 8–11 | OSPS Baseline v2026.08.28 |
| --- | --- | --- | --- | --- |
| Spec with executable acceptance, Spec approval by hash (§5, §8) | Part II (3): each change is tested and reviewed before it merges | (e) security in development | Art. 9(4)(e): each change assessed and approved before it is built | |
| SHA-bound evidence, red-then-green (§7) | Part II (3) | (f) assessing whether the measures work: each result is an exit code on a known commit | Art. 9(4)(e): each change tested and verified | OSPS-QA-06.01: a test suite runs before a change is accepted |
| Scope via Task scope, route budgets (§4.2, §7) | | (e) | Art. 9(4)(e): each change assessed for its impact (`route_reasons`) | |
| Protected paths, base-branch config, trusted gate job (§6, §14) | | (d) supply chain security, for the agents' instructions, hooks, and CI | Art. 9(4)(e): changes to security parameters controlled | OSPS-AC-03.01, once the platform requires `aidd/gate`; OSPS-BR-01.03: pull request code runs with no privileged credential |
| SoD against the author, agents cannot approve (§8) | | (i) access control policies | Art. 9(4)(e): each change approved; RTS (EU) 2024/1774 Art. 17: approved by someone other than its author | |
| Policy and freeze with emergency break-glass (§13, §6) | Part II (2): an emergency fix lands without delay and is reviewed after | (b) incident handling | RTS (EU) 2024/1774 Art. 17: the emergency change recorded and reviewed | |
| Supply-chain rule, registry verification (§11) | Part II (1): the SBOM job of `aidd-security.yml`, when compliance is on | (d) | | OSPS-QA-02.01 and OSPS-BR-05.01: dependencies pinned by lockfile, with standard tooling |
| Untrusted-input rule, secrets rule (§11) | | (g) cyber hygiene, as agent guidance | | OSPS-BR-07.01: the secret scan of `aidd-security.yml` |
| Provenance trailers and `assisted_by` (§11) | | | Art. 9(4)(e): each change recorded | OSPS-QA-01.02: who made each change, and which agent |
| Roll out's observe window, rollback trigger, Learn (§12) | | (b), (f) | Art. 10: `aidd observe` runs the post-release check; Art. 11: the rollback plan and trigger | |
| Gate events and records retained (§12, [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)) | | (f) | Art. 9(4)(e): each change recorded | OSPS-QA-01.02 |

Notes:

- CRA Part I's properties are the product's, such as secure defaults in (2)(b), access control in (2)(d), and encryption in (2)(e). The `enterprise-controls` pack's checklist covers several when compliance is on, as guidance, never a check aidd runs.
- CRA Part II (4) to (8) are yours: disclosing fixed vulnerabilities, the disclosure policy, the contact address, and shipping updates. The pack's EC-18 checklist names the policy.
- NIS2 (a), (c), (h), and (j), and DORA Article 8, are yours. aidd keeps no asset register, no backups, and no keys.
- aidd assesses itself against the OSPS Baseline in [ENTERPRISE.md §14](ENTERPRISE.md#14-project-aidds-own-osps-baseline).

## What the record evidences

Every gate run writes a record, `aidd-record.json`, in the format [schemas/record.schema.json](../schemas/record.schema.json) defines. An auditor samples records against the controls above, and each field says what it evidences.

<!-- aidd:gen fields:record -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | `"1"` | no | `aidd gate --json` only: the version of the printed record, as for the other --json outputs. The file `--record` writes leaves it out; its `aidd_version` says which release wrote it. |
| `aidd_version` | string | yes | The aidd release whose gate judged the change, so the rules that applied are known. |
| `decision` | `decision` | yes | The verdict the gate posted: pass may merge, pending waits, fail blocks. |
| `failed_rules` | list of string | yes | Rules at fail level; `aidd gate --explain <rule>` states each one. |
| `pending_rules` | list of string | yes | Rules still waiting on a human or on evidence. |
| `findings` | list of mapping | no | Every finding, with the stable code that says which check fired. Messages are for people; codes are what tools and the conformance suite compare. |
| `change` | string or null | no | The PR/MR number or local ref under review. |
| `head_sha` | any | no | The exact commit judged. Evidence, approvals, and the posted status bind to it. |
| `base_sha` | string | no | The base commit the diff and the red run were measured against. |
| `platform` | string or null | no | github, gitlab, local, or another adapter. |
| `trusted` | boolean | no | Whether the platform supplied the facts (CI) or a local, untrusted context built them. A local record is never evidence. |
| `config_sha256` | string | no | Digest of the base-branch config with its org preset and parents: the policy in force when the change was judged. |
| `config_mode` | `enforce` \| `advisory` | no | The mode the base branch's resolved config sets, when it sets one. It wins over the CI setting. |
| `profile` | `profile` | no | The conformance profile that set the gate strictness. |
| `tenant` | string or null | no | The tenant the repository's config names (`tenant`), or null: whose Approvers this decision counted. |
| `spec` | string or null | no | The Spec path, or null for an inline change. |
| `specs` | list of mapping | no | A goal's change (the Change Request block's `specs`): each Spec it carries, as the gate judged it. `spec` and `spec_id` are null then. |
| `spec_id` | string or null | no | The Spec's id, or null for an inline change. |
| `trace_id` | string or null | no | The id that links this change to its Spec, its ticket, and sibling changes in other repositories: traceability. |
| `owner_team` | string or null | no | The team accountable for the Spec, from its `owner_team`. |
| `route` | `route` | no | The route applied, after the gate's own assessment. |
| `declared_route` | `route` | no | Present only when the gate raised the declared route (a normal Spec raised to major). |
| `required_route` | `route` | no | The minimum route the real diff requires; routes only go up. |
| `route_reasons` | list of string | no | Why that minimum: the rules and paths that raised it (impact analysis). |
| `required_pools` | list of string | no | The specialist Approver pools the change needs. |
| `type` | `type` | no | The kind of change, in Conventional Commits vocabulary. |
| `confidence` | `confidence` | no | The confidence the assessment declared; low stops the run. |
| `risk` | mapping (`risk`) | no | The declared blast radius and risk dimensions. |
| `rollback` | string | no | The declared back-out plan. |
| `residual_risk` | string or null | no | The risk that remains after the rollback plan, as declared. |
| `assisted_by` | list of string | no | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `scope` | list of string | no | The paths the change was allowed to touch. |
| `scope_declared` | boolean | no | Whether the scope was declared or taken from the changed paths (minor changes). |
| `declaration` | `block` \| `derived` | no | Where the change's declaration came from: `block`, a Change Request block; `derived`, none, so the gate took it from facts it checks: a bot's standard change class, the one Spec the diff carries, or else the route computed from the diff, the type from the commit subjects, and `assisted_by` from the commit trailers. |
| `revert_of` | string | no | An emergency that is an exact revert of this commit, merged on the base: it landed on the commander's approval alone. |
| `phase` | `spec` \| `implementation` | no | A Spec-backed change's phase: spec while every changed path is the Spec, its frozen test and design files, or its backfill, and a Task has yet to change anything (the gate waits for Spec approval, and failing tests are expected); implementation after. |
| `plan` | mapping | no | Plan adherence for a Spec: how many Tasks it planned, and which changed nothing in their scope. |
| `changed_paths` | list of string | no | Every path the change touched, as the platform reported it. |
| `changed_files` | integer | no | The number of changed files. |
| `changed_lines` | integer | no | Lines changed, as the changed-line limit counts them, excluding changed_lines_exclude_paths and the Spec's frozen files. |
| `binary_files` | integer | no | The number of binary files in the change; a binary file rules out the minor route. |
| `authors` | list of string | no | Everyone accountable for the change: the PR/MR author, every commit author and committer. No one in this list may approve it. |
| `separation_of_duties` | `enforced` \| `waived_solo` | no | Whether approvals had to come from outside the authors, or the solo profile waived it and recorded the waiver. |
| `spec_hash` | string | no | The 128-bit hash of the Spec, its test files, and its design files, as approved at Spec approval. |
| `spec_approved_by` | list of string | no | The Approvers of that exact hash: Spec approval, the authorization of what will be built. |
| `spec_approval_before_implementation` | boolean | no | Whether an approval named a commit holding only the Spec and its frozen files, proving Spec approval came before the code. |
| `approved_by` | list of string | no | The Approvers of the head commit: Merge approval, the authorization of what was built. |
| `spec_approvals` | list of mapping (`approval`) | no | Each counted Spec approval: who, when the approval comment was posted, and the commit it named (null when it named none). |
| `merge_approvals` | list of mapping (`approval`) | no | Each counted Merge approval: who, when, and the head commit it binds to. |
| `evidence_runner` | mapping | no | The CI run that produced the test evidence, as the evidence file names it (`ci`, `run_id`, `url`). |
| `specialist_approved_by` | mapping | no | Per required pool, the specialist Approvers who approved the head. |
| `policy` | string | no | The result of the organization's Policy command for this change. |
| `status_checks` | mapping | no | Existing CI check runs reused as evidence, with the state each had on the head. |
| `tests` | list of mapping | no | Each required test command's result on the head: an exit code from a defined runner, never a claim. |
| `shared_with` | string | no | Set when the head is shared with another pull request into a protected base and the worse decision was posted. |
| `merge_queue_sha` | string | no | Set when the decision is for a merge queue entry: the entry's commit whose tests ran and on which the status is posted. `head_sha` stays the pull request head the approvals bind to. |
<!-- aidd:end -->

The commit status posted by the gate App and the CI run log are the tamper-evident anchors for a record. The record itself is a workflow artifact, as [ENTERPRISE.md](ENTERPRISE.md#6-audit-evidence) explains.

## What aidd builds into the product when compliance is on

The tables above map how aidd controls *the change*. When compliance is on, the team also builds a control set into *the product*. Compliance is on with a `project.compliance` target, or under the audited profile ([ADOPTION.md](ADOPTION.md#compliance-ready-by-default)). The set comes from the [`enterprise-controls` pack](../plugins/aidd-team/skills/enterprise-controls/SKILL.md). The pack's [control reference](../plugins/aidd-team/skills/enterprise-controls/references/controls.md) gives each control's checklist per loop step and the SOC 2, ISO/IEC 27001:2022, and GDPR items it serves.

| Control | What the product does | How aidd makes it the default |
| --- | --- | --- |
| EC-01 Change management | every change approved, tested, and recorded | the gate (built) |
| EC-02 Input validation | allow-list validation, parameterized queries | the secure-coding default rules (built) |
| EC-03 Deny-by-default authorization | one policy point and an authorization matrix per auth surface | `aidd validate` warns without the matrix on auth paths when compliance is on |
| EC-04 Secrets in a manager | no secret in code, config, logs, or prompts | the secure-coding default rules; `aidd init` ignores environment files; gitleaks in the `secrets` job of `aidd-security.yml` (GitHub) or the `aidd-secrets` job of `aidd-security.gitlab-ci.yml` (GitLab) |
| EC-05 Secure architecture | written trust boundaries and fitness functions | the architect's overview and ADRs (built) |
| EC-06 Backup and restore | drilled restores within the RTO and RPO | `aidd doctor` warns on an undrilled restore runbook (built) |
| EC-07 Threat model | one per Spec on a security path | `aidd validate` warns without it on security and auth paths when compliance is on |
| EC-08 Scanning and SBOM | dependency scan, SAST, SBOM, dependency updates | `aidd init` writes `aidd-security.yml` when compliance is on and `dependabot.yml` always |
| EC-09 CI least privilege | read-only tokens, actions pinned by SHA, provenance | the templates `aidd init` writes |
| EC-10 Logging and security events | structured, redacted, with security events | the pack's checklist and tests |
| EC-11 Encryption | TLS with HSTS, encryption at rest, managed keys | the pack's checklist and tests |
| EC-12 Authentication hardening | SSO-ready, MFA, lockout, session timeout and rotation | the pack's tests; ASVS Level 2 on these surfaces |
| EC-13 Tenant isolation | cross-tenant access impossible | the multi-tenant pack |
| EC-14 Rate limiting | limits and anti-automation on every endpoint | the pack's checklist |
| EC-15 Audit log | who, what, when, which record; append-only | the pack's audit event test |
| EC-16 Access management | joiner, mover, leaver; periodic review; break-glass | the `enterprise-controls` pack's `references/readiness.md`; least privilege in code, `secure-coding` |
| EC-17 Incident response | a commander, evidence, and the breach-notification clock | the incident-response skill; `aidd validate` warns on overdue postmortem actions |
| EC-18 Vulnerability disclosure | a published policy and timed fixes, and under the `cra` target the CRA's Annex I Part II and Art. 14 reporting | `aidd new vulnerability-policy`; `aidd doctor` checks `security.txt` and its `Expires` |
| EC-19 Enterprise-deal items | SSO, SCIM, admin console, IP allowlisting, residency, SLA, trust center, VPAT | the pack's readiness checklist |

**Evidence by control.** `aidd record export records <record dirs> --by-control`, run at the repository root, reads each Spec's compliance doc. The `Control id` column of its Obligations table names the controls it serves, with commas between several. For each control id, it prints these, sorted so the same inputs give the same bytes:

- the obligations that name it
- the Specs that declare it
- every doc those Specs link, such as the threat model, the authorization matrix, and the runbook
- the gate records of those Specs

`unmapped_records` counts the records no control reaches. The output is JSON, [schemas/control-evidence.schema.json](../schemas/control-evidence.schema.json); `--out DIR` writes `DIR/controls.json`.

## DORA AI capabilities

The 2025 DORA AI Capabilities Model names seven capabilities that let AI adoption improve delivery rather than degrade it.

- aidd supplies four of them directly:
  - a clear and communicated AI stance, through `AGENTS.md`, the skill, and provenance trailers
  - strong version control practices, with every artifact in git, prompts as code, and SHA-bound evidence
  - working in small batches, through route budgets, one PR/MR per change, and short-lived branches
  - a quality internal platform, which the gate, the CLI, and the MCP tools make up
- The team plugin brings one more, the user-centric focus, through its product roles.
- You build the last two yourself, healthy data ecosystems and AI-accessible internal data.
