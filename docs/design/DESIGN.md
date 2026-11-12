---
version: alpha
name: "aidd's built-in pages"
# generated from src/aidd/views/design/tokens.json by `aidd gen-docs`: never edit by hand
colors:
  background: "#fafaf9"
  foreground: "#1c1b19"
  card: "#ffffff"
  card-foreground: "{colors.foreground}"
  popover: "{colors.card}"
  popover-foreground: "{colors.foreground}"
  primary: "#4d4b47"
  primary-foreground: "{colors.background}"
  secondary: "{colors.muted}"
  secondary-foreground: "{colors.foreground}"
  muted: "#f4f4f2"
  muted-foreground: "#5b5955"
  accent: "#ebeae7"
  accent-foreground: "{colors.foreground}"
  destructive: "{colors.fail}"
  border: "#1c1b191f"
  input: "#87847e"
  ring: "#2563eb"
  ring-halo: "#2563eb40"
  link: "#1d5fd1"
  backdrop: "#e8e7e4"
  scrim: "#1c1b1973"
  shadow-color: "#1c1b1914"
  pass: "#17764c"
  fail: "#be1e3c"
  pending: "{colors.muted-foreground}"
  warn: "#8f5a00"
  warn-subtle: "#fcf4e2"
  emergency: "#b83d0b"
  emergency-foreground: "#ffffff"
  emergency-subtle: "#fdede4"
  comment: "#6d28d9"
  comment-foreground: "#ffffff"
  comment-subtle: "#f3eefe"
  diff-added: "#e4f4ea"
  diff-removed: "#fcebe8"
  background-dark: "#151514"
  foreground-dark: "#e4e2de"
  card-dark: "#1e1e1c"
  card-foreground-dark: "{colors.foreground-dark}"
  popover-dark: "{colors.card-dark}"
  popover-foreground-dark: "{colors.foreground-dark}"
  primary-dark: "#d0cec9"
  primary-foreground-dark: "{colors.background-dark}"
  secondary-dark: "{colors.muted-dark}"
  secondary-foreground-dark: "{colors.foreground-dark}"
  muted-dark: "#1b1b19"
  muted-foreground-dark: "#b9b6b0"
  accent-dark: "#282725"
  accent-foreground-dark: "{colors.foreground-dark}"
  destructive-dark: "{colors.fail-dark}"
  border-dark: "#e4e2de1f"
  input-dark: "#7e7b75"
  ring-dark: "#60a5fa"
  ring-halo-dark: "#60a5fa40"
  link-dark: "#8cb4ff"
  backdrop-dark: "#232321"
  scrim-dark: "#00000099"
  shadow-color-dark: "#00000073"
  pass-dark: "#5bc98b"
  fail-dark: "#ff8a9b"
  pending-dark: "{colors.muted-foreground-dark}"
  warn-dark: "#f0b94e"
  warn-subtle-dark: "#2f2710"
  emergency-dark: "#ff8f57"
  emergency-foreground-dark: "#1a0d06"
  emergency-subtle-dark: "#392218"
  comment-dark: "#c4a7ff"
  comment-foreground-dark: "{colors.background-dark}"
  comment-subtle-dark: "#272140"
  diff-added-dark: "#14301f"
  diff-removed-dark: "#3a1d1c"
typography:
  meta:
    fontFamily: "system-ui, -apple-system, Segoe UI Variable Text, Segoe UI, Roboto, sans-serif"
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: 0rem
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI Variable Text, Segoe UI, Roboto, sans-serif"
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0rem
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI Variable Text, Segoe UI, Roboto, sans-serif"
    fontSize: 1rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0rem
  display:
    fontFamily: "system-ui, -apple-system, Segoe UI Variable Text, Segoe UI, Roboto, sans-serif"
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0rem
  code:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: 0rem
rounded:
  sm: 0.375rem
  md: 0.5rem
  lg: 0.625rem
  full: 9999px
spacing:
  "0_5": 0.125rem
  "1": 0.25rem
  "1_5": 0.375rem
  "2": 0.5rem
  "3": 0.75rem
  "4": 1rem
  "6": 1.5rem
  "8": 2rem
