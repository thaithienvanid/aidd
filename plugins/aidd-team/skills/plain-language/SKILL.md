---
name: plain-language
description: "Practice skill: write at the level the reader needs. Use in an aidd repository when a Task writes prose a person reads: docs, Specs, runbooks, messages, or client documents."
metadata:
  checked: "2026-10-22"
---

# Plain language

**Use it when** a Task writes prose for a person: a doc, a Spec, a runbook, a handoff, a CLI message, or a client document.

**Do not use when** the text is code, a command, or data a program parses. Prose an agent reads, such as `AGENTS.md`, a skill, or a prompt, is `ste-80`.

## Standards

<!-- aidd:gen practice:plain-language -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| ASD-STE100 Simplified Technical English: its writing rules, and its controlled dictionary only where a project adopts it | Issue 9, January 2025 | 2026-10-16 | <https://www.asd-ste100.org/> |
| ISO 24495-1 plain language | ISO 24495-1:2023 | 2026-10-16 | <https://www.iso.org/standard/78907.html> |
| Docs under test: the prose linter (Vale) runs as a test command | Vale CLI v3.24.0 | 2026-10-22 | <https://vale.sh/> |
<!-- aidd:end -->

## Implement

### What the text does sets the level

There is no global default. ASD-STE100 was made for procedures and warnings, where a misread step costs the most. Text that explains reads better in a natural voice. Find the doc kind in this table, and write at its level.

| Level | The text | Doc kinds | Rules |
| --- | --- | --- | --- |
| `ste-80` | tells someone inside the team what to do, or states a rule | runbooks, rollback and observe steps, numbered install and onboarding steps, handoffs, Specs, approval text, CLI messages and denials, templates, normative rules | the ASD-STE100 writing rules, without its dictionary |
| `plain` | explains, or is read outside the team | READMEs, guides (quickstart, how-to, adoption, FAQ), changelogs, team digests, proposals, contracts, change orders, client status, user release notes | the ISO 24495-1:2023 principles, in a natural voice |
| `ste-100` | as the project decides | only the kinds the project lists in `project.writing.ste_100` | all of ASD-STE100, with its controlled dictionary |

A kind the table does not list is `ste-80`. A page that mixes both, such as a guide with numbered steps, writes its steps at `ste-80` and the rest at `plain`. A person may ask for any level. For `ste-100`, the project supplies the dictionary. aidd never includes it.

### `ste-80`

STE-80 follows ASD-STE100 mostly. It drops the dictionary and allows a tolerance. It does not stretch the numbers.

- Count each sentence by its type. An instruction has 20 words or fewer. A description has 25 words or fewer.
- Write one instruction in each sentence. Use the active voice.
- Use the terms in the project's GLOSSARY.md: one word, one meaning. Spell out a term or an abbreviation a reader outside the team may not know, at its first use.
- Keep 90% of the sentences within their limit. No sentence has more than 35 words.
- The limits apply to each sentence and are ceilings. Aim for an average of 15 to 20 words.
- Never split a sentence if the meaning is lost. A qualifier ("only", "unless", "otherwise") or a reference ("it", "there") must stay with its sentence. Use a list instead.
- Give each paragraph one topic, with about 6 sentences at most.

### `plain`

Apply the four principles of ISO 24495-1. Readers get what they need, find it easily, understand it, and can use it. Use the reader's words, not the team's. Never label the reader, or guess at what they know. The sentence limits of `ste-80` still hold, and the voice rules below matter most here.

### Voice: clear, and still natural

Short sentences alone don't make text easy to read. At every level but `ste-100`, talk to the reader who acts as "you". Link sentences with "so", "because", and "then", not with colons and parentheses, and give the reason with the rule. Each rule, with examples, is in [references/voice.md](references/voice.md). The words on a product's screens, state by state, are in [references/ux-copy.md](references/ux-copy.md).

### At every level

- Never paraphrase code, commands, paths, URLs, exact errors, or quotes. Copy them exactly, in code format.
- Write a security warning or a warning about an irreversible step in full sentences.
- Give a program structured data, such as YAML, JSON, or a table, never prose it must parse.

### Lists

- Use a numbered list when order matters: steps, an order of operations, or a priority. Use bullets when it does not.
- Never reorder a sequence.
- In a list of rules, put the most critical rule first.
- Keep a reference list in one stated order, such as alphabetical or by loop step.

## Review

- **Measured:** sentence length, with the Vale rule for the level. The `ste-80` rule fails over 35 words, because up to 10% of the sentences may pass their limit, and no sentence may pass 35. The 35 for `plain` is aidd's choice.
- **Measured where the project counts them:** the voice shares in [references/voice.md](references/voice.md).
- **By review:** the rules that no tool here measures.
  - The instruction and description limits, and the 90% share.
  - One instruction in each sentence, the active voice, the glossary terms, and one topic in each paragraph.
  - The voice rules: "you", the reasons, the links between sentences, and the read-aloud test.
  - The grammar, from agreement, articles, and tense to doubled words.
  - The list kind and the list order.
  - The ISO principles, the `ste-100` dictionary, and the exact text of code, paths, errors, and quotes.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Sentence length | no sentence is longer than its level allows | `vale` (v3.24.0) with one rule per level: `extends: occurrence`, `scope: sentence`, `token: '[^\s]+'`, `level: error`, and `max:` 35 for `ste-80` and `plain`, 25 for `ste-100`; `.vale.ini` maps each level to its doc kinds' paths |

## Stop if

- A rewrite would change a command, a path, an error, or a quote.
- A split would lose a qualifier or a reference.
- A kind is listed in `ste_100`, and the project supplies no dictionary.

## Hand off

- Done: the text at its level, and the Vale output. Next: the reviewer. Needs: the dictionary for an `ste-100` kind. Stopped at: none, or the stop rule that fired.
