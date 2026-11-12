---
name: naming
description: "Practice skill: choose, check, or improve a name. Use in an aidd repository when a Task names a module, type, file, column, event, flag, metric, component, token, or label, or a name misleads readers."
metadata:
  checked: "2026-10-22"
---

# Naming

**Use it when** a Task adds or renames something other people read: a module, type, function, file, column, event, flag, metric, or document, or a design's component, token, screen, state, or label. Load it in Specify too, whenever the change adds a public name (an API type, error code, event, field, environment variable, or database role): a contract freezes it.

**Do not use when** the name is local to a few lines and its scope makes it clear. Rename only for a reason a reader would feel, never for taste.

## Standards

<!-- aidd:gen practice:naming -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Naming as a process: small safe renames, from honest to a domain concept | — | 2026-10-16 | <https://www.digdeeproots.com/articles/naming-process/naming-as-a-process/> |
| Conventional Commits | 1.0.0 | 2026-10-16 | <https://www.conventionalcommits.org/en/v1.0.0/> |
| CloudEvents: event attributes, a reverse-DNS type prefix, and lowercase extension names | 1.0.2 | 2026-10-16 | <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md> |
| OpenTelemetry semantic conventions for metric and attribute names | 1.44.0 | 2026-10-16 | <https://opentelemetry.io/docs/specs/semconv/> |
| ISO 4217 currency codes and minor units | ISO 4217:2015 | 2026-10-16 | <https://www.iso.org/iso-4217-currency-codes.html> |
<!-- aidd:end -->

## Specify

- A hard-to-name thing is a design signal: it may do too much, sit in the wrong place, or be an unagreed concept. Fix the design, and the name follows.
- A new domain concept: the module owner and product agree its word first. Add its row to `docs/GLOSSARY.md` (`aidd new glossary`): term, meaning, words to avoid, owning module.

### Before you add a field or a group

`aidd-team:data-model-design` owns the shape: the one sentence the field holds, what it groups and merges with, and what may come later. This skill owns the name: which name family it joins, and whether the name can still change.

## Implement

### Principles

1. Name for the reader. A new teammate understands it without opening the code.
2. Use the business's words. If product says "invoice", code does not say "bill".
3. One concept, one name, and one name, one concept: in code, database, events, metrics, and docs. The glossary decides.
4. Say what it is or does, at its full scope, in plain words: not how it is built (`OrderRepository`, not `OrderDbHelperImpl`), not when it runs (`checkStock`, not `beforeSaveHook`), and no metaphor a reader must decode. A table of every invoice is `invoices`, not `unpaid_invoices`. A word the domain uses, like "ledger" in accounting, is plain to its readers.
5. Scope sets the length. A loop index can be `i`. A public API or event name stands alone.
6. Be honest and complete: show side effects, I/O, and mutation. If an honest name needs "and", split the thing.
7. Make facts explicit: units (`timeoutMs`), money (`amountMinor` and `currency`), certainty (`findUser` can return nothing, `getUser` returns or fails).
8. Cut noise: `data`, `info`, `helper`, `util`, `impl`, `temp`. Abbreviate only universal words (`id`, `url`, `api`).
9. Match the neighbours and the medium. After `createOrder` and `cancelOrder` comes `refundOrder`.
10. Rename as you learn: a wrong name costs more each month.

### A new name

1. Write one plain sentence that says what it is or does.
2. Take its key words: "customers with an order in the last 30 days" gives `customersWithRecentOrders`.
3. Check the glossary and nearby code. Use the team's word, not your preference.
4. Fit the pattern for its kind: [references/across-media.md](references/across-media.md) for code, design, and each medium's case style, [references/systems.md](references/systems.md) for folders, database, events, flags, metrics, commits, and docs. An API's errors, responses, and exceptions: [references/errors-and-names.md](references/errors-and-names.md). A CLI: `aidd-team:cli-design`. A schema or config: `aidd-team:data-model-design`.

### Improve a name

After Arlo Belshee: rename in small safe steps, each its own refactor commit.

1. Honest: `doStuff` becomes `validateCartAndSaveOrderAndEmailCustomer`. Long and true beats short and wrong.
2. Complete: the name shows every effect, the hidden email too.
3. One thing: split it, and give each part a short honest name (`validateCart`, `saveOrder`, `sendOrderConfirmation`).
4. Intent: name why the parts exist (`placeOrder`).
5. Domain concept: related parts become one named idea (`Checkout`, `OrderPolicy`).

A name others depend on changes by expand and contract (systems.md).

## Review

- Checks: a new teammate guesses it from the name alone. Swapped with a sibling's name, someone would notice. It is searchable, speakable, and claims and hides nothing. A domain expert knows the word.
- Smells: "And" or "Or" in a name (two jobs), and `Manager`, `Helper`, `Util`, `Processor`, or a bare `Service` (no clear job). So are `order2`, `newOrder`, and `finalV2` (a missing concept or dead code), and `data`, `item`, or `result` in a wide scope. So is a comment that explains the name, or a negative boolean (`isNotDisabled`). So is a changed meaning with the old spelling, or two words for one thing (a missing glossary row). So is a name narrower or wider than what it holds, or jargon from outside the domain that a newcomer must look up.
- "This name made me guess wrong" is a blocking comment.

## Learn

- A smell that comes back becomes a lint rule or a banned-word check.
- A renamed misleading name goes under the glossary's Avoid, so the avoided-word check catches its return.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Avoided-word check | added lines use no word the glossary lists under Avoid | `! git diff -U0 <base>...HEAD -- . ':!docs/GLOSSARY.md' \| grep -v '^+++' \| grep '^+' \| grep -iwE '<Avoid words>'` exits 0 |

## Stop if

- You cannot write the one plain sentence: the design is not clear yet.
- A rename of a public API, column, event, or module would ship in one step.
- Two names collide, or two words name one concept: follow systems.md; a person decides.

## Hand off

- Done: the names, new glossary rows, and the renames. Next role: the reviewer. Needs: the module owner and product, for a new domain word. Stopped at: none, or the stop rule's code.
