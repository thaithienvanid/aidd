# 10. Every stored request is a file in `requests/`

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. Today a saved request lives in `specs/requests/`, and a Spec quotes its request in a `## Request` section.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A request stands before every work item. A client's brief becomes items of a product scope and a proposal, and neither is a Spec. Where does a request live, and does a request that becomes exactly one Spec get its own file?

## Considered options

- **`specs/requests/`, as today.** It costs accuracy: the folder says "a Spec's" about a thing that stands before every type.
- **A folder under `product/`.** It costs a project with no product scope, which writes one Spec from one request and gets `product/` for the request alone.
- **A folder of its own, `requests/`.** It costs one new config key, `requests_dir`, beside `specs_dir`, `proposals_dir`, and `product_dir`, and a change to the 22 files that name the old path.
- **For one Spec, keep the words in the Spec.** It costs two homes for one fact and two trust rules, to save one small file.

## Decision outcome

The chosen option is "a folder of its own, and a file for every request", because a type with its own identity, writer, and life gets its own folder.

> Every stored request is a file, `requests/<yyyy-mm-dd>-<slug>.md`, even when it becomes exactly one Spec, and the Spec names it in `request`. A document that came with a request is named by the id git gives its content, and is committed only on a person's word.

### The case that decided it

A project that writes only proposals, or only Specs, or a full product scope reads the same with one folder. The trust rule for another party's words ([0012](0012-another-partys-request-always-asks.md)) can also match one folder. A committed attachment stays in history for good, with its size and any personal data in it, so the default is to name it and not commit it.

### Consequences

- Good, because a request has one home, and an item's `request` always holds a request's path.
- Bad, because every Spec that takes up a request has one more small file, and the path change touches 22 files.

### Reopen when

A tool needs requests grouped by product, and a flat folder stops being readable.

## More information

[0009](0009-a-request-is-stored-when-taken-up.md) says when a request is stored.
