# Designing a data model

Load this when a Task adds or changes a schema, a config format, a file format, or an API body: a field, a group of fields, an enum, a code, or an id. Load it too when a Task decides who writes or reads a field. The shape you freeze is hard to change later, so decide it before code uses it. The ids in brackets are the standards in the skill's table. A rule with no id is common practice that the standards do not state.

## Structure

- Name the entities before the fields: the things that have an identity and a life of their own. Each has a key. Each link between two entities says how many at both ends, whether it is required, and which one end stores it. This is the entity-relationship model (Chen, 1976).
- A fact about a link belongs to neither end. A grade is a fact about one student on one course, so the enrolment is an entity. A link with many at both ends needs that home too.
- A part that cannot exist without its parent, and is written with it, nests inside the parent. A part with its own life, its own writer, or no bound on how many is its own entity, with a link. Where the two pull apart, ask when the part is written. An invoice's lines change only with their invoice, so they nest, however many there are. Comments keep arriving after their ticket is written, so each is an entity.
- Group facts that are decided, locked, or overridden together. Keep an independent selector flat. Kubernetes groups by who writes a fact: `spec` for what a person wants, `status` for what the system observed. [k8s-api-conventions]
- One field holds one fact, and one enum answers one question. Run three tests on each. Does a value's name join two facts, as `paid_and_shipped` does? Do two values agree on one fact and differ on another? Would one more fact double the list? Then the enum is the product of two smaller ones. Give each fact its own field when the two vary on their own. [k8s-api-conventions]
- Run the opposite test before you split. When one fact always follows from another, store one and read the other from it. When only some pairs are allowed, keep one enum whose every value names both facts in the same order. Or keep two fields, and state the pairs that the model refuses. [relational-normal-forms]
- Fix a name clash with a name: a rename or a glossary line. Move structure only when the grouping rule above calls for it, because a move breaks every reader.
- `aidd-team:naming` says when to stop renaming and check the model instead (its Stop if).
- Hold a collection of named things as a list of objects with a `name` field, not as a map keyed by name. When configs layer, entries then merge by that name, and a child can change one entry without copying the list. A list with no name key is replaced whole on update. [k8s-api-conventions, aip-144]
- One fact, one shape, at every scope. A fact set at several scopes (a task, a team, the repository) has one field name and one schema definition at each, and the narrower scope wins.
- Where a layer can fix a setting, say whether the layers below may change it or may only tighten it.
- State each exception in the data, next to the rule. A rule that says "none may exceed" while the code skips one case is a false claim. Put the exempt case in the file the rule reads, with its reason, so a reader sees the rule as it applies.

## Room to grow

- For each field, and each link between two objects, write how many the domain has: exactly one, none or one, or many. Ask someone who knows the domain whether a second one can exist, and read how the prior art holds it. Hold a list when the domain has many today, even where today's data has one, because a single value that becomes a list is a type change. Never hold a list for "might". A contact has many phone numbers, and an invoice has one total. [aip-180]
- A name with a number in it, such as `phone_2`, is a list written flat. So is a name with a dimension joined on, such as `title_en` or `ready_in_staging`. Hold one entry for each language or each environment, so a new one adds an entry and never a field. Two fixed ends, such as `starts_on` and `ends_on`, are no dimension. Fields that are written together and mean nothing apart are one object. [relational-normal-forms]
- Start a field as an object, or as an id-or-object (a `oneOf` of a string and an object), when it will gain a second attribute. The domain, its prior art, or a likely change that the design names says so. Turning a shipped string into an object changes its type, which is a breaking change. [json-schema-2020-12, aip-180]
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
- Each kind of name has its own form: a field, a value, a state, an event, an action, and a derived view. A suffix or a separator that marks one kind never appears on another. The forms are in `aidd-team:naming`, `references/across-media.md`, "Names in a data model".
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

- A change to a shipped field has its rules in `design-proof.md`, "A change to a shipped model". It is a breaking change, each old value needs a destination, each reader is listed, and the change is proved by its answers.

## Hold the families

A rule that lives only in a reviewer's head is forgotten. Put each family in a check that fails the build:

- A schema linter with a rule per family, such as a casing rule over every property name. [spectral]
- A schema test that walks every schema file and asserts each family, with an allow-list of exceptions kept as `{name: reason}`, so a new exception needs a written reason.
- A test that every property is used by code and every enum value is reachable.
- A reference test that collects every string key naming another record, a file, a function, or a handler, and fails on one that resolves nowhere. Where it matters, it also fails on a target that nothing points to, such as a handler no event reaches.
