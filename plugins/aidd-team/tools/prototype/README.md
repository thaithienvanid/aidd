# The prototype tool

aidd-team's built-in tool for the product designer's prototypes. It shows a design in the prototype viewer, checks it, and reads its component contract, which the built UI's stories match by name. It is `prototype.py` and `design_checks.py` beside it, both standard-library Python, so it runs wherever Python 3.11 does, with aidd or without it. Keep the two together, with `viewer.html` and `system.css`. With aidd, `aidd prototype` runs it.

## The three parts

| Part | Owner | Where |
| --- | --- | --- |
| The viewer: the review column, device frames, the Board, System, comments, build details, and full screen | aidd-team, this folder's `viewer.html` | never in a project: each page is written to `.aidd/views/` from the viewer as it stands. The viewer draws from aidd's design system: `system.css`, which `aidd gen-docs` writes from `src/aidd/views/design/` and the tool inlines, holds every value and the shared components, so the viewer writes no value twice. `aidd status --html` draws from the same system |
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
python3 "$TOOL" shots specs/SPEC-12/design/prototype.html --changed-component note-card   # the fidelity pass's views, sized to the change
python3 "$TOOL" stories storybook-static/index.json   # exit 1 on a variant with no story
python3 "$TOOL" new-design directions/a.html --title "Cards"
python3 "$TOOL" example --open                        # the showcase, to learn from, opened in your browser
python3 "$TOOL" serve specs/SPEC-12/design/prototype.html --lan   # open it on a phone on this network
```

With aidd, the same commands are `aidd new product-prototype`, `aidd prototype [file]`, `--check`, `--components`, `--screens`, `--shots` (with `--changed-screen <id>`, `--changed-component <name>`, and `--frames <ids>`), `--stories <index.json>`, `--new-design <file>`, `--example`, `--open`, which opens the written page in your browser, and `--serve`.

`serve` (`--serve`) is opt-in, for a review on a real phone. It serves the page on 127.0.0.1 until Ctrl-C, and builds it again on each reload, so an edit shows when you reload. `--lan` listens on the local network too, so a phone on the same network opens the address it prints, which carries a random token. It serves only the page and the files in the design's folder: no path out of it, no dot-file, and no folder listing. `AIDD_OFFLINE=1` keeps it off, and `--port` picks the port, 8765 by default.

## The viewer

Each page is one design in three views, beside your review. The left column holds the round, how many states you have seen, where you have seen them, the next one you haven't (`N`), and each screen with its states. **Prototype** is the screen you click through, in the frame you pick: the web at 320, 768, 1024, or 1440 wide or full width, iPhone, Android, or a desktop app at 1280 or 1440. The product theme sits beside the frame, as the frame's second axis, and Fit and 100% sit in the caption under it. Each frame has its row's fixed width and height, and the design scrolls inside it. Fit shows the whole frame, and the caption gives its width, its height, and the scale. A window under 768 px wide opens the iPhone frame when the link names no frame, and keeps it out of the link. There a frame fits by its width, and the artboard scrolls. From 768 to 1279 px wide, the bar holds Add a comment, since the comments are a closed drawer. **Test views** turns on text at 200%, right to left, and a phone's safe areas: the system bars its row of the device table gives, which the design reads as `--safe-area-inset-*`. On the Board it holds Every state and Links between screens too, and the bar holds Fit and 100%. Fit grows a board that leaves room, up to twice its size. A script picks a frame with `?frame=` in the link, or by selecting it in the `proto-frame` list. **Board** shows each screen as a row and each state as a column, marked seen, not seen, or with comments. A click opens that state, and **Links between screens** draws an arrow for each link and names the screens each row opens; drag to pan, and Ctrl or Cmd with the wheel to zoom. **System** shows the tokens and the components.

A state counts as seen once the Prototype view has shown it in each platform group the design styles and in each theme it styles. The groups are web, phone, and desktop app, read from the design's `data-platform` rules, and the themes are light and dark. Nobody clicks to mark a state seen. So every state seen means someone looked at the phone and at dark too. `N` opens the next state not seen in this group and theme, then moves on to the next group or theme.

| Key | Does |
| --- | --- |
| `[` and `]` | hide or show the review column and the comments; a frame too wide for them closes them |
| `1` to `9` | show a state of this screen, by its number in the list |
| `J` and `K` | the next or previous state, on into the next screen |
| `N` | the next state you haven't seen |
| `V`, `T`, and `D` | the next view, product theme, or frame |
| `C` | turn Add a comment on or off |
| `F` | full screen; `Esc` leaves |
| `?` | every shortcut, with a switch that turns the single-key shortcuts off |

**Add a comment** pins a numbered comment to an element, by its test id and, when several share one, its `index` among the visible ones. Its `box` is where the element showed in the frame's view when the comment was made. Its type says what to do: change, remove, add, or a question. A deleted comment leaves Undo in its place. Comments and the states seen stay in this browser per design and round. The Comments tab lists the earlier rounds under the current one, each comment done or open by the later rounds' `changes.json`. **Build details** lists each screen's components and test ids. **Compare** loads screenshots of the built UI, named `<screen>-<state>-<frame>-<theme>.png` as the screenshot loop writes them. It shows each beside the design, at the frame's width.

The panel ends with the closing block, which says what is left before the round ends. With comments, its one button sends them: it copies them as a prompt for your agent. With states not seen yet, it opens the next one. With every state seen and no comment open, it shows the approval your agent asks in the chat, such as "Approve SPEC-24?", when the design names its Spec (`aidd-spec`). The page records no decision. Each outcome shows for a few seconds and is said once to a screen reader, and agents read it at `proto-announce`.

Each view has a deep link, so a comment points at one screen and state. `view=board` or `view=system` opens a view, `show=unseen` or `show=commented` filters the Board, and `comments=1`, `compare=1`, `side=build`, and `safe=1` open the rest.

A link that names a screen, state, frame, theme, or view the design lacks opens the nearest one. It says so above the artboard, in the `proto-link-problem` banner, and as a console warning. That fallback never counts as seen until you move on. A link in the design that names no screen says where it goes when you click it, and stays put. A page built from a design with problems names them above the artboard too, in `proto-design-problems`: the list `check` prints. A screenshot loop waits for `data-ready="true"`: on `#workspace` once the frame has painted with its fonts, and on `#board` once every cell in view has loaded.

