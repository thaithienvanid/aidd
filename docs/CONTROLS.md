# Control mapping

How aidd's mechanisms support common frameworks. This is guidance for your auditors, not a certification: a mechanism listed against a control contributes evidence toward it, and each organization maps its own control IDs and decides what satisfies them. References are to `docs/METHOD.md`; which mechanisms the gate enforces and which are guidance is in [METHOD.md §11](METHOD.md#11-ai-era-security-controls).

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
| Ship's observe window, rollback trigger, Learn (§12) | RV.2, RV.3 (analyze root causes) | | A.6.2.6 operation and monitoring | Art. 72 post-market monitoring |
| Gate events and records retained (§12, [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)) | PO.3.3 (audit trail), PS.3 | | Clause 9 performance evaluation, A.6.2.8 event logs | Art. 12, Art. 19 logs |

General frameworks:

| Mechanism | SOC 2 | SLSA / DORA | ISO/IEC 27001:2022, PCI DSS v4.0.1, NIST SP 800-53r5 |
| --- | --- | --- | --- |
| Spec with executable acceptance, Spec approval by hash (§5, §8) | CC8.1 change authorization | | A.8.32 change management; PCI 6.5.1 (documented approval before the change); 800-53 CM-3 |
| SHA-bound evidence, red-then-green (§7) | CC8.1 testing | SLSA-style: evidence produced by a defined CI runner | A.8.29 security testing in development and acceptance; PCI 6.5.1 (testing before deployment); 800-53 SA-11 |
| Scope via Task scope, route budgets (§4.2, §7) | CC8.1 | | A.8.32; PCI 6.5.1; 800-53 CM-4 impact analysis |
| Protected paths, base-branch config, trusted gate job (§6, §14) | CC6.1, CC8.1 | SLSA: source and build integrity | A.8.9 configuration management, A.8.32; PCI 6.5.1; 800-53 CM-5 access restrictions for change |
| SoD against the author, agents cannot approve (§8) | CC8.1, CC1.3 | | A.5.3 segregation of duties; PCI 6.5.1 (approval by authorized parties); 800-53 AC-5 |
| Policy and freeze with emergency break-glass (§13, §6) | CC8.1, CC7.4 | DORA: change fail rate, failed deployment recovery time | A.8.32 (emergency changes recorded and reviewed); PCI 6.5.1 (back-out procedures); 800-53 CM-3 |
| Supply-chain rule, registry verification (§11) | CC9.2 | pinned dependencies (lockfiles) | A.5.21 ICT supply chain, A.8.28 secure coding; PCI 6.3.2 (component inventory); 800-53 SR-3 |
| Untrusted-input rule, secrets rule (§11) | CC6.1 | | A.8.28 secure coding; PCI 6.2.4; 800-53 SI-10 input validation |
| Provenance trailers and `assisted_by` (§11) | CC2.1 | supports provenance: unsigned commit trailers record which agent wrote a change; they are not SLSA provenance, which is a signed build attestation | A.8.25 secure development life cycle; PCI 6.3.2; 800-53 SA-8 |
| Ship's observe window, rollback trigger, Learn (§12) | CC7.2 to CC7.5 | DORA: `aidd metrics --dora` reports proxies for the five metrics against `[targets]`, with `--specs` for change fail rate and recovery time | A.8.16 monitoring, A.5.27 learning from incidents; PCI 6.5.2 (confirmation after a significant change); 800-53 IR-4 |
| Gate events and records retained (§12, [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)) | CC4.1, CC7.2 | the source of the DORA proxies in `aidd metrics --dora` | A.8.15 logging, A.5.28 collection of evidence; PCI 10.5.1 (retention); 800-53 AU-3, AU-11 |

Notes:

- The OWASP LLM Top 10 column uses the 2026 edition, the one the standards registry records: LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Excessive Agency, LLM04 Supply Chain, LLM07 Misinformation, and LLM10 Improper Output Handling. The 2025 edition numbered several of these differently (Excessive Agency was LLM06, Supply Chain LLM03, Misinformation LLM09, Improper Output Handling LLM05), so check which edition a control ID in your own mapping uses.
- The untrusted-input rule and the secrets rule are process: agent guidance, not a gate.
- The observe window, the rollback trigger, and Learn are process, not tool: aidd records the plan, and `aidd observe` runs one check; your release tooling watches and rolls back.
- The EU AI Act mostly places obligations on AI system *providers* and *deployers*. aidd helps a software organization evidence human oversight and record-keeping for AI-assisted development; it does not classify your product under the Act.
- For NIST SP 800-218A, treat `assisted_by`, evidence, and gate records as the development-time artifacts for AI-generated code.

## What the record evidences

Every gate run writes a record (`aidd-record.json`, [schemas/record.schema.json](../schemas/record.schema.json)). An auditor samples records against the controls above; each field says what it evidences.

