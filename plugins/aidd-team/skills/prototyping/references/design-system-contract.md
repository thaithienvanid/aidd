# The design-system contract

Load this when you set up or change the design system a prototype uses, build its CSS, or check it.

A repository has one design system. Every prototype, design spec, and screen uses it and never copies it: a copy drifts the day a token changes. `aidd validate` warns when a Spec's `design-files` docs hold their own tokens file beside `design/tokens.json`.

```text
DESIGN.md                 the contract in words, with a token front matter (`aidd new design-system`)
design/
  tokens.json             the contract in numbers: the one source
  build.mjs               writes the files below and DESIGN.md's token mirror; `--check` is the drift test
  tokens.css              generated: every token but the color roles
  themes/<theme>.css      generated: one preset per theme set (`color.light`, `color.dark`)
specs/SPEC-220/design/    one Spec's files and nothing of the system's: directions/, ui-<topic>.md, prototype.html
```

A change to `DESIGN.md` or `design/` is its own change, on the normal route. It merges before the Spec that needs it goes to Spec approval. Propose a missing token or component as that separate change, never inside a Spec's folder. On an outside design system, `DESIGN.md` names it and its version and `design/tokens.json` is a pinned export. Never mix two systems.

## DESIGN.md in the design.md format

`DESIGN.md` follows Google Labs' design.md format (Apache-2.0), an emerging format at version alpha. It starts with a YAML token front matter, then has prose sections in the format's order, with this contract's own sections between them. That order is Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, and Do's and Don'ts. An optional Iteration Guide follows, which the format's tools keep as written. The front matter mirrors `design/tokens.json` and never replaces it. design.md holds one flat set of CSS color strings, with no themes or durations. The tokens file holds both themes as typed Design Tokens Format Module 2025.10 values. So there is one source and one generated copy:

- Between `# generated from design/tokens.json ...` and `# end generated`, the build writes `colors` (the light roles by name, the dark ones as `<role>-dark`, `primary` for `accent`), `typography`, `rounded`, and `spacing`. Never edit it by hand.
- `components` is the only hand-written token group: each text and background pair a screen draws, in both themes (`button-primary`, `button-primary-dark`), by reference (`{colors.accent}`), so the lint checks its contrast.
- The prose names roles and tokens, never values; the roles, principles, and states live there.

## The build, the theme presets, and the drift test

`design/build.mjs` is Node with no package. Raw colors sit directly under `color` and are never emitted. Each group under `color` is a theme preset with the same role names. The build writes each preset to `design/themes/<theme>.css` as `--color-<role>`:

- light on `:root`;
- dark also under `prefers-color-scheme`, until a `data-theme` is picked;
- a `color.high-contrast` set adds a preset.

Depth is a token beside the colors. A `shadow` group in `design/tokens.json` holds the one shadow for a floating layer, `shadow.raised`, which the build writes as `--shadow-raised`, and a blur is a token too. Three rules come from what a browser does. Forced colors compute a shadow to none, so a floating layer keeps a real border too (CSS Color Adjustment Module Level 1). A clickable thing keeps a border, a fill, an underline, or a shape, because flat parts with weak signifiers cost people time and attention (a Nielsen Norman Group study of 71 people, 2017). Translucency follows the person's setting for reduced transparency, and a design that reads it keeps its look where a browser lacks it (`prefers-reduced-transparency`, Media Queries Level 5, a Working Draft). `aidd prototype --check` refuses a raw shadow or blur outside `<style id="tokens">`. It lets a ring through, a layer whose offsets and blur are zero, because a ring draws an edge and no depth.

Screens read roles only: `var(--color-accent)`. The prototype template reads only these names. Its `<style id="tokens">` block is this build's output for the template tokens. Paste the repository's `tokens.css` and `themes/*.css` in its place, and nothing else changes.

```sh
node design/build.mjs --check                                   # drift: names each file that differs, exit 1
f=$(mktemp); npx @google/design.md@0.4.0 lint DESIGN.md > "$f"; [ -s "$f" ] && ! grep -qE '"rule": "(broken-ref|contrast-ratio)"' "$f"
b=$(mktemp); git show "$BASE":DESIGN.md > "$b" && npx @google/design.md@0.4.0 diff "$b" DESIGN.md   # BASE: the branch the change merges into; exit 1 on a regression
npx @google/design.md@0.4.0 export --format css-tailwind DESIGN.md   # where the stack uses Tailwind: a v4 theme; commit it, diff it like the rest
```

