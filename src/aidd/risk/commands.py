"""Which actions a shell command is, from the actions' `commands` patterns, and which branch or environment a `git
push` reaches.

A pattern matches a whole simple command, with `*` for any run of characters (`git push --force*`). A command line is
split at `&&`, `||`, `;`, `|`, and new lines outside quotes, and each part is matched alone, so `make && git push -f`
is `git.push.force`. Git's own options before its subcommand (`git -C repo -c k=v push`), the runner a tool starts
through (`npx prisma`, `bundle exec rails`, RUNNER_FORMS), and settings before the program (`FOO=1 git push`) are set
aside first. The part is matched again with its settings kept, so `RAILS_ENV=production rails db:*` can match. A command
that another runs (`sudo git push -f`, `bash -c '...'`, `$(...)`) is matched too (shell.py). A reader that an action's
`file_reads` names, such as `cat`, is that action when a word after it is a path in the action's area (`cat .env`). A `git merge` reads its branch from git,
as a push does (`merge_reach`), and also from a `git checkout` or `git switch` earlier on the line, whichever is
stricter (`checkout_after`).

This is advice, never a control: an alias, a script, or a variable gets past any pattern. SECURITY.md says so.
"""

from __future__ import annotations

import contextvars
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from aidd.kernel import git, git_calls, globs
from aidd.risk.gh_api import gh_api_actions, ref_target
from aidd.risk.rules import LEVEL_RANK, RuleSet, level_of, winning_rule
from aidd.risk.shell import SETTING, shell_words, split, without_redirections, wrapped

# Git's options that take a value before the subcommand, and those that take none.
_GIT_VALUE_OPTIONS = {"-C", "-c", "--attr-source", "--config-env", "--exec-path", "--git-dir", "--namespace", "--work-tree"}
_GIT_FLAG_OPTIONS = {"-p", "-P", "--paginate", "--no-pager", "--bare", "--literal-pathspecs", "--no-optional-locks", "--no-replace-objects"}

# The usual ways to start a tool, each read as the tool's own command: `npx prisma migrate reset` is `prisma migrate
# reset`. A pattern names the tool's form, and each harness's ask rules get every form here (harness_rules).
_NODE = ("npx", "pnpm", "pnpm exec", "pnpm dlx", "bunx", "yarn")
# Each harness's ask rules list the forms in this order (harness_rules).
RUNNER_FORMS: dict[str, tuple[str, ...]] = {
    "prisma": tuple(f"{r} prisma" for r in _NODE),
    "drizzle-kit": tuple(f"{r} drizzle-kit" for r in _NODE),
    "wrangler": tuple(f"{r} wrangler" for r in _NODE),
    "alembic": ("uv run alembic", "poetry run alembic", "python -m alembic", "python3 -m alembic"),
    "python manage.py": ("python3 manage.py", "./manage.py", "uv run python manage.py", "uv run manage.py", "poetry run python manage.py"),
    "rails": ("bin/rails", "bundle exec rails", "rake", "bin/rake", "bundle exec rake"),
    "php artisan": ("./vendor/bin/sail artisan", "vendor/bin/sail artisan", "sail artisan"),
    # aidd's own launch forms, so a rule for an aidd command, such as `records.push`, holds however aidd is started.
    "aidd": ("python3 -m aidd", "python -m aidd", "uvx aidd", "uv run aidd", "pipx run aidd", "python3 aidd.pyz", "python aidd.pyz"),
}
# Longest first, so `uv run python manage.py` is read before `uv run manage.py`.
_RUNNER_PREFIXES = sorted(((form, tool) for tool, forms in RUNNER_FORMS.items() for form in forms), key=lambda x: -len(x[0]))