components:
  foreground-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
  foreground-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.foreground}"
  foreground-on-muted-dark:
    backgroundColor: "{colors.muted-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.foreground}"
  foreground-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-backdrop:
    backgroundColor: "{colors.backdrop}"
    textColor: "{colors.foreground}"
  foreground-on-backdrop-dark:
    backgroundColor: "{colors.backdrop-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-warn-subtle:
    backgroundColor: "{colors.warn-subtle}"
    textColor: "{colors.foreground}"
  foreground-on-warn-subtle-dark:
    backgroundColor: "{colors.warn-subtle-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-emergency-subtle:
    backgroundColor: "{colors.emergency-subtle}"
    textColor: "{colors.foreground}"
  foreground-on-emergency-subtle-dark:
    backgroundColor: "{colors.emergency-subtle-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-comment-subtle:
    backgroundColor: "{colors.comment-subtle}"
    textColor: "{colors.foreground}"
  foreground-on-comment-subtle-dark:
    backgroundColor: "{colors.comment-subtle-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-diff-added:
    backgroundColor: "{colors.diff-added}"
    textColor: "{colors.foreground}"
  foreground-on-diff-added-dark:
    backgroundColor: "{colors.diff-added-dark}"
    textColor: "{colors.foreground-dark}"
  foreground-on-diff-removed:
    backgroundColor: "{colors.diff-removed}"
    textColor: "{colors.foreground}"
  foreground-on-diff-removed-dark:
    backgroundColor: "{colors.diff-removed-dark}"
    textColor: "{colors.foreground-dark}"
  muted-foreground-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.muted-foreground-dark}"
  muted-foreground-on-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-muted-dark:
    backgroundColor: "{colors.muted-dark}"
    textColor: "{colors.muted-foreground-dark}"
  muted-foreground-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.muted-foreground-dark}"
  muted-foreground-on-backdrop:
    backgroundColor: "{colors.backdrop}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-backdrop-dark:
    backgroundColor: "{colors.backdrop-dark}"
    textColor: "{colors.muted-foreground-dark}"
  muted-foreground-on-comment-subtle:
    backgroundColor: "{colors.comment-subtle}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-comment-subtle-dark:
    backgroundColor: "{colors.comment-subtle-dark}"
    textColor: "{colors.muted-foreground-dark}"
  primary-foreground-on-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
  primary-foreground-on-primary-dark:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.primary-foreground-dark}"
  emergency-foreground-on-emergency:
    backgroundColor: "{colors.emergency}"
    textColor: "{colors.emergency-foreground}"
  emergency-foreground-on-emergency-dark:
    backgroundColor: "{colors.emergency-dark}"
    textColor: "{colors.emergency-foreground-dark}"
  comment-foreground-on-comment:
    backgroundColor: "{colors.comment}"
    textColor: "{colors.comment-foreground}"
  comment-foreground-on-comment-dark:
    backgroundColor: "{colors.comment-dark}"
    textColor: "{colors.comment-foreground-dark}"
  pass-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.pass}"
  pass-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.pass-dark}"
  pass-on-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.pass}"
  pass-on-muted-dark:
    backgroundColor: "{colors.muted-dark}"
    textColor: "{colors.pass-dark}"
  pass-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.pass}"
  pass-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.pass-dark}"
  fail-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.fail}"
  fail-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.fail-dark}"
  fail-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.fail}"
  fail-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.fail-dark}"
  warn-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.warn}"
  warn-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.warn-dark}"
  warn-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.warn}"
  warn-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.warn-dark}"
  emergency-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.emergency}"
  emergency-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.emergency-dark}"
  emergency-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.emergency}"
  emergency-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.emergency-dark}"
  comment-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.comment}"
  comment-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.comment-dark}"
  link-on-background:
    backgroundColor: "{colors.background}"
    textColor: "{colors.link}"
  link-on-background-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.link-dark}"
  link-on-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.link}"
  link-on-muted-dark:
    backgroundColor: "{colors.muted-dark}"
    textColor: "{colors.link-dark}"
  link-on-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.link}"
  link-on-card-dark:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.link-dark}"
  link-on-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.link}"
  link-on-accent-dark:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.link-dark}"
  foreground-on-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
  foreground-on-card-dark:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.foreground-dark}"
  muted-foreground-on-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.muted-foreground}"
  muted-foreground-on-card-dark:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.muted-foreground-dark}"
  pass-on-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.pass}"
  pass-on-card-dark:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.pass-dark}"
  emergency-on-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.emergency}"
  emergency-on-card-dark:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.emergency-dark}"
  fail-on-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.fail}"
  fail-on-muted-dark:
    backgroundColor: "{colors.muted-dark}"
    textColor: "{colors.fail-dark}"
  warn-on-warn-subtle:
    backgroundColor: "{colors.warn-subtle}"
    textColor: "{colors.warn}"
  warn-on-warn-subtle-dark:
    backgroundColor: "{colors.warn-subtle-dark}"
    textColor: "{colors.warn-dark}"
  link-on-warn-subtle:
    backgroundColor: "{colors.warn-subtle}"
    textColor: "{colors.link}"
  link-on-warn-subtle-dark:
    backgroundColor: "{colors.warn-subtle-dark}"
    textColor: "{colors.link-dark}"
  link-on-emergency-subtle:
    backgroundColor: "{colors.emergency-subtle}"
    textColor: "{colors.link}"
  link-on-emergency-subtle-dark:
    backgroundColor: "{colors.emergency-subtle-dark}"
    textColor: "{colors.link-dark}"
# end generated
---

# Design system: aidd's built-in pages

This is the one design system of the pages aidd and aidd-team write. They are the prototype viewer, its design format doc,
`aidd status --html`, and `aidd explore`. This file is the contract in words. The contract in numbers is
[`tokens.json`](../../src/aidd/views/design/tokens.json), in the W3C Design Tokens format, and the components' rules
are [`components.css`](../../src/aidd/views/design/components.css). The [reference page](reference.html) draws every
token and component in both themes, and each page's fidelity pass compares against it.

<!-- The token front matter above is generated from tokens.json by `aidd gen-docs`, and `--check` fails on drift. Never
     edit it by hand. Its `components` entries list every text pair a page draws, in both themes, so
     `npx @google/design.md@0.4.0 lint` can check them too. The prose below is written by hand, by the product designer. -->

## Overview

Daylight paper and ink. The pages are instruments a person reads between agent runs, sometimes during an incident,
so they stay light, calm, and dense, and they never decorate. An off-white page, faintly warm greys, and near-black text
carry the work. Blue marks only where you can go, a link, and where you are: the focus ring, and the ring around the
current thumbnail, such as a state on the prototype viewer's Board. A state speaks in its own hue, with a word and an
icon. You read a page in the order you act on it: what waits for you, then what moves on its own.

- **The ink rule.** Color means a state; blue alone marks a link, focus, and the current thumbnail; nothing is decoration. Everything else is the text's color on paper.
- **The word rule.** A state is a word with its icon. Color never carries a state alone, so a page reads the same in
  forced colors and in grayscale.
- **The three looks rule.** Focus is a blue ring, the current row is a bar, and a chosen option is a fill. The current
  thumbnail, such as a state on the Board, is a thick blue ring with a soft glow, and focus adds a thin ring outside
  it. They never look alike.
