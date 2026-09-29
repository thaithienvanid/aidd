# The design-system contract

Load this when you set up the design system a prototype uses, or check a generated theme against its tokens.

A prototype uses one named design system. The system is written down in two files, and both sit in the Spec's `design.files`, so Spec approval freezes them together with the prototype. The developer then builds against the same numbers the Approver saw.

## Where the files go

```text
docs/design/SPEC-220/
  DESIGN.md              the contract in words
  tokens.tokens.json     the contract in numbers (the source)
  tokens.css             generated from the source; never edited by hand
  directions/            the two or three rough directions, and which one was picked
  prototype/             the prototype that consumes tokens.css
```

When the product already has a design system, `DESIGN.md` names it and its version, and the tokens file is a copy or a pinned export of its tokens. Do not mix two systems in one prototype, and do not add a token the system lacks without asking: a missing token is a design decision, and it goes in the handoff's Needs line.

## DESIGN.md

Short, one screen if possible. Each section is a list, not an essay.

1. **Name and version.** Which design system this is, and where its source lives.
2. **Principles.** Three to five lines on what the design favors, such as "dense tables over cards" or "one primary action per screen".
3. **Type scale.** Each step by token name, with its size, line height, and use.
4. **Colour roles.** Roles, not hues: `surface`, `text`, `text-muted`, `accent`, `danger`, `focus`. Name the token behind each role and the contrast pair it must meet (4.5:1 for body text, 3:1 for large text and for controls, WCAG 2.2 SC 1.4.3 and 1.4.11).
5. **Spacing.** The scale by token name, and the rule for using it.
6. **Components used.** Only the ones this prototype uses, with the states each one needs.

## The tokens file

Use the Design Tokens Format Module 2025.10 (Design Tokens Community Group, a Final Community Group Report published 28 October 2025, the format's first stable version; it is not a W3C Standard). The file is JSON, named `*.tokens.json` or `*.tokens`. Each token has a `$value`, and a `$type` on the token or its group; an alias points to another token as `{group.token}`.

```json
{
  "color": {
    "$type": "color",
    "blue-600": { "$value": { "colorSpace": "srgb", "components": [0.145, 0.388, 0.922] } },
    "accent": { "$value": "{color.blue-600}", "$description": "Primary actions and links" }
  },
  "space": {
    "$type": "dimension",
    "2": { "$value": { "value": 8, "unit": "px" } }
  }
}
```

Roles (`color.accent`) point at raw values (`color.blue-600`). The prototype uses only roles.

## Generated files and the drift test

The CSS variables, a Tailwind theme, or a native theme are generated from the tokens file by a tool such as Style Dictionary (DTCG support since version 4; support for every 2025.10 detail is still in progress in version 5, so pin the version and check the output). Commit the generated file so a reviewer can read it, and add a test that proves it still matches its source:

```sh
npx style-dictionary build --config docs/design/SPEC-220/sd.config.json   # writes to a temporary folder
diff -u docs/design/SPEC-220/tokens.css "$TMP/tokens.css"                  # exit 1 when they drift
```

The same test works for any generator: regenerate into a temporary folder and diff with what is committed. Put the two lines in the design folder's lint script and give it its own entry in the Spec's `tests.commands` ([prototype-lint.md](prototype-lint.md)), so the tester freezes it with the rest.
