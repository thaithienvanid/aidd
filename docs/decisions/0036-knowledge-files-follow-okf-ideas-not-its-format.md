# 36. Knowledge files follow the ideas of OKF, and not its format

Accepted on 2026-11-16, for a decision made while aidd was built. In force.
The maintainers decided it while aidd was built, and this record keeps the reasons that the architecture page gave. Every contributor is informed through this record.

## Context and problem statement

aidd keeps the team's know-how as files: the library's standards, its stacks, and the skills. They must say where a claim came from, when it was checked, and when it goes stale. The Open Knowledge Format (OKF) names those ideas. Does aidd store its files in OKF, or in a format of its own?

## Considered options

- **Store the files in OKF.** It costs a dependency on a format that is young and has no validator, so a mistake in a file would go unseen.
- **No shared ideas: a format of aidd's own alone.** It costs the provenance, the sources, and the staleness that a reader of a standard needs.
- **OKF's ideas, in aidd's own fields.** It costs a mapping from OKF's words to aidd's, which a table holds.

## Decision outcome

The chosen option is "OKF's ideas, in aidd's own fields", because aidd already checks its own fields, and OKF has no validator to check them.

> Knowledge files are Markdown with YAML front matter, with provenance and sources, as OKF's ideas have it. aidd does not use OKF as a storage format.

### The case that decided it

A library standard says who checked it and when, in `checked` and `checked_by`, as `agent:<harness>/<model>`. Where it states an edition, it carries a `citation` with the page, the `url`, and a sentence quoted from it. It goes stale on a date set by `review_every_days` or `review_due`, and `aidd eval standards` fails past it. OKF has an idea for each of these. aidd's schemas validate each field, so a wrong value fails a check.

### Consequences

- Good, because every field of a knowledge file has a schema, so a wrong value fails a check.
- Good, because a team that knows OKF finds its ideas in the files.
- Bad, because aidd's files do not read as OKF to a tool that expects it, and the mapping is aidd's to keep true.

### Reopen when

OKF has a validator that checks what aidd's schemas check.

## More information

[The architecture page](../architecture/README.md#the-knowledge-model) holds the table that maps each OKF idea to an aidd field. [STANDARDS.md](../STANDARDS.md) defines the library. [0024](0024-recommendation.md) renames the library's items.
