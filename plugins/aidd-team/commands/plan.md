---
description: "Plan work as an Initiative, Epics, and Spec stubs with the product manager"
argument-hint: "<idea or request>"
---

Loop step: **Plan**, before the loop, only for work bigger than one Spec.

Lanes: spec.

Run the `aidd-team:product-manager` subagent on this request: $ARGUMENTS

When it returns, show the author the Initiative, the Epics, and the Spec stubs it wrote, and stop. Planning is done only when a human agrees to it. The plan goes on its own branch; each Spec ships later in its own change, which starts with `aidd next`. The Initiative, the Epics, and the stubs are files in the repository; mirroring them to a tracker is optional, and only when the project already has one connected.
