---
name: aidd-team
description: "In an aidd repository, run a team flow: plan, propose, MVP, onboard, specify, implement, fix, review, rollout, handover, postmortem, retro, autopilot, or a mode (refine, explore, rework, upkeep); or one names a role (product-manager, delivery-manager, architect, product-designer, security-engineer, compliance-analyst, developer, tech-writer, verifier, reviewer, delegate, sre)."
license: "Apache-2.0"
metadata:
  version: "1.0.0"
---

# aidd-team

The aidd skill is the rulebook; this skill only decides who does each step of its loop. Each role is a subagent that works only in its loop steps and writes only its own files. Before an action, a role checks its risk rule with `aidd risk` or the MCP `risk` tool. On `ask`, it stops and hands the question to the lead, who asks the person.

<!-- aidd:gen roles:loop:diagram -->
```mermaid
flowchart TD
  accTitle: The loop, its roles, and the human approvals
  accDescr: Three rows, top to bottom: before any code, build and prove, and merge, roll out, and learn. Each step names the roles that work in it, each hexagon is a point where a person decides, and each dashed line is a path a person sends work back on.
  subgraph before["Before any code: with no Spec, go to Implement"]
    direction LR
    Plan["Plan<br/><i>product-manager,<br/>delivery-manager,<br/>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>tech-writer, sre</i>"]
    IA{{"Intent agreement"}}
    Specify["Specify<br/><i>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>tech-writer, verifier,<br/>delegate, sre</i>"]
    SA{{"Spec approval"}}
    Plan --> IA --> Specify --> SA
    SA -.->|"changes requested"| Specify
  end
  subgraph build["Build and prove"]
    direction LR
    Implement["Implement<br/><i>architect,<br/>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>developer, tech-writer,<br/>sre</i>"]
    Verify["Verify<br/><i>verifier</i>"]
    Review["Review<br/><i>product-designer,<br/>security-engineer,<br/>compliance-analyst,<br/>reviewer, delegate</i>"]
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
    Learn["Learn<br/><i>product-manager, sre</i>"]
    Merge --> PR --> Roll_out
    Roll_out -.->|"incident, rollback,<br/>missed hypothesis"| Learn
    Plan_again(["back to Plan"])
    Learn -.->|"a new change"| Plan_again
  end
  before --> build
  build --> run
  classDef default fill:#7a787433,stroke:#7a7874,stroke-width:1px
  classDef group fill:#7a787414,stroke:#7a7874
  class before,build,run group
  classDef human fill:#4d4b47,stroke:#7a7874,stroke-width:2px,color:#fafaf9
  class IA,SA,MA,PR human
  linkStyle 3,9,12,13 stroke-width:2px,stroke-dasharray:6 4
```

Legend: a dark hexagon is a point where a person decides, and a dashed line is a path a person sends work back on.
<!-- aidd:end -->

Each role's steps, write area, handoff, and standards: [references/roles.md](references/roles.md). Living work: [references/living-work.md](references/living-work.md). Workers under Orca: [references/orca-channel.md](references/orca-channel.md).

## Who does what