- **The one primary rule.** A view has at most one primary button. On a page that only reads, it is the Copy of the
  one next step the view leads with, such as an item's next step or the current row. Every other Copy is a default button.
- **The mono rule.** Mono is for what a machine reads: an id, a path, a command, the words to copy. Prose is never mono.
- **The truth rule.** aidd advises, and a page only reads. No word, color, or badge says that aidd approved, blocked,
  enforced, or verified anything. A page says who decides and what to type.

The voice is plain and second person. A page names the next step a person takes, and an error says how to fix it. It
never says "approved" for a choice nobody made, "verified" for a summary, or "blocked" for advice.

## Colors

Each role takes the name shadcn/ui gives it, so a later rebuild on shadcn/ui and Tailwind v4 carries it over unchanged.
aidd's own roles follow, for states that shadcn/ui has no name for. A role that equals another names it, so a theme
changes in one place.

The front matter above holds each role's value in each theme, and the [reference page](reference.html) draws them.
This table says what each role is for. "Equals" names the role it takes its value from.

| Role | What it colors | Equals |
| --- | --- | --- |
| `background` | the page | |
| `foreground` | body text, headings, links | |
| `muted` | a panel, a callout, a board column, a words-to-copy field, a table's header | |
| `muted-foreground` | secondary text: an id, a count, a time, a hint | |
| `accent` | a hovered control or row, and the current row | |
| `primary`, `primary-foreground` | the primary button, a pressed segment, a chosen row, Blocked, the toast: a graphite fill one step off the text in light, a soft light grey in dark | none; `background` |
| `border` | a hairline between rows and around panels, and a meter's track: the text at 12%, so a hairline reads the same on every surface | |
| `input` | the edge of a button, a field, a segment group, and kbd | |
| `ring` | the focus ring, and the ring around the current thumbnail, such as a state on the Board: a blue of its own, never the ink, a state, or a comment, so neither reads as pressed or chosen | |
| `ring-halo` | the soft halo outside a focused field: `ring` at 25%, as a `color-mix()` | |
| `card`, `popover`, `secondary`, each with its `-foreground` | a card on a board column, white in light and lighter than the page in dark; a menu, the keys dialog, and the toast's layer; shadcn/ui's `secondary`, kept for the mapping | none; `card`; `muted` |
| `destructive` | an error; the pages offer no destructive action | `fail` |
| `backdrop` | the viewer's artboard, under a design frame or a screenshot | |
| `link` | a link's text; never a fill and never a state | |
| `shadow-color` | the one shadow's ink | |
| `scrim` | behind a dialog | |
| `pass` | a run that passed, and finished work; never a state a person has only looked at | |
| `fail` | a run that failed | |
| `pending` | not run, not answered, not seen; a dashed edge carries it | `muted-foreground` |
| `warn`, `warn-subtle` | a file aidd cannot read, an overdue flag, a link that opened something else | |
| `emergency`, `-foreground`, `-subtle` | an open emergency, always with its icon and the word | |
| `comment`, `-foreground`, `-subtle` | a comment on a design; only the viewer draws it | |
| `diff-added`, `diff-removed` | an added or a removed line, with its sign | |

Two rules keep the states honest:

- **One hue, one meaning.** The emergency's orange appears for an open emergency and nothing else. A comment is violet,
  so a person never reads a review note as a production repair. A warning is amber, so a page's problem with a file never
  looks like an emergency. Green means passed or finished, so a state a person has seen is a filled check in the text's
  color, never green.
- **Waiting is not a color.** Most work waits on someone, so `pending` is the secondary text's gray with a dashed edge. A
  page that colored every waiting item would color most of itself.

### Contrast

Every pair passes WCAG 2.2 AA in both themes. Text needs 4.5:1, and an edge, an icon, or a fill needs 3:1. `tokens.json`
lists each pair a page draws under `$extensions.aidd.contrast`, with its least ratio and where a page draws it. A test
computes each ratio from the tokens, and the reference page lists them all. A role with alpha, such as `border`, is
measured as drawn over the page. The closest calls are the light theme's state hues on the current row's fill, such as
Passed and the Emergency flag, and a control's edge in a panel.

### Comfort

AA is the floor, and comfort is the target above it, for a person who reads these pages for hours. `tokens.json` holds
the bands under `$extensions.aidd.comfort`, the one owner of their numbers, and a test checks each in both themes.
WCAG 2.2 AA stays the normative floor. APCA-W3 0.0.98G-4g, a candidate contrast method outside any W3C standard
(emerging), measures the bands as an aid. The bands are aidd's own convention, calibrated on Material 3's levels, never
APCA's thresholds, and APCA's size table does not apply.

- **Body text** reaches 7:1 and sits in an APCA band, high in light and softer in dark, so it reads crisp. It never
  glares, so it is never pure black on pure white, or near-white on near-black.
- **Secondary text** stays plainly readable in both themes, and it sits a clear step below body text.
- **A fill bigger than an icon**, such as a primary button, a pressed segment, a chosen row, or the toast, stays under
  the fill cap on the page, a card, and a dialog. So `primary` is a graphite in light and a soft grey in dark, never
  the text's full ink.
- **Disabled text** in `input` stays visible, above its own floor, so a disabled control still reads as one.
- **A wide surface**, a page, a panel, a row, or a notice, keeps a low chroma. The overdue emergency banner is the one
  saturated exception.
- **The dark page** is a grey, never black.
- **Opacity** is for decoration only: a hairline, a halo, a scrim, a shadow, an underline, and a dimmed thumbnail. A dimmed
  thumbnail keeps its seen mark and its count at full strength, because the dimming changes neither fact. Text always
  takes a solid role, because text drawn with opacity changes its contrast with whatever lies behind it.

