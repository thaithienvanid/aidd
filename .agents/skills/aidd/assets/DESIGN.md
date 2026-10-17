---
version: alpha
name: "{{title}}"
# generated from design/tokens.json by design/build.mjs: never edit by hand
colors:
  surface: "#ffffff"
  surface-raised: "#f3f4f5"
  text: "#1c1e21"
  text-muted: "#5b616b"
  accent: "#1d4ed8"
  accent-subtle: "#dbe4ff"
  danger: "#b91c1c"
  success: "#067647"
  warning: "#8a4b00"
  warning-subtle: "#fff4cc"
  focus: "#1d4ed8"
  primary: "{colors.accent}"
  surface-dark: "#111317"
  surface-raised-dark: "#1c1e21"
  text-dark: "#f3f4f5"
  text-muted-dark: "#9ea5b0"
  accent-dark: "#93c5fd"
  accent-subtle-dark: "#26345c"
  danger-dark: "#fca5a5"
  success-dark: "#47cd89"
  warning-dark: "#fdb022"
  warning-subtle-dark: "#3a3000"
  focus-dark: "#93c5fd"
typography:
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  heading:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 1.5rem
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: 0px
rounded:
  control: 6px
  surface: 12px
spacing:
  "1": 4px
  "2": 8px
  "3": 16px
  "4": 24px
  "5": 32px
# end generated
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "{spacing.2}"
  button-primary-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.surface-dark}"
  text-body:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
  text-body-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.text-dark}"
  text-muted:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
  text-muted-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.text-muted-dark}"
  text-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
  text-danger-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.danger-dark}"
  text-success:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.success}"
  text-success-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.success-dark}"
  text-warning:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
  text-warning-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.warning-dark}"
  panel:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-muted}"
  panel-dark:
    backgroundColor: "{colors.surface-raised-dark}"
    textColor: "{colors.text-muted-dark}"
  item-selected:
    backgroundColor: "{colors.accent-subtle}"
    textColor: "{colors.text}"
  item-selected-dark:
    backgroundColor: "{colors.accent-subtle-dark}"
    textColor: "{colors.text-dark}"
  notice:
    backgroundColor: "{colors.warning-subtle}"
    textColor: "{colors.text}"
  notice-dark:
    backgroundColor: "{colors.warning-subtle-dark}"
    textColor: "{colors.text-dark}"
---

# Design system: {{title}}

Written {{today}}. The one design system of this repository. This file is the contract in words, and
`design/tokens.json` is the contract in numbers. Living: every change to either file is its own change through the
loop. The baseline rule `baseline:design-system` routes it normal, so a person reviews it.

<!-- The product designer writes this file (`aidd new design-system`) from the direction a person picked. Or the
     designer drafts it from an existing product, for a person to accept. Every prototype, per-Spec design spec, and
     screen uses these roles and tokens, and never copies them. A Spec's design folder holds only its screens and
     design spec. Propose a token that a Spec needs and this file lacks as a separate change to this file and the
     tokens. Keep each section a short list. Name tokens by their path in design/tokens.json, such as `color.accent`.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill).

     The file follows Google Labs' design.md format (alpha): a YAML front matter of tokens, then these sections. The
     format's own sections (Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components) keep its
     order. The token groups between the two marker lines mirror design/tokens.json. `node design/build.mjs` writes
     them: the light theme's roles by name, the dark theme's as `<role>-dark`, and `primary` for `accent`. Never edit
     them by hand. `--check` is the drift test. Only `components` is written by hand. It lists every text and
     background pair a screen draws, in both themes, by reference, so `npx @google/design.md@0.4.0 lint DESIGN.md`
     checks its contrast. -->

## Overview

<!-- Principles and voice. Three to five lines on what the design favors. Each is a choice with a cost, such as
     "dense tables over cards" or "one primary action per screen". Then the voice: how the product speaks (plain
     words, second person, no blame in an error), and two or three words it never uses. -->

- TODO: a principle, and what it rules out.
- Voice: TODO.

## Colors

<!-- The color roles. Roles, never hues: a screen uses `color.accent`, not `color.blue-600`. Each role has a value in
     each theme. It names the pair it must pass in both themes (WCAG 2.2 SC 1.4.3 and 1.4.11):
     - 4.5:1 for body text
     - 3:1 for large text, and for the edges of controls and focus indicators. -->

