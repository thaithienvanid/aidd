# The prototype tool

aidd-team's built-in tool for the product designer's prototypes. It shows a design in the prototype viewer, checks it, and reads its component contract, which the built UI's stories match by name. It is `prototype.py` and `design_checks.py` beside it, both standard-library Python, so it runs wherever Python 3.11 does, with aidd or without it. Keep the two together. With aidd, `aidd prototype` runs it.

## The three parts

| Part | Owner | Where |
| --- | --- | --- |
| The viewer: the review column, device frames, the Board, System, notes, build details, and full screen | aidd-team, this folder's `viewer.html` | never in a project: each page is written to `.aidd/views/` from the viewer as it stands |
| A design: tokens, styles, chrome, screens, and example data | the product designer | a Spec's prototype file, or the product prototype in `docs/design/app/`. Each starts from `design.html`, a neutral skeleton that takes the project's own tokens from `design/tokens.css` |
| The showcase: a complete design to learn the format from | aidd-team, `examples/showcase.html` | shown by `example` (`aidd prototype --example`), never copied into a project, so it biases no design |
| The component contract: each `data-component`, its variants, screens, and test ids | read from the design, never kept by hand | printed by `components`, checked against Storybook by `stories` |

Because the viewer is never copied into a project, every design gets every fix to it. A design Spec approval froze is never rewritten. It is shown again in the current viewer.

## Commands

Run it from the project's root, with the copy that came with aidd-team. Below, `$TOOL` is that file: `"${CLAUDE_PLUGIN_ROOT}/tools/prototype/prototype.py"` inside Claude Code, or the same path under wherever aidd-team is installed.

```sh
python3 "$TOOL" new-product --name "Field Notes"      # start docs/design/app/
python3 "$TOOL" build                                 # the product prototype
python3 "$TOOL" build specs/SPEC-12/design/prototype.html
python3 "$TOOL" check                                 # check only, exit 1 on a problem
python3 "$TOOL" check specs/SPEC-12/design/prototype.html   # every problem, each with its line
python3 "$TOOL" components                            # the component contract, as JSON
python3 "$TOOL" screens specs/SPEC-12/design/prototype.html # the screens and their states, as JSON
python3 "$TOOL" stories storybook-static/index.json   # exit 1 on a variant with no story
python3 "$TOOL" new-design directions/a.html --title "Cards"
python3 "$TOOL" example --open                        # the showcase, to learn from, opened in your browser
```

With aidd, the same commands are `aidd new product-prototype`, `aidd prototype [file]`, `--check`, `--components`, `--screens`, `--stories <index.json>`, `--new-design <file>`, `--example`, and `--open`, which opens the written page in your browser.

## The viewer

Each page is one design in three views, beside your review. The left column holds the round, how many states you have seen, the next one you haven't (`N`), and each screen with its states. **Prototype** is the screen you click through, in the frame you pick: the web at 320, 768, 1024, or 1440 wide or full width, iPhone, Android, or a desktop app at 1280 or 1440. A phone fits whole; a web page or a window fits by its width. A window under 768 px wide opens the iPhone frame when the link names no frame, and keeps it out of the link. **Checks** turns on text at 200%, right to left, and a phone's safe areas. Below 1440 px, Checks also holds the theme, Fit, and 100%. On the Board it holds Every state and Links between screens too. That keeps the controls on one row. A script picks a frame with `?frame=` in the link, or by selecting it in the `proto-frame` list. **Board** shows each screen as a row and each state as a column, marked seen, not seen, or with notes. A click opens that state, and **Links between screens** draws an arrow for each link; drag to pan, and Ctrl or Cmd with the wheel to zoom. **System** shows the tokens and the components.

| Key | Does |
| --- | --- |
| `[` and `]` | hide or show the review column and the notes; a frame too wide for them closes them |
| `1` to `8` | show a core state |
| `J` and `K` | the next or previous state |
| `N` | the next state you haven't seen |
| `C` | turn notes on or off |
| `F` | full screen; `Esc` leaves |
| `?` | every shortcut, with a switch that turns the single-key shortcuts off |

