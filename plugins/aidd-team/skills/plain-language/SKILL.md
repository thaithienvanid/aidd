---
name: plain-language
description: "Practice skill: write at the level the reader needs. Use in an aidd repository when a Task writes prose a person reads: docs, Specs, runbooks, messages, or client documents."
metadata:
  checked: "2026-10-22"
---

# Plain language

**Use it when** a Task writes words a person or an agent reads, such as a doc, a Spec, a message, or an agent file.

**Do not use when** the text is code, a command, or data a program parses.

## Standards

<!-- aidd:gen practice:plain-language -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| ASD-STE100 Simplified Technical English: its writing rules, and its controlled dictionary only where a project adopts it | Issue 9, January 2025 | 2026-10-16 | <https://www.asd-ste100.org/> |
| ISO 24495-1 plain language | ISO 24495-1:2023 | 2026-10-16 | <https://www.iso.org/standard/78907.html> |
| Docs under test: the prose linter (Vale) runs as a test command | Vale CLI v3.24.0 | 2026-10-22 | <https://vale.sh/> |
<!-- aidd:end -->

## Implement

### 1. Answer three questions first

1. What will the reader do next? They decide, act, or look something up. Cut what does not serve that.
2. What is the answer? Put the result or decision first, then the reasons. In a step, a condition or a warning still comes before the action.
3. What has the reader not seen? A reader who just arrived knows no label you made while working, no id they cannot open, and no earlier talk.

### 2. Find the writing level

There is no global default, because what the text does sets its writing level.

| Writing level | The text | Doc types | Rules |
| --- | --- | --- | --- |
| `instruction` | tells someone inside the team what to do, or states a rule | runbooks, rollback and observe steps, install and onboarding steps, handoffs, Specs, approval text, CLI messages, templates, normative rules, agent files, skills, prompts | the ASD-STE100 writing rules, without its dictionary |
| `plain` | explains, or is read outside the team | READMEs, guides, changelogs, team digests, proposals, contracts, change orders, client status, user release notes, messages a customer reads | the ISO 24495-1:2023 principles, in a natural voice |
| `controlled` | as the project decides | the types the project lists in `project.writing.controlled` | all of ASD-STE100, with its controlled dictionary |

A type the table does not list is `instruction`. A page with both writes its steps at `instruction` and the rest at `plain`. A person may ask for any level. For `controlled`, the project supplies the dictionary, and aidd never includes it.

### 3. Keep the limits

| Limit | Value | Set by | Held by |
| --- | --- | --- | --- |
| Words in an instruction | 20 or fewer | ASD-STE100 | review |
| Words in a description | 25 or fewer | ASD-STE100 | review |
| Sentences past their limit | 10% at most; none at `controlled` | aidd | review |
| Words in any sentence | 35 at most | aidd | Vale |
| Instructions in a sentence | one | ASD-STE100 | review |
| Sentences in a paragraph | 6 at most, on one topic | ASD-STE100 | review |

ASD-STE100 is free only on request, so these figures come from public secondary sources. Vale cannot count a share, so it holds the 35 only. Limits are ceilings. Aim for an average of 15 to 20 words, aidd's aim.

### 4. Follow the rules of every level

- Use the active voice, and name who acts.
- Use the project's GLOSSARY.md terms, one word for one meaning. Spell out a term or abbreviation your reader may not know, at its first use.
- Give the fact, then its reason, joined by "so" or "because", never by a colon or parentheses.
- Name the specific thing, such as the number, the command, or the file.
- Say once what is unknown or not done, in plain words such as "not run" or "an estimate".
- Never split a sentence if the split loses a qualifier ("only", "unless", "otherwise") or a reference ("it", "there"). Use a list instead.
- Never paraphrase code, commands, paths, URLs, exact errors, or quotes. Copy them in code format.
- Write a security or irreversible-step warning in full sentences.
- At `plain`, apply the four ISO principles. Readers get what they need, find it, understand it, and use it. Say "you", in the reader's words.

### 5. Choose the form

| When the text | Use |
| --- | --- |
| is steps, an order, or a priority | a numbered list, one action in each step, never reordered |
| is items with no order | bullets in one stated order, the most critical first, each new item where that order places it |
| compares things, or gives each case its answer | a table |
| gives a reason, a condition, or an exception | a sentence with "because", "if", or "unless" |
| holds a number | digits with the unit, and dates as 2026-11-11 |
| is a message or an error | what happened, why, and the next step (`aidd-team:technical-writing`) |
| is words on a screen | [references/ux-copy.md](references/ux-copy.md) |
| is read by an agent | closed values, then a table, an example, steps, and prose last |
| is read by a program | structured data such as YAML, never prose |

### 6. Rewrite without a loss

1. Before a rewrite or a cut, list each fact, commitment, and qualifier.
2. After, check that each one kept its certainty, its conditions, and who acts. A "may" that became "will", a dropped "if", or a changed actor is a defect.

Each rule has a pair to copy in [references/examples.md](references/examples.md). The voice rules are in [references/voice.md](references/voice.md).

## Review

1. Run the Vale rule, and fix each sentence it names.
2. Check the writing level, the limits that only a review holds, the grammar, each term against the glossary, and at `controlled` the dictionary.
3. Check each code, path, error, and quote against its source.
4. Check each claim against what you ran or read. Mark or remove a claim you did not verify.
5. Cut what the reader would not miss, a preamble, a restated question, or a closing offer.
6. Read it as the reader. Could they act on it as the only text they read today?

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Sentence length | no sentence is too long | `vale` (v3.24.0) with one rule per level: `extends: occurrence`, `scope: sentence`, `token: '[^\s]+'`, `level: error`, and `max:` 35 for `instruction` and `plain`, 25 for `controlled`; `.vale.ini` maps each level to its doc types' paths |

## Stop if

- A rewrite would change a command, a path, an error, or a quote.
- A split would lose a qualifier or a reference.
- The project lists a type in `controlled` and supplies no dictionary.

## Hand off

- Done: the text at its level, and the Vale output. Next role: the reviewer. Needs: the dictionary for a `controlled` type. Stopped at: none, or the stop rule's code.
