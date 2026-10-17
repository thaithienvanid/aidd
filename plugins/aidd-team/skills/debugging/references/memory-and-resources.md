# Memory and resources

Load this when the symptom grows with time or load: memory that climbs, a pool that runs dry, "too many open files", or a process the system kills.

## Make it fail

- A leak is a slope, not a size. Run the same request or job in a loop and record memory, open handles, and pool use per round. Memory that settles after a warm-up is a cache; memory that climbs on every round is a leak.
- Read the right number: the process's resident memory (RSS) and the runtime's own heap are different, and only one of them is the leak. The container's limit counts RSS.
- Compare two snapshots taken some rounds apart, not one. Use a heap snapshot in V8 or the JVM, `tracemalloc` in Python, `pprof` heap in Go, Instruments or the memory graph on iOS, Android Studio's memory profiler. The objects that grew between them name the leak.

## The usual causes

- Something that only grows: a module-level cache with no bound, a listener added and never removed, a map keyed by request or user.
- A resource opened on one path and never closed on another: an exception between open and close. Close in the language's own form (`with`, `try`-with-resources, `defer`, `using`), never by hand at the end.
- A pool smaller than the work in flight. By Little's law, connections in use average the arrival rate times the time each one is held. So a slow query empties a pool that was large enough yesterday. Measure the wait for a connection, and time out the wait.
- No back-pressure: a queue or an in-memory buffer with no limit grows until the process dies. Every queue has a bound, and what happens at the bound (reject, block, drop) is a decision in the Spec.

## Fix and prove

- The regression test runs the loop and asserts the slope: memory, handles, or pool use after N rounds is within a bound of the value after the warm-up. A test of one round proves nothing about a leak.
- Tune the garbage collector or raise a limit only after the slope is flat. A larger heap only delays a leak.
