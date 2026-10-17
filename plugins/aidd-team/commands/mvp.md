---
description: "Build an MVP from a brief: a one-screen plan of vertical slices, a Day-0 baseline, a walking skeleton, the other slices in parallel worktrees, and a launch review, with a person deciding at each stop"
disable-model-invocation: true
argument-hint: "<the brief>"
---

Loop steps: **Plan**, **Specify** where a slice needs a Spec, **Implement**, **Verify**, **Review**, and a launch review before **Ship**.

Lanes: fast, spec. Each slice takes the lane the gate gives it (`aidd gate --paths`); run only the roles whose lanes include it. The gate's routes and rules are the same as for any other change.

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

Build the MVP for $ARGUMENTS. Each stage below is a stop: go on only when the person has decided.

1. **The plan.** Run the `aidd-team:product-manager` subagent on the brief. It writes a one-screen plan in an Initiative (`aidd new initiative`) with:
   - the outcome
   - the riskiest assumption, and how the first slices test it
   - five to ten vertical slices, ordered skeleton first, each an end-to-end Spec stub
   - a hardening slice right after the skeleton: the abuse cases, the full accessibility matrix, the evals in CI
   - the non-goals

   Stop until the person agrees to the plan.
2. **Day 0.** Run these subagents in parallel:
   - the `aidd-team:architect` subagent, for the stack decision in the ADR template (its decision-record practice skill) and the architecture overview (`aidd new architecture`, `docs/architecture/README.md`). Unless `project.defaults` turns `modular_monolith` off, the stack is a modular monolith in one repository, and the overview holds its module map (its modular-monolith practice skill).
   - the `aidd-team:product-designer` subagent, for two or three rough directions. Once the person has picked one, it writes `DESIGN.md` and `design/tokens.json` (`aidd new design-system`) from the picked direction.

   Each returns its files on its handoff note. No Spec is active yet, so the guard keeps those paths closed to them.

   Then run the `aidd-team:platform-engineer` subagent. On the stack the ADR names, it builds the scaffold: the framework generator's output, the lockfile, the test runner, and a first passing test. It adds the product defaults that `project.defaults` in the config leaves on, each with its test (its product-defaults practice skill):
   - the `apps/`, `modules/`, and `packages/` layout, with the boundary check in CI
   - the theme toggle (system, light, dark, on the design system's two token sets)
   - the security headers and cookie settings
   - the health endpoint and readiness check
   - the designed error pages (404, 500, maintenance)
   - the privacy policy and terms placeholders a person writes
   - the formatter, linter, type check, and pre-commit hook, with an `.editorconfig`

   It skips a default set false, with the config's reason on the note. Then it adds the one-command local preview with seed data (a Compose file or a script), named in the config's `preview` for the verifier. It adds a hosted preview only if the client already has hosting and needs to click it. CI files are protected paths, so it hands the CI workflow over on its note rather than writing it.

   The person adds the ADR as `docs/adr/0001-stack.md`, the overview, the design system, and the workflow. The person commits the whole as the Day-0 baseline on the default branch, never through a Spec, and merges it. This follows the aidd skill's scale reference for a new repository. Stop until the person has merged the baseline.
3. **Slice 1, the walking skeleton.** The smallest end-to-end path through the stack, kept thin so the person sees it run within the day:
   - one happy path, at most three Tasks and six Acceptance items (`aidd validate` warns past that)
   - a specialist's further concern (more states, an abuse suite, an accessibility matrix) goes to the hardening slice or a later one, unless it blocks the skeleton
   - no refactor or rename Task: a refactor is its own change
   - its first Task (`skeleton: true`) builds the structure, the contracts, the test runner, CI, and one smoke test. The architect or the platform engineer builds it, and the later slices fan out against it
   - a slice of new code with nothing to break (no risk dimension, below major) may set `tests.mode: with`: the developer writes its tests with the code, and every Acceptance id needs a command that covers it

   `aidd gate --paths` gives its lane:
   - On the fast lane, run the `aidd-team:developer` subagent tests-first (the test red on base, then green).
   - When it needs a Spec, run `/aidd-team:specify` first, so the tester writes the tests and the developer never edits them.

   Then run the `aidd-team:verifier` subagent on the head (the local preview, with its screenshots under `.aidd/evidence/preview/`), the `aidd-team:reviewer` subagent, and the preview for the person to try. Stop at Merge approval.
4. **Slices 2 to n.** Take the next slices whose scopes are disjoint, two or three at a time, each in its own worktree. Make one Agent call per slice with `isolation: "worktree"`, all launched in one message. Each slice runs as slice 1 did. A specialist joins only when the gate names its risk dimension:
   - the security engineer for auth, secrets, payments, or AI
   - the product designer for a new user-facing flow

   Merge the slice branches back one at a time, with `aidd test` after each. Never leave the person more open changes than they can decide today.
5. **Launch review.** Run these subagents in parallel:
   - `aidd-team:security-engineer`: a threat review of the whole app, not one diff
   - `aidd-team:sre`: the SLO, the observe signals, the rollback steps and trigger

   Show the person both, with the open findings and the rollback plan, and stop: go-live is the person's decision, and so is running the rollback.
