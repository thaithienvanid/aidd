# aidd-packs

An optional Claude Code plugin: the domain packs of the [aidd](https://github.com/thaithienvanid/aidd#readme) development team, one skill per domain, such as web, APIs, mobile, health, payments, and public sector. Each pack holds the domain's standards, a checklist per loop step, and the test commands a Spec runs. It needs the `aidd-team` plugin, whose roles load a pack.

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd-team@aidd
/plugin install aidd-packs@aidd --scope project
```

A role loads a pack by name, such as `aidd-packs:payments-and-finance`, when `aidd risk --paths`, the config, or the lead names it. So no model has to find a pack from its description.

Claude Code lists every skill's name, and every description within 1% of the model's context window. The aidd-team plugin lists only the skills a model finds alone. This plugin lists the rest, so enable it in a project that calls for a pack. `aidd doctor` names the packs a repository calls for, and `aidd init --claude-plugins --aidd-team` enables the plugin there.

The packs are generated from `schemas/packs.json`. Edit the registry and run `aidd gen-docs`, never a pack. [plugins/README.md](../README.md) says how to add one.
