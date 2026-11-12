# 7. The graph is a generated page, and METHOD.md keeps the rules

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `docs/GRAPH.md` does not exist yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The graph is data: stages, steps, edges, gates, and states. [METHOD.md](../METHOD.md) holds the normative rules and also describes the graph by hand. Where should the graph live, and what stays in METHOD.md? The question had two parts, where the graph lives and whether it replaces METHOD.md.

## Considered options

- **Keep everything in METHOD.md.** It costs a hand-written picture that can drift from the data.
- **`docs/GRAPH.md` replaces METHOD.md.** It costs the links, because 30 files link to METHOD.md today. It also mixes a rule that people write with a picture that code writes.
- **`docs/GRAPH.md` holds the graph, generated from the data, and METHOD.md keeps the rules and points to it.** It costs a second page to find.

## Decision outcome

The chosen option is "a generated graph page, and METHOD.md keeps the rules", because a generated page cannot drift and a rule is written by a person.

> `docs/GRAPH.md` holds the development graph and is generated from its data. `docs/METHOD.md` keeps the rules and points to it.

### The case that decided it

The project owner proposed that GRAPH.md replace METHOD.md. The two pages differ in who writes them. A person writes a rule, such as "a person decides the risky steps". The generator writes a table of states and edges, and nobody may edit it by hand. Merging them would put a generated block inside a normative text, and it would break the 30 links.

### Consequences

- Good, because the graph, its states, and its links stay true to the data on every `aidd gen-docs --check`.
- Bad, because a reader goes to two pages, so each must link the other.

### Reopen when

METHOD.md holds only links, and nothing normative is left in it.

## More information

[0005](0005-development-graph-and-team.md) says why the method is a graph.
