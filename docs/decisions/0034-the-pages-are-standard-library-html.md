# 34. The built-in pages are standard-library HTML, with no framework

Accepted on 2026-11-16, for a decision made while aidd was built. In force.
The maintainers decided it while aidd was built, and this record keeps the reasons that the architecture page gave. Every contributor is informed through this record.

## Context and problem statement

aidd writes three pages: the work-item page, the exploration page, and the prototype viewer. Each is one file that a person opens in a browser. They need components, a style, and a little behavior. Does aidd build them with a front-end framework, or write the HTML itself?

## Considered options

- **A framework build, such as React or Preact.** It costs size and a build. A build on 2026-11-08 gave a page script far over its budget in both.
- **One page by hand with its own style and script, for each page.** It costs drift, because three pages would repeat the same parts and change them separately.
- **HTML that Python writes, one shell, and one set of components.** It costs each component by hand, in aidd's own design system.

## Decision outcome

The chosen option is "HTML that Python writes, with one shell and one set of components", because it fits the budget and adds no dependency.

> The built-in pages are HTML that Python writes, with small hashed scripts and no framework. They share one shell and one set of components, and they draw from aidd's own design system.

### The case that decided it

The work-item page's script only shows and hides views, folds search text, moves focus, copies, and keeps the state in the URL. `tests/budgets.py` holds it to 8 KiB, so it stays small enough to read in one sitting. A React build and a Preact build were measured on 2026-11-08. Both came out far over that budget, for a page that needs none of what a framework adds.

### Consequences

- Good, because the pages need no build step and no runtime dependency, which the standard-library-only rule asks.
- Good, because a budget test holds the script's size, so growth shows at once.
- Bad, because each component is written by hand, in aidd's own design system.
- Neutral, because a project's own `design/tokens.json` stays apart from aidd's design system.

### Reopen when

A page outgrows its budget.

## More information

[The architecture page](../architecture/README.md#module-map) lists the pages and the design system's files. [0033](0033-strict-layers-and-a-door-for-each-package.md) places `views` in the layers.
