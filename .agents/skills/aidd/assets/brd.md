---
type: brd
sponsor: "TODO: who decides what this document holds, as @handle or Name <email>"
objectives:
  - id: Objective-1
    title: "TODO: what the business wants"
    metric:
      name: "TODO: what is measured"
      source: "TODO: where the number is read"
      baseline: "TODO: where it stands now, or none: new product"
      target: "TODO: the value the sponsor chose"
    due: "TODO: YYYY-MM-DD"
requirements:
  - id: Requirement-1
    title: "TODO: what the business must be able to do"
    serves: Objective-1
---

<!-- The business requirements document: why the business wants the product, and what it must be able to do. A one-page
     brief with no measure may drop `objectives` and each `serves`, and keep the sponsor and the requirements. A person
     outside the product team approves it, because it commits money, scope, or risk. Each id is the next free number and is
     never reused. A person decides every number, date, and name. An agent never fills one: it leaves TODO, and
     `aidd validate` fails until a person decides. Write the prose at the `instruction` level (`aidd-team:plain-language`). -->

## Why this product

TODO: the problem, who has it, the evidence, and why it is worth solving now.

## Scope

TODO: what is in, and what is out.

## Constraints

TODO: the budget, the dates a person named, the rules, and any technology a person decided, with who decided it and when.
