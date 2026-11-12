# Designing a data model

Load this when a Task adds or changes a schema, a config format, a file format, or an API body: a field, a group of fields, an enum, a code, or an id. Load it too when a Task decides who writes or reads a field. The shape you freeze is hard to change later, so decide it before code uses it. The ids in brackets are the standards in the skill's table. A rule with no id is common practice that the standards do not state.

## Structure

- Group facts that are decided, locked, or overridden together. Keep an independent selector flat. Kubernetes groups by who writes a fact: `spec` for what a person wants, `status` for what the system observed. [k8s-api-conventions]
- Fix a name clash with a name: a rename or a glossary line. Move structure only when the grouping rule above calls for it, because a move breaks every reader.
- Hold a collection of named things as a list of objects with a `name` field, not as a map keyed by name. When configs layer, entries then merge by that name, and a child can change one entry without copying the list. A list with no name key is replaced whole on update. [k8s-api-conventions, aip-144]
- One fact, one shape, at every scope. A fact set at several scopes (a task, a team, the repository) has one field name and one schema definition at each, and the narrower scope wins.
- Where a layer can fix a setting, say whether the layers below may change it or may only tighten it.
- State each exception in the data, next to the rule. A rule that says "none may exceed" while the code skips one case is a false claim. Put the exempt case in the file the rule reads, with its reason, so a reader sees the rule as it applies.

## Room to grow

- Start a field that may gain attributes as an object, or as an id-or-object (a `oneOf` of a string and an object). Turning a shipped string into an object changes its type, which is a breaking change. [json-schema-2020-12, aip-180]
- Make that change before the first release, or add a new field beside the old one and retire the old one by expand and contract. [aip-180]
- Every allowed field has an effect and a reader. No field holds one constant, and the schema accepts no field the code ignores. Cut a field that nothing reads, or name its reader in the field's description, because a field with no reader drifts from the truth and nobody notices when it is wrong. Guard a field that applies in one case with `if` and `then`. [json-schema-2020-12]
- A field is optional or required, never both. Say what leaving an optional one out means. [k8s-api-conventions]

## Name families

A project keeps one pattern for each kind of fact. Check a new name against the project's own families first. Where a guide and the project differ, the project's family wins, and the Spec says so.

- Units, instants, and dates: the pattern is in `aidd-team:naming`, `references/across-media.md`, "Units, money, and time". A guide may differ (AIP-142 ends an instant in `_time`). Copy the project's suffix, and take the guide's only where the project has none. [aip-141, aip-142]
- A count ends in `_count`. [aip-141]
- A boolean names a positive fact, never a negated one. AIP-140 omits the `is` prefix. A medium with its own convention, such as `is_` in a database column (`aidd-team:naming`, `references/systems.md`), keeps it. [aip-140]
- A name states what a thing is, not what it does to something else: declarative, not imperative. [k8s-api-conventions]
- A code or a status value uses one case, the case the project's other codes use.
- One concept has one word everywhere: the glossary decides (`aidd-team:naming`).

## Flow and trust

A shape also fixes how data moves. For each new or changed field, record who writes it, who reads it, which copy decides, and its trust class, in the field's description or, where the format has none, in the Spec. A reader who lacks one of these facts guesses, and the guess becomes a defect.

- **One owner for each fact.** Never store what another field already decides. A field that is a function of another has two owners, and every reader must agree on both. Derive it where it is read, such as a run's duration from its start and end times. A value stored for speed is a cache. Say what rebuilds it, and say that the source wins when the two differ.
- **Name the deciding copy.** Where data judges one party's change, the judging copy is one that party cannot edit: the version before the change, the approver's copy, or the server's record. A record never attests to itself. An order that carries its own "approved" flag cannot approve itself, and the price a client stores does not decide what it pays.
- **Give each field a trust class:** the system writes it, a person with a stated role writes it, or anyone writes it. A value from outside the trust boundary is data wherever it flows. Quote or escape it where it is shown. Never put it into a command, a query, or a sentence that reads as the system's own words. Bound its length. `aidd-team:secure-coding` owns the escaping rules. The model records the class, so each reader knows which fields to treat as data.
- **Writers closed.** What a system writes validates strictly against its own schema, and a test checks each writer's output against it.
- **Readers open, never to success.** What a system reads from another version tolerates a field it does not know, such as a record that a newer app version synced to an older one. When it writes that record back, it keeps the field. State that rule in the format, because an extension needs stated handling for new elements, and accidental tolerance is not a rule. [rfc-9413-maintaining-robust-protocols] A value the reader does not know never counts as success: an unknown run state is not "succeeded", and an unknown role grants nothing. The reader refuses it, or treats it as the most restrictive case. AIP-180 warns that client code may not handle a new enum value gracefully, so state that behavior for each enum that may grow. [aip-180]
- **People strict.** What a person types, such as a config file, stays strict, because a typo must fail. A value that fails loudly gets fixed while the fix is cheap.
- **An identifier states its scope.** Say what it is unique within (one record, one document, or the whole store), who assigns it, and whether it may be reused after a delete. A reference names the scope it resolves in. A note's id in a phone's local store is unique within that device, so a sync that cites it also names the device.
- **A reference by name must resolve.** A string key that names another record, a file, a function, or a handler is a foreign key that the type system cannot see. Hold it with the reference test in "Hold the families".

## Change

- Removing or renaming a field is a breaking change. Break a name only for a real misreading, and only before the first release. After it, use expand and contract. [aip-180]
- Before you remove or rename a field, list each value it could hold and that value's destination in the new model, or say that the reader refuses it. Nothing drops silently, because a dropped value can loosen what it used to control, as a missing "restricted" flag falls back to open. `aidd-team:schema-migration` owns the migration.
- Prove a change that removes or renames a field, or changes what a field decides, by its answers, never by reading the diff. Build a table of inputs over the input space, with the boundary rows: empty, one, many, and unknown. Run every reader on it before and after. The answers must match, except the ones the change intends, and you list each of those. `aidd-team:test-design` holds the technique for choosing rows.

## Hold the families

A rule that lives only in a reviewer's head is forgotten. Put each family in a check that fails the build:

- A schema linter with a rule per family, such as a casing rule over every property name. [spectral]
- A schema test that walks every schema file and asserts each family, with an allow-list of exceptions kept as `{name: reason}`, so a new exception needs a written reason.
- A test that every property is used by code and every enum value is reachable.
- A reference test that collects every string key naming another record, a file, a function, or a handler, and fails on one that resolves nowhere. Where it matters, it also fails on a target that nothing points to, such as a handler no event reaches.