## Themes

- Light and dark hold the same role names. A page follows `prefers-color-scheme`, and `data-theme="light"` or
  `data-theme="dark"` on any element sets its theme for everything inside it. The reference page uses that to show both
  themes side by side.
- The theme applies before the first paint, because the tokens are in the page's one style block.
- The viewer's product theme is a separate control. It changes the design in the frame, never the viewer around it.

## Typography

The reader's own system font, so a page loads nothing. Four sizes, each with its line height, in rem, so text at 200%
grows the layout with it.

| Token | Use |
| --- | --- |
| `--text-meta` | an id, a count, kbd, code, a hint |
| `--text-body` | body text, controls, rows |
| `--text-title` | an item's title, a section heading, a lead |
| `--text-display` | the page's one heading |
| `--font-sans` | every word but code: `system-ui` first, then each platform's name for it |
| `--font-mono` | ids, paths, commands, the words to copy |
| `--font-weight-normal`, `-medium`, `-semibold` | body; tabs and kbd; headings, titles, flags |

Numbers use tabular figures, so counts line up. A title takes `dir="auto"`, so a right-to-left title sits correctly
beside left-to-right words.

## Layout

- **Spacing.** A step is 0.25rem times its name, as Tailwind v4 counts it. The steps are `--spacing-0_5`, `-1`, `-1_5`,
  `-2`, `-3`, `-4`, `-6`, and `-8`, where `_` stands for the decimal point. Space inside a component is smaller than
  the space between components.
- **Sizes.** `--size-control` is the height of a button, a field, and a segment group. `--size-target` is the least a
  control draws both ways, 24px at the default text size (WCAG 2.2 SC 2.5.8). `--size-icon` sizes an icon, and
  `--size-bar` is the top bar's height.
- **Columns.** A page of rows and prose runs at most `--container-text`. A page with a side column runs at most
  `--container-page`, and the keys dialog is `--container-dialog` wide.
- **Prose.** A block of prose a person reads, such as an item's next step, takes `.prose` and runs at most
  `--container-prose`, about 80 characters a line (WCAG 2.2 SC 1.4.8). A one-line row may run wider, so no rule narrows
  every paragraph.
- **Breakpoints.** A media query cannot read a token, so it writes a `--breakpoint-*` value in rem, by range syntax,
  such as `(width < 40rem)`. A test checks each one against the tokens. Below
  40rem the tabs take their own row, and below 48rem the viewer's panels become a tab bar. Below 64rem a side column
  moves under the main one, and from 80rem the viewer shows both side panels.

## Elevation & Depth

Three levels, and one shadow. The page is `background`. A panel is one step of tone, `muted`, with a hairline in
`border`. A floating layer, the keys dialog, a menu, or the toast, sits on `popover` with `--shadow-raised`. In light
mode the page is an off-white, and a raised surface, `card` or `popover`, is white. In dark mode the page is a tuned
grey, never pure black, and a raised surface is lighter. The shadow there
only separates. A card on a board column stays flat: tone and its hairline lift it.

## Shapes

`--radius-sm` rounds kbd, a flag, and a badge's corner. `--radius-md` rounds a button, a field, and a segment group.
`--radius-lg` rounds a panel, a callout in a box, a board column, and a dialog.
`--radius-full` makes a count badge and a comment pin round. A hairline is `--border-width-thin`, and the current tab's
underline, the current row's bar, and the emergency banner's edge are `--border-width-thick`.

## Motion

`--duration-fast` moves a hover and a chevron, and `--duration-base` moves a drawer and a toast. Each
uses `--ease-standard`. Motion explains a change of state and never delays the person. Under
`prefers-reduced-motion: reduce`, both durations are 0, and nothing moves or pulses.

## Components

Each component is one set of rules in `components.css`, and every page uses those rules and adds none of its own. A
component keeps its class, its name, and its states in the code, the reference page, and the tests. A control also
keeps the `data-testid` its page gives it, because the tests select on it.

### Page shell

The page is the top bar, one main column, and the foot. Its parts are `.shell`, `.page`, `.page-wide`, `.page-head`,
`.lead`, `.section`, and `.foot`. The main column is the `<main id="main">` the skip link moves to. The foot says when the
page was written and that a page is never evidence and never approves.

### Top bar and toolbar

The top bar holds the product's name and what the page is, the views as tabs, and the tools at its end. Its height is
`--size-bar`, and a hairline sits under it. The toolbar is a row of controls for the view below it, such as the viewer's
frame and theme, or the Board's columns and teams. Below 40rem the tabs take their own row and share its width evenly.

| Part | Class | States and tokens |
| --- | --- | --- |
| Top bar | `.topbar`, `.topbar-name`, `.topbar-end` | `background`, a `border` hairline under it |
| Tabs | `.tabs`, each tab an `a` or a `button` | `muted-foreground`; hover and current in `foreground`; the current one has a thick bar in `foreground` |
| Toolbar | `.toolbar`, `.grow` to push the rest to the end | `background`, a `border` hairline under it |

A tab bar is a `nav` with a name, and its current tab carries `aria-current="page"`. In the viewer, where the tabs switch
a panel in place, they are a `tablist` and the current one carries `aria-selected="true"`.

### Button

| Variant | Class | Use |
| --- | --- | --- |
| Default | `.btn` | any action: an outline in `input` on `background` |
| Primary | `.btn .btn-primary` | the one action a view leads with, such as Copy, or Next state you haven't seen |
| Quiet | `.btn .btn-quiet` | a tool in a bar, such as Keyboard shortcuts |
| Icon | `.btn .btn-icon` | a square button with an icon alone; it needs an `aria-label` |
| Comment | `.btn .btn-comment` | Add a comment, in the viewer only |

