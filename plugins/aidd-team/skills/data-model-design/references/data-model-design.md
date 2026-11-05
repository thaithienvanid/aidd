# Designing a data model

Load this when a Task adds or changes a schema, a config format, a file format, or an API body: a field, a group of fields, an enum, a code, or an id. The shape you freeze is hard to change later, so decide it before code uses it. The ids in brackets are the standards in the skill's table. A rule with no id is common practice that the standards do not state.

## Structure

- Group facts that are decided, locked, or overridden together. Keep an independent selector flat. Kubernetes groups by who writes a fact: `spec` for what a person wants, `status` for what the system observed. [k8s-api-conventions]
- Fix a name clash with a name: a rename or a glossary line. Move structure only when the grouping rule above calls for it, because a move breaks every reader.
- Hold a collection of named things as a list of objects with a `name` field, not as a map keyed by name. When configs layer, entries then merge by that name, and a child can change one entry without copying the list. A list with no name key is replaced whole on update. [k8s-api-conventions, aip-144]
- One fact, one shape, at every scope. A fact set at several scopes (a task, a team, the repository) has one field name and one schema definition at each, and the narrower scope wins.
- Where a layer can fix a setting, say whether the layers below may change it or may only tighten it.

## Room to grow

- Start a field that may gain attributes as an object, or as an id-or-object (a `oneOf` of a string and an object). Turning a shipped string into an object changes its type, which is a breaking change. [json-schema-2020-12, aip-180]
- Make that change before the first release, or add a new field beside the old one and retire the old one by expand and contract. [aip-180]
- Every allowed field has an effect. No field that holds one constant, and no field the schema accepts where the code ignores it. Guard a field that applies in one case with `if` and `then`. [json-schema-2020-12]
- A field is optional or required, never both. Say what leaving an optional one out means. [k8s-api-conventions]

## Name families

A project keeps one pattern for each kind of fact. Check a new name against the project's own families first. Where a guide and the project differ, the project's family wins, and the Spec says so.

- Units, instants, and dates: the pattern is in `aidd-team:naming`, `references/across-media.md`, "Units, money, and time". A guide may differ (AIP-142 ends an instant in `_time`). Copy the project's suffix, and take the guide's only where the project has none. [aip-141, aip-142]
- A count ends in `_count`. [aip-141]
- A boolean names a positive fact, never a negated one. AIP-140 omits the `is` prefix. A medium with its own convention, such as `is_` in a database column (`aidd-team:naming`, `references/systems.md`), keeps it. [aip-140]
- A name states what a thing is, not what it does to something else: declarative, not imperative. [k8s-api-conventions]
- A code or a status value uses one case, the case the project's other codes use.
- One concept has one word everywhere: the glossary decides (`aidd-team:naming`).

## Change

- Removing or renaming a field is a breaking change. Break a name only for a real misreading, and only before the first release. After it, use expand and contract. [aip-180]

## Hold the families

A rule that lives only in a reviewer's head is forgotten. Put each family in a check that fails the build:

- A schema linter with a rule per family, such as a casing rule over every property name. [spectral]
- A schema test that walks every schema file and asserts each family, with an allow-list of exceptions kept as `{name: reason}`, so a new exception needs a written reason.
- A test that every property is used by code and every enum value is reachable.