| Role | Light token | Dark token | On | Contrast pair |
| --- | --- | --- | --- | --- |
| surface | `color.light.surface` | `color.dark.surface` | | |
| surface-raised (panels, bars, app chrome) | `color.light.surface-raised` | `color.dark.surface-raised` | | text and text-muted 4.5:1 on it |
| text | `color.light.text` | `color.dark.text` | surface | 4.5:1 |
| text-muted (and control edges) | `color.light.text-muted` | `color.dark.text-muted` | surface | 4.5:1 |
| accent (primary actions, links) | `color.light.accent` | `color.dark.accent` | surface | 3:1 as a control, 4.5:1 as text |
| accent-subtle (the selected item) | `color.light.accent-subtle` | `color.dark.accent-subtle` | | text 4.5:1 on it |
| danger | `color.light.danger` | `color.dark.danger` | surface | 4.5:1 |
| success | `color.light.success` | `color.dark.success` | surface | 4.5:1 |
| warning | `color.light.warning` | `color.dark.warning` | surface | 4.5:1 |
| warning-subtle (a notice) | `color.light.warning-subtle` | `color.dark.warning-subtle` | | text 4.5:1 on it |
| focus | `color.light.focus` | `color.dark.focus` | surface | 3:1 |

## Themes

<!-- Light and dark are the default (`project.defaults.dark_mode` in .aidd/config.yaml). A product with one theme
     turns it off there, with its reason, and deletes the dark column above. -->

- Two sets, one role list: `design/tokens.json` holds `color.light.<role>` and `color.dark.<role>` with the same role
  names. A screen names only the role (`color.accent`).
- Each set is a theme preset. `node design/build.mjs` writes `design/themes/<theme>.css`, with its roles as
  `--color-<role>`. Light goes on `:root`, and dark also under `prefers-color-scheme` until a person picks. A third set,
  such as `color.high-contrast`, adds a preset. A tool that reads the Design Tokens Resolver Module 2025.10 can take
  the sets as a `theme` modifier, with the contexts `light` and `dark`. The source stays `design/tokens.json`.
- The system decides first: the UI follows `prefers-color-scheme` until the person picks a theme. iOS and Android follow
  the system appearance. A manual toggle (system, light, dark) persists that choice across sessions and devices where
  the product has an account. The theme applies before first paint, so a page never flashes the other theme.
- Contrast checks run in both themes: every pair in the color roles, axe per screen state once per theme, and a
  screenshot per theme. For example, run axe under Playwright's `emulateMedia({colorScheme: "dark"})`.
- Images and illustrations work on both themes. A logo and an illustration have a dark variant, or a transparent
  background that reads on both surfaces. An image switches with `<picture>` and a `prefers-color-scheme` source. A
  chart's colors come from the roles.
- TODO: anything this product adds, such as a high-contrast theme, or a surface that stays light (a printed receipt).

## Typography

<!-- The type scale: each step by token, with its use. Sizes in rem so text scales with the reader's setting. -->

| Token | Size / line height | Use |
| --- | --- | --- |
| `typography.body` | 1rem / 1.5 | body text, form fields |
| `typography.heading` | 1.5rem / 1.25 | page and section titles |
| TODO | | |

## Layout

<!-- The spacing scale by token, and the rule for using it, such as "space inside a component is smaller than the
     space between components". Then the layout grid. -->

- Scale: `space.1` (4px), `space.2` (8px), `space.3` (16px), `space.4` (24px), `space.5` (32px).
- Rule: TODO.
- Grid: TODO: the columns per breakpoint (320, 768, 1024, 1440 CSS px), and the widest a line of text runs.

## Elevation & Depth

<!-- How the product shows that one surface sits above another: shadow, border, or tone. At most three levels. -->

- TODO: level 0 (page), level 1 (card, menu), level 2 (dialog, sheet), and what marks each.

## Shapes

- `radius.control` for inputs and buttons, `radius.surface` for cards and sheets; TODO: when a corner is square.

## Motion

<!-- Durations by token and what moves. Motion explains a change of state; it never delays the person. -->

- `duration.fast` (120ms) for hover, press, and small state changes; `duration.base` (200ms) for panels and sheets.
- Reduced motion: under `prefers-reduced-motion: reduce` (iOS Reduce Motion, Android remove animations) every movement
  becomes a cut or a short fade, and nothing auto-plays.

