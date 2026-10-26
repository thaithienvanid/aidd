---
description: A docs edit in an aidd repository flags ambiguous terms and replaces them with the glossary's preferred ones.
plugins:
  - "../.."
  - "../../../.."
max_turns: 20
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - practice
---

Please tidy this paragraph for our aidd onboarding guide. Keep the meaning, and tell me what you changed.

> Once the designer's mockups pass the design gate, the product lead signs off on the Spec and the agents start building. When the PR is ready, the reviewer approves it, and the CI logs are our evidence that the tests passed. Before all this, the product lead approves the plan.
