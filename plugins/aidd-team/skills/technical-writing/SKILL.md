---
name: technical-writing
description: "Practice skill: write docs humans and agents can use. Use in an aidd repository when a Task changes docs, a README, a changelog, release notes, or AGENTS.md."
metadata:
  checked: "2026-09-30"
---

# Technical writing

**Use it when** a Task changes documentation, a README, a changelog, release notes, or the instructions agents read (`AGENTS.md`, and an optional `llms.txt` index, which few readers honor).

**Do not use when** the text is a Spec's Acceptance or a code comment, which have their own authors and conventions. This is for prose a reader outside the change acts on.

## Standards

<!-- aidd:gen practice:technical-writing -->
| Standard | Edition |
| --- | --- |
| Diátaxis (tutorial, how-to, reference, explanation) | — |
| Google developer documentation style guide | — |
| Keep a Changelog | 1.1.0 |
| Docs as code (reviewed, versioned, generated tables untouched) | — |
| WCAG 2.2 for documentation | 2.2 |
| AGENTS.md and Agent Skills conventions for agent-readable repositories | — |
| Docs for machine readers: an llms.txt index, a markdown version of every page an agent needs, and the link relations pointing at them (emerging) | llms.txt v2 of 2026-08-10 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:technical-writing`.
<!-- aidd:end -->

## Implement

- One Diátaxis type per page. A how-to has numbered steps toward a goal. A reference is complete and generated from the source where possible. An explanation gives reasons. A tutorial works exactly as written.
- Write at the level `aidd-team:plain-language` sets for the doc kind: it owns sentence length, voice, and glossary terms. Here: second person, present tense, an acronym expanded on first use.
- Follow the glossary's *Avoid* notes. In an aidd repository:
  - "Spec approval" and "Merge approval", not "sign-off" (a Proposal's decision only)
  - "the gate" for `aidd/gate` only, never a person's decision
  - "evidence" for what the test runner recorded on the head commit, never a pasted log or an agent's summary
- Every command and code sample runs as written. Every link resolves. Every screenshot has alt text. Generated tables are never hand-edited.
- Changelog entries follow Keep a Changelog under the unreleased heading. Release notes say what changed for the reader, not what was done.

## Review

- Could a new reader complete the task without asking? Do the words match the glossary, with each ambiguous term replaced or listed in the handoff? Does it state anything the code does not do?

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Markdown lint | the Markdown is well formed | `npx markdownlint-cli2@0.23.3 "**/*.md"` |
| Link check | every link resolves | `lychee` (v0.24.2) over the docs |
| Prose lint | the style guide's rules hold | `vale` (v3.23.0) with the project's styles |
| Spell check | no misspelling outside the project's word list | `uvx codespell==2.4.3` with the word list |
| Reading-level check | notices read at the reader's level, which `aidd-team:plain-language` sets; this row adds a grade measure | `vale` (v3.23.0) with a `metric` rule on the Flesch-Kincaid grade, or the Readability package (v0.2.0) |
| Docs build and samples | the docs build and every code sample runs | the docs build, and the samples executed in CI |
| Generated-table check | no generated table was edited by hand | `aidd gen-docs --check` in the aidd repository |

## Stop if

- A statement describes something the code does not do.
- A generated table is about to be edited by hand.
- You are about to guess a fact only the change's author can confirm.

## Hand off

- Done: the pages and the changelog entry. Next: the reviewer. Needs: a fact only the author of the change can confirm. Stopped at: none, or the stop rule that fired.
