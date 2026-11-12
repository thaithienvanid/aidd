# 33. The packages sit in strict layers, and each has one door

Accepted on 2026-11-16, for a decision made while aidd was built. In force.
The maintainers decided it while aidd was built, and this record keeps the reasons that the architecture page gave. Every contributor is informed through this record.

## Context and problem statement

`src/aidd/` has one package for each capability, such as `risk`, `testing`, and `workitems`. aidd tells adopters to build a modular monolith, and its own code must hold the same rule. A service would link its modules with events. How do aidd's packages depend on each other, and how does one package use another?

## Considered options

- **Peer modules that send events.** A command-line tool has no running peers to send events to, so it costs machinery that nothing uses.
- **One package, with any import allowed.** It costs the boundaries, because cycles and wrong-way imports would grow unseen.
- **Layers, with no door.** A package would import any module of a package below it. It costs the freedom to change a package inside, because every module is public.
- **Strict layers, and one door for each package.** It costs a place for every shared helper: a layer low enough for each caller.

## Decision outcome

The chosen option is "strict layers, and one door for each package", because a machine can then check both rules on every change.

> A package imports only from the packages below it, and only through its door, its `__init__.py`, which holds only names. `.importlinter` holds the layers, the doors, and the rule that no two modules in a package form a cycle. It lists no exception.

### The case that decided it

A change imports a higher package from a lower one. `lint-imports` fails, and the fix is the import. The contract has no `ignore_imports`, so a wrong-way import is fixed and never listed. A door also loads none of its children until a caller uses a name, so a quick command such as `aidd risk --command` loads only its own code. A test that patches the module that defines a name reaches every caller, because the door reads its child on each access.

### Consequences

- Good, because the layers, the doors, and the absence of cycles are fitness functions that fail a change in CI, not a convention.
- Good, because `risk` answers from the config and the paths alone, so a package with its own door could become a service.
- Bad, because a helper that two packages need moves down to a layer below both. `kernel` knows no domain, has no door, and takes what has no other home.
- Bad, because a door lists each name twice, once for the reader and once for the type checker.

### Reopen when

A package needs a peer at its own layer that the layers cannot state.

## More information

[The architecture page](../architecture/README.md#module-map) lists the layers and what each holds. [CONTRIBUTING.md](../../CONTRIBUTING.md#code-and-imports) holds the rules for contributors.