A person starts each command; asked for a flow in words, name it. Each command runs its flow's roles in order, and stops where a human decides. The session that runs a command is the lead. It places each role: it plays only a role that adds a view to its own work, never one that checks it, and starts the rest. It names each role's model and starts fresh each command. At each launch and finish, it tells the person where the work stands (the aidd skill's Talk to the person). The flows and the handoffs, as tables: [references/flows.md](references/flows.md).

## Handoffs

Every handoff is a file plus the note the loop contract requires (also an `aidd-handoff` block in the Spec or PR/MR). The note holds `done`, `next_role`, `needs` (what only a human can give, or `none`), `stopped_at`, and `spend`, and `open_decisions` when the role leaves a choice for the lead. The next role reads the note, then the file. A read-only role returns its note in its last message; the lead posts it. Who hands what to whom: [references/flows.md](references/flows.md).

Three rules keep it fast:

1. **One writer per file.** In Specify the architect holds the Spec. The specialists return their parts in fixed templates, or write their own doc with `aidd new <type> <topic> --spec <ID> --no-link`, which the architect links in `docs`. In Implement each Task's assignee holds its scope.
2. **Readers run in parallel.** In Review the reviewer, the security engineer, and the product designer read at once. In Roll out the SRE and the compliance analyst do. The command that ran them merges their reports.
3. **Escalate through Needs; never guess.** A question only a human can answer goes on the note's Needs line, and the role stops. No one re-derives a fact the file holds.

## Domain packs

Every domain has a pack, a skill `aidd-packs:<pack>` of the optional aidd-packs plugin, with its standards, a checklist per loop step, and test commands for the Spec. Load one per domain the change touches, by the name that `aidd risk --paths`, the config, or the lead gives. A business pack starts no role: the role that loads it checks the work against its rules, missed cases, and Terms. No pack (the plugin is not enabled here, or no pack covers the domain), or a standard due for review (emerging every 90 days, established every year): the research-first rule applies. The list of packs and when each applies: [references/domain-packs.md](references/domain-packs.md).

## Practice skills

A practice skill (`aidd-team:<name>`) says how to do one kind of work well. The architect names at most two in each Task's `skills`. The list and which roles load each: [references/practice-skills.md](references/practice-skills.md).

## Extending a role

A skill, plugin, MCP server, or tool the project already uses extends a role once verified, pinned, and installed through a change. An extension never widens a write area or answers an `ask`. Per role: [references/extensions.md](references/extensions.md).

## Rules

1. **Spec first, the verifier and the builder are different agents.** Whoever writes a frozen test never makes it pass. With no Spec, or on the emergency route, nothing is frozen and the verifier only verifies. There the developer writes the regression test with the fix, sees it red on base, and names that run on its handoff: `aidd test` runs none without a Spec. An emergency's backfill Spec holds it. No reviewer reviews its own work. With `agents.independent_review` on, the verifier and reviewer run on another provider than the developer ([Independent review](references/flows.md)).
2. **Files, not chat.** Roles hand off through files and the note, never chat alone.
3. **The contract holds.** Each agent file carries the contract rules that bind its role (all of them: [references/roles.md](references/roles.md)). Every stop in the aidd skill still stops the team.
4. **No approvals.** No role approves, merges, or declares a route below what `aidd risk` advises. On a person's yes, the lead acts. Under a delegation, it acts on the delegate's accept too.
5. **Subagents inherit.** A role may delegate its own work to subagents of its own type, terminals, or worktrees. They inherit its step, its area, and the loop contract, and never decide an approval. A helper only reads, and only the lead starts another role. A read-only role works alone.
6. **Few agents with no Spec.** A small minor change of any type runs one builder, and the reviewer past 20 changed lines (`/aidd-team:fix`); every other change with no Spec runs the builder, the verifier, and the reviewer.
7. **Parallel by scope, serial by queue.** Run Tasks with disjoint scope in parallel after the first Task lands green, each in its own worktree ([Parallel Tasks](references/flows.md)), and specialists and readers in parallel. Keep no more slices in flight than review keeps up with, nor more open changes than a person decides today.
8. **Priced to value.** A role's model `tier` follows the cost of its mistakes: `reasoning` (the strongest) is for roles whose judgment no test checks. `execution` is for the rest, the verifier included, where the tests, the review, or a human catch their mistakes. `inherit`, or any model by name, is opt-in per tier or role in `agents.models`. Change a tier only on `aidd eval roles` or a retrospective.
9. **Proven over new.** A role applies an emerging standard, extension, or unlisted tool only when the change needs it, and says so in the Spec.
10. **Work with what the project has.** Use another service only when the project's own settings enable it.
11. **Explain visually where a picture earns its place.** A Spec's Design, a threat model, a plan, or a runbook gets a Mermaid diagram where prose falls short.