def normalize(command: str, *, keep_settings: bool = False) -> str:
    """One simple command as the patterns read it: words joined by one space, with git's own options and a tool's
    runner set aside, and the settings before the program too unless `keep_settings`."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    settings = []
    while words and SETTING.fullmatch(words[0]):
        settings.append(words.pop(0))  # an environment assignment before the program
    line = " ".join(words)
    for form, tool in _RUNNER_PREFIXES:
        if line == form or line.startswith(form + " "):
            words = tool.split() + words[len(form.split()) :]
            break
    if len(words) > 1 and words[0].rsplit("/", 1)[-1] in ("python", "python3") and words[1].rsplit("/", 1)[-1] == "aidd.pyz":
        words = ["aidd", *words[2:]]  # the release's zipapp, wherever it lies
    if words and words[0].rsplit("/", 1)[-1] in ("aidd", "aidd.pyz"):
        words = ["aidd", *words[1:]]  # aidd by its path, such as the plugin's `scripts/aidd`
    if words and words[0].rsplit("/", 1)[-1] == "git":
        rest, out = words[1:], ["git"]
        while rest and rest[0].startswith("-"):
            opt = rest.pop(0)
            if opt in _GIT_VALUE_OPTIONS and rest:
                value = rest.pop(0)
                if keep_settings and opt == "-c":
                    key, eq, val = value.partition("=")
                    out += [opt, key.lower() + eq + val]  # git ignores a key's case; `push.followTags=true` changes the push
            elif "=" in opt or opt in _GIT_FLAG_OPTIONS:
                continue
        words = out + rest
    return " ".join((settings if keep_settings else []) + words)


def _matches(patterns: list[str], *texts: str) -> bool:
    """Whether any of `texts` matches any of the patterns, which read their whitespace as one space."""
    return any(globs.match_text(" ".join(p.split()), t) for p in patterns for t in texts)


def call_actions(rs: RuleSet, call: str) -> list[tuple[str, str]]:
    """Each (action, simple command) one simple command matches, without the commands it runs inside itself, which
    `command_level` reads as calls of their own (`sudo`, `bash -c`, `$(...)`, shell.py). A `gh api` call matches by its
    parsed arguments (gh_api.py), and a reader by the files it reads; both only add actions."""
    simple = normalize(call)
    typed = normalize(call, keep_settings=True)  # so a pattern can name a setting (`RAILS_ENV=production rails db:*`)
    found = [a for a, spec in rs.actions.items() if _matches(spec.get("commands", []), simple, typed)]
    found += [a for a in gh_api_actions(rs.actions, call) if a not in found]
    found += [a for a in file_read_actions(rs, call) if a not in found]
    return [(a, simple) for a in found]


# The readers whose first word is a pattern or a script, never a file, unless an option gives it instead: `-e` or `-f`, in a
# run of short flags too (`-ie x`), or `--regexp`, `--expression`, or `--file`, also with `=`. `-f` and `--file` read a file.
_PATTERN_FIRST = {"grep", "rg", "sed", "awk"}
_PATTERN_LONG = {"--regexp", "--expression", "--file"}
# The flags each of them takes with no value, which aidd fully understands. Any other option keeps the first word.
_PATTERN_FLAGS = {"grep": "abcEFGhHiIlLnoqrRsUvVwxzZ", "rg": "aceFhHiIlLnNopPqsSuUvwxz", "sed": "Einrsuz", "awk": ""}
_PATTERN_FLAGS_LONG = {
    "--count",
    "--extended-regexp",
    "--files-with-matches",
    "--fixed-strings",
    "--ignore-case",
    "--invert-match",
    "--line-number",
    "--quiet",
    "--recursive",
    "--word-regexp",
}


def _pattern_option(program: str, word: str, rest: list[str]) -> tuple[bool, list[str], bool]:
    """One option of a grep-like reader: whether it gives the pattern, the files it reads, and whether aidd fully
    understands it. It takes its value from `rest` when none is attached."""
    if word.startswith("--"):
        name, eq, value = word.partition("=")
        if name in _PATTERN_LONG:
            value = value if eq else (rest.pop(0) if rest else "")
            return True, [value] if name == "--file" else [], True
        return False, [], not eq and word in _PATTERN_FLAGS_LONG
    for pos, char in enumerate(word[1:], 1):
        if char in "ef":
            value = word[pos + 1 :] or (rest.pop(0) if rest else "")
            return True, [value] if char == "f" else [], True
        if char not in _PATTERN_FLAGS[program]:
            return False, [], False
    return False, [], True


def read_paths_of(program: str, words: list[tuple[str, bool]]) -> list[str]:
    """The words of a reader's command that name a file it reads: a word that is no option, no target of an output
    redirection, and no pattern of a grep-like reader, the file after an input redirection, and a file `-f` gives. For
    `cp`, never its last word, the file it writes. A grep-like reader's first word stays when an option it has gives the
    pattern, or when aidd does not fully understand one of its options. `words` are those after the program, as
    `shell_words` gives them."""
    words = list(words)
    reads: list[str] = []
    positional: list[str] = []
    pattern_given, understood, options_done = False, True, False
    while words:
        word, operator = words.pop(0)
        target = words.pop(0)[0] if operator and words and not words[0][1] else ""
        if operator:
            reads += [target] if word.lstrip("0123456789") in ("<", "<>") else []  # the shell opens it for the reader
        elif options_done or word == "-" or not word.startswith("-"):
            positional.append(word)
        elif word == "--":
            options_done = True
        elif program in _PATTERN_FIRST:
            rest = [w for w, _ in words]
            given, files, known = _pattern_option(program, word, rest)
            words = words[len(words) - len(rest) :]
            pattern_given, understood, reads = pattern_given or given, understood and known, reads + files
    if program in _PATTERN_FIRST and not pattern_given and understood:
        positional = positional[1:]
    return reads + (positional[:-1] if program == "cp" else positional)


def file_read_actions(rs: RuleSet, call: str) -> list[str]:
    """The actions whose `file_reads` a simple command, as typed, is: its program is one of the readers, and a file it
    reads (`read_paths_of`) matches one of the action's `paths` and none of its `exclude`, unless one of its `include`. Case is ignored, as for an
    area."""
    words = shell_words(call)
    while words and not words[0][1] and SETTING.fullmatch(words[0][0]):
        words.pop(0)
    if not words:
        return []
    program = words[0][0].rsplit("/", 1)[-1]
    out = []
    for action, spec in rs.actions.items():
        reads = spec.get("file_reads") or {}
        if program not in reads.get("readers", []):
            continue
        paths, exclude, include = reads.get("paths", []), reads.get("exclude", []), reads.get("include", [])
        files = read_paths_of(program, words[1:])
        kept = [p for p in files if globs.match_any(include, p, fold_case=True) or not globs.match_any(exclude, p, fold_case=True)]
        if any(globs.match_any(paths, p, fold_case=True) for p in kept):
            out.append(action)
    return out


def is_local_merge(text: str) -> bool:
    """Whether a command or a pattern is a `git merge` or a `git pull`, whose level turns on the branch checked out
    (`merge_reach`)."""
    return text.split()[:2] in (["git", "merge"], ["git", "pull"])


# The `git merge` options that take the next word as their value, and those that end a merge and land nothing.
_MERGE_VALUE_OPTIONS = {"-m", "-F", "-s", "-X", "--file", "--strategy", "--strategy-option", "--into-name", "--cleanup"}
# The `git pull` options that take the next word as their value, beside the merge's.
_PULL_VALUE_OPTIONS = {"-j", "-o", "--jobs", "--depth", "--deepen", "--server-option", "--shallow-since", "--shallow-exclude", "--upload-pack"}
_MERGE_ENDS = {"--abort", "--quit"}
# The git options and settings that point a command at another repository than the folder it runs in.
_ELSEWHERE_OPTIONS = ("-C", "--git-dir", "--work-tree")
_ELSEWHERE_SETTINGS = ("GIT_DIR=", "GIT_WORK_TREE=")


def names_another_repository(call: str) -> bool:
    """Whether a git command, as typed, names a repository other than the folder it runs in: `git -C <dir>`,
    `--git-dir`, `--work-tree`, or a `GIT_DIR` or `GIT_WORK_TREE` setting before it."""
    try:
        words = shlex.split(call)
    except ValueError:
        words = call.split()
    while words and SETTING.fullmatch(words[0]):
        if words.pop(0).startswith(_ELSEWHERE_SETTINGS):
            return True
    if not words or words[0].rsplit("/", 1)[-1] != "git":
        return False
    rest = words[1:]
    while rest and rest[0].startswith("-"):  # git's own options, up to the subcommand
        word = rest.pop(0)
        if word in _ELSEWHERE_OPTIONS or word.startswith(tuple(f"{o}=" for o in _ELSEWHERE_OPTIONS[1:])):
            return True
        if word in _GIT_VALUE_OPTIONS and rest:
            rest.pop(0)
    return False


_CD = ("cd", "pushd", "popd")


def folder_after(part: str, here: str | None) -> str | None:
    """The folder the rest of a command line runs in after one part of it: a `cd` or `pushd` moves it to its target,
    resolved against `here`, also behind a `(` or `{` or a `builtin` or `command` prefix. None when aidd cannot tell: no
    target, `-`, a `~` or a variable, a relative target while `CDPATH` is set, a folder that does not exist, a `popd`, a
    `cd` inside a command another runs (`bash -c`, `eval`, `$(...)`), the end of a subshell, or a folder it could not
    tell before. Any other part leaves it as it was. Whatever aidd cannot model counts as another repository, so it asks."""
    try:
        words = shlex.split(part)
    except ValueError:
        words = part.split()
    first = words[0].lstrip("({") if words else ""
    words = ([first] if first else []) + words[1:]
    while words and words[0] in ("builtin", "command"):
        words = words[1:]
    text = part.strip()
    if text.endswith(")") and "(" not in text:
        return None  # a subshell ends, and its folder with it: aidd does not track where it began
    if text.startswith("(") and text.endswith(")"):
        return here  # a whole subshell: its `cd` ends with it
    if not words or words[0] not in _CD:
        inner = (c.lstrip("({ ").split()[:1] for c in wrapped(part))
        return None if any(w and w[0] in _CD for w in inner) else here
    targets = [w.rstrip(")};") for w in words[1:] if w not in ("-L", "-P", "--")]
    if here is None or words[0] == "popd" or len(targets) != 1:
        return None
    target = targets[0]
    if target == "-" or target.startswith("~") or any(c in target for c in "$`"):
        return None
    if os.environ.get("CDPATH") and not target.startswith("/"):
        return None  # the shell may find a relative target under one of CDPATH's folders first
    folder = Path(here) / target
    return str(folder.resolve()) if folder.is_dir() else None


# The `git checkout` and `git switch` options that create the branch they name, and the flags that change no branch.
# Any other option, such as `--detach`, `--track`, or a bare `-` (the branch checked out before), is one aidd cannot tell.
_CREATE_OPTIONS = {"checkout": ("-b", "-B", "--orphan"), "switch": ("-c", "-C", "--create", "--force-create", "--orphan")}
_SWITCH_FLAGS = {
    "-q",
    "--quiet",
    "-f",
    "--force",
    "-m",
    "--merge",
    "--discard-changes",
    "--progress",
    "--no-progress",
    "--no-track",
    "--guess",
    "--no-guess",
    "--ignore-other-worktrees",
    "--overwrite-ignore",
    "--no-overwrite-ignore",
    "--recurse-submodules",
    "--no-recurse-submodules",
}


@dataclass(frozen=True)
class Checkout:
    """A branch a `git checkout` or `git switch` earlier on a line may leave checked out in `folder`: its `name`, and its
    `branch` as a rule names it. That is `default`, `own` for a branch the line creates, or `shared` for another branch
    that exists, since aidd cannot tell whose it is. A name aidd cannot read is empty, and counts as the default branch.
    A checkout may fail, or run in a way the line does not wait for, so it only adds a branch to read beside the
    session's, and the stricter reading wins (`command_level`)."""

    folder: str | None
    name: str
    branch: str


