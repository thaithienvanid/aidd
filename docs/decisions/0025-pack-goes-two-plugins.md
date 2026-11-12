# 25. The word "pack" goes, and two plugins stay

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. The plugin is still `aidd-packs` and the config key is still `agents.domain_packs`.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A domain pack and a practice skill are both a folder with a `SKILL.md`. The coding agents already have skills and plugins. Does the word "pack" go from the plugin's name too, and how many plugins does aidd ship?

## Considered options

- **Keep `aidd-packs`.** It costs a second word for a skill, and the word cannot change after the tag, because a plugin's name is stored.
- **Rename it to `aidd-domains`.** It costs 253 files by script and the fourteen wiring tests.
- **One plugin and one list.** It costs attention, because a project would see 65 skill descriptions where it sees 38 today.
- **Plugins cut by the three words.** It costs 581 files.
- **Keep two plugins.** It costs nothing beyond the rename.

## Decision outcome

The chosen option is "rename to `aidd-domains` and keep two plugins", because a domain skill is simply a skill and a project turns on a domain skill only where it needs one.

> The word "pack" goes. `aidd-packs` becomes `aidd-domains`. A domain skill and a practice skill are both skills. Two plugins stay, the team with its practice skills and the domain skills.

### The case that decided it

The project owner asked that aidd not add a concept that a coding agent already has. A skill, a plugin, and a folder of skills exist in the coding agents. A "pack" was a second name for a skill. Only the timing is hard, because the rename must land before the tag and a plugin's name cannot change after it.

### Consequences

- Good, because a person learns one word for a unit that an agent loads.
- Good, because the role key `practices` becomes `skills`, as a Task's `skills` is.
- Bad, because the rename touches 253 files, and the config key `agents.domain_packs` becomes `agents.domain_skills`.

### Reopen when

A project needs a unit larger than a skill that no coding agent offers.

## More information

[0023](0023-knowledge-rules-capabilities.md) says why a plugin installs knowledge and capabilities.
