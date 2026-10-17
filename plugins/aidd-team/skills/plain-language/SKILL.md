---
name: plain-language
description: "Practice skill: write at the level the reader needs. Use in an aidd repository when a Task writes prose a person reads: docs, Specs, runbooks, messages, or client documents."
metadata:
  checked: "2026-10-02"
---

# Plain language

**Use it when** a Task writes prose for a person: a doc, a Spec, a runbook, a handoff, a CLI message, or a client document.

**Do not use when** the text is code, a command, or data that an agent parses. Agents get structured data, not prose.

## Standards

<!-- aidd:gen practice:plain-language -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| ASD-STE100 Simplified Technical English: its writing rules, and its controlled dictionary only where a project adopts it | Issue 9, January 2025 | 2026-10-16 | <https://www.asd-ste100.org/> |
| ISO 24495-1 plain language | ISO 24495-1:2023 | 2026-10-16 | <https://www.iso.org/standard/78907.html> |
| Docs under test: the prose linter (Vale) runs as a test command | Vale CLI v3.23.0 | 2026-10-16 | <https://vale.sh/> |
<!-- aidd:end -->

## Implement

### The reader sets the level

There is no global default. Find the doc kind in this table, and write at its level.

| Level | Readers | Doc kinds | Rules |
| --- | --- | --- | --- |
| `ste-80` | inside the team | runbooks, rollback and observe steps, install and onboarding, handoffs, Specs, approval text, technical docs, team digests, CLI messages, templates | the ASD-STE100 writing rules, without its dictionary |
| `plain` | outside the team | proposals, contracts, change orders, client status, user release notes | the ISO 24495-1:2023 principles |
| `ste-100` | as the project decides | only the kinds the project lists in `project.writing.ste_100` | all of ASD-STE100, with its controlled dictionary |

A kind the table does not list is `ste-80`. A person may ask for any level. For `ste-100`, the project supplies the dictionary. aidd never includes it.

### `ste-80`

STE-80 follows ASD-STE100 mostly. It drops the dictionary and allows a tolerance. It does not stretch the numbers.

- Count each sentence by its type. An instruction has 20 words or fewer. A description has 25 words or fewer.
- Write one instruction in each sentence. Use the active voice.
- Use only the terms in the project's GLOSSARY.md: one word, one meaning.
- Keep 90% of the sentences within their limit. No sentence has more than 35 words.
- The limits apply to each sentence and are ceilings. Aim for an average of 15 to 20 words.
- Never split a sentence if the meaning is lost. A qualifier ("only", "unless", "otherwise") or a reference ("it", "there") must stay with its sentence. Use a list instead.
- Give each paragraph one topic, with about 6 sentences at most.

### `plain`

Apply the four principles of ISO 24495-1. Readers get what they need, find it easily, understand it, and can use it. Use the reader's words, not the team's.

### At every level

- Never paraphrase code, commands, paths, URLs, exact errors, or quotes. Copy them exactly, in code format.
- Write a security warning or a warning about an irreversible step in full sentences.
- Write prose for humans. Give agents structured data: YAML, JSON, or a table.

### Lists

- Use a numbered list when order matters: steps, an order of operations, or a priority. Use bullets when it does not.
- Never reorder a sequence.
- In a list of rules, put the most critical rule first.
- Keep a reference list in one stated order, such as alphabetical or by loop step.

## Review

- **Measured:** sentence length, with the Vale rule for the level. The `ste-80` rule fails over 35 words, because up to 10% of the sentences may pass their limit, and no sentence may pass 35. The 35 for `plain` is aidd's choice.
- **By review:** the rules that no tool here measures.
  - The instruction and description limits, and the 90% share.
  - One instruction in each sentence, the active voice, the glossary terms, and one topic in each paragraph.
  - The list kind and the list order.
  - The ISO principles, the `ste-100` dictionary, and the exact text of code, paths, errors, and quotes.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Sentence length | no sentence is longer than its level allows | `vale` (v3.23.0) with one rule per level: `extends: occurrence`, `scope: sentence`, `token: '[^\s]+'`, `level: error`, and `max:` 35 for `ste-80` and `plain`, 25 for `ste-100`; `.vale.ini` maps each level to its doc kinds' paths |

## Stop if

- A rewrite would change a command, a path, an error, or a quote.
- A split would lose a qualifier or a reference.
- A kind is listed in `ste_100`, and the project supplies no dictionary.

## Hand off

- Done: the text at its level, and the Vale output. Next: the reviewer. Needs: the dictionary for an `ste-100` kind. Stopped at: none, or the stop rule that fired.