def checkout_after(call: str, here: str | None, before: tuple[Checkout, ...]) -> tuple[Checkout, ...]:
    """The branches a later merge or push on the line may run on, beside the session's: `before`, and the branch a
    `git checkout` or `git switch` in this one simple command names. A checkout of files (`-- <paths>`) adds none.
    `command_level` reads each command another runs (`bash -c`, `$(...)`) as a call of its own."""
    text = call.strip().lstrip("({ ").rstrip(";)} ")
    words = normalize(without_redirections(text)).split()
    if words[:2] not in (["git", "checkout"], ["git", "switch"]):
        return before
    if here is None or names_another_repository(text):
        return (*before, Checkout(here, "", "default"))  # a checkout in a folder or a repository aidd cannot read
    found = _switched(words[1], words[2:], here)
    return before if found is None else (*before, found)


def _switched(command: str, rest: list[str], here: str) -> Checkout | None:
    """The branch `git <command> <rest>` names in `here`, or None when it moves no branch: a checkout of files, or no
    word at all. Anything aidd cannot read names the default branch."""
    unknown = Checkout(here, "", "default")
    create: str | None = None
    names: list[str] = []
    while rest:
        word = rest.pop(0)
        option, eq, value = word.partition("=")
        if word == "--":
            if rest and command == "checkout" and create is None and len(names) <= 1:
                return None  # the files after `--` come from the index or a commit, and no branch moves
            if rest:
                return unknown
            break
        if option in _CREATE_OPTIONS[command]:
            create = value if eq else (rest.pop(0) if rest else "")
        elif word not in _SWITCH_FLAGS and word.startswith("-"):
            return unknown
        elif not word.startswith("-"):
            names.append(word)
    if create is not None:
        return _named(create, here, created=True) if len(names) <= 1 else unknown  # a new branch, with its start point
    if not names:
        return None
    return _named(names[0], here, created=False) if len(names) == 1 else unknown


