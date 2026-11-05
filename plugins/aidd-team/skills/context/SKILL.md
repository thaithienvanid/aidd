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
| Context engineering for the window (emerging) | — | 2026-11-05 | <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents> |
| AGENTS.md and Agent Skills conventions for agent-readable repositories | — | 2026-10-16 | <https://agents.md/> |
<!-- aidd:end -->

## Plan

- Start from the Spec and the latest handoff note. Your Task's `scope`, the Spec's `docs`, and its `tests` name the files to read, and `aidd status <ID>` names the next step. Never paste a file into a prompt.
- After a new commit, or after the Spec changes, read the changed parts again.

### Where each memory lives

- A person's memory, how they like to work, stays in their harness's memory.
- Your memory across runs is the handoff note and the records (`aidd records`).
- The team's memory is the repository's files: the ADRs, the glossary, the product brief, the improvement log, and the shared `refs/aidd/records`.
- Put a project fact in the file that owns it, never only in one harness's memory, because another harness, a teammate, or the next role never sees that memory. A harness memory may be stale, so check it against the files.
- A lesson you learn joins a team file only when a person confirms it.

## Implement

- Read by path, when the step needs it, and only the part it needs: a section by its heading, a function by its name. Search before you open a whole file.
- Never re-read a file that has not changed since you read it in this session. Quote the line you rely on instead.
- When a change moves the structure or settles a decision, record it in a file your role writes. If its owner is another role, put it on the handoff note's Needs line, so the next step reads it there, not from chat.

## Learn

- A file you needed that the Spec did not name, or one it named that you never used, goes in the handoff note, so the team can fix the step's reads once.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Handoff note | each stop leaves a note the next step can read: Done, Next, Needs, and Stopped at | `aidd validate specs/<ID>.md`, which warns on a handoff note it cannot read |

## Stop if

- The Spec names a file outside the repository, or one that is missing: say so, and never guess its contents.
- The step needs a fact no file holds. It goes on the handoff note's Needs line, for a person.

## Hand off

- End with the handoff note: Done, Next, Needs, and Stopped at, in the Spec or the PR/MR. The next role starts from it and the Spec, never from this chat.