<!-- aidd:gen fields:record -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The verifier release that judged the change, so the rules that applied are known. |
| `decision` | `decision` | yes | The verdict the gate posted: pass may merge, pending waits, fail blocks. |
| `failed_rules` | list of string | yes | Rules at fail level; `aidd gate --explain <rule>` states each one. |
| `pending_rules` | list of string | yes | Rules still waiting on a human or on evidence. |
| `findings` | list of table | no | Every finding, with the stable code that says which check fired. Messages are for people; codes are what tools and the conformance suite compare. |
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
| `spec_id` | string or null | no | The Spec's id, or null for an inline change. |
| `trace_id` | string or null | no | The id that links this change to its Spec, its ticket, and sibling changes in other repositories: traceability. |
| `owner_team` | string or null | no | The team accountable for the Spec, from its `owner_team`. |
| `route` | `route` | no | The route applied, after the gate's own assessment. |
| `declared_route` | `route` | no | Present only when the gate raised the declared route (a normal Spec raised to major). |
| `required_route` | `route` | no | The minimum route the real diff requires; routes only go up. |
| `route_reasons` | list of string | no | Why that minimum: the rules and paths that raised it (impact analysis). |
| `required_pools` | list of string | no | The specialist reviewer pools the change needs. |
| `type` | `type` | no | The kind of change, in Conventional Commits vocabulary. |
| `confidence` | `confidence` | no | The confidence the assessment declared; low stops the run. |
| `risk` | table (`risk`) | no | The declared blast radius and risk dimensions. |
| `rollback` | string | no | The declared back-out plan. |
| `residual_risk` | string or null | no | The risk that remains after the rollback plan, as declared. |
| `assisted_by` | list of string | no | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `scope` | list of string | no | The paths the change was allowed to touch. |
| `scope_declared` | boolean | no | Whether the scope was declared or taken from the changed paths (minor changes). |
| `plan` | table | no | Plan adherence for a Spec: how many Tasks it planned, and which changed nothing in their scope. |
| `changed_paths` | list of string | no | Every path the change touched, as the platform reported it. |
| `changed_files` | integer | no | The number of changed files. |
| `changed_lines` | integer | no | Lines changed inside the budget, excluding budget_exclude_paths and the Spec's frozen files. |
| `binary_files` | integer | no | The number of binary files in the change; a binary file rules out the minor route. |
| `authors` | list of string | no | Everyone accountable for the change: the PR/MR author, every commit author and committer. No one in this list may approve it. |
| `separation_of_duties` | `enforced` \| `waived_solo` | no | Whether approvals had to come from outside the authors, or the solo profile waived it and recorded the waiver. |
| `spec_hash` | string | no | The 128-bit hash of the Spec, its test files, and its design files, as approved at Spec approval. |
| `spec_approved_by` | list of string | no | The Approvers of that exact hash: Spec approval, the authorization of what will be built. |
| `spec_approval_before_implementation` | boolean | no | Whether an approval named a commit holding only the Spec and its frozen files, proving Spec approval came before the code. |
| `approved_by` | list of string | no | The Approvers of the head commit: Merge approval, the authorization of what was built. |
| `spec_approvals` | list of table (`approval`) | no | Each counted Spec approval: who, when the approval comment was posted, and the commit it named (null when it named none). |
| `merge_approvals` | list of table (`approval`) | no | Each counted Merge approval: who, when, and the head commit it binds to. |
| `evidence_runner` | table | no | The CI run that produced the test evidence, as the evidence file names it (`ci`, `run_id`, `url`). |
| `specialist_approved_by` | table | no | Per required pool, the specialist reviewers who approved the head. |
| `policy` | string | no | The result of the organization's Policy command for this change. |
| `status_checks` | table | no | Existing CI check runs reused as evidence, with the state each had on the head. |
| `tests` | list of table | no | Each required test command's result on the head: an exit code from a defined runner, never a claim. |
| `shared_with` | string | no | Set when the head is shared with another pull request into a protected base and the worse decision was posted. |
| `merge_group_sha` | string | no | Set when the decision is for a merge-queue entry: the merge-group commit whose tests ran and on which the status is posted. `head_sha` stays the pull request head the approvals bind to. |
<!-- aidd:end -->

The commit status posted by the gate App and the CI run log are the tamper-evident anchors for a record; the record itself is a workflow artifact ([ENTERPRISE.md](ENTERPRISE.md#6-audit-evidence)).

## DORA AI capabilities

The DORA AI Capabilities Model (2025) names seven capabilities that let AI adoption improve delivery rather than degrade it.

- aidd supplies four of them directly:
  - a clear and communicated AI stance: `AGENTS.md`, the skill, provenance trailers
  - strong version control practices: every artifact in git, prompts as code, SHA-bound evidence
  - working in small batches: route budgets, one PR/MR per change, short-lived branches
  - a quality internal platform: the gate, the CLI, and the MCP tools
- One comes with the team plugin: the user-centric focus, through its product roles.
- Two are yours to build: healthy data ecosystems, and AI-accessible internal data.