def _local_branch(name: str, cwd: str) -> bool:
    return bool(git.run(["rev-parse", "--verify", "-q", f"refs/heads/{name}"], cwd, check=False).strip())


def _named(name: str, here: str, *, created: bool) -> Checkout | None:
    """The branch a checkout of `name` names, or of a new branch `name` when `created`. None for the branch git has
    checked out already, which the session's reading covers."""
    unknown = Checkout(here, "", "default")
    if not name or name.startswith("-") or any(c in name for c in "$`~*?[\\@"):
        return unknown  # a variable, a substitution, a pattern, or `@{-1}`
    if name in default_names(here)[0]:
        return Checkout(here, name, "default")
    exists = _local_branch(name, here)
    if created:
        # A new branch is one's own; a name that exists already fails or resets that branch, which aidd cannot tell.
        return unknown if exists else Checkout(here, name, "own")
    if name == git.current_branch(here):
        return None
    # Another branch that exists is `shared`; a tag, a commit, a file, or a remote's branch git would track is unclear.
    return Checkout(here, name, "shared") if exists else unknown


def merge_reach(
    simple: str,
    cwd: str = ".",
    *,
    elsewhere: bool = False,
    current: str | None = None,
    moved: tuple[bool, ...] = (False, False, False),
) -> tuple[bool, str | None]:
    """Whether a `git merge` or a `git pull` lands other work, and on which branch, as a rule names it: `default` while
    the default branch is checked out, `own` on another branch when the default one is known, and None when git cannot
    tell: a detached HEAD, an unknown default branch, or a command that names another repository (`elsewhere`), which
    counts before anything else. A merge lands nothing when `--abort` or `--quit` is its only argument, or when it merges
    only the branch's own upstream: no branch named, or only the branch itself or its configured upstream. A pull lands
    nothing only when all its arguments are options, since it then pulls the branch's own upstream: any other word, a
    remote, a URL, a path, `.`, or a refspec, lands work, with no reading of what it names. `--ff-only` lands the other
    branch's commits all the same. `current` is the branch a checkout earlier on the line left, when there is one
    (`checkout_after`): an empty one is a branch aidd cannot tell."""
    if not is_local_merge(simple):
        return False, None
    if elsewhere:
        return True, None
    pull = simple.split()[1] == "pull"
    args, named, rest = [], [], simple.split()[2:]
    while rest:
        word = rest.pop(0)
        args.append(word)
        if word in _MERGE_VALUE_OPTIONS | (_PULL_VALUE_OPTIONS if pull else set()) and rest:
            rest.pop(0)  # the option's value, never a flag or a branch
        elif word == "-" or not word.startswith("-"):  # a bare `-` is the branch checked out before (`@{-1}`)
            named.append(word)
    if len(args) == 1 and args[0] in _MERGE_ENDS:
        return False, None  # it ends a merge
    if current is None:
        current = git.current_branch(cwd)
    upstream = git.run(["rev-parse", "--symbolic-full-name", f"{current}@{{u}}"], cwd, check=False).strip() if current else ""
    defaults, known = default_names(cwd)
    # An upstream that is another branch's work (`git branch --set-upstream-to=feat main`, itself allowed, or a remote's
    # copy of another branch) never lowers a merge into the default branch. Only the branch's own name on a remote does.
    names_moved, tracking_moved, upstream_moved = moved  # an earlier command moved a name, a tracking ref, or an upstream
    # A bare pull fetches its upstream fresh, so only a changed upstream (`upstream_moved`) redirects it. A bare merge and
    # `@{u}` read the local tracking ref, which a ref write can move too (`tracking_moved`). Any move makes a name unknown.
    guarded = upstream_moved or (bool(upstream) and current in defaults and not git.tracks_own_name(current, upstream, cwd))
    if pull and not named and not guarded:
        return False, None  # it pulls the branch's own upstream
    tracked = guarded or tracking_moved

    def own(ref: str) -> bool:
        # The full name git resolves the word to: a text match would take a tag named `main`, or a name two refs share.
        resolved = git.full_ref_name(ref, cwd)
        if ref.endswith(("@{u}", "@{upstream}")):  # resolved through the config, so no tag or branch name shadows it
            return bool(current) and resolved is not None and resolved == upstream and not tracked
        return bool(current) and not names_moved and resolved is not None and (resolved == f"refs/heads/{current}" or (resolved == upstream and not guarded))

    if not pull and args != ["--continue"] and not (tracked and not named) and all(own(r) for r in named):
        return False, None
    if not current or not known:
        return True, None
    return True, "default" if current in defaults else "own"


