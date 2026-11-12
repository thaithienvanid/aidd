"""The table of git calls that only read, and the one function that finds a call's row in it.

A call is a read only where a row names its form: the subcommand, the exact option words it may carry, and how many
arguments follow. Every other call is a write, whatever its words: an unknown subcommand, an option no row lists (an
abbreviation such as `--del` too), or a count of arguments no row allows. So a new or odd form fails closed: it drops what
`aidd.kernel.git_reads.shared_reads` kept, and a read of it is never kept. A row says why the form only reads, from git's own
manual, and `keeps` whether its answer comes from refs, the config, and objects alone, so a scope may answer it once.

`tests/test_git_read_forms.py` runs each row's example against a real repository, and checks every form the product issues.
"""

from __future__ import annotations

from dataclasses import dataclass

_ENDS = frozenset({"--", "--end-of-options"})
_SCOPES = frozenset({"--local", "--global", "--system"})
_CONFIG_FORMS = frozenset({"-z", "--null", "--includes", "--no-includes", "--show-scope", "--show-origin", "--type=bool"})


@dataclass(frozen=True, kw_only=True)
class Form:
    """One form of read. `options` are the exact words it may carry, `prefixes` the `--name=` words with any value, and
    `needs` the words of which one must be there (the one that picks what the call does). `arguments` counts the words that
    are no option, after `verb` if the form names one. Options may follow arguments, as git allows, unless `mixed` is False:
    then the first argument ends them, as `git config` reads them (`config name --get` sets a value, it does not read one). With `dotted`, each
    argument holds a `.`, as a config key does (`section.key`): no subcommand of git config does, so `config edit` is none of this row's."""

    name: str
    reason: str
    example: tuple[str, ...]
    keeps: bool = False
    verb: str = ""
    options: frozenset[str] = frozenset()
    prefixes: tuple[str, ...] = ()
    needs: frozenset[str] = frozenset()
    arguments: tuple[int, int | None] = (0, None)
    mixed: bool = True
    numeric: bool = False
    dotted: bool = False

    def matches(self, words: list[str]) -> bool:
        """Whether `words`, the ones after the subcommand, are this form."""
        given: set[str] = set()
        arguments: list[str] = []
        ended = False
        for word in words:
            if ended or word == "-" or not word.startswith("-"):
                arguments.append(word)
            elif word in self.options or word.startswith(self.prefixes) or (self.numeric and word[1:].isdigit()):
                if len(arguments) > bool(self.verb) and not self.mixed:
                    return False
                given.add(word)
                ended = word in _ENDS
            else:
                return False
        if self.verb:
            if arguments[:1] != [self.verb]:
                return False
            arguments = arguments[1:]
        low, high = self.arguments
        if self.dotted and not all("." in argument for argument in arguments):
            return False
        return (not self.needs or bool(self.needs & given)) and len(arguments) >= low and (high is None or len(arguments) <= high)


def _form(name: str, reason: str, *example: str, **shape) -> Form:
    return Form(name=name, reason=reason, example=example, **shape)


