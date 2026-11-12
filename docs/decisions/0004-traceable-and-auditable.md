# 4. Traceable and auditable is a stated principle

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. [METHOD.md](../METHOD.md) does not state the principle yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The first release adds a traceability matrix, stored decisions, and release files. Nothing in the method says why. Should "traceable and auditable" become a stated principle, and where does it go?

## Considered options

- **No principle.** It costs the reason: the matrix and the audit would look like features with no rule behind them.
- **A principle in `AGENTS.md`.** It costs room that file does not have, because it stays under doctor's 12 KiB.
- **A principle in `docs/METHOD.md`, with its limits beside it.** It costs one paragraph, and the limits must stay true as the code changes.

## Decision outcome

The chosen option is "a principle in METHOD.md, with its limits beside it", because a claim of audit that hides what an audit cannot show misleads the reader.

> Traceable and auditable: every work item names what it came from, so a reader can follow a request to its release and back, and each gap is printed. Every decision is stored with who, when, and the exact content, so someone who was not there can check it from the repository alone.

### The case that decided it

Take the question "who approved what reached production on 2026-11-20, and on what evidence?" The repository answers it step by step. It holds the release file, the Spec's chain, the commit that approves and the content it names, the reviews, and the frozen tests. It cannot say who typed a file, whether each ask was put, or who said yes to a merge beyond git's name. A principle that stated only the first half would overclaim.

### Consequences

- Good, because each gap in a chain is printed and never left out.
- Bad, because the word "auditable" promises less than a reader may expect, so METHOD.md states the limits next to it.

### Reopen when

A stored fact can close one of the stated limits, such as a signed commit that says who typed.

## More information

[Architecture](../architecture/README.md) and [METHOD.md](../METHOD.md) own the what.
