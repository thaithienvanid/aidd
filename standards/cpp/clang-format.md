---
id: cpp/clang-format
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: [.clang-format, "**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp"]
why: "clang-format, from the LLVM project, is the formatter C and C++ editors and CI share, and one pinned version with a .clang-format file lays the code out the same on every machine."
reviewed: "2026-10-22"
maturity: established
tool:
  name: clang-format
  registry: pypi
  package: clang-format
version_policy: current_stable
checked_version: "23.1.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "23.1.3"
source: https://clang.llvm.org/docs/ClangFormat.html
evidence: clang-format is located in clang/tools/clang-format and can be used to format C/C++/Java/JavaScript/JSON/Objective-C/Protobuf/C# code.
alternatives: [Uncrustify, Artistic Style]
status: active
enforced_by:
  - name: format
    command: [sh, -c, "git ls-files -z -- '*.c' '*.h' '*.cc' '*.cpp' '*.cxx' '*.hh' '*.hpp' | xargs -0 uvx clang-format@23.1.3 --dry-run --Werror"]
---

# clang-format sets the layout of the C and C++ code

It answers the formatter choice of `aidd-team:ci-pipeline` for C and C++. clang-format is under the Apache License 2.0 with LLVM exceptions.

## What the team does

- Commit one `.clang-format` at the root. Start from a named style with `BasedOnStyle`, such as LLVM or Google, and change only the options the team agrees on.
- Run the PyPI wheel at `pin` everywhere, in CI, in the pre-commit hook, and in each editor. Two clang-format versions can lay out the same file differently.
- Keep generated and third-party code out of the check with a `.clang-format-ignore` file, or a `DisableFormat: true` file in that folder.
- Move `pin` and reformat the whole tree in one change, with nothing else in it.

## What the gate runs

One `tests` entry runs clang-format at `pin` over every tracked C and C++ file, without changing them. A file whose layout differs fails the change.