def push_branch(simple: str, cwd: str = ".") -> str | None:
    """The branch a `git push` reaches, as a rule names it: `default` when it names the repository's default branch,
    pushes HEAD while that branch is checked out, or pushes every branch (`--all`, `--mirror`); `own` for the branch
    checked out; `shared` for another branch it names, since aidd cannot tell whose it is; and None when the command is
    not a push or git cannot tell."""
    return push_reach(simple, cwd)[0]


def deploys_to(environments: list[dict], ref_type: str, name: str) -> list[str]:
    """The environments whose `branches` or `tags` (`ref_type`) globs match the ref `name`. A glob with no wildcard
    names one ref, never the refs under it, so `dev` is not `dev/login`."""
    hit = lambda p: globs.match(p, name) if any(c in p for c in "*?") else p == name  # noqa: E731
    return [str(e["name"]) for e in environments if any(hit(str(p)) for p in e.get(ref_type) or [])]


def push_reach(simple: str, cwd: str = ".", environments: list[dict] | None = None, current: str | None = None) -> tuple[str | None, list[str]]:
    """The branch a `git push` reaches, as `push_branch` names it, and the environments it deploys to. A ref that an
    environment's globs match counts for that environment instead of as `own` or `shared`, so a push that reaches only
    environments reaches no branch (None). The default branch stays `default`, even when it is an environment too."""
    envs = environments or []
    words = simple.split()
    if words[:2] != ["git", "push"]:
        return None, []
    options = set(words[2:])
    deployed: list[str] = []
    if {"--tags", "--follow-tags", "--mirror"} & options:
        deployed += [str(e["name"]) for e in envs if e.get("tags")]
    if {"--all", "--mirror", "--branches"} & options:
        deployed += [str(e["name"]) for e in envs if e.get("branches")]
        return "default", list(dict.fromkeys(deployed))
    args = [w for w in words[2:] if not w.startswith("-")]
    defaults = default_names(cwd)[0]
    if current is None:  # else the branch a checkout earlier on the line left, as for `merge_reach`
        current = git.current_branch(cwd)
    refspecs = args[1:] if len(args) > 1 else []
    if not refspecs:
        if not current:
            return None, list(dict.fromkeys(deployed))
        hit = deploys_to(envs, "branches", current)
        where = "default" if current in defaults else None if hit else "own"
        return where, list(dict.fromkeys(deployed + hit))
    reached = []
    deleting = bool({"--delete", "-d"} & options)
    for spec in refspecs:
        body = spec.lstrip("+")
        src, dest = body.partition(":")[0], body.split(":")[-1]
        if deleting or (":" in body and not src):
            # A deletion deploys nothing: it stays a push to a shared branch (or the default one), which asks.
            name = dest.removeprefix("refs/heads/")
            reached.append("default" if name in defaults else "shared")
            continue
        if (src and _is_tag(src, cwd)) or dest.startswith("refs/tags/"):
            # A tag lands under refs/tags/ whatever name it is given, never on the agent's branch.
            hit = deploys_to(envs, "tags", (dest if ":" in body else src).removeprefix("refs/tags/").removeprefix("tags/"))
            deployed += hit
            reached += [] if hit else ["shared"]
            continue
        dest = dest.removeprefix("refs/heads/")
        dest = current if dest == "HEAD" else dest
        hit = deploys_to(envs, "branches", dest) if dest else []
        deployed += hit
        if dest in defaults:
            reached.append("default")
        elif not hit:
            reached.append("own" if dest and dest == current else "shared")
    where = next((b for b in ("default", "shared", "own") if b in reached), None)
    return where, list(dict.fromkeys(deployed))


