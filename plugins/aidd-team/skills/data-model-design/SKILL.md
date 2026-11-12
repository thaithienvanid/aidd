---
name: data-model-design
description: "Practice skill: design a config or data model. Use in an aidd repository when a Task adds or edits a schema, config key, file format, field, enum, or who writes one, or a name clashes with a sibling."
metadata:
  checked: "2026-11-12"
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
| RFC 9413 Maintaining Robust Protocols: the robustness principle, read with stated rules for unexpected input | RFC 9413 | 2026-11-12 | <https://www.rfc-editor.org/rfc/rfc9413.html> |
| Kubernetes API conventions | — | 2026-11-10 | <https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md> |
| JSON Schema 2020-12 | 2020-12 | 2026-11-10 | <https://json-schema.org/draft/2020-12/json-schema-core> |
| Spectral, a JSON and YAML linter | 6.17.0 | 2026-11-10 | <https://github.com/stoplightio/spectral> |
<!-- aidd:end -->

## Specify

- List the siblings (the fields or keys of the same kind), and write the one sentence each new one holds. This skill owns the shape: what it groups and merges with, and what may come later. `aidd-team:naming` owns the name: its family, and whether it can still change.
- For each new or changed field, record its writer, its readers, the copy that decides, and its trust class. Put them in the field's description, or in the Spec where the format has none.
- The rules, each with its standard: [references/data-model-design.md](references/data-model-design.md), for grouping, merging, room to grow, name families, flow and trust, change, and how to hold them.
- The project's own name families win over a guide. When they differ, say so in the Spec.

## Implement

- Write the check that holds a family, a schema test or a linter rule, in the same change as the first field that needs it.

## Review

- Read the schema as a newcomer would. The review checks and the blocking comment are in `aidd-team:naming`.
- Check that every field has a reader, every reference by name resolves, and a value the reader does not know fails closed, never as success.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Schema lint | every property name keeps its family | `npx @stoplight/spectral-cli@6.17.0 lint <schema> --ruleset .spectral.yaml`, with one rule per family, such as `casing` over `$..properties[*]~`, as a `tests.commands` entry with `when_changed` on the schema |
| Schema family test | the schema keeps its families and every property has an effect | a unit test that walks each schema file, with an allow-list of `{name: reason}` for exceptions |
| Reference test | every string key that names a record, file, function, or handler resolves | a unit test that collects each such key and looks it up in the registry it names, with a case for one that resolves nowhere |
| Answer table | a change that removes or renames a field, or changes what one decides, leaves every reader's answer the same, except the ones it intends | a generated table of inputs with the rows empty, one, many, and unknown, run through every reader on the base commit and on the head; the differences are listed and each one is intended |

## Stop if

- A shipped name, field, or code would change meaning or disappear in one step: use expand and contract (`aidd-team:naming`).
- A field a person writes is cut or renamed, and an old value has no stated destination: stop until each one has a destination or a refusal.
- A new name clashes with a sibling and the glossary does not decide it: a person decides.

## Hand off

- Done: the shape, its sibling check, and the family test or lint rule. Next role: the reviewer. Needs: a person, for a clash the glossary does not decide. Stopped at: none, or the stop rule's code.
