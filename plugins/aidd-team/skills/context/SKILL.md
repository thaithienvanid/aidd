---
name: context
description: "Practice skill: read only what a step needs. Use in an aidd repository at the start of any step, or when a role re-reads files, runs out of context, or loses the thread of a change."
metadata:
  checked: "2026-10-29"
---

# Context

**Use it when** a step starts, resumes after a pause or a compaction, or reads more than it uses. Every role starts a step this way, so the next role finds the same files. No Task names it in its skills: it is how every step begins.

**Do not use when** the step is a one-line answer from a file already open. Then read it and answer.

## Standards

<!-- aidd:gen practice:context -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Context engineering for the window (emerging) | — | 2026-10-16 | <https://www.anthropic.com/engineering/building-effective-agents> |
| AGENTS.md and Agent Skills conventions for agent-readable repositories | — | 2026-10-16 (reviewed) | <https://agents.md/> |
<!-- aidd:end -->

## Plan

- Start from the pack: `aidd context <ID> --role <role> --step <code>`. It names each file to read, why, and about how many tokens, and each command to run. It never pastes a file.
- The pack says when it was made: its head commit and Spec hash. After a new commit, or after the Spec changes, ask for it again.

## Implement

- Read by path, when the step needs it, and only the part it needs: a section by its heading, a function by its name. Search before you open a whole file.
- Never re-read a file that has not changed since you read it in this session. Quote the line you rely on instead.
- When a change moves the structure or settles a decision, record it in a file your role writes. If its owner is another role, put it on the handoff note's Needs line, so the next step reads it there, not from chat.

## Learn

- A file you needed that the pack missed, or one it named that you never used, goes in the handoff note, so the team can fix the step's reads once.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Handoff note | each stop leaves a note the next step can read: Done, Next, Needs, and Stopped at | `aidd validate specs/<ID>.md`, which warns on a handoff note it cannot read |

## Stop if

- The pack names a file outside the repository, or one that is missing: say so, and never guess its contents.
- The step needs a fact no file holds. It goes on the handoff note's Needs line, for a person.

## Hand off

- End with the handoff note: Done, Next, Needs, and Stopped at, in the Spec or the PR/MR. The next role starts from it and the pack, never from this chat.