def ref_reach(call: str, cwd: str = ".", environments: list[dict] | None = None) -> tuple[str | None, list[str]]:
    """What a `gh api` call that moves a ref reaches, as `push_reach` says it for a push: the branch (`default` for the
    default branch and for a ref aidd cannot read, else `shared`), and the environments whose branch or tag globs name the
    ref. A ref an environment names reaches that environment instead of `shared`. (None, []) for any other command."""
    target = ref_target(call)
    if target is None:
        return None, []
    kind, name = target
    if kind == "default":
        return "default", []
    hit = deploys_to(environments or [], "tags" if kind == "tag" else "branches", name)
    if kind == "branch" and name in default_names(cwd)[0]:
        return "default", hit
    return (None if hit else "shared"), hit


def _pushed_after_checkout(reached: str | None, envs: list[str], co: Checkout) -> str | None:
    """The branch a push reaches from the branch a checkout earlier on the line names: its own branch is that one, as a
    rule names it, and a push from a branch aidd cannot read reaches the default one."""
    if reached == "own" or (reached is None and not envs):
        return co.branch
    return reached


def push_reads_head(simple: str) -> bool:
    """Whether a `git push` pushes the branch checked out: it names no refspec, or one whose source is `HEAD` or `@`.
    A push that names its branches (`git push origin feat`), or every branch or tag, reads the same on any branch."""
    words = simple.split()
    if words[:2] != ["git", "push"] or {"--all", "--mirror", "--branches", "--tags"} & set(words[2:]):
        return False
    refspecs = [w for w in words[2:] if not w.startswith("-")][1:]
    return not refspecs or any(r.lstrip("+").partition(":")[0] in ("HEAD", "@") for r in refspecs)


