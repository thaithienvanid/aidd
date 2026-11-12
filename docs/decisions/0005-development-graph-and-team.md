# 5. The method is a development graph, and the team is a development team

Accepted on 2026-11-14. In force in the data, with the `graph` key in `schemas/roles.json` and `development_teams` in the config. Decided for 1.0.0, and the prose is not finished: it still says "loop" in places.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The method was called a loop. A request enters from outside it, three routes leave that entry, and gates and ways back sit on the edges. What should the whole be called, and the team that works in it?

## Considered options

- **"Loop".** It costs accuracy, because the entry stands outside the loop and the name hides the start.
- **"Flow" or "workflow".** It costs a clash, because aidd already calls each team command a flow.
- **"Graph".** It costs a risk of misreading. "Graph engineering" is a term of 2026 and is emerging, and a reader may think aidd runs the graph.

## Decision outcome

The chosen option is "graph", because the work has an order, a start, gates, and ways back, which is what a graph states.

> The method is the development graph, the map of how work moves from a request to production and back. The people and agents that work in it are the development team. aidd defines the graph and reads where each item stands, and it runs nothing.

### The case that decided it

A request enters at Intake, and Learn sends new work back to Intake. A loop with an outside start does not draw that. The graph keeps both loops as parts. The inner loop is Specify, Implement, and Verify repeated until green, and the outer loop holds the people's gates. The project owner chose "development team" to match, over "delivery team".

### Consequences

- Good, because the picture shows every gate and every way back, and a test can check each edge against the data.
- Good, because the role `delivery-manager` and the skill `client-delivery` keep their names, because they name a client engagement's delivery and not the team.
- Bad, because the old word "loop" stays in many pages until the text is rewritten once.

### Reopen when

A reader of the first release still reads the graph as a program that runs agents.

## More information

[METHOD.md](../METHOD.md) holds the rules, and [0007](0007-graph-page-is-generated.md) says where the graph page lives.