Each draws its default, hover (`accent`), focus (the ring), pressed (`aria-pressed="true"`, a `primary` fill), open
(`aria-expanded="true"`, `accent`), and disabled state. A disabled button keeps its words in `muted-foreground` and
a `border` edge, never a lowered opacity. Every button is at least `--size-control` tall and `--size-target` wide. A
`kbd` inside a primary or pressed button takes the button's color.

### Segmented control

One choice from two to five, drawn as one control: `.seg` around `button` elements, each with `aria-pressed`. The chosen
segment is filled with `primary`. A count inside a segment is a `.count`. Use a select instead when the choices pass five.

### Link

A link in text is underlined in `foreground`. A quiet link, `.link-quiet`, is `muted-foreground` with its underline in
`input`; it sits in a foot or a bar, such as Copy link. A button that reads as a link is `.link`, so it still has a 24px
target.

### Field, select, and switch

A text field, a search, and a select are one size, `--size-control`, with an `input` edge on `background`. A field's
label sits above it in `muted-foreground`, from `.label`. The switch, `.switch` with `role="switch"`, shows its state as
a word, On or Off, in a pill that fills with `primary` when on.

### kbd

A key to press: `kbd` in `--text-meta`, with an `input` edge that is thick at the bottom. A page that turns the
single-key shortcuts off hides its kbd hints, so it never shows a key that does nothing.

### Count and badge

A count, `.count`, is a number in text in `muted-foreground`, after a heading or as "1 of 4". A badge, `.badge`, is a
number in a round pill: `primary` for a tally, and `.badge-comment` for a design's comments. Use a badge only on a control
or a pin. Anywhere else, use a count.

### Flag

A flag says one state in a word with its icon, in `--text-meta`. The icon is decorative and hidden from assistive
technology, because the word says it.

| Variant | Class | Says |
| --- | --- | --- |
| Neutral | `.flag` | Needs you, Seen, a team, a step |
| Muted | `.flag .flag-muted` | Waits for SPEC-14, Due in 2 days |
| Strong | `.flag .flag-strong` | Blocked, Stopped: a `primary` fill, so it stands out with no hue |
| Pending | `.flag .flag-pending` | Not run yet, Not seen: a dashed `pending` edge |
| Pass | `.flag .flag-pass` | Passed, Done |
| Fail | `.flag .flag-fail` | Failed |
| Warn | `.flag .flag-warn` | Unreadable, Overdue, Gone in round 2 |
| Emergency | `.flag .flag-emergency` | Emergency |

A flag never judges a change. "Changed" and "New in round 2" are neutral, because a change is neither good nor bad. A
flag never says aidd decided, and it never states as done what still waits. A step waits on a person, and the flag says
so, such as "Waits for Mai".

### Box and callout

A box, `.box`, groups related content on `muted` with a hairline and `--radius-lg`, such as an item's next step. A
callout, `.callout`, says something about the page, with its icon first.

| Variant | Class | Use |
| --- | --- | --- |
| Notice | `.callout .callout-notice` | a file aidd cannot read, a link that opened something else, the design's problems |
| Emergency | `.callout .callout-emergency` | an open emergency, above every view: `emergency-subtle` with a thick `emergency` edge |
| Overdue | `.callout .callout-overdue` | an emergency whose review is past due: an `emergency` fill, with every part inside in `emergency-foreground` |

A callout that spans the page has no radius. Inside a box, it takes `--radius-md`.

### Table

`.table` in a `.table-wrap`, which scrolls sideways inside its own box on a narrow screen. The caption names the
table, the header row sits on `muted` in `--text-meta`, and a hairline separates the rows. Each header cell carries
`scope`. A table is for data with columns; a list of term and value is a facts list.

### Facts list

`dl.facts`, a term in `muted-foreground` beside its value, in two columns. Below 40rem it becomes one column, the value
under its term.

### Code and words to copy

`code` and `pre` are mono in `--text-meta`, and `.id` is a muted id that never wraps. The words to copy, `.words`, are
the one line a person pastes into their agent: the words in a `muted` field, and a Copy button. Copy is a default
button, and a primary one only for the next step the view leads with. A label above
them, `.words-label`, says where they go, such as "Say to your agent". With scripts off, the button stays hidden and the
words stay selectable. On a phone the button takes its own row. Copy says what it copied once, in the page's status line.

### Current row, chosen option, and progress

- A row, `.row`, takes `accent` on hover. The row a keyboard cursor points at carries `aria-current="true"`, and it
  draws a thick bar in `foreground` at its start and the `accent` fill.
- An option, `.option`, is one of a list a person picks from, such as the viewer's states. The chosen one carries
  `aria-checked="true"` or `aria-selected="true"`, and it is filled with `primary`.
- A meter, `.meter`, is a track in `border` and a fill in `primary`. The words beside it say what it counts, such as
  "3 of 9 finished" or "1 of 15 states seen", so the meter is never the only cue.

### Toast and dialog

A toast, `.toast`, shows an outcome for a few seconds at the foot of the window, filled with `primary`. The page's live
region says the same words once, so a screen reader skips the toast. A dialog, `.dialog`, is the keys list on `popover`
over the `scrim`. It is a `dialog` element opened with `showModal()`. Esc closes it, and focus returns to the button
that opened it.

### Empty, loading, and error states