### A round's comments

A round's comments, copied out of the viewer, go in that round's folder beside the design, as `rounds/<N>/comments.json`:

```json
{"round": 1, "items": [{"id": "r1-1", "type": "remove", "screen": "home", "state": "empty", "testid": "home-banner", "comment": "Remove this.", "by": "agent:claude-code/claude-opus-5-5"}]}
```

An item may name its writer in `by`, by the shared identity: an agent writes `agent:<harness>/<model>`. The viewer writes none, so an item without `by` is a person's. The label is text the writer gave, never proof, and it decides nothing. Agent rounds run only before Spec approval, because after it a design change is `spec.revise`. The designer starts two reviewers as subagents, a critique and an accessibility pass, and gives each the design, the screenshots, and the Spec's Request, never its reasons. They return their comments and write nothing. The designer merges them into the round's one file, numbers the ids, and sets each `by`. A file holds the agents' pass or a person's, never both, and the designer never writes over a file, so a person's comments get the next round. A second model joins only when a person or the harness starts it, because aidd starts no agent. The designer answers each comment in the next round's `changes.json`. It does what a sound comment asks, or declines it with the reason as the summary. It never declines a person's comment without asking them. It stops for a person after the third agent round, at the timebox, and at a pass with no comment, which writes no file. It also stops at a comment only a person can settle. Such a comment touches scope, Acceptance, or a claim in the copy, or two reviewers disagree on it. It stays open in the viewer, which holds back its approval line. In an exploration, agents may comment on each direction, and only a person picks one.

The designer answers them in the next round's `rounds/<N+1>/changes.json`, naming each comment it answers:

```json
{"changes": [{"answers": ["r1-1"], "summary": "Removed the banner."}]}
```

A direction of an exploration, a design in its `directions/` folder, keeps its comments in the exploration's own round folder, one file per direction: `directions/a.html` writes `rounds/<N>/comments-a.json`. Its comment ids start with its name, such as `a-r1-1`, so two directions' ids never collide. Its file name takes letters, digits, and `-` only, and the tool refuses any other.

A comment is done once a later round answers it. A file of another shape is left out, and the Comments tab says why. aidd's `schemas/round-comments.schema.json` and `schemas/round-changes.schema.json` own both formats, and `aidd validate` warns on a file they reject.

## The design tools

The designer uses the design tools the project enabled, and with none, this tool alone. Enabled means the repository's own committed settings turn a tool on, such as Claude Code's `.claude/settings.json` and `.mcp.json`; a plugin installed for your whole machine is not enabled for a project. A person picks by enabling a tool in the project, as for every role's tools. The `product-designer` rows of the team skill's `references/extensions.md` list the designer's extensions, each with its pin and what it can touch. Other extensions the project enabled work too, such as Figma's or Penpot's MCP server, with tokens coming in as DTCG.

