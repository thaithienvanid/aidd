---
description: "Build an MVP from a brief: a one-screen plan of vertical slices, a Day-0 baseline, a walking skeleton, the other slices in parallel worktrees, and a launch review, with a person deciding at each stop"
disable-model-invocation: true
argument-hint: "<the brief>"
---

Loop steps: **Plan**, **Specify** where a slice needs a Spec, **Implement**, **Verify**, **Review**, and a launch review before **Roll out**.

Lanes: fast, spec. Each slice takes the lane `aidd risk --paths` gives it; run only the roles whose lanes include it. The routes and the risk rules are the same as for any other change.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Read its agent file, and keep to its area until the step ends. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary: the Spec, its linked docs, and the files by path. Name the practice skills for the files it writes, except one its agent file preloads, and it loads them before it writes those files: for code, `maintainable-code` and `secure-coding`; for docs, `plain-language`; for a UI, `accessible-ui`. It returns its work in the file it owns, or a part another role folds in `.aidd/returns/<ID>/<role>.md`, and names that file on its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act on their work. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with a handoff note that `aidd validate` passes: every required key, no other key, and `stopped_at` starting with a stop code. Include its Spend line, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never a person's: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. A role's `ask` comes to you: ask the person in plain words, and on their yes, do the action. A proposed edit comes as a unified diff in `.aidd/returns/`, which the person reads and you `git apply` on the yes. Spec approval covers `code.edit` in its Tasks' `scope`, so it asks no more there. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`spec.revise`), or a production repair (the emergency route).
9. Under a standing delegation in Claude Code, run `aidd delegate check` before a delegated ask. On `eligible`, start aidd-team:delegate with the action, the command the check covered, and the head, and nothing else. Act only on its accept: run that exact command, or commit the Spec's approval with the check's three trailers, never `Approved-by`. On a defer, ask the person, once. Never answer for the delegate.
<!-- aidd:end -->

Build the MVP for $ARGUMENTS. Each part below is a stop: go on only when the person has decided. In a new session, find the part from the files: no Intent is part 1, no baseline on the default branch is part 2, and each slice's stage says where it stands.

1. **The plan.** Run the `aidd-team:product-manager` subagent on the brief. It writes a one-screen plan in an Intent (`aidd new intent`) beside the brief, never over it, with:
   - the outcome
   - the riskiest assumption, and how the first slices test it
   - vertical slices sized to the brief, in phases, skeleton first: one slice for a brief as small as one endpoint, five to ten for a real product. Each slice is one end-to-end line with its outcome, and gets its Spec when its work starts, with what the earlier ones taught.
   - a hardening slice right after the skeleton, only when the brief needs one: the abuse cases, the full accessibility matrix, and the evals in CI, where each applies
   - the non-goals

   A one-slice plan skips the ADR and the design directions of Day 0 unless the brief needs them, such as a stack it leaves open or a screen. Stop until the person agrees to the Intent (`intent.agree`).