| State | Class | What it says |
| --- | --- | --- |
| Empty | `.state .state-empty` | what is missing, and the one next step, such as the words that start the first Spec |
| Error | `.state .state-error` | what happened, the file and line, and how to fix it; the page around it still works |
| Loading | `.state` with `aria-busy="true"`, and `.placeholder` | the layout, with each part not there yet as a `muted` block, and no spinner |

An error never blames the person. A page written from files has no loading state of its own. Only the viewer loads,
when it draws its Board's cells.

### Skip link

`.skip` is the first stop on every page. It shows only while it has focus, at the top left, and it moves to `main`.

### Focus

Focus has its own hue, `ring`, a blue that no state, comment, or fill uses, so focus never reads as pressed or chosen.
It reaches 3:1 on `background`, `muted`, `accent`, `border`, and `backdrop` in both themes (WCAG 2.2 SC 1.4.11 and
2.4.7), and the contrast test checks each pair.

The ring's blue also marks the current thumbnail: a state on the prototype viewer's Board. Each ring there is drawn
from the thumbnail it marks. It sits on a halo a focus offset outside the thumbnail's own edge, so it follows the
corners and never repeats the edge, whether that edge is a phone's dark bezel or a window's hairline. The current state
has a thick ring with a soft glow in `ring-halo`, the cell under the pointer has a thin one, and keyboard focus adds a
second, thin ring outside, on the current state too.

- **A button, a link, a tab, a segment, and the switch** show an outline of `--focus-width` in `ring`, `--focus-offset`
  from the control, with a halo of `--focus-halo` in `background`. Beside an outlined button's ink edge, the blue ring
  reads as focus, not as a second border, and the halo keeps it clear of a fill and of the emergency banner. A segment's
  ring sits inside it, on a halo of `background`, because a segmented control scrolls on a narrow screen and would clip
  a ring outside it.
- **A field, a select, and a textarea** draw no outline and no gap, as shadcn/ui's and GitHub Primer's inputs do. The
  border turns to `ring`, an inset shadow of `--border-width-thin` doubles it inside, and a halo of `--focus-field-halo`
  in `ring-halo` sits outside.
- In the overdue banner the ring takes `emergency-foreground`. Sticky content never hides a focused control (WCAG 2.2
  SC 2.4.11). Under forced colors the system's `Highlight` draws the outline, and a field gets a transparent outline of
  `--focus-width`, which the system paints.

### Forced colors

Under `forced-colors: active` the system's colors replace these, and a fill disappears. So a pressed segment, a chosen
option, the switch when on, a primary button, a strong flag, and a badge take the system's `SelectedItem`. The current
row's bar, the current tab's bar, and a meter's fill take `Highlight`.

## Patterns

- **Navigation.** One view at a time, its tab current, and the view and its filters in the URL. Back returns to the
  view a person came from.
- **The next step.** Each item says who acts next and what they type. The words to copy are the only action, so a
  page never needs a form.
- **A file aidd cannot read.** One notice callout names the file, the line, and the fix, on every page alike. The rest of
  the page still renders.
- **When.** A page is written once and read later, so the top bar says when it was written, and every date is a date. A
  phrase such as "in 2 days" appears only where the page's script works it out when you read it. With scripts off, the
  date stands alone.
- **Who says it.** A recommendation, a comment, and a change name who wrote them, such as "the product designer
  recommends". A page never states a person's yes it has not seen.
- **The foot.** Every page ends with one line: aidd advises, and this page records no decision and is never evidence.
- **Help.** Each page lists its keys in one dialog, opened with `?`, and the dialog's switch turns the single-key
  shortcuts off.

## Do's and Don'ts

- Do keep one primary button per view, filled with `primary`. Every other action is an outline button.
- Do use blue only for a link, for focus, and for the current thumbnail.
- Do pair every state hue with its word and its icon.
- Do lift with tone and a hairline. Only a floating layer gets `--shadow-raised`.
- Don't put a shadow on a card, a row, or a panel.
- Don't use pure black or pure white text, or pure black in dark mode.
- Don't tint a large area with a state hue. A subtle state background is for a notice or a banner only.
- Don't fill anything bigger than an icon with ink. Such a fill takes `primary`, a step off the text.
- Don't draw text with opacity. Secondary or disabled text takes `muted-foreground` or `input`.
- Don't add a second accent, a gradient, or a pill button.

## Accessibility

WCAG 2.2 AA is the floor on every page, and comfort is the target, as Colors says. Every pair passes in both themes. Every control is reachable by
keyboard, with the focus ring above. Every target is at least 24 by 24 CSS px. No state is told by color alone. Every page
works at 320 CSS px wide, at 200% text, under forced colors, and with reduced motion. An axe run on each page, in each
theme, finds nothing.

## Platforms

### Web

`aidd gen-docs` writes the tokens as CSS custom properties, the shadcn/ui names for colors and the Tailwind v4
namespaces for the scale. Light sits on `:root` and `[data-theme="light"]`, and dark on `[data-theme="dark"]` and under
`prefers-color-scheme: dark`. A page's CSS uses only these tokens and the rules in `components.css`.

### Mermaid diagrams

The diagrams in aidd's Markdown take their colors from one palette, by the rule in the `aidd-team:diagrams` skill
(craft D14). GitHub draws a diagram with Mermaid 12.2 in a frame. In light mode it uses Mermaid's `default` theme on a
white page, `#ffffff`, with text in `#333333`. In dark mode it uses Mermaid's `dark` theme on `#0d1117`, with text in
`#cccccc`. One `classDef` applies in both, so the palette draws each box as a tint the page shows through:

- **A tint, not a fill.** A class fills its box with its border's color at low alpha and sets no text color. On the
  white page the box is a light stone card, and on the dark page a dark stone card, from one line, as the hero image's
  cards are in each scheme. The reader's theme keeps the text, which reads at 9.3:1 to 10.5:1 on every tint, inside the
  comfort band. A box sits at 1.1:1 to 1.3:1 against the page, so a diagram never glares in either mode.
