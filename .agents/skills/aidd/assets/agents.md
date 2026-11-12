<!-- The project's guide for every agent that works here: one per repository, owned by the architect, living. Write only what
     an agent cannot read from the code and would get wrong without it. A change that makes a line untrue updates it in the
     same change, and a lesson from a retro or an incident comes back as a change to it. AGENTS.md is agent config, so a
     person reviews each change. aidd's own section, from its marker down, is aidd's: leave it. -->

## This project

TODO: what the project is and who it serves, in two sentences. Then the team's current goal, in one measurable sentence, such as "make onboarding succeed on the first try". Every agent weighs an open choice against the goal and says so. Name the language of ticket titles and PR summaries, when it is not English.

## Build, test, and run

TODO: each command exactly as it runs here, in a code span, with what it does. Cover install, one test, the linters and type checks, and the local preview. `aidd test` runs the whole suite, so never restate it.

## Layout

TODO: only what the folder names do not say. Name where each type of change goes, and any folder that is generated or must not be edited. For a monorepo, say how the parts depend on each other and which hold their own `AGENTS.md`.

## Principles and conventions

TODO: one line for each rule that a linter or the code does not show. Write it as the action to take, with its reason: "Use X for Y, because Z". For the detail, point to the architecture overview (`docs/architecture/README.md`), the glossary (`docs/GLOSSARY.md`), and the design system (DESIGN.md). Never copy them.

## Rules

TODO: what every change keeps, as "always", "ask first", and "never" lines. Name the sensitive areas (`risks`), what never goes in a commit, and the standards the project adopted. A rule that a test, a linter, or a risk rule can hold lives there, and this section only names it.

## Read first

TODO: the documents an agent reads before its first change here, each as a path with one line on when to read it.
