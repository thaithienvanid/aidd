---
id: typescript/shadcn-ui
type: opinionated
fills: [web-front-end:component-library]
default: true
implements: accessible-ui:Accessibility per state
roles: [developer, product-designer, reviewer]
when_changed: [components.json, "components/ui/**", "src/components/ui/**", "**/*.tsx", package.json]
why: "shadcn/ui copies each component into the repository as source on accessible headless primitives, so the team styles it with the design tokens and owns every line, with no component package to upgrade."
reviewed: "2026-10-22"
maturity: established
tool:
  name: shadcn
  registry: npm
  package: shadcn
version_policy: current_stable
checked_version: "4.22.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default
evidence: "Starting today, Base UI is the default component library in shadcn/ui."
pin: "4.22.1"
alternatives: [React Aria Components, Angular CDK, Reka UI]
status: active
enforced_by:
  - name: config
    command:
      - node
      - -e
      - "const c = require('./components.json'); process.exit(c.tailwind && c.tailwind.cssVariables === true && !c.tailwind.config && require('fs').existsSync(c.tailwind.css) ? 0 : 1)"
---

# shadcn/ui gives the React front end its components

It answers the component-library choice of `aidd-team:web-front-end`, on a React stack. License: MIT for the CLI, Base UI, and Radix.

## What the team does

- Run the CLI only at `pin`: `pnpm dlx shadcn@4.22.1 init`, then `pnpm dlx shadcn@4.22.1 add <component>`. Never copy a component from a web page.
- Commit `components.json`. Set `tailwind.cssVariables` to `true`, leave `tailwind.config` empty for Tailwind CSS v4, and point each semantic variable it writes, such as `--primary`, at a role from the design tokens.
- Follow shadcn's default primitive library. A new project takes Base UI (`@base-ui/react`, 1.9.0 when checked). A project already on Radix (`radix-ui`, 1.8.1 when checked) stays on it, because Radix is not deprecated. Move a component only as its own change.
- Treat every file under `components/ui/` as the team's code. A person reads each added or updated component in the diff, as any other code.
- List each component in `DESIGN.md` with its states and test ids before a screen uses it.
- A team's own registry is static JSON that `shadcn build` writes; install from it with the same pinned CLI.
- Check each component's states with axe through `typescript/testing-library` and `typescript/playwright-e2e`.

## What the gate runs

One `tests` entry reads `components.json`. It fails when the file is missing, when the components do not read CSS variables, or when the CSS file it names is gone.
