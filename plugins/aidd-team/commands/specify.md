---
description: "Specify a Spec with the architect, the product designer for user-facing changes, the security engineer and compliance analyst when risky, the SRE, and the tester, then prepare Spec approval"
disable-model-invocation: true
argument-hint: "<SPEC id or path>"
---

Loop step: **Specify**, ending at **Spec approval**. Spec lane only. `aidd gate --paths` gives the route before the first edit.

Lanes: spec.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route; you never edit an artifact yourself. Send a change to a Spec, a test, a proposal, or code to the role that owns the file. Pass on that role's handoff note.
2. Hand over file paths, not pasted facts: "read specs/SPEC-1.md and its latest handoff note", never a restatement of what a file already says.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report ran out of turns: never take silence as done; start it again on what is left, from the files it wrote, and after two silent runs ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions (METHOD §5.2, Who decides what), each on its evidence, never an approval. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Specify $ARGUMENTS as a team. Whoever writes the tests never makes them pass: the tester never implements, and no builder edits a test Spec approval froze.

Give each role one line per domain pack the change touches: "Load the `aidd-team:<pack>` skill with the Skill tool before your first edit." Once the architect has written the Spec's Context, the packs it names there are the list. A mention in prose does not load a skill.

When `docs.exemplars` in `.aidd/config.yaml` names the project's best Specs, tell each role that writes the Spec to read them first. `aidd context <ID> --step spec.draft` lists them. A role follows their shape and depth, and never copies their content.

1. Run `aidd gate --paths <planned paths>` (or `aidd gate` on a branch with a diff). When it says minor or standard, this is the fast lane: stop, and use `/aidd-team:fix` or `/aidd-team:implement` without a Spec. A production repair is the emergency lane, declared by the author, never computed: follow it instead.
2. **Small Spec.** A normal route with one Task and no specialist condition in step 5: run the `aidd-team:architect` and the `aidd-team:tester` subagents in parallel. The architect writes every section but Acceptance and `tests`. The tester writes the test files from the stub's acceptance intent and the planned paths. Once the architect has returned, the tester writes its Acceptance and `tests` into the Spec. For that, continue the same tester, or run it again with the Spec's path. There is no second pass for the architect. Go to step 8.
3. Otherwise run the `aidd-team:architect` subagent: scope, design, decisions, Tasks, risk, and rollback. It writes the planned paths as the Tasks' scope. It keeps the route at least what the gate computes. Before Spec approval, the team writes only the Spec and its tests. ADRs, threat models, and runbooks become documentation Tasks, written after Spec approval.
4. **Assign the Tasks.** The architect assigns each Task by artifact, never by stack:
   - `assignee: agent:developer` for application code of any layer
   - `agent:ml-engineer`, `agent:data-engineer`, `agent:platform-engineer`, or `agent:tech-writer`
   - a documentation Task a specialist planned goes to that specialist:
     - `agent:architect` for an ADR
     - `agent:security-engineer` for a threat model
     - `agent:compliance-analyst` for a DPIA or an evidence map
     - `agent:sre` for a runbook

   The architect names the domain packs the change touches in the Spec's Context. It puts the practice skill for each Task's kind of work in the Task's `skills` (`api-design`, `schema-migration`, `accessible-ui`, `ai-evals`, at most two). The guard then lets only that role write the Task's scope.
5. Run the specialists whose condition holds **in parallel**. Each runs as a reader that returns its part in its fixed template (the aidd skill's Spec reference, Specialist returns). On a normal route run only those, and the full fan-out only on major:
   - a user-facing surface: `aidd-team:product-designer` for the flow, every screen state, and copy in `design.files`, which Spec approval freezes with the Spec
   - major, a security, data, privacy, compliance, or third_party dimension, or an AI feature: `aidd-team:security-engineer`. It covers the threat model, the ASVS level, and the security tests it hands to the tester.
   - compliance or data dimensions, a audited profile, or an AI feature above the minimal EU AI Act tier: `aidd-team:compliance-analyst` for obligations, controls, and a DPIA plan
   - a domain pack named in the Spec's Context: `aidd-team:domain-expert` for the domain's rules, the cases the Spec misses, and the terms it uses wrongly, as a perspective card
   - major, or a profile that requires observe: `aidd-team:sre` for the SLO-based observe block, the rollback trigger, a runbook, and the pre-mortem
6. When a specialist ran, the architect folds each return into the section its template names, in one pass. It records the open questions that remain as assumptions in `## Context` (the aidd skill's Clarify rule). A question for the author carries a recommended answer and why, and a lookup answers the rest. When no specialist ran, skip this second pass.
7. Run the `aidd-team:tester` subagent, last and alone, on the folded Spec. It writes Acceptance, and tests for every condition and abuse case. It also writes visual, accessibility, and eval tests from the design and AI thresholds. It sees each new-behavior test failing on the current code. For a test whose name does not make its purpose plain, it writes a value card from `references/test-value.md` in the test-design practice skill, here and in step 2. When the Spec has a tech spec, the architect then copies each test's level and file from the tester's note into its Test strategy, in one edit.
8. Run `aidd validate` on the Spec. Loop back to the right role until it reports 0 errors.
9. Commit the Spec, its tests, and its design files, on the Spec's own branch from the base branch. Open a draft PR/MR with `spec: specs/<ID>.md` in the Change Request block (without a platform, keep the Spec, its tests, and its design files on the branch). Run `aidd hash <spec> --line`. From here to the approval, never rebase or amend: the line names this commit.
10. Give the author the approval line, and stop. Spec approval is a human decision, posted on the PR/MR or, without a platform, recorded by a person with `aidd approve spec`.
