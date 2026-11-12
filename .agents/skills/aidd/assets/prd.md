---
type: prd
# objectives:   # only when no BRD exists: it holds the objectives, and `aidd validate` errors on both.
#   Copy an objective's shape from the BRD template: id, title, metric, due.
# requirements:   # only when no BRD exists: it holds the requirements, and `aidd validate` errors on both.
#   Copy a requirement's shape from the BRD template: id, title, and `serves` when objectives exist.
outcomes:
  - id: Outcome-1
    title: "TODO: what changes for the people who use the product"
    metric:
      name: "TODO: what is measured"
      source: "TODO: where the number is read"
      baseline: "TODO: where it stands now, or none: new product"
      target: "TODO: the value the product owner chose"
    serves: "TODO: a requirement of the BRD, as Requirement-n, or an objective when no BRD exists"
---

<!-- The product requirements document: who the product is for, and the outcomes it must bring about, in a page or two.
     Features, stories, and acceptance criteria live in Intents and Specs, never here. Each id is the next free number and
     is never reused. A person decides every number and name. An agent never fills one: it leaves TODO, and `aidd validate`
     fails until a person decides. Write the prose at the `instruction` level (`aidd-team:plain-language`). -->

## Users

TODO: who uses the product, and the job each one wants done, with the evidence.

## Not doing

TODO: what the product will not do.

## Shared context

TODO: what every Intent needs to know, such as the flows, the design, and the terms.
