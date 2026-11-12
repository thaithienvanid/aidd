# 19. A decision is one entity, with named keys of one shape

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `$defs/decision` does not exist in `schemas/common.schema.json` yet. An Intent's `approval` refers to `$defs/approval`, and a Spec holds a loose pair.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Review, approve, and accept are all decisions. The project owner asked why they do not share one entity. Files hold approvals, cancellations, declines, and picks, each in its own shape. What is a decision, and how is it stored?

## Considered options

- **One key that holds a list of decisions.** It costs a search, because "is it approved?" becomes a scan of a tagged list. The list is also a second home for the history that git already keeps.
- **One generic key with a tag.** It costs the reading, because a generic key does not read as a fact about its object.
- **Named keys of one shape.** It costs several key names, each with the same two parts.

## Decision outcome

The chosen option is "named keys of one shape", because each key answers one question about its object.

> A decision is someone's answer to an action, on exact content. It names the action, which way, who, when, and why where it is a no. It is defined once, as `{by, at}`, with a `reason` where it is a no. `approval`, `cancellation`, `decline`, and an exploration's `result` are that one entity under named keys.

### The case that decided it

A proposal carries two answers by two parties at once, our person's yes to send it and the client's answer. Under one key they would be a list with a tag. An Intent is approved and later cancelled, and both facts stay true, so each sits under the key that names its question. A Spec is approved, sent back, and approved again. The file holds the newest approval, `revisions` holds each sending back, and git holds the earlier approvals in their commits.

### Consequences

- Good, because the file holds the current state and git holds the history, so no fact has two homes.
- Good, because a test can check that every decision key refers to the one definition.
- Bad, because other shapes look like decisions and are not, such as a delegate's approval, a proposal's `answer` whose `by` is free words, a measure's `result`, and `revisions`. A list names each so none passes as a decision.

### Reopen when

A new decision needs a key that the one shape cannot hold.

## More information

[0020](0020-an-approval-names-its-content.md) says how a decision holds.
