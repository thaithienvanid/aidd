---
type: standing-outcomes
# requirements:   # only when no BRD or PRD exists: it holds the requirements, and `aidd validate` errors on both.
#   Copy a requirement's shape from the BRD template: id and title.
outcomes:
  - id: Outcome-1
    title: "TODO: what must stay true of the product"
    metric:
      name: "TODO: what is measured"
      source: "TODO: where the number is read"
      target: "TODO: the threshold the measure must hold"
---

<!-- The standing outcomes: what must stay true of a product that has neither a BRD nor a PRD. Each target is a threshold,
     so there is no baseline. Each id is the next free number and is never reused. A person decides every number and name.
     An agent never fills one: it leaves TODO, and `aidd validate` fails until a person decides. Write the prose at the
     `instruction` level (`aidd-team:plain-language`). -->

## Why these outcomes

TODO: why each one must hold, and who notices when it does not.