- **A border mixed for both pages.** Each border is its role's light and dark values mixed to the point where it reads
  alike on both pages, at 4.1:1 to 4.6:1. On its own tint it keeps 3.3:1 or more.
- **A neutral group.** A subgraph takes `group`, or `boundary` when it is a trust, ownership, or runtime boundary, by a
  `class` line on the subgraph. Its 8% tint replaces Mermaid's yellow group in light mode and its grey slab in dark mode.
- **One opaque class.** `human` is `primary` with `primary-foreground` from the light theme, at 8.3:1: dark on the
  white page, a soft lift on the dark one, with its mixed border at 4.3:1 or more.
- **The rest keeps the theme.** Lines, edge labels, and subgraph titles stay Mermaid's own, which reads on each page. A
  sequence or an entity diagram takes no class, so it keeps the theme too.

Every flowchart copies `default` and the classes it uses from here, unchanged, and a test checks every diagram against
these lines. They are aidd's version of the default palette that the design-system template ships (`aidd new
design-system`): the same classes and technique, with aidd's stone and accents, and `human` opaque. The aidd skill's
templates and the `diagrams` skill's example keep the template's default.

```text
classDef default fill:#7a787433,stroke:#7a7874,stroke-width:1px
classDef group fill:#7a787414,stroke:#7a7874
classDef boundary fill:#7a787414,stroke:#7a7874,stroke-dasharray:6 4
classDef focus fill:#3373ef26,stroke:#3373ef,stroke-width:4px
classDef human fill:#4d4b47,stroke:#7a7874,stroke-width:2px,color:#fafaf9
classDef added fill:#27895b26,stroke:#27895b,stroke-width:2px
classDef changed fill:#7f7d7833,stroke:#7f7d78,stroke-width:3px
classDef removed fill:#d23e5826,stroke:#d23e58,stroke-width:2px,stroke-dasharray:6 4
```

| Class | Marks | Told apart without color by | Its colors, from the roles |
| --- | --- | --- | --- |
| `default` | every box no other class marks | a 1px border | the border mixes `primary`; the tint is the border at 20% |
| `group` | a subgraph that groups steps or parts | a faint 8% tint | the border mixes `primary`; the tint is the border at 8% |
| `boundary` | a subgraph that is a boundary: trust, ownership, or runtime | a dashed border | the border mixes `primary`; the tint is the border at 8% |
| `focus` | the one or two parts the diagram is about, such as the system in scope | a 4px border | the border mixes `ring`; the tint is the border at 15% |
| `human` | a person, or a point where a person decides | its shape, a stadium or a hexagon, and its opaque fill | `primary` and `primary-foreground`, light; the border mixes `primary` |
| `added` | a part the change adds | a 2px border, and the change's table | the border mixes `pass`; the tint is the border at 15% |
| `changed` | a part the change alters or moves | a 3px border, and the change's table | the border mixes `primary`; the tint is the border at 20% |
| `removed` | a part the change removes | a dashed 2px border, and the change's table | the border mixes `fail`; the tint is the border at 15% |

The status classes stay apart under the three common color-vision deficiencies, simulated with Machado, Oliveira, and
Fernandes (2009) at full severity. The closest pair is `changed` and `removed` under protanopia, at a CIE76 difference of
11.3. To keep that pair apart, `changed` takes a mix a step lighter than `default`'s, and `removed` a mix a step toward
the light theme's red, with every border still above 4:1. The dash on `removed` and the width on `changed` tell them
apart without color, and a diagram of a change keeps a table keyed by node id.

### Device frames

A device frame is the screen a design is drawn in. Its size is a real device's, never a number someone picked. The table
below holds every size, in CSS px, in `tokens.json`: the viewer draws from it, `aidd prototype --check` measures against
it, and the prototyping skill points to it. A size enters the table with the public source it was read from and the day,
and a size no source confirms stays out.

- **Fixed height.** A frame has the table's height, and its design scrolls inside. A frame that grows with its content is wrong.
- **One frame.** A prototype built outside the tool reuses the tool's frame. A design that must draw its own marks the
  element `data-device="<frame>"` and gives it the table's width and height, with `overflow-y: auto`.
- **A name, never a number.** A link or a screenshot names a frame, such as `?frame=ios`. A bare size such as `frame=360` is no frame.
- **System bars from a source too.** A phone's row holds `safe_area`, its status bar and bottom bar in CSS px, each read
  from its own public source. The viewer draws them and gives the design the same values as `--safe-area-inset-*`. A row
  with none draws no bar, because no bar is more honest than a wrong one.

<!-- aidd:gen devices:frames -->
| Frame | Name and platform | CSS px | Devices with this size | Source, read on |
| --- | --- | --- | --- | --- |
| `ios` | iPhone, ios | 390 by 844 | iPhone 12 Pro, iPhone 14, iPhone 16e | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `android` | Android, android | 412 by 915 | Pixel 7, Pixel 8, Pixel 8a, Samsung Galaxy S20 Ultra | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `320` | Web, web | 320 by 568 | iPhone SE (1st generation), iPhone 5s | [www.ios-resolution.com](https://www.ios-resolution.com/iphone-se-1st-gen/), 2026-11-11 |
| `768` | Web, web | 768 by 1024 | iPad Mini, upright | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `1024` | Web, web | 1024 by 768 | iPad Mini, on its side | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `1440` | Web, web | 1440 by 900 | Chrome's laptop with a HiDPI screen | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `desktop` | Desktop app, desktop | 1280 by 800 | Chrome's laptop with an MDPI screen | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
| `desktop-1440` | Desktop app, desktop | 1440 by 900 | Chrome's laptop with a HiDPI screen | [raw.githubusercontent.com](https://raw.githubusercontent.com/ChromeDevTools/devtools-frontend/main/front_end/models/emulation/EmulatedDevices.ts), 2026-11-11 |
<!-- aidd:end -->

### Mapping to shadcn/ui and Tailwind v4

A later rebuild on React, Tailwind v4, and shadcn/ui keeps every name. Its `:root` and `.dark` blocks take the color roles
as they are, its `@theme inline` maps each one to `--color-<role>: var(--<role>)`, and its `@theme` takes the scale.

| Here | shadcn/ui or Tailwind v4 | Note |
| --- | --- | --- |
| `--background`, `--foreground`, `--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent`, each with `-foreground`; `--destructive`, `--border`, `--input`, `--ring` | the same shadcn/ui variables | the values move unchanged, in hex or as `oklch()` |
| `--pass`, `--fail`, `--pending`, `--warn`, `--emergency`, `--comment`, their `-foreground` and `-subtle`, `--backdrop`, `--scrim`, `--diff-added`, `--diff-removed` | added to `:root` and `.dark`, and to `@theme inline` as `--color-*` | utilities such as `text-emergency` and `bg-warn-subtle` |
| `--chart-1` to `--chart-5`, `--sidebar-*` | not defined | no page draws a chart; the viewer's review column uses the base roles |
| `--radius-lg` | `--radius`, which shadcn/ui's sm, md, and lg derive from | sm and md are lg less 4px and 2px, as here |
| `--radius-full` | Tailwind's `rounded-full` | |
| `--link` | `--link` in `:root` and `.dark`, and `--color-link` in `@theme inline` | the utility `text-link` |
| `--shadow-raised`, `--shadow-color` | `--shadow-raised` as a `--shadow-*` key in `@theme`; `--shadow-color` stays in `:root` | the utility `shadow-raised` |
| `--spacing-N`, with `_` for the point | Tailwind's spacing scale, `p-N` from `--spacing: 0.25rem` | delete the named steps; `--spacing-1_5` is `p-1.5` |
| `--size-control`, `--size-target`, `--size-icon`, `--size-bar` | `--spacing-control` and the rest in `@theme` | utilities such as `h-control` and `size-target` |
| `--container-dialog`, `-text`, `-page` | `--container-*` | `max-w-text` |
| `--text-meta`, `-body`, `-title`, `-display`, each with `--line-height` | `--text-*` with `--text-*--line-height` | the values of Tailwind's `text-xs`, `text-sm`, `text-base`, and `text-xl`, so shadcn/ui's components need no override |
| `--font-sans`, `--font-mono`, `--font-weight-*` | `--font-*`, `--font-weight-*` | the same keys |
| `--duration-fast`, `--duration-base`, `--ease-standard` | `duration-120`, `duration-200`, `--ease-standard` | |
| `--breakpoint-sm` to `-xl` | Tailwind's default `--breakpoint-*` | the same values |
| `--focus-width`, `-offset`, `-halo` | `outline-2 outline-offset-2 outline-ring` with a `--background` ring shadow | a button, a link, a tab, a segment, the switch |
| `--focus-field-halo`, `--ring-halo` | `focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25`, shadcn/ui's input focus | a field, a select, a textarea |
| `--border-width-thin`, `-thick` | `border`, `border-2` | |

## Decisions

| Date | Question | Picked | Why the others lost | Picked by | Exploration |
| --- | --- | --- | --- | --- | --- |
| 2026-11-07 | The look of the work-items page | Direction A, tabs and pages, in the prototype viewer's paper and ink | the other directions drew a look of their own, a second system beside the viewer's | the owner | the page's directions |
| 2026-11-07 | The names of the tokens | shadcn/ui's color roles and Tailwind v4's namespaces, plus aidd's state roles | aidd's own names would need a mapping layer in the later rebuild on React, Tailwind v4, and shadcn/ui | the owner, as a direction the lead passed on | none |
| 2026-11-08 | How the pages stay comfortable through a long read | Accessible and comfortable: AA as the floor, the comfort bands in `tokens.json` as the target, an off-white page, a graphite `primary`, softer dark text, and a hairline drawn as the text at 12% | grey body text and text drawn with opacity lose contrast; AA alone left ink-black fills and dim dark secondary text | the owner | none |

## Changing the design system

- A change to `tokens.json`, `components.css`, or this file is its own change. `aidd risk --paths` routes it major,
  because the two source files sit in the `aidd_toolkit` area, so its Spec comes first and a person reviews it. The
  product designer is its author, and it never rides inside a page's change.
- `aidd gen-docs` writes the generated parts from `tokens.json`: the CSS the pages read, the copy in the prototype tool,
  and this file's front matter. Never edit them by hand, and `aidd gen-docs --check` fails on drift.
- A person rebuilds the reference page by hand after a change to `tokens.json` or `components.css`. A test
  fails when its style, token list, or contrast table drifts from them. A builder in `aidd gen-docs` waits, because the
  page's specimens are hand-written markup, and that test already catches drift.
- A page that needs a token or a component this system lacks waits for the change that adds it here first.

## Iteration Guide

For an agent changing a page:

1. Change one component at a time, and name it by its class in `components.css`.
2. Use roles and tokens by name, such as `--muted-foreground`, never a value.
3. Choose its level first: the page, a panel, or a floating layer.
4. A new color pair goes into `tokens.json`'s contrast list before any page draws it.
5. Run `aidd gen-docs --check` and the design tests, then compare with the reference page in both themes.
