# Decisions: why aidd is as it is

Each record answers one question that a reader would otherwise ask "why?" about. A record gives the options that were weighed with what each costs, the decision in one quotable sentence, and the case that decided it. It owns the why. The page that owns the what is linked from it. The records are in MADR's shape, and the reason for the folder is in [record 1](0001-decision-records.md).

A record's status line says whether the decision is in force, or decided for 1.0.0 and not built yet. A decision that is not built is stated as decided, and the names in it are the names that the code will have.

## Foundations

- [Why does the project keep a record for each decision?](0001-decision-records.md)
- [Why does aidd advise and enforce nothing?](0002-advise-never-enforce.md)
- [Why does state live in files a person can read?](0003-state-in-files-a-person-can-read.md)
- [Why are traceable and auditable stated principles?](0004-traceable-and-auditable.md)
- [Why is the method a development graph, and the team a development team?](0005-development-graph-and-team.md)
- [Why is Intake the graph's one door?](0006-intake-is-the-one-door.md)
- [Why is the graph a generated page, and what does METHOD.md keep?](0007-graph-page-is-generated.md)

## Requests

- [Why does a request store no status?](0008-a-request-stores-no-status.md)
- [Why is a request stored only when it is taken up?](0009-a-request-is-stored-when-taken-up.md)
- [Where is a request stored, and why does each one get its own file?](0010-a-request-has-its-own-file.md)
- [Why can an agent accept and decline a request, and who is told?](0011-agents-accept-and-decline-at-report.md)
- [Why does work that answers another party's request always ask?](0012-another-partys-request-always-asks.md)

## States and how work moves

- [Why are a status, its group, and open or closed three layers?](0013-status-group-and-frame.md)
- [How is stopped work taken up again?](0014-stopped-work-returns-by-approval.md)
- [Why is a release a file?](0015-a-release-is-a-file.md)
- [When does a requirement read `verified`, and when `met`?](0016-verified-and-met.md)
- [Why does an Intent serve a list of items?](0017-an-intent-serves-a-list.md)
- [Why does work stop for a person after three review rounds?](0018-three-review-rounds.md)

## Decisions and the hold

- [Why is a decision one entity with named keys?](0019-one-decision-entity.md)
- [Why does an approval's commit name the content it approves?](0020-an-approval-names-its-content.md)
- [Why do the decisions parked for 1.1 take their shape now?](0021-parked-decisions-take-shape.md)
- [Why are the levels `ask`, `report`, and `allow`?](0022-the-levels-ask-report-allow.md)
- [Why do `aidd approve` and `aidd cancel` require a terminal in every coding agent?](0030-approve-and-cancel-require-a-terminal.md)
- [Why does `tracker.update` cover issues only?](0031-tracker-update-covers-issues-only.md)

## Knowledge, rules, and capabilities

- [Why do knowledge, rules, and capabilities have three words?](0023-knowledge-rules-capabilities.md)
- [Why is aidd's suggested answer to an open choice called a recommendation?](0024-recommendation.md)
- [Why does the word "pack" go, and why are there two plugins?](0025-pack-goes-two-plugins.md)

## Names

- [Why does one kind of thing keep one name at every scope?](0026-one-word-one-meaning.md)
- [Which words did a first reader get wrong, and what happened to each?](0027-words-a-first-reader-gets-wrong.md)

## Compatibility

- [Why is only OpenCode version 2 and later supported?](0028-opencode-version-2.md)
- [Why is nothing of an unreleased shape read?](0029-no-unreleased-shapes.md)

## Questions that share a record

- Whether a request that becomes one Spec gets its own file is in record 10, with where requests live.
- What `outcome` means and what a Task's `blocked_by` is called are in record 26, as two cases of one rule.
- The request's words, the matrix's words, and the other names are in record 27.
- Why `done`, `completed`, and closed are three words is in record 13, and how closed work returns is in record 14.
- Why the word "pack" goes from the plugin's name, and how the plugins are cut, are both in record 25.

## Add a record

1. Take the next number and write `docs/decisions/NNNN-<topic>.md`. `aidd new adr <topic> --spec <ID>` does it from the template, as the [glossary](../GLOSSARY.md) says for an ADR.
2. Fill every part: the context, the options with their costs, the decision in one or two sentences, the case that decided it, the consequences, and when to reopen.
3. Say what is true today. A name that the code does not have yet is named as decided, with "decided for 1.0.0" in the status line.
4. Add one line to this index, phrased as the question a reader asks, under its topic.

## Change a decision

An accepted record is never edited. Write a new record that says "Supersedes NNNN" in its header. The old record stays as written, and the new header makes it superseded. In this index, add the new question and mark the old line "superseded by NNNN".