Whatever the tools, the work lands in this format and its contract, so the developer, the verifier, and the tests never change. Each tool's output is an input, rewritten into this format, as "Inputs, never sources" in `skills/prototyping/references/design-system-contract.md` says. Example data sent to any tool holds no real personal data.

## The design format

A design names its format on its `<html>`, `data-aidd-prototype="1"`, and the product's `sitemap.json` as `"schema_version": "1"` (before aidd 1.0.0 it was `"format": 1`, which the tool still reads). A newer design than the tool asks for a newer tool, and the tool never guesses.

Every word a screen shows comes from the fixtures, as text: `data-text` names a top-level field, and `data-field` a field of a list's item. An image field, `<img data-image="photo" alt="">`, shows the image its fixture names. The value is a `data:image` URI, or a file beside the design, such as `"photo": "people/mai.png"`. The page loads nothing, so the tool reads the file into the page. A path stays inside the design's folder: `..`, an absolute path, or a link out of it is a problem `check` names. A file is PNG, JPEG, GIF, WebP, AVIF, or SVG, at most 2 MB, and 20 MB a page. Write the alt text yourself, or `alt=""` when the words beside the image say who or what it is.

## The checks

- Every link and navigation item opens a screen, every screen has a state, and every flow is reachable. This holds for the product prototype.
- A design file, the one Spec approval freezes, gets the same care with every problem and its line: `check specs/SPEC-12/design/prototype.html`, or `aidd prototype --check` on the file. It exits 1 on any problem. On success it prints one line, such as `ok: 3 screens, 15 states, 41 test ids`. `build` on a design file runs the same check: it still writes the page, so you can look, then prints each problem and exits 1.
  - Each `data-go` and `data-item-go` names a screen, and a `/<state>` that screen has. Each `data-initial` names a state its screen has, and each `data-parent` names a screen.
  - Every `button`, `a`, `input`, `select`, and `textarea` has a `data-testid`. A test id never repeats in one state, except in a list's item template, which repeats once for each item.
  - The first screen reaches every screen through `data-go`. A tab in the chrome counts, because it shows on every screen.
  - Every control has a name: text, an `aria-label`, a label, or an `alt`.
  - The prototype lint rules of `skills/prototyping/references/prototype-screenshots.md` hold, written in Python: no raw color outside the tokens block, no hotlink, no placeholder text, and no emoji as an icon.
  - Every device frame is a row of the device table, `devices.json` beside the tool (aidd's design system writes it, with each size's source). A link names a frame by id, such as `?frame=ios`, and a bare size such as `frame=360` fails with the frames to name. A frame the design draws itself, `data-device="<frame>"`, has the table's width and height in px and `overflow-y: auto`, so it never grows with its content.
  - A `{{placeholder}}` in a starting design is skipped, not the file.
  - A design is held to the rules of the format it names (`data-aidd-prototype`). Spec approval freezes the design and its check, so a newer aidd never fails it: a rule newer than the design prints as a `note:` under the ok line. A new rule after 1.0.0 comes with a new format, and a design takes it through its own change.
- A list's item template is defined, by flow, so two flows may each name a `card`.
- The design runs nothing and reaches past nothing. It holds no script, event handler, or embed. Nothing closes, swallows, or hides its `<template id="product">`, whichever parser reads it.
- The page runs only the viewer's script, which its Content-Security-Policy names by hash.
- `screens` prints each screen's id, title, parent, first state, and states in order, as JSON, so an agent reads it instead of parsing the HTML.
- `shots` prints the views a fidelity pass takes, sized to the change as the prototyping skill's `references/design-review.md` says, and the screenshot loop takes them. With no option it lists the full matrix of every screen, and with `--changed-screen` the full matrix of that screen. With `--changed-component` it lists each screen the component appears on, then its states on each variant, then the narrowest frame and 200% text. It never lists none: a screen, a component, or a frame the design or the device table lacks is a problem. `screens`, `components`, and `shots` follow `schemas/design-manifest.schema.json` in aidd, and name their `schema_version`, as every versioned file does.

## Components and stories

The designer names each reusable part `data-component="<name>"`, with `data-variant="<variant>"`. The developer builds one component per name, with a story per variant: its CSF title ends with the name, and its name is the variant, so `Components/NoteCard` with `Compact` matches `note-card` / `compact`. Names are lowercase words joined by hyphens. `stories` reads Storybook's static `index.json`, so the check needs no browser and no Storybook process.
