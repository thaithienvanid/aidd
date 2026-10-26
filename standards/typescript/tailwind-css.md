---
id: typescript/tailwind-css
type: opinionated
fills: [web-front-end:styling]
default: true
implements: web-front-end:Design-token lint
roles: [developer, product-designer, reviewer]
when_changed: ["**/*.css", "**/*.tsx", "**/*.jsx", "**/*.html", "**/*.vue", DESIGN.md, design/tokens.json, package.json]
why: "Tailwind CSS v4 reads its theme from CSS variables in an @theme block, so the theme can come from the design tokens alone, and with the default palette removed a class can name only a token."
reviewed: "2026-10-22"
maturity: established
tool:
  name: tailwindcss
  registry: npm
  package: tailwindcss
version_policy: current_major
checked_version: "4.3.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://tailwindcss.com/docs/theme
evidence: "When you do this, all of the default utilities that use that namespace (like bg-red-500) will be removed, and only your custom values (like bg-midnight) will be available."
alternatives: [CSS Modules, Plain CSS on the token custom properties, vanilla-extract]
status: active
enforced_by:
  - name: theme
    command:
      - sh
      - -c
      - "npx @google/design.md@0.4.0 export --format css-tailwind DESIGN.md | diff -u design/tailwind-theme.css -"
  - name: raw-values
    command:
      - sh
      - -c
      - "git grep -nE -e '-\\[(#|rgba?\\(|hsla?\\(|oklch\\(|[0-9.]+(px|rem|em)\\])' -- '*.ts' '*.tsx' '*.jsx' '*.html' '*.vue'; test $? -eq 1"
---

# Tailwind CSS styles the components from the design tokens

It answers the styling choice of `aidd-team:web-front-end`. License: MIT. Tailwind CSS was at 4.3.3 when this file was checked.

## What the team does

- Add `tailwindcss` and its build plugin (`@tailwindcss/vite` or `@tailwindcss/postcss`) as exact dev dependencies of the same release.
- Keep `design/tokens.json` the one owner of every value. Write the Tailwind theme with `npx @google/design.md@0.4.0 export --format css-tailwind DESIGN.md > design/tailwind-theme.css`, and commit the output. Never edit it by hand.
- In the CSS entry file, after `@import "tailwindcss";`, reset each namespace the tokens own in an `@theme` block, such as `--color-*: initial;`, then import `design/tailwind-theme.css`. The stock palette and scales are then gone.
- Write no arbitrary value such as `bg-[#fff]` or `p-[13px]`. A missing value is a design-system change. `bg-[var(--color-accent)]` still reads a token, so it passes.
- On ESLint, `eslint-plugin-better-tailwindcss` (MIT) adds `no-unknown-classes`, and its `no-restricted-classes` takes the same pattern as a regular expression.

## What the gate runs

Two `tests` entries. `theme` exports the theme again and fails when it differs from the committed file. `raw-values` fails on any arbitrary color or length in a class, and also when `git grep` cannot run.