def _is_tag(src: str, cwd: str) -> bool:
    """Whether a push's source names a tag: `refs/tags/<name>`, `tags/<name>`, a tag's own name, or a tag object's id."""
    if src.startswith(("refs/tags/", "tags/")):
        return True
    for ref in (f"refs/tags/{src}", f"{src}^{{tag}}"):
        if git.run(["rev-parse", "--verify", "-q", ref], cwd, check=False).strip():
            return True
    return False


# The default branch of each folder, read once in one `command_level` call: each reading of a line asks for it.
_DEFAULTS: contextvars.ContextVar[dict[str, tuple[list[str], bool]] | None] = contextvars.ContextVar("default_branches", default=None)


def default_names(cwd: str) -> tuple[list[str], bool]:
    """The names that read as the default branch, and whether the repository tells which one it is, as the harness
    ask rules read them (`kernel.git.default_branches`). When it cannot tell, every branch that could be the default is
    one, so the reading is the stricter one. ([], False) when git cannot run."""
    memo = _DEFAULTS.get()
    if memo is not None and cwd in memo:
        return memo[cwd]
    try:
        found = git.default_branches(cwd)
    except (git.GitError, OSError, ValueError):
        found = ([], False)
    if memo is not None:
        memo[cwd] = found
    return found


def command_level(rs: RuleSet, line: str, *, branch: str | None = None, role: str | None = None, cwd: str | None = ".") -> dict:
    """What a command line is: each action it matches, with its level and the rule that decided it, and the highest
    level of them all (`allow` when it matches no action). A push to a branch or tag of one of the config's
    `environments` is also `deploy.run` to that environment. It stands in place of `git.push` to a shared branch only
    when a rule names that environment and no locked rule decides `git.push` there, so it is never looser by accident.
    `cwd` is the folder the line runs in, or None when aidd cannot tell, which reads as another repository and asks.
    A `git checkout` or `git switch` earlier on the line adds the branch it names to read beside the session's, for a
    later merge or a push of the branch checked out, and the stricter reading wins (`checkout_after`)."""
    token = _DEFAULTS.set({})
    try:
        with git.shared_reads():  # one answer writes nothing, so each ref read runs once
            return _command_level(rs, line, branch, role, cwd)
    finally:
        _DEFAULTS.reset(token)


