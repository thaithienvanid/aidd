---
name: data-model-design
description: "Practice skill: design a config or data model. Use in an aidd repository when a Task adds or edits a schema, config key, file format, field, enum, or who writes one, or a name clashes with a sibling."
metadata:
  checked: "2026-11-13"
---

# Data-model design

**Use it when** a Task adds or changes a shape that other software or people depend on: a schema, config key, file format, field, enum, code, or id. An HTTP API's body is one too, and so is a local store that a later version of the same program reads. Load it in Specify as well, because the shape freezes at Spec approval and is hard to change later.

**Do not use when** the data is internal and nothing outside the code reads it. A command-line tool's flags are `aidd-team:cli-design`.

## Standards

<!-- aidd:gen practice:data-model-design -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Google AIP-140: Field names | AIP-140 (Approved) | 2026-11-10 | <https://google.aip.dev/140> |
| Google AIP-141: Quantities | AIP-141 (Approved) | 2026-11-10 | <https://google.aip.dev/141> |
| Google AIP-142: Time and duration | AIP-142 (Approved) | 2026-11-10 | <https://google.aip.dev/142> |
| Google AIP-144: Repeated fields | AIP-144 (Approved) | 2026-11-10 | <https://google.aip.dev/144> |
| Google AIP-180: Backwards compatibility | AIP-180 (Approved) | 2026-11-10 | <https://google.aip.dev/180> |
| Google AIP-216: States | AIP-216 (Approved) | 2026-11-13 | <https://google.aip.dev/216> |
| RFC 9413 Maintaining Robust Protocols: the robustness principle, read with stated rules for unexpected input | RFC 9413 | 2026-11-12 | <https://www.rfc-editor.org/rfc/rfc9413.html> |
| Kubernetes API conventions | — | 2026-11-10 | <https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md> |
| Relational normal forms: each fact stored once, as a fact about its key | Kent, Communications of the ACM 26(2), 1983 | 2026-11-13 | <https://www.bkent.net/Doc/simple5.htm> |
| Cognitive walkthrough: whether a new user can learn a system, tested on tasks set in advance | — | 2026-11-13 | <https://www.nngroup.com/articles/cognitive-walkthroughs/> |
| JSON Schema 2020-12 | 2020-12 | 2026-11-10 | <https://json-schema.org/draft/2020-12/json-schema-core> |
| Spectral, a JSON and YAML linter | 6.17.0 | 2026-11-10 | <https://github.com/stoplightio/spectral> |
<!-- aidd:end -->

## Specify

- List the siblings (the fields or keys of the same kind), and write the one sentence each new one holds. This skill owns the shape: what it groups and merges with, and what may come later. `aidd-team:naming` owns the name: its family, and whether it can still change.
- Look for the same kind of thing at another scope: on the object's parent, on its parts, or on a neighbouring object. Where one exists, the new one takes its name and its shape, and where it sits tells the scope. `aidd-team:naming` has the test for one kind against two (`references/systems.md`, "One word at several scopes"). AIP-140 asks for the same name for the same concept, and different names for different concepts.
- For each new or changed field, record its writer, its readers, the copy that decides, and its trust class. Put them in the field's description, or in the Spec where the format has none. Say them once where every field shares them, and for one field only where it differs.
- For each new field, and each link between two objects, write how many the domain has: exactly one, none or one, or many. A single value where the domain has many is the costliest shape to change later.
- One field holds one fact. Split an enum whose value joins two facts, when the two vary on their own. Where one fact always follows from another, store one and read the other from it, with the three exceptions that `references/states.md` names.
- Read a value that joins a set with the whole set. Every value answers one question and is one kind of thing. A set that keeps growing may be one that should not exist (`references/states.md`, "A set of values").
- Give each object whose state changes one state table: each state, the event that moves it there, who causes that event, and what comes next. A derived answer is a view, never a state. What comes after a final state is never one more state: [references/states.md](references/states.md) gives its three shapes.
- The rules, each with its standard: [references/data-model-design.md](references/data-model-design.md), for grouping, merging, room to grow, name families, flow and trust, change, and how to hold them.
- The project's own name families win over a guide. When they differ, say so in the Spec.
- A new object with a state, a set of codes, or rules and settings that people write by hand may owe a proof before a person sees it: [references/design-proof.md](references/design-proof.md). Its parts are the model on one page, a worked example, a normal-form table, the likely changes, and the hard cases. Where the change owes all six parts, the last is a cold read by a reader who has no context. It says what each change owes, and that an internal record with no state owes none.

## Implement

- Write the check that holds a family, a schema test or a linter rule, in the same change as the first field that needs it.

## Review

- Read the schema as a newcomer would. The review checks and the blocking comment are in `aidd-team:naming`.
- Check that every field has a reader, every reference by name resolves, and a value the reader does not know fails closed, never as success.
- Read each set that gains a value as a whole, with its old values (`references/states.md`, "A set of values").
- Read each state field against its state table. Every value has a row, no derived value is listed as a state, and nothing on a finished object means that work is still owed.
- Walk each state table through its hard cases yourself (`references/states.md`). Each fact that a person's decision writes says who may write it, and what enforces that.
- The parts of the design proof that the change owes are there, and no more. Where a cold read was due, it holds the reader's answers as the reader wrote them, and a fix for each finding. A read by the author, or by a reader who saw the chat, is no proof.
- Rank each finding by what it costs a reader. It blocks when, on the model as it stands, a reader would write a wrong value, get a wrong answer, lose data, or trust a value that anyone can write. It blocks only where nothing on the page or in the checks would catch that. A gap that leaves every answer right is a note.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Schema lint | every property name keeps its family | `npx @stoplight/spectral-cli@6.17.0 lint <schema> --ruleset .spectral.yaml`, with one rule per family, such as `casing` over `$..properties[*]~`, as a `tests.commands` entry with `when_changed` on the schema |
| Schema family test | the schema keeps its families and every property has an effect | a unit test that walks each schema file, with an allow-list of `{name: reason}` for exceptions |
| Reference test | every string key that names a record, file, function, or handler resolves | a unit test that collects each such key and looks it up in the registry it names, with a case for one that resolves nowhere |
| State table test | every value of a state field has a way in, and a way out unless it is final | a unit test that reads the state field's values and the moves the code allows, and fails on a value that no move reaches, and on one that is not final and has no move out |
| Answer table | a change that removes or renames a field, or changes what one decides, leaves every reader's answer the same, except the ones it intends | a generated table of inputs with the rows empty, one, many, and unknown, run through every reader on the base commit and on the head; the differences are listed and each one is intended |

## Stop if

- A shipped name, field, or code would change meaning or disappear in one step: use expand and contract (`aidd-team:naming`).
- A field a person writes is cut or renamed, and an old value has no stated destination: stop until each one has a destination or a refusal.
- A new name clashes with a sibling and the glossary does not decide it: a person decides.
- A finished object would gain a state, a code, or a flag that means something is still owed. Give what comes later one of the three shapes in `references/states.md`.
- The cold reader still answers wrong after the second read: bring the open findings to a person, and never explain them away.

## Hand off

- Done: the shape, its sibling check, the family test or lint rule, the state table of each state field, and the parts of the design proof that the change owed. Next role: the reviewer. Needs: a person, for a clash the glossary does not decide, or for a finding the cold read left open. Stopped at: none, or the stop rule's code.