The lint exits 1 only on a broken reference; a pair below 4.5:1 is a warning, hence the grep. Put each in `tests` as `["sh", "-c", "..."]`, and the diff in a design-system change's `tests.commands`. Style Dictionary reads the Design Tokens format since version 4, but not yet all of 2025.10 (color and dimension objects). Once it does, use it for native themes (SwiftUI, Compose), and keep the same regenerate-and-diff check.

## Depth and alignment

`DESIGN.md` states how the product shows depth and how it keeps things in line. The start is smart flat, and a product may state another model, in tokens. These are the rules the start holds, and the designer reviews a design against them.

Depth, in eight rules:

1. Depth is a token, with at most three stated levels. Every shadow and blur value comes from a token.
2. Tone and a border first. A shadow is only for a layer that floats over content.
3. A clickable thing looks clickable with no depth: a border, a fill, an underline, or a shape, never color alone. The tab row is the one exception: a tab is marked by its place in the row, and the current one by its bar.
4. A control's edge keeps 3:1 against what is around it (WCAG 2.2 SC 1.4.11).
5. The page works in forced colors: every separation that matters is a real border. There the tone step and the shadow are lost, and every layer is still told by its edge.
6. In dark mode a raised surface is lighter.
7. Decoration never carries meaning.
8. Translucency, where a product uses it, follows the person's settings for reduced transparency and more contrast.

Alignment, in nine rules. Measure each in the browser, and never judge it from a screenshot.

1. Every size, padding, and gap is a step of the spacing tokens.
2. The items of a row or a column share a start edge, a centre line, or a text baseline, within 0.5px.
3. A centred thing is centred on both axes, within 0.5px.
4. Text aligns by its baseline, and an icon beside text sits on the middle of the text's letters, within 1px.
5. Opposite paddings are equal, and one component has one padding wherever it appears.
6. Repeated items keep one gap, and related items sit closer than the next group.
7. Positions and sizes land on whole pixels.
8. An optical correction is stated in the component's entry in `DESIGN.md`, with its reason and amount, and in the test's table of exceptions. Every other offset is a defect.
9. Alignment holds in each state, in both themes, at each width, at 200% text, with long and short content, and in a right-to-left language.

An icon is a flex or grid item, or a block, and never an inline box on a text line, because an inline box sits on the baseline and drifts from the middle. The product's `DESIGN.md` names the rules it keeps and its tolerance.

## Components first

Before drawing a component, reuse one `DESIGN.md` lists. Else take what the `web-front-end:component-library` choice names, which `aidd standard list` shows, or the stack's accessible headless component library. On a React stack its default is shadcn/ui, under MIT. Each item is copied into the repository as source, on accessible, unstyled primitives such as Base UI or Radix, and restyled with the roles. Its standard pins the CLI and installs from a team's own static registry too, and the shadcn MCP server is optional, never required. Either way it is a design-system change, its states and test ids in `DESIGN.md`. In a prototype, draw its markup and states; code comes at Implement.

## Inputs, never sources

A direction or a design-system change may start in any design tool, such as Figma, Penpot, Claude Design (its handoff bundle), or Google Stitch. The prototype tool is the team's shared, minimal format, not a rival to them. Read the export, then write what the loop needs:

- **Tokens**: export them as DTCG JSON (Figma variables through Tokens Studio, or Penpot's design tokens), and merge them into `design/tokens.json`. Then run `node design/build.mjs`, so the CSS and `DESIGN.md` follow.
- **Screens**: take the tool's HTML or code export as a draft. Rewrite each screen as a `<section data-screen>` with its `<div data-state>` children, with no script, the colors as `var(--color-...)`, and a `data-component` on each reusable part.
- **Pictures**: keep a static export as a mockup in a `design-files` doc.
- **Reasons**: the choices go into `DESIGN.md` or the design spec.

Nothing requires a tool, and an agent never builds against an export directly.