def _command_level(rs: RuleSet, line: str, branch: str | None, role: str | None, cwd: str | None) -> dict:
    found: list[dict] = []
    matched: list[tuple[str, str, str, str | None, tuple[Checkout, ...], tuple[bool, ...]]] = []
    here: str | None = cwd
    checkouts: tuple[Checkout, ...] = ()
    moved = (False, False, False)  # an earlier command on the line moved a name, a tracking ref, or an upstream
    for part in split(line):
        here = folder_after(part, here)
        for call in (part, *wrapped(part)):
            # A branch a checkout named in another folder is one aidd cannot read in this one.
            cos = tuple(dict.fromkeys(c if c.folder == here else Checkout(here, "", "default") for c in checkouts))
            words = normalize(without_redirections(call.strip().lstrip("({ ").rstrip(";)} ")), keep_settings=True).split()
            words = words[next((i for i, w in enumerate(words) if not SETTING.fullmatch(w)), len(words)) :]  # settings before git
            git_words = words[1:] if words[:1] == ["git"] else None
            # A `-c` on the call itself can rename what it merges. The same action twice keeps its strictest reading.
            own_config = git_words is not None and git_calls.sets_config(git_words)
            seen = (moved[0] or own_config, moved[1] or own_config, moved[2] or own_config)
            for a, s in call_actions(rs, call):
                same = [i for i, m in enumerate(matched) if m[:2] + m[3:5] == (a, s, here, cos)]
                if not same:
                    matched.append((a, s, call, here, cos, seen))
                else:
                    kept = matched[same[0]][5]
                    matched[same[0]] = matched[same[0]][:5] + (tuple(a or b for a, b in zip(kept, seen, strict=True)),)
            checkouts = checkout_after(call, here, checkouts)
            if git_words is not None:
                step = (git_calls.moves_refs(git_words), git_calls.moves_tracking(git_words), git_calls.changes_upstream(git_words))
                moved = (moved[0] or step[0], moved[1] or step[1], moved[2] or step[2])
    for action, simple, call, folder, cos, moves in matched:
        hit = (action, simple, call, folder, moves)
        reads_head = (action == "git.merge" and is_local_merge(simple)) or (action.startswith("git.push") and push_reads_head(simple))
        readings = [r for co in (None, *(cos if reads_head else ())) if (r := _reading(rs, hit, co, branch, cwd)) is not None]
        # The session's branch and each one a checkout names: the strictest reading wins, the session's on a tie.
        rank = lambda entries: max(LEVEL_RANK[str(e["level"])] for e in entries)  # noqa: E731
        found += max((_entries(rs, action, simple, reading, role) for reading in readings), key=rank, default=[])
    top = max((str(a["level"]) for a in found), key=LEVEL_RANK.__getitem__, default="allow")
    return {"command": line, "level": top, "actions": found}


def _reading(
    rs: RuleSet, hit: tuple[str, str, str, str | None, tuple[bool, ...]], co: Checkout | None, branch: str | None, cwd: str | None
) -> tuple[str | None, list[str]] | None:
    """The branch and the environments an action reaches on one reading: the session's branch (`co` None), or the
    branch a checkout earlier on the line names. `hit` is the action, the simple command, the call as typed, its
    folder, and whether an earlier command can move a ref. None for a merge that lands nothing."""
    action, simple, call, folder, moved = hit
    # A command run in another repository, by `cd` or by git's own options, reads no branch here: it asks.
    elsewhere = folder is None or names_another_repository(call)
    where = branch
    envs: list[str] = []
    current = co.name if co else None
    if action.startswith("git.push") and (branch is None or rs.environments) and elsewhere and simple.split()[:2] == ["git", "push"]:
        where = branch or "default"
    elif action.startswith("git.push") and (branch is None or rs.environments):
        reached, envs = push_reach(simple, str(folder), rs.environments, current=current)
        if reached is None and not envs:
            reached, envs = ref_reach(call, str(folder or cwd or "."), rs.environments)  # a `gh api` call that moves a ref is a push too
        where = branch or (reached if co is None else _pushed_after_checkout(reached, envs, co))
    if action == "git.merge" and is_local_merge(simple):
        lands, merged = merge_reach(simple, str(folder or cwd or "."), elsewhere=elsewhere, current=current, moved=moved)
        if not lands:
            return None  # it ends a merge, or brings in only the branch's own upstream
        where = branch or (merged if co is None or elsewhere else co.branch)
    elif action == "pr.merge":
        where = None  # a PR/MR merges into its base, whatever branch the agent is on
    return where, envs


def _entries(rs: RuleSet, action: str, simple: str, reading: tuple[str | None, list[str]], role: str | None) -> list[dict]:
    """The steps one reading of an action is, its branch and environments, each with its level and the deciding rule."""
    where, envs = reading
    if where is None and envs:
        shared = winning_rule(rs, action, branch="shared", role=role)
        named = all(getattr(winning_rule(rs, "deploy.run", role=role, environment=e), "environment", None) == e for e in envs)
        # Only `git.push` gives way to the environment's own rule; `git.push.force` and the rest read it as shared.
        where = None if action == "git.push" and named and not (shared and shared.locked) else "shared"
    steps: list[tuple[str, str | None, str | None]] = [] if action == "git.push" and envs and where is None else [(action, where, None)]
    steps += [("deploy.run", None, env) for env in envs] if action == "git.push" else []
    out = []
    for step, on, env in steps:
        level, rule = level_of(rs, step, branch=on, role=role, environment=env)
        out.append(
            {
                "action": step,
                "command": simple,
                "branch": on,
                "environment": env,
                "level": level,
                "rule": rule.label() if rule else None,
                "source": rule.source if rule else None,
            }
        )
    return out