2. **Day 0.** Switch to a new `day0` branch from the default branch, where every Day-0 role writes and commits its own files, never in `/tmp`. Run these subagents in parallel, each one the agreed plan needs:
   - the `aidd-team:architect` subagent, for the stack decision in the ADR template (its adr practice skill) and the architecture overview (`aidd new architecture`, `docs/architecture/README.md`). Unless `project.defaults` turns `modular_monolith` off, the stack is a modular monolith in one repository, and the overview holds its module map (its modular-monolith practice skill).
   - the `aidd-team:product-designer` subagent, for two or three rough directions. Once the person has picked one, it drafts `DESIGN.md` and `design/tokens.json` (in the shape of `aidd new design-system`) from the picked direction.

   Each writes its product-level files itself, the area its agent file names, and lists them on its handoff note. Nothing reaches the default branch before the person's yes to the baseline.

   Then run the `aidd-team:sre` subagent. On the stack the ADR names, it builds the scaffold: the framework generator's output, the lockfile, the test runner, and a first passing test. It adds the product defaults that `project.defaults` in the config leaves on, each with its test (its product-defaults practice skill). It adds only those that fit the kind of product, such as a web app, a mobile app, a CLI, or a library. For a web app:
   - the `apps/`, `modules/`, and `packages/` layout, with the boundary check in CI
   - the formatter, linter, type check, and pre-commit hook, with an `.editorconfig`
   - the security headers and cookie settings
   - the health endpoint and readiness check
   - the designed error pages (404, 500, maintenance)
   - the theme toggle (system, light, dark, on the design system's two token sets)
   - the privacy policy and terms placeholders a person writes

   It skips a default set false, with the config's reason on the note. Then it adds the one-command local preview with seed data (a Compose file or a script). It names the preview command on its handoff note, and writes the config's `preview` entry as a diff in `.aidd/returns/day0/`, which you apply on the person's yes. It adds a hosted preview only if the project already has hosting and the person needs to click it. It writes the CI workflow too, in the `ci` area, and reports each CI edit on its note.

   The architect's ADR is `docs/adr/0001-stack.md`. The SRE's handoff note names the practice skills it loaded. Then run the `aidd-team:verifier` subagent (the preview command from the SRE's note, on a clean checkout of the `day0` head, and its health check) and the `aidd-team:reviewer` subagent (the baseline's diff) in parallel. A finding goes back to the SRE, and both run again on the new head. Once both are clean, start the preview, and give the person its URL and what to try. Then ask one question in numbered rows: merge the whole as the Day-0 baseline on the default branch, never through a Spec, and set the config's `preview` to the SRE's command. Say each row in plain words, never as a diff. On their yes, apply the diff and merge. This follows the aidd skill's scale reference for a new repository. Stop until the baseline is merged.
3. **Slice 1, the walking skeleton.** The smallest end-to-end path through the stack. The target is something to click on Day 1, so keep it thin:
   - one happy path, at most three Tasks and six Acceptance items (`aidd validate` warns past that)
   - a specialist's further concern (more states, an abuse suite, an accessibility matrix) goes to the hardening slice or a later one, unless it blocks the skeleton
   - no refactor or rename Task: a refactor is its own change
   - its first Task (`skeleton: true`) builds the structure, the contracts, the test runner, CI, and one smoke test. The architect or the SRE builds it, and the later slices fan out against it

   `aidd risk --paths` gives its lane:
   - With no Spec, run the `aidd-team:developer` subagent tests-first (the test red on base, then green).
   - When it needs a Spec, `aidd new spec <ID>` writes it from the slice's line. Run `/aidd-team:specify`, whose step 2 runs the lightest Specify the skeleton's risk allows. The verifier writes only the acceptance tests, and the developer writes the unit tests with the code and never edits the frozen ones. Stop at Spec approval. After the person's yes, run `/aidd-team:implement`.

   Once the skeleton's acceptance tests pass, start the local preview, and tell the person its URL and what to click. Keep it running through Merge approval. Report the hours from the agreed plan to that first click, the time to first usable, against the Day-1 target. Then run the `aidd-team:verifier` subagent (the local preview, with its screenshots under `.aidd/evidence/preview/`) and the `aidd-team:reviewer` subagent on the head in parallel. Stop at Merge approval.
4. **Slices 2 to n.** Take the next slices whose scopes are disjoint, two or three at a time and never more than review keeps up with, each in its own worktree. Make one Agent call per slice with `isolation: "worktree"`, all launched in one message. Each slice runs as slice 1 did, and ends by telling the person what to click in the local preview. A specialist joins only when `aidd risk --paths` names its area:
   - the security engineer for auth, secrets, payments, or AI
   - the product designer for a new user-facing flow

   Each slice merges on the person's yes to its Merge approval, one at a time. Never merge a slice without that yes, and never leave the person more open changes than they can decide today.
5. **Launch review.** Run these subagents in parallel:
   - `aidd-team:security-engineer`: a threat review of the whole app, not one diff
   - `aidd-team:sre`: the SLO, the observe signals, the rollback steps and trigger

   Show the person both, with the open findings and the rollback plan, and stop: the launch is the person's decision, and so is running the rollback.