## Components

<!-- The components and their states: only the components the product uses, each with every state it must draw. A
     state not listed here is a state the developer will invent.
     Add a new or changed component here in its own change. Give it a subsection when a row is not enough, with:
     - its purpose (and what it is not)
     - its Anatomy: each part a person sees or a screen reader announces
     - its Props and variants (with defaults)
     - all its states, and the tokens each uses
     - its Accessibility: role, name, keyboard, focus, target size, contrast in both themes
     - its test ids.
     Keep the names the same in the prototype, the code, and the tests. Before drawing a component, reuse one listed
     here. If none fits, reuse a registry item, restyled with the roles. On a React stack, the registry is shadcn/ui
     on Radix primitives. Otherwise, the registry is the stack's accessible headless component library. Each text and
     background pair a component draws gets a `components` entry in the front matter, in both themes. -->

| Component | States |
| --- | --- |
| Button (primary, secondary, destructive) | default, hover, focus, pressed, disabled, loading |
| Text field | empty, filled, focus, invalid with its message, disabled, read-only |
| TODO | |

### TODO: a new component

- Purpose: TODO, and what it is not (such as "a menu, not a select: it runs commands").
- Anatomy: TODO: 1 container, 2 label, 3 leading icon (decorative: hidden from assistive technology).
- Props and variants: TODO: variant (primary, secondary), size (small still meets the target size), disabled.
- States: TODO: every state above, with what changes and its tokens.
- Accessibility: TODO: the role and accessible name, the keyboard and focus order, the target size, contrast in both themes.
- Test ids: TODO: `data-testid`, `accessibilityIdentifier`, `testTag`.

## Patterns

- **Navigation:** TODO: the top-level pattern, where back goes, and what stays when a person switches section.
- **Forms:** labels above fields, the error beside its field and in a summary at the top, never only in color; TODO.
- **Empty and error states:** each says what happened and the one next action, in the product's voice. An error
  never blames the person. Loading shows the layout, not a spinner, when it takes over a second.

## Accessibility

<!-- WCAG 2.2 AA is the floor for every screen built on this system. -->

- WCAG 2.2 AA:
  - contrast per the color roles
  - a visible focus indicator on every control (`color.focus`)
  - targets of at least 24 by 24 CSS px (SC 2.5.8)
  - keyboard operation of everything
  - no information by color alone.
- Text: every screen works at 200% zoom and at the largest Dynamic Type and Android font scale.
- TODO: anything this product adds (a screen reader pattern, a language, a audited audience).

## Platforms

<!-- Only the deltas from the shared system, per platform the product ships to. Delete a platform it does not. -->

### Web

- Tokens become CSS custom properties, generated by `node design/build.mjs`: `design/tokens.css` and one preset per theme in
  `design/themes/` (`[data-theme]` and `prefers-color-scheme`). TODO: the breakpoints, and any other build (a Tailwind
  theme from `npx @google/design.md@0.4.0 export --format css-tailwind DESIGN.md`, drift-tested the same way).

### iOS

- TODO: tokens become SwiftUI values; where the system follows Apple's Human Interface Guidelines over this file (navigation, sheets, Dynamic Type).

### Android

- TODO: tokens become Compose values; where the system follows Material 3 (navigation by window size class, predictive back).

## Decisions

<!-- Each direction a person picked for the design system itself, from an exploration's comparison page (`aidd explore`):
     newest last, never rewritten. A Spec's own UI direction goes in that Spec's Design section instead. -->

| Date | Question | Picked | Why the others lost | Picked by | Exploration |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | TODO | TODO: the folder |

## Changing the design system

- A change to this file or `design/tokens.json` is its own change, routed normal by `baseline:design-system`. The
  product designer is its author, and a person reviews it. It never rides inside a feature.
- A Spec that needs a token or component this system lacks names it in its design spec as a proposed change. The
  designer opens that change first. The Spec's own design files never hold a copy of the tokens.
- Generated files (this file's token mirror, the CSS, a SwiftUI or Compose theme) are regenerated from the tokens,
  never edited by hand. In `tests`: the drift test `node design/build.mjs --check`, and the design.md lint (a broken
  reference or a pair below 4.5:1 fails). A change here also runs `npx @google/design.md@0.4.0 diff` against the base
  branch's copy, which exits 1 on a regression.
