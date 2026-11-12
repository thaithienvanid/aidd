# 38. A skill's main file keeps each standard's name and edition, and its sources sit in one generated file

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. A skill's standards table holds four columns today: the standard, its edition, its `checked` date, and its source's link. No `references/sources.md` exists.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Each of the 37 practice skills and 27 domain skills carries a generated table of the standards it cites. The table loads every time the skill loads. Its date and link columns are for whoever checks a source, and they take between a third and a half of each table's bytes. A skill near its size limit cannot cite one more source. What does the main file keep?

## Considered options

- **Keep the four columns.** It costs nothing now, and it frees nothing.
- **Keep the name and the edition, and move the date and the link to a generated file.** It frees about 34 KB over the 64 skills. It costs one read of a small file, in the one case where an agent must check a source.
- **Keep only the names where a rule cites one.** It frees about 82 KB. It costs the edition: an agent that does not see "WCAG 2.2" applies the edition it remembers, which is the fault the registry exists to prevent.

## Decision outcome

The chosen option is "keep the name and the edition, and move the date and the link", because a rule means its edition, and a date and a link are read only on a check.

> A skill's main file keeps each standard's name and edition. Each such skill has a generated `references/sources.md` with all four facts. The standards registry stays the one owner of them, and both texts are generated from it.

### The case that decided it

Take `data-model-design`. When this was measured it sat near 90% of its size limit, and each new source adds a row of about 150 bytes. With the date and link out, it falls to about 82%, so it can cite more. The edition stays in the main file, so a rule that names "PCI DSS v4.0.1" keeps it where the agent reads. The new file follows the open-choices reference, which is already generated. The check of a domain skill's two references leaves a generated file out of the count and out of the comparison with the registry's list. A hand-written file of that name fails it. The file keeps the size limit of a reference.

### Consequences

- Good, because every session that loads a skill pays fewer bytes, about 5% of a practice skill and 11% of a domain skill on average.
- Good, because the roles reference drops the rows it holds for the skills a role preloads, so the largest reference shrinks.
- Bad, because an agent that checks a date or a link reads one more file.
- Bad, because the change touches the 64 skills, adds 64 generated files, and changes the checks on references and on size.

### Reopen when

An agent often needs a source's date or link in the middle of a Task.

## More information

[0023](0023-knowledge-rules-capabilities.md) says why a standard is knowledge. [STANDARDS.md](../STANDARDS.md) says where the date is read today.
