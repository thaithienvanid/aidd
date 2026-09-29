---
name: technical-writing
description: "Practice skill: write documentation people and agents can use. Use when a Task changes docs, a README, a guide, a tutorial, a changelog, release notes, an API reference, a runbook's prose, or agent instructions such as AGENTS.md, or when someone says document this, the docs are wrong or out of date, nobody can follow the setup, we use two words for one thing, or write the release notes: Diátaxis, plain language, docs as code, Keep a Changelog, glossary terms over ambiguous ones, and the test commands that keep docs honest."
metadata:
  checked: "2026-09-28"
---

# Technical writing

**Use it when** a Task changes documentation, a README, a changelog, release notes, or the instructions agents read.

**Do not use when** the text is a Spec's Acceptance or a code comment, which belong to their own authors and conventions; this is for prose a reader outside the change has to act on.

## Standards

- Diátaxis (tutorial, how-to, reference, explanation).
- The Google developer documentation style guide.
- ISO 24495-1:2023 plain language.
- Keep a Changelog 1.1.0.
- Semantic Versioning 2.0.0.
- Docs as code.
- WCAG 2.2 for documentation.
- `AGENTS.md` and an optional `llms.txt` index (few readers honor it yet) for agent readers.

## Implement

- Pick one Diátaxis type per page and keep it: a how-to has numbered steps with a goal, a reference is complete and generated from the source where possible, an explanation gives reasons, a tutorial is followed exactly as written.
- One idea per sentence, active voice, second person, present tense; terms from the project glossary and nothing invented; expand an acronym on first use.
- Flag an ambiguous term and replace it with the glossary's preferred one; where the glossary has an *Avoid* note, follow it. In an aidd repository: "Spec approval" and "Merge approval", not "sign-off" (a Proposal's decision only); "the gate" for `aidd/gate` only, never for a person's decision; "evidence" for what the test runner recorded on the head commit, never a pasted log or an agent's summary.
- Every command and code sample runs as written; every link resolves; every screenshot has alt text; generated tables are never edited by hand.
- Changelog entries follow Keep a Changelog under the unreleased heading; release notes say what changed for the reader, not what was done.

## Test commands

- A Markdown linter; a link checker; a spell checker with the project's word list; the docs build; code samples executed in CI; the generated-table check (`aidd gen-docs --check` in the aidd repository).

## Review

- Could a new reader complete the task without asking? Do the words match the glossary, and is each flagged term either replaced or listed in the handoff? Is anything stated that the code does not do?

## Hand off

- Done: the pages and the changelog entry. Next: the reviewer. Needs: a fact only the author of the change can confirm. Stopped at: none, or the stop rule that fired.