**Add a note** pins a numbered note to an element, by its test id and, when several share one, its `index` among the visible ones. Its `box` is where the element showed in the frame's view when noted. Its kind says what to do: change, remove, add, or a question. Notes and the states seen stay in this browser per design and round; Download saves the round's file. The Notes tab lists the earlier rounds under the current one, each item done or open by the later rounds' `changes.json`. When the design names its Spec (`aidd-spec`), the panel ends with the words to type at your agent's prompt, such as `approve SPEC-24`, because the page records no decision. **Build details** lists each screen's components and test ids. **Compare** loads screenshots of the built UI, named `<screen>-<state>-<frame>-<theme>.png` as the screenshot loop writes them. It shows each beside the design, at the frame's width. Each view has a deep link, so a review comment points at one screen and state; `view=canvas` (the Board) or `system`, `safe=1`, and `feedback=1` open the rest.

### Feedback rounds

A round's notes, copied out of the viewer, go beside the design as `feedback-round-<N>.json`:

```json
{"round": 1, "items": [{"id": "r1-1", "kind": "remove", "screen": "home", "state": "empty", "testid": "home-banner", "note": "Remove this."}]}
```

The designer answers them in the next round's `rounds/<N+1>/changes.json`, naming each item it answers:

```json
{"changes": [{"answers": ["r1-1"], "summary": "Removed the banner."}]}
```

An item is done once a later round answers it. A file of another shape is left out, and the Notes tab says why. aidd's `schemas/feedback-round.schema.json` and `schemas/round-changes.schema.json` own both formats, and `aidd validate` warns on a file they reject.

## The design tools

The designer uses the design tools the project enabled, and with none, this tool alone. Enabled means the repository's own committed settings turn a tool on, such as Claude Code's `.claude/settings.json` and `.mcp.json`; a plugin installed for your whole machine is not enabled for a project. A person picks by enabling a tool in the project, as for every role's tools. `aidd extensions suggest --role product-designer` lists the designer's toolsets, such as `ai-design`. Each part shows its pin, what it can touch, and the Spec test command it adds. Other extensions the project enabled work too, such as Figma's or Penpot's MCP server, with tokens coming in as DTCG.

Whatever the tools, the work lands in this format and its contract, so the developer, the verifier, and the gate never change. Each tool's output is an input, rewritten into this format, as "Inputs, never sources" in `skills/prototyping/references/design-system-contract.md` says. Example data sent to any tool holds no real personal data.

## The design format

A design names its format on its `<html>`, `data-aidd-prototype="1"`, and the product's `sitemap.json` as `"format": 1`. A newer design than the tool asks for a newer tool, and the tool never guesses.

## The checks

- Every link and navigation item opens a screen, every screen has a state, and every flow is reachable. This holds for the product prototype.
- A design file, the one Spec approval freezes, gets the same care with every problem and its line: `check specs/SPEC-12/design/prototype.html`, or `aidd prototype --check` on the file. It exits 1 on any problem. On success it prints one line, such as `ok: 3 screens, 15 states, 41 test ids`.
  - Each `data-go` and `data-item-go` names a screen, and a `/<state>` that screen has. Each `data-initial` names a state its screen has, and each `data-parent` names a screen.
  - Every `button`, `a`, `input`, `select`, and `textarea` has a `data-testid`. A test id never repeats in one state, except in a list's item template, which repeats once for each item.
  - The first screen reaches every screen through `data-go`. A tab in the chrome counts, because it shows on every screen.
  - Every control has a name: text, an `aria-label`, a label, or an `alt`.
  - The prototype lint rules of `skills/prototyping/references/prototype-screenshots.md` hold, written in Python: no raw color outside the tokens block, no hotlink, no placeholder text, and no emoji as an icon.
  - A `{{placeholder}}` in a starting design is skipped, not the file.
  - A design is held to the rules of the format it names (`data-aidd-prototype`). Spec approval freezes the design and its check, so a newer aidd never fails it: a rule newer than the design prints as a `note:` under the ok line. A new rule after 1.0.0 comes with a new format, and a design takes it through its own change.
- `screens` prints each screen's id, title, parent, first state, and states in order, as JSON. A screenshot loop reads it instead of parsing the HTML.
- A list's item template is defined, by flow, so two flows may each name a `card`.
- The design runs nothing and reaches past nothing. It holds no script, event handler, or embed. Nothing closes, swallows, or hides its `<template id="product">`, whichever parser reads it.
- The page runs only the viewer's script, which its Content-Security-Policy names by hash.

## Components and stories

The designer names each reusable part `data-component="<name>"`, with `data-variant="<variant>"`. The developer builds one component per name, with a story per variant: its CSF title ends with the name, and its name is the variant, so `Components/NoteCard` with `Compact` matches `note-card` / `compact`. Names are lowercase words joined by hyphens. `stories` reads Storybook's static `index.json`, so the check needs no browser and no Storybook process.
