# 23. Knowledge informs, a rule binds, and a capability acts

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. The three words are not yet the structure of the documents, and the glossary lacks them.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

What aidd gives a project came with fourteen words, among them industry standard, opinionated standard, stack, domain pack, practice skill, role, flow, product default, risk rule, and more. Some carried two meanings. A person and an agent need a few words above the precise ones. What are they?

## Considered options

- **Keep the fourteen words.** It costs a reader, who must learn all of them.
- **Two words, knowledge and capabilities.** It leaves what binds with no word, and what binds is aidd's own core.
- **Three words above the precise ones, with one test.** It costs the documents' structure and one glossary line for each word. The precise words stay for the config and the commands.

## Decision outcome

The chosen option is "three words above the kinds", because one test sorts every kind, which is whether it can be broken.

> Knowledge informs, and it holds a standard, a skill, a recommendation, and a stack. It can only be ignored or out of date. A rule binds, and it holds a risk rule, a project rule, a product default, an obligation, and the method's own rules. It can be broken, checked, and waived. A capability acts, and it holds an agent, a command, and a tool.

### The case that decided it

A law shows the test. A law is a published source, so it is a standard and knowledge. A regulated domain's skill cites it and says what it demands, which is knowledge too. The binding is the project's own line, the law's name in `project.compliance.targets`, and that line is a rule. The three words also match what is core and what is optional. The rules are the governance, and knowledge and capabilities are optional parts.

### Consequences

- Good, because fourteen words become nine and none keeps two meanings, and each fact gets one home.
- Neutral, because what an agent loads for a Task stays about 65 KB. The gain is words and homes, not bytes.
- Bad, because the three words need a glossary line each and a change to the documents' structure.

### Reopen when

A kind of thing appears that the test "can it be broken?" cannot place.

## More information

[0024](0024-recommendation.md) names the library's suggested answer, and [0025](0025-pack-goes-two-plugins.md) says what happens to "pack".
