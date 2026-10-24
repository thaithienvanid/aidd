# Codemods

Load this when an upgrade needs the same edit across many files.

The same edit across many files is a codemod: a renamed API, a framework's migration, or a deprecated call. It is never hand edits file by file, and never a regular expression over source, which matches text, not syntax, so it also changes comments, strings, and look-alike names.

- **Pick the tool the ecosystem has.** The package's official codemod first; otherwise ast-grep (`@ast-grep/cli` 0.45.3) for most languages, OpenRewrite recipes for Java, Kotlin, Maven, and Gradle, jscodeshift (17.4.0) for JavaScript and TypeScript.
- **Dry run.** `ast-grep run --pattern '<old>' --rewrite '<new>' --lang <lang> src/` prints each rewrite as a diff and writes nothing; `mvn rewrite:dryRun` (or `gradle rewriteDryRun`) writes `rewrite.patch`; `jscodeshift --dry --print -t transform.js src/`.
- **Review the diff.** Count the files it touches; a match outside the Task's scope means the pattern is too wide: narrow it and run the dry run again.
- **Apply, then run the tests.** `ast-grep run ... --update-all`, `mvn rewrite:run`, or `jscodeshift -t transform.js src/`; commit the output alone, then the hand edits; run the full suite, the type checker, and the build.
- **Keep a transform you wrote** with a before-and-after fixture as its test when a later change will need it; delete it otherwise.
