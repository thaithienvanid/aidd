# Practice skills

A pack says what applies to a domain; a practice skill says how to do one kind of work well. Each is a hand-written playbook (`aidd-team:<name>`) in one template, in this order:

1. When to use it, and when not.
2. Its Standards: registry ids in `schemas/roles.json` `practices`, rendered by `aidd gen-docs`. A skill a role preloads lists each name and edition only; the checked date and source are in [roles.md](roles.md), Preloaded skills.
3. The loop steps it works in.
4. Its Test commands.
5. Stop if.
6. Hand off.

Each role lists the ones for its own work. The architect names the one for each Task's kind of work in the Task's `skills` (at most two). So a builder changing an endpoint loads `aidd-team:api-design` on top of the `aidd-team:apis-and-services` pack. Every practice skill carries a checked date, and every standard it names is a registry entry. So `aidd eval standards` flags one past its review, and the research-first rule covers a kind of work with no skill yet.

<!-- aidd:gen roles:practices -->
| Practice skill | Does | Roles that load it | Checked |
| --- | --- | --- | --- |
| `aidd-team:context` | read only what a step needs. Use in an aidd repository at the start of any step, or when a role re-reads files, runs out of context, or loses the thread of a change. | `product-manager`, `delivery-manager`, `architect`, `product-designer`, `security-engineer`, `compliance-analyst`, `domain-expert`, `developer`, `tech-writer`, `verifier`, `reviewer`, `sre`, `agile-coach` | 2026-10-29 |
| `aidd-team:diagrams` | explain a change as a Mermaid diagram. Use in an aidd repository when a Design, threat model, plan, or runbook needs a picture, or someone asks to draw the flow. | `product-manager`, `architect`, `product-designer`, `security-engineer`, `compliance-analyst`, `developer`, `tech-writer`, `sre`, `agile-coach` | 2026-10-22 |
| `aidd-team:estimation` | estimate effort or cost as a range. Use in an aidd repository when a proposal, plan, or budget needs a number, or someone asks how long or how much. | `product-manager`, `delivery-manager`, `architect` | 2026-10-22 |
| `aidd-team:plain-language` | write at the level the reader needs. Use in an aidd repository when a Task writes prose a person reads: docs, Specs, runbooks, messages, or client documents. | `product-manager`, `delivery-manager`, `product-designer`, `domain-expert`, `tech-writer`, `sre` | 2026-10-22 |
| `aidd-team:product-discovery` | frame the problem before building. Use in an aidd repository when planning an Initiative or Epic, slicing Specs, or judging whether a request is worth doing. | `product-manager`, `product-designer` | 2026-10-22 |
| `aidd-team:proposal` | write a proposal a person decides on. Use in an aidd repository when writing a bid, quote, statement of work, RFP answer, or business case. | `product-manager`, `delivery-manager`, `tech-writer` | 2026-10-22 |
| `aidd-team:support-desk` | triage incoming issues and report support. Use in an aidd repository for a bug report, support ticket, feedback, or a support report. | `product-manager`, `delivery-manager` | 2026-10-22 |
| `aidd-team:client-delivery` | run a client engagement from qualification to handover. Use in an aidd repository for a kickoff, RAID log, milestone, change order, or handover. | `delivery-manager` | 2026-10-22 |
| `aidd-team:adr` | record an architecture decision (MADR). Use in an aidd repository when a choice is hard to reverse, or someone asks X or Y, why we picked this, or for an ADR. | `architect`, `compliance-analyst`, `tech-writer`, `agile-coach` | 2026-10-22 |
| `aidd-team:api-design` | design or change an API contract first. Use in an aidd repository when a Task changes an endpoint, event, schema, webhook, or SDK, or someone says breaking change. | `architect`, `developer`, `reviewer` | 2026-10-22 |
| `aidd-team:caching` | cache a result without serving a wrong one. Use in an aidd repository when a Task adds or changes a cache, HTTP cache headers, a CDN rule, or memoization, or users see stale data. | `architect`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:data-access` | read and write a database correctly under concurrency. Use in an aidd repository when a Task writes in a transaction, locks rows, queues jobs in a table, or reads a replica. | `architect`, `developer`, `reviewer` | 2026-10-22 |
| `aidd-team:legacy-modernization` | replace a legacy system one slice at a time. Use in an aidd repository when a Task rewrites, ports, or migrates old code, data, or a cloud, or someone says strangler or cutover. | `architect`, `developer` | 2026-10-22 |
| `aidd-team:maintainable-code` | keep code readable as it grows. Use in an aidd repository when a Task grows a function, file, module, or package, writes a comment or docstring, or a diff's shape is reviewed. | `architect`, `developer`, `reviewer` | 2026-10-22 |
| `aidd-team:modular-monolith` | one deployable, split into modules with enforced boundaries. Use in an aidd repository on a new project, or when a Task adds a module or changes its API, events, or data. | `architect`, `developer` | 2026-10-22 |
| `aidd-team:naming` | choose, check, or improve a name. Use in an aidd repository when a Task names a module, type, file, column, event, flag, metric, component, token, or label, or a name misleads readers. | `architect`, `product-designer`, `developer`, `tech-writer`, `verifier`, `reviewer` | 2026-10-22 |
| `aidd-team:observability` | make a change observable, with a rollback trigger. Use in an aidd repository when writing an observe block, adding logs, metrics, traces, or alerts, or a release. | `architect`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:performance` | make a change fast enough, against a budget. Use in an aidd repository when a Spec touches a hot path, a Task has a latency or load goal, or something is slow or times out. | `architect`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:release-rollout` | roll out progressively and undo it. Use in an aidd repository for a release, a feature flag or kill switch, an A/B test, a canary, a staged rollout, or a rollback. | `architect`, `developer`, `verifier`, `sre` | 2026-10-22 |
| `aidd-team:resilience` | recover each failure exactly once. Use in an aidd repository when a Task calls a service, queue, provider, or job, or someone says retries, timeouts, or duplicates. | `architect`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:schema-migration` | change a schema, data contract, or pipeline safely. Use in an aidd repository when a Task adds a migration, column, index, event schema, or backfill. | `architect`, `developer` | 2026-10-22 |
| `aidd-team:system-design` | design from measured goals and compared options. Use in an aidd repository when a Spec's Design adds a component, a data store, a queue, or a service, or meets a new scale goal. | `architect` | 2026-10-27 |
| `aidd-team:accessible-ui` | build and check accessible UI (WCAG 2.2 AA). Use in an aidd repository when a Task changes a screen, form, or UI copy, or someone says a11y, focus, or contrast. | `product-designer`, `developer`, `verifier`, `reviewer` | 2026-10-22 |
| `aidd-team:product-defaults` | build what `project.defaults` leaves on, each with its test. Use in an aidd repository on Day 0 or when a Task touches a default. | `product-designer`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:prototyping` | build an interactive prototype for Spec approval. Use in an aidd repository when a user-facing Spec needs a clickable flow, not just a wireframe. | `product-designer` | 2026-10-22 |
| `aidd-team:ai-evals` | prove an AI feature with evals. Use in an aidd repository when a Task changes a prompt, model call, RAG, agent, or guardrail, or answers got worse. | `security-engineer`, `developer`, `verifier` | 2026-10-22 |
| `aidd-team:dependency-upgrade` | upgrade one dependency at a time. Use in an aidd repository when a Task bumps a package, runtime, image, or lockfile, a bot PR arrives, or a CVE lands. | `security-engineer`, `developer`, `sre` | 2026-10-22 |
| `aidd-team:secure-coding` | write and change code securely. Use in an aidd repository when a Task handles input, auth, secrets, config, files, SQL, shell, or crypto, or on any Implement Task. | `security-engineer`, `developer`, `reviewer` | 2026-10-22 |
| `aidd-team:threat-model` | threat-model a change before code exists. Use in an aidd repository when a Spec touches auth, personal data, secrets, a trust boundary, or an AI feature. | `security-engineer`, `compliance-analyst` | 2026-10-22 |
| `aidd-team:technical-writing` | write docs humans and agents can use. Use in an aidd repository when a Task changes docs, a README, a changelog, release notes, or AGENTS.md. | `compliance-analyst`, `tech-writer`, `agile-coach` | 2026-10-22 |
| `aidd-team:test-design` | turn Acceptance into tests before code. Use in an aidd repository when writing or reviewing a Spec's tests, or someone asks what to test or says tests are flaky. | `domain-expert`, `developer`, `verifier`, `reviewer` | 2026-10-22 |
| `aidd-team:concurrency` | run work in parallel and share state without races. Use in an aidd repository when a Task adds threads, async tasks, goroutines, or shared state, or a bug shows only under load. | `developer`, `reviewer` | 2026-10-22 |
| `aidd-team:debugging` | find a failure's cause by experiment first. Use in an aidd repository when a test fails, a bug is reported, something is flaky, or someone says it broke. | `developer`, `sre` | 2026-10-22 |
| `aidd-team:code-review` | review a diff against its Spec. Use in an aidd repository when reading a PR/MR as a reviewer, or someone asks to review a diff or whether it is ready to merge. | `reviewer` | 2026-10-22 |
| `aidd-team:ci-pipeline` | change CI, CD, or build pipelines safely. Use in an aidd repository when a Task touches a workflow, build script, Dockerfile, release job, or IaC, or CI is red. | `sre` | 2026-10-22 |
| `aidd-team:incident-response` | run a live incident until service is back. Use in an aidd repository when production is down or degraded, an alert fires, or a breach is suspected. | `sre` | 2026-10-22 |
<!-- aidd:end -->
