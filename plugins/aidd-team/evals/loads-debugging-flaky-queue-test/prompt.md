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

This repository uses aidd. Our Jest suite fails about one run in twenty on CI with `expected 10, received 9`, and never on my laptop. Find out why. Here is the case:

```ts
it("drains the queue", async () => {
  const results: number[] = [];
  startWorker(queue, results);
  for (let n = 0; n < 10; n++) queue.push(n);
  await sleep(100);
  expect(results).toHaveLength(10);
});
```