FORMS = (
    # Answers that come from refs, the config, and objects alone, never from the work tree or the index.
    _form(
        "rev-parse",
        "prints the name of an object or a path (git-rev-parse)",
        "rev-parse",
        "-q",
        "--verify",
        "HEAD^{commit}",
        keeps=True,
        options=frozenset(
            {
                "-q",
                "--quiet",
                "--verify",
                "--symbolic-full-name",
                "--show-toplevel",
                "--is-inside-work-tree",
                "--path-format=absolute",
                "--git-common-dir",
                "--show-object-format",
            }
        ),
    ),
    _form(
        "symbolic-ref",
        "given one name and no -d or -m, it prints where the symbolic ref points (git-symbolic-ref)",
        "symbolic-ref",
        "-q",
        "refs/remotes/origin/HEAD",
        keeps=True,
        options=frozenset({"-q", "--quiet", "--short"}),
        arguments=(1, 1),
        mixed=False,
    ),
    _form(
        "for-each-ref",
        "lists refs (git-for-each-ref)",
        "for-each-ref",
        "--format=%(refname)",
        "refs/heads",
        keeps=True,
        prefixes=("--format=", "--sort=", "--merged=", "--no-merged=", "--count="),
    ),
    _form(
        "merge-base",
        "prints the common ancestor of commits, or tests one by exit code (git-merge-base)",
        "merge-base",
        "--is-ancestor",
        "HEAD",
        "HEAD",
        keeps=True,
        options=frozenset({"--is-ancestor", "--end-of-options"}),
    ),
    _form(
        "ls-tree",
        "lists the contents of a tree object (git-ls-tree)",
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        "HEAD",
        keeps=True,
        options=frozenset({"-r", "-z", "--full-tree", "--name-only", "--", "--end-of-options"}),
    ),
    _form(
        "tag",
        "with --points-at it lists the tags of one object (git-tag, listing mode)",
        "tag",
        "--points-at",
        "HEAD",
        keeps=True,
        needs=frozenset({"--points-at"}),
        options=frozenset({"--points-at"}),
        arguments=(1, 1),
    ),
    _form(
        "rev-list",
        "counts or lists commits (git-rev-list)",
        "rev-list",
        "--count",
        "--end-of-options",
        "HEAD",
        keeps=True,
        options=frozenset({"--count", "--end-of-options"}),
    ),
    _form(
        "config",
        "--get, --get-all, and --get-regexp print what the config holds for one name (git-config)",
        "config",
        "--get",
        "user.name",
        keeps=True,
        needs=frozenset({"--get", "--get-all", "--get-regexp"}),
        options=frozenset({"--get", "--get-all", "--get-regexp"}) | _SCOPES | _CONFIG_FORMS,
        arguments=(1, 1),
        mixed=False,
    ),
    _form(
        "config",
        "--list prints the whole config (git-config)",
        "config",
        "--list",
        keeps=True,
        needs=frozenset({"--list", "-l"}),
        options=frozenset({"--list", "-l"}) | _SCOPES | _CONFIG_FORMS,
        arguments=(0, 0),
        mixed=False,
    ),
    _form(
        "config",
        "with one name and no option that sets, it prints that name's value (git-config); a name holds a dot, a subcommand (`edit`) does not",
        "config",
        "user.name",
        keeps=True,
        dotted=True,
        options=_SCOPES | _CONFIG_FORMS,
        arguments=(1, 1),
        mixed=False,
    ),
    _form(
        "remote", "with no verb it lists the remotes (git-remote)", "remote", keeps=True, options=frozenset({"-v", "--verbose"}), arguments=(0, 0), mixed=False
    ),
    _form(
        "remote",
        "get-url prints a remote's URL (git-remote)",
        "remote",
        "get-url",
        "origin",
        keeps=True,
        verb="get-url",
        options=frozenset({"--push", "--all"}),
        arguments=(1, 1),
        mixed=False,
    ),
    # Answers that read the work tree, the index, or a stream, so no scope keeps them; none writes a ref or the config.
    _form(
        "status",
        "shows the state of the work tree, and with --no-optional-locks (which aidd adds) writes nothing (git-status)",
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=no",
        options=frozenset({"--porcelain", "-z", "--"}),
        prefixes=("--untracked-files=",),
    ),
    _form(
        "diff",
        "compares trees, the index, and the work tree, and prints (git-diff)",
        "diff",
        "--name-only",
        "-z",
        "HEAD",
        options=frozenset({"--name-only", "--numstat", "--no-renames", "-M", "-z", "--", "--end-of-options"}),
    ),
    _form(
        "log",
        "prints commits (git-log)",
        "log",
        "-z",
        "--format=%H",
        "HEAD",
        options=frozenset({"-z", "--reverse", "-E", "--extended-regexp", "-n", "--all", "--", "--end-of-options"}),
        prefixes=("--format=", "--grep="),
        numeric=True,
    ),
    _form("show", "prints an object (git-show)", "show", "--end-of-options", "HEAD:a.txt", options=frozenset({"--end-of-options"})),
    _form(
        "ls-files",
        "lists files of the index and the work tree (git-ls-files)",
        "ls-files",
        "-z",
        "--cached",
        options=frozenset({"-z", "--cached", "--ignored", "--others", "--exclude-standard", "-v", "-t", "-s", "-m", "--"}),
        prefixes=("--exclude=", "--exclude-per-directory="),
    ),
    _form(
        "cat-file",
        "prints an object, or tests that it exists (git-cat-file)",
        "cat-file",
        "-e",
        "HEAD",
        options=frozenset({"-e", "-p", "-t", "--batch", "--filters"}),
    ),
    _form(
        "check-ignore",
        "tells which ignore rule matches a path, and writes nothing (git-check-ignore)",
        "check-ignore",
        "-q",
        "a.txt",
        options=frozenset({"-q", "-v", "--no-index", "--stdin", "-z", "--"}),
    ),
    _form(
        "worktree",
        "list prints the work trees (git-worktree)",
        "worktree",
        "list",
        "--porcelain",
        verb="list",
        options=frozenset({"--porcelain", "-z"}),
        arguments=(0, 0),
        mixed=False,
    ),
)
_BY_NAME: dict[str, list[Form]] = {}
for _row in FORMS:
    _BY_NAME.setdefault(_row.name, []).append(_row)


def read_form(name: str, words: list[str]) -> Form | None:
    """The row for subcommand `name` with these words after it, or None: the call is no read the table knows."""
    return next((row for row in _BY_NAME.get(name, ()) if row.matches(words)), None)
