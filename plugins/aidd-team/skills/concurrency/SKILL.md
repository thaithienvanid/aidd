---
name: concurrency
description: "Practice skill: run work in parallel and share state without races. Use in an aidd repository when a Task adds threads, async tasks, goroutines, or shared state, or a bug shows only under load."
metadata:
  checked: "2026-10-17"
---

# Concurrency

**Use it when** a Task runs work in parallel inside a process (threads, goroutines, async tasks, worker pools), or shares mutable state between such tasks. Use it too when a failure shows up only sometimes, or only under load.

**Do not use when** the shared state lives in the database (`aidd-team:data-access`), or the parallel work spans services (`aidd-team:resilience`).

## Standards

<!-- aidd:gen practice:concurrency -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| The Go data race detector | Go 1.x toolchain | 2026-10-17 | <https://go.dev/doc/articles/race_detector> |
| ThreadSanitizer (C, C++, and Rust) | Clang/LLVM | 2026-10-17 | <https://clang.llvm.org/docs/ThreadSanitizer.html> |
| Structured concurrency in Python: asyncio.TaskGroup | Python 3.11 and later | 2026-10-17 | <https://docs.python.org/3/library/asyncio-task.html> |
| Node.js: don't block the Event Loop or the Worker Pool | Node.js guide | 2026-10-17 | <https://nodejs.org/learn/asynchronous-work/dont-block-the-event-loop> |
<!-- aidd:end -->

## Specify

- Name what runs at the same time and what it shares. For each shared value, the Design names its owner and the rule that protects it: it is immutable, one task owns it and passes it by message, or one lock guards it.
- Bound the parallelism: the most tasks in flight, and what happens at the bound (wait, shed, or fail). An unbounded fan-out is a defect.

## Implement

- Prefer not to share. Pass data by value or through a channel or a queue, and let one task own each piece of state. Shared mutable state gets one lock, held briefly, never across I/O or an `await`.
- Structured concurrency: start tasks in a scope that waits for all of them, cancels the rest when one fails, and raises its error. Use `asyncio.TaskGroup`, Go's `errgroup`, Kotlin's `coroutineScope`, or Java's `StructuredTaskScope`. No task starts without an owner and an error path.
- Every wait has a timeout or a cancellation, and code honors cancellation. Never swallow the cancellation error.
- Never block an event loop. CPU-heavy work and blocking calls go to a worker pool or another process, such as Node.js's Worker Pool or `asyncio.to_thread`.
- Bound fan-out with a semaphore or a fixed pool. Take locks in one fixed order. Use the language's atomic types, never a hand-written flag.
- Run the race detector in CI where the language has one: `go test -race`, or ThreadSanitizer (`-fsanitize=thread`) for C, C++, and Rust.

## Review

- Each shared value has an owner and a protection. Every task has a scope, a timeout, and an error path, and the parallelism is bounded. No lock is held across I/O or an `await`, and no blocking call runs on an event loop.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Race detector | no data race on the tested paths | `go test -race ./...`, or the suite built with `-fsanitize=thread` |
| Stress test | the result is the same under many parallel runs | run the concurrent path many times in parallel with a fixed seed; assert the invariant each time |
| Cancellation test | a cancelled or timed-out operation releases what it held | cancel mid-flight; assert no task, lock, or connection is left |
| Event-loop delay check | no request blocks the loop | measure the loop delay under load (Node's `monitorEventLoopDelay`) against a ceiling |

## Stop if

- A flaky test is retried instead of reproduced. A race is a bug until a detector or a stress test says otherwise (`aidd-team:debugging`).
- Shared mutable state has no stated owner or protection.
- A task starts with no scope that waits for it or handles its error.

## Hand off

- Done: what runs in parallel, what it shares, and how each value is protected; the bounds; and the tests above, green. Next: the reviewer. Needs: none. Stopped at: none, or the stop rule that fired.
