# aidd-domains

An optional Claude Code plugin: the domain skills of the [aidd](https://github.com/thaithienvanid/aidd#readme) development team, one skill per domain, such as web, APIs, mobile, health, payments, and public sector. Each domain skill holds the domain's standards, a checklist per loop step, and the test commands a Spec runs. It needs the `aidd-team` plugin, whose roles load a domain skill.

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd-team@aidd
/plugin install aidd-domains@aidd --scope project
```

A role loads a domain skill by name, such as `aidd-domains:payments-and-finance`, when `aidd risk --paths`, the config, or the lead names it. So no model has to find a domain skill from its description.

Claude Code lists every skill's name, and every description within 1% of the model's context window. The aidd-team plugin lists only the skills a model finds alone. This plugin lists the rest, so enable it in a project that calls for a domain skill. `aidd doctor` names the domain skills a repository calls for, and `aidd init --claude-plugins --aidd-team` enables the plugin there.

The domain skills are generated from `schemas/packs.json`. Edit the registry and run `aidd gen-docs`, never a domain skill. [plugins/README.md](../README.md) says how to add one.
