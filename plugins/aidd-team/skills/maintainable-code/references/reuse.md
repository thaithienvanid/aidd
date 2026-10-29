# Search before you write

Load this before you write a helper, a utility, a client, a parser, or any function another part of the code could already have. A second copy of a behavior is a second place to fix every bug.

## Where to search, in order

1. **The module you are in.** Its door (the file that names what it offers, such as `__init__.py`, `index.ts`, or `mod.rs`) and its own helpers.
2. **The shared kernel.** The small layer every module may use: text, time, paths, I/O, and errors. A general need belongs there; if it is not there yet and the kernel is outside the Task's scope, say so on the handoff note.
3. **The module that owns the concept.** A rule about money lives with money, about dates with scheduling. Use it through its door, never by reaching into its files.
4. **The library choices.** The project's chosen libraries, as its config and its manifests name them, and the language's standard library. A choice already made beats a new dependency. A dependency the project's stack and licence policy allow beats new code for a solved problem, such as parsing, dates, or retries.

Search by what it does, not only by its name: the verb and the object ("parse duration", "retry", "slugify"), the error message it would raise, and the tests that would cover it.

## What makes a match reusable

Reuse it when all of these hold:

- It does the same thing, with the same edge cases, not just a similar name.
- It sits where your module may import it: a lower layer, or a door you may use.
- Its tests cover the case you need, or you add that test beside it.

Extend it instead when it needs one more parameter for your case and the change keeps its other callers' behavior. Write your own only when the meaning differs; then name it for the difference, so nobody merges the two by mistake.

## A contrast pair

A Task needs `<a behavior>` in `<a module>`.

- **Weak:** a new `<helper>` in `<the module>`, written from memory. It handles an edge case one way, the existing helper another, and two screens or two services now disagree on the same input.
- **Strong:** a search for the behavior's words, its error message, and the call sites that need it finds `<the existing helper>`, with its tests. The Task imports it through its door and adds the one missing test for its own case.

Illustrative, from three unrelated codebases:

- a byte count shown as "1.5 MB", which a shared `human_size()` already rounds;
- a date shown in the reader's time zone, which the scheduling module already converts;
- a retry on a payment provider's timeout, which the HTTP client library already does with backoff.

The line that tells them apart: the strong one searched by behavior before it wrote a line, and left one owner for the rule.

## Check it

- The diff adds no function whose body matches one that already exists. Search for the body's key line before you hand off.
- A new shared helper has its own test, and the copies it replaces inside the Task's scope are gone in the same change; a copy outside it goes on the handoff note as debt.
- The handoff note says what you reused, and what you wrote new and why.
