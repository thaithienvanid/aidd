"""Where a line's git runs. Another repository counts only when the whole line is `git -C <absolute folder> ...`: git
resolves `-C` itself, so no shell control flow can leave git elsewhere, and nothing else on the line can make or
rewire that repository. It reads that repository's stored refspecs (ref_writes); the base-branch rule never skips one,
since another repository's branches can be this one's (a commondir, a link). A `cd` the guard follows only
to deny more (after_cd), never to allow. So a repository that never adopted aidd keeps its own branches, while this
repository's are held wherever git reaches them.
"""

from __future__ import annotations

from aidd.guard import shell_parser
from aidd.kernel import git

# The separators a list starts after: the line's start, `;` or a newline, `&`, and a subshell's `(`. A command there runs
# whatever came before it.
_LIST_START = ("", ";", "&", "(")


def after_cd(simple: list[shell_parser.SimpleCommand], cd: int, at: int) -> bool:
    """Whether the command at `at` runs only in the folder the `cd` at `cd` moved to: the `cd` runs whenever it does
    (back to the start of its list, it follows only `&&`, so `a || cd x && git` is no such line), and every command
    from the `cd` to `at` follows the one before by `&&`, at the `cd`'s depth. After `;`, `||`, or a pipe, or a `cd`
    in a subshell, git may run in the folder the line started in. `cd` is the first `cd` the folder depends on: the
    last one to an absolute folder, or the first of the line."""
    depth = simple[cd].depth
    j = cd
    while simple[j].after == "&&":
        j -= 1
        if j < 0 or simple[j].depth != depth:
            return False
    if simple[j].after not in _LIST_START:
        return False
    return all(simple[k].after == "&&" and simple[k].depth == depth for k in range(cd + 1, at + 1))


def absolute_c(simple: list[shell_parser.SimpleCommand], at: int, argv: list[str], sub: int) -> str | None:
    """The folder `git -C <folder>` names for the git command at `at` (`argv`, its subcommand at `sub`), when the guard
    can say where git runs and what it reads there: the line's only command, so nothing runs before it (a command
    substitution in its words runs first) to make, move, or rewire that repository; one `-C` and no other option; a
    literal path from `/` (a `~` follows HOME, which a line may set); no wrapper or variable before git; and a folder
    git already answers in, read as it is now. None for anything else."""
    if len(simple) != 1 or at != 0 or len(shell_parser.program_argv(simple[at].argv)) != len(simple[at].argv):
        return None  # another command may make or change the repository; a wrapper or an assignment may move git
    opts = argv[1:sub]
    if len(opts) != 2 or opts[0] != "-C":
        return None
    word = str(opts[1])
    if not word.startswith("/") or any(c in word for c in "$`*?[{~\\"):
        return None
    try:
        git.toplevel(word, check=True)
    except (git.GitError, OSError):
        return None
    return word
