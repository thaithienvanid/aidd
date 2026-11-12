# 26. One kind of thing keeps one name and one shape at every scope

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. The renames below land with the code, and `depends_on` and the proposal's `outcome` are still in it.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The same idea appeared under different words at different scopes. A proposal's `outcome` was an answer. A Task's `depends_on` and an Intent's `blocked_by` said one thing. How does the project name a thing that exists at several sizes?

## Considered options

- **Let each scope name its own.** It costs the reader a word for each scope, and one word may mean two things.
- **One name and one shape for one kind of thing, and where it sits tells the scope.** It costs renames across many files.

## Decision outcome

The chosen option is "one name and one shape at every scope", because a reader who learns a word at one scope can use it at all of them.

> One kind of thing keeps one name and one shape at every scope, and where it sits tells the scope. One word has one meaning in every type. `outcome` means only a goal, and `blocked_by` names what must finish first on a Task as on an Intent.

### The case that decided it

`outcome` meant a goal on a product scope item and on an Intent, and also a proposal's answer, an exploration's finding, and a record's decision. Now a proposal's `outcome` becomes `answer`, an exploration's and the delegate check's become `result`, a record's becomes `decision`, and a proposal's `goal` becomes `outcome`. About 40 of the 215 files that hold the word change. A Task's `depends_on` becomes `blocked_by`, which 22 files hold. Outcome, success criteria, and acceptance criteria then read the same at a product scope item, an Intent, a Spec, and a Task.

### Consequences

- Good, because a status is one word with one meaning in every type, and a vocabulary test holds it as data.
- Good, because words that look alike but name different things stay apart: `due`, `review_due`, and `until` each name a different day, and a Task's `done` is a tick and no decision.
- Bad, because the renames cost many files and must land together, so that no name means two things during the change.

### Reopen when

A scope needs a word that no sibling uses, because its meaning really differs.

## More information

[0027](0027-words-a-first-reader-gets-wrong.md) lists the words a first reader stopped at. [AGENTS.md](../../AGENTS.md) holds the naming rules.
