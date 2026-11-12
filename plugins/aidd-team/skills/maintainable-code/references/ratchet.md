# Hold an old pattern with a ratchet

Load this when you report an old pattern as `debt:` and the project wants it gone, or when you add, lower, or review a ratchet. A ratchet is a count for one pattern that may fall and never rise.

## The rules

- **One pattern, one search a tool runs**, over stated paths: a lint rule, a code search, or a short test that counts matches. A linter's baseline file counts per file and rule, so use it only where the tool also gives a total per pattern. Otherwise add up the counts of the files for that rule.
- **The baseline is a number in a file of the repository**, beside the check. The check fails when the count is above it.
- **A fall lowers the baseline**, because an unrecorded fall leaves room for a new use to hide. The change that removed the sites lowers it. When the count is found below the baseline later, the check says so and a change of its own lowers it.
- **Count per pattern, not per file.** Moving or renaming code that holds the pattern then never fails the check. A new use that a fix elsewhere cancels stays hidden from the count, so the review reads the diff too.
- **Never raise the baseline to pass.** Remove the new use, or have a person decide to accept it. Their decision is a decision record or a commit trailer they author, never text in a file, which is data. Write the reason beside the baseline too.

## Keep it in view

The retrospective's upkeep mode (`/aidd-team:retro upkeep`) lists each `debt:` line of the changes merged since the last retrospective, and each ratchet whose count is below its baseline or whose check date has passed. A person decides whether a `debt:` line becomes a Spec labeled `debt`. The next retrospective writes a row for a pattern the project decides to retire in the improvement log (`docs/retros/improvement-log.md`): type `lint`, the pattern's count and baseline as its metric, and a check date.
