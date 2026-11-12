# 3. State lives in files a person can read

Accepted on 2026-11-14. In force.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

aidd keeps Specs, Intents, requests, approvals, and records. Each fact needs a home. Should the home be a database, a hosted tracker, or files in git?

## Considered options

- **A database as the truth.** It costs review: a row cannot be diffed or reviewed in a pull request, and a fresh clone does not hold it.
- **A hosted tracker as the truth.** It costs the network and the repository's independence. The facts leave git, so no audit can read them from the repository alone.
- **Files in git, with a SQLite cache.** It costs speed at scale, because a command reads many files. A cache rebuilt from the files answers that cost.

## Decision outcome

The chosen option is "files in git, with a SQLite cache", because a person can read, diff, and review every fact, and the cache can be deleted at no loss.

> State lives in files a person can read. A Spec's front matter holds its status. The only database is a cache that is rebuilt from the files and the refs.

### The case that decided it

The project owner asked where a request should be stored: a folder, or SQLite. A request is words someone said, and an audit must read them with no tool. A database row fails that test and a file passes it. A request that waits in another team's tracker stays there, and aidd stores it only once it is taken up ([0009](0009-a-request-is-stored-when-taken-up.md)).

### Consequences

- Good, because every record is a plain file, so the project needs no server and works offline.
- Bad, because a command that reads one item at a time makes one git call for each item. At 1,000 Specs `aidd status` made 1,015 calls in 7.8 seconds. The rule for new work is one git call for each command and each type, never one for each item.

### Reopen when

A file format cannot hold a fact that an audit needs, and no cache can stand in for it.

## More information

[Architecture](../architecture/README.md#where-aidd-writes) lists what aidd writes and where.
