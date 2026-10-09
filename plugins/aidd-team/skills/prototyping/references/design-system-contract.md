# The design-system contract

Load this when you set up or change the design system a prototype uses, build its CSS, or check it.

A repository has one design system. Every prototype, design spec, and screen uses it and never copies it: a copy drifts the day a token changes. `aidd validate` warns when a Spec's `design.files` hold their own tokens file beside `design/tokens.json`.

```text
DESIGN.md                 the contract in words, with a token front matter (`aidd new design-system`)
design/
  tokens.json             the contract in numbers: the one source
  build.mjs               writes the files below and DESIGN.md's token mirror; `--check` is the drift test
  tokens.css              generated: every token but the colour roles
  themes/<theme>.css      generated: one preset per theme set (`color.light`, `color.dark`)
docs/design/SPEC-220/     one Spec's files and nothing of the system's: directions/, ui-<topic>.md, prototype.html
```

A change to `DESIGN.md` or `design/` is its own change (`baseline:design-system`, normal). It merges before the Spec that needs it goes to Spec approval. Propose a missing token or component as that separate change, never inside a Spec's folder. On an outside design system, `DESIGN.md` names it and its version and `design/tokens.json` is a pinned export. Never mix two systems.

## DESIGN.md in the design.md format

`DESIGN.md` follows Google Labs' design.md format (alpha, Apache-2.0). It starts with a YAML token front matter, then has prose sections in the format's order, with this contract's own sections between them. That order is Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, and Components. The front matter mirrors `design/tokens.json` and never replaces it. design.md holds one flat set of CSS colour strings, with no themes or durations. The tokens file holds both themes as typed Design Tokens Format Module 2025.10 values. So there is one source and one generated copy:

- Between `# generated from design/tokens.json ...` and `# end generated`, the build writes `colors` (the light roles by name, the dark ones as `<role>-dark`, `primary` for `accent`), `typography`, `rounded`, and `spacing`. Never edit it by hand.
- `components` is the only hand-written token group: each text and background pair a screen draws, in both themes (`button-primary`, `button-primary-dark`), by reference (`{colors.accent}`), so the lint checks its contrast.
- The prose names roles and tokens, never values; the roles, principles, and states live there.

## The build, the theme presets, and the drift test

`design/build.mjs` is Node with no package. Raw colours sit directly under `color` and are never emitted. Each group under `color` is a theme preset with the same role names. The build writes each preset to `design/themes/<theme>.css` as `--color-<role>`:

- light on `:root`;
- dark also under `prefers-color-scheme`, until a `data-theme` is picked;
- a `color.high-contrast` set adds a preset.

Screens read roles only: `var(--color-accent)`. The prototype template reads only these names. Its `<style id="tokens">` block is this build's output for the template tokens. Paste the repository's `tokens.css` and `themes/*.css` in its place, and nothing else changes.

```sh
node design/build.mjs --check                                   # drift: names each file that differs, exit 1
f=$(mktemp); npx @google/design.md@0.4.0 lint DESIGN.md > "$f"; [ -s "$f" ] && ! grep -qE '"rule": "(broken-ref|contrast-ratio)"' "$f"
b=$(mktemp); git show origin/main:DESIGN.md > "$b" && npx @google/design.md@0.4.0 diff "$b" DESIGN.md   # exit 1 on a regression
npx @google/design.md@0.4.0 export --format css-tailwind DESIGN.md   # a Tailwind v4 theme; commit it, diff it like the rest
```

The lint exits 1 only on a broken reference; a pair below 4.5:1 is a warning, hence the grep. Put each in `[[tests]]` as `["sh", "-c", "..."]`, and the diff in a design-system change's `tests.commands`. Style Dictionary reads the Design Tokens format since version 4, but not yet all of 2025.10 (colour and dimension objects). Once it does, use it for native themes (SwiftUI, Compose), and keep the same regenerate-and-diff check.

## Components first

Before drawing a component, reuse one `DESIGN.md` lists. Else, on a React stack, take a shadcn/ui item (MIT); on another, the stack's accessible headless component library. A shadcn/ui item is copied into the repository as source, built on Radix primitives (MIT, accessible and unstyled), restyled with the roles. A team's own registry is static JSON (`shadcn build` writes `public/r/<name>.json`) served by any file host, installed with `npx shadcn@4.21.0 add <url>`; the shadcn MCP server is optional, never required. Either way it is a design-system change, its states and test ids in `DESIGN.md`. In a prototype, draw its markup and states; code comes at Implement.

## Inputs, never sources

A direction or a design-system change may start from a Claude Design handoff bundle (its HTML, screenshots, and README). It may also start from a Figma link or a Figma DTCG export. Read it, then write what the loop needs: tokens into `design/tokens.json`, screens into `prototype.html`, the reasons into `DESIGN.md` or the design spec. Nothing requires one, and an agent never builds against it directly.
