# Living work

Load this when a change touches a role's product-level work: the body of work a role keeps across changes, as opposed to a file that belongs to one Spec.

## The pattern

Each document kind says in the team registry (`loop.documents`) whether it is the product's or one change's, which product-level kind a per-change kind feeds, and which roles read it. For example, a change's design spec and prototype feed the product prototype, and its tech spec feeds the architecture overview.

The same rule holds for every kind:

1. **Start it once.** `aidd new <kind>` writes the product-level work from its template, with what `aidd init` knows. The owner fills the rest from an intent or a Spec.
2. **Keep it in line in the same change.** A Spec's own file is the proposal, frozen at Spec approval. The same change brings the product-level work in line. `aidd validate` warns when a change feeds it and leaves it as it was, until a Task's scope names its home.
3. **Read it, never copy it.** `aidd context` hands it to its owner and its readers. Nothing restates it.
4. **Derive, never store, what the files already say.** An index of screens, flows, or pages comes from the files on demand.

## The product prototype

- `aidd new product-prototype` writes `docs/design/app/`:
  - `sitemap.json`: the product, its platforms, its navigation, its flows, and its example data, each defined once;
  - `shell.html`: the product's tokens, styles, and chrome, which aidd's viewer frames;
  - `flows/<flow>.html`: one flow's screens, as `<section data-screen>` blocks with their `data-state` children.
- Navigation lives only in `sitemap.json`, in order, so every screen shows the same items. A flow draws no navigation and runs no script of its own.
- Link inside a flow by the screen's id, and to another flow as `<flow>:<screen>`.
- `aidd prototype` assembles the whole product into one clickable page, `.aidd/views/prototype.html`, and prints what breaks. `aidd prototype --check` is the test command for a Spec that changes it, with `new_behavior: false`.
- Iterate in rounds, as a flow's prototype does. A person picks each direction.

## When a change feeds nothing

Some changes don't touch the product-level work, such as a design spec that only fixes a typo. The warning stays while the change is open, and it never blocks, so say why in the PR/MR description, where the reviewer reads it.
