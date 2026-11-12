# 37. The route answer names the rules and the skills that apply to a change

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `aidd risk --paths` prints a project rule that carries its text, and a hint to load a domain pack when a matched area brings one. It prints no `read:` line, and `agents.domain_packs` takes names with no paths.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Before the first edit, a developer must read the project rules and the domain skills that apply to the paths. Today the route answer names a rule that holds its text in the config. A rule adopted from the library lives in a file, and the skill tells the agent to match its `when_changed` globs by hand. Who finds each rule and skill: the agent, or `aidd risk --paths`?

## Considered options

- **Leave the match to the agent.** It costs deterministic work given to a model, which a program does the same every time.
- **Name them in the answer after the tag.** It costs the answer's shape twice: a rule gains `page`, a domain skill moves from a hint to data, and the skill's sentence is written again.
- **Name them in the answer before the tag.** It costs about 90 bytes for each `read:` line, and the paths of a domain skill must be data.

## Decision outcome

The chosen option is "name them in the answer before the tag", because matching globs is deterministic work, and it belongs in code.

> `aidd risk --paths` names each project rule whose `when_changed` matches the paths, and each domain skill that the paths call for, as a `read:` line. The JSON holds both as data. A rule whose text is inline is still printed in full.

### The case that decided it

A developer starts a Task on `src/pay/refund.py` in a project that wrote one rule and adopted one library rule, `python-import-linter`, with `when_changed: ["**/*.py"]`. Today the answer names the first and not the second. After the change it adds `read: docs/rules/python-import-linter.md (project rule python-import-linter, must)`. For a domain skill, only 4 of the 27 can be named from a path today, because only four carry an `areas` entry. No path says that a project is about health or insurance, and its config can. So the project's list of domain skills takes paths, as `agents.domain_skills` with `when_changed`. A practice skill stays outside the answer, because the work chooses it and the Task names it.

### Consequences

- Good, because one command names every rule and skill to read, the adopted rules too, and gives the same answer for the same input.
- Good, because `--role` keeps only the rules that name the role or no role.
- Bad, because each `read:` line adds about 90 bytes, and a rule's page is about 2 KB when the agent opens it. Matching adds no git call.
- Bad, because the answer's JSON gains `page` on a rule and `skills` for the domain skills, which a reader of that JSON must handle.

### Reopen when

Tasks stop naming their practice skills, so a path must choose them.

## More information

[0023](0023-knowledge-rules-capabilities.md) and [0024](0024-recommendation.md) say what a rule and a recommendation are. [0025](0025-pack-goes-two-plugins.md) says why the word "pack" goes, so the key is `agents.domain_skills`.
