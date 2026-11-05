---
description: 'A bug report, a failing or flaky test, or a wrong result makes the agent load the debugging practice skill.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
  - debugging
  - claim:trigger:debugging
  - tier:description-change
---

This repository uses aidd. Our nightly check of invoice totals turned red: it expects 107.0 and gets 107.1. Nobody has edited that area since it last passed. Find out why. Here is the code:

```ts
export const invoiceTotal = (lines: [number, number][]) =>
  Math.round(lines.reduce((sum, [price, qty]) => sum + price * qty, 0) * 1.07 * 10) / 10;
```
