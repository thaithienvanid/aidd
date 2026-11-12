"""The two checks of git's settings that a `git push` gets, and both only raise a level.

`push_reach` (commands.py) reads a push from its words. These checks ask whether a setting may send the push somewhere else than
its words say.

- The config check (`redirects`) asks git, with one `git config` call, for three facts, and nothing else: for the remote the push
  resolves to (every remote when it cannot tell), `remote.<name>.push` is set, or `remote.<name>.mirror` is true; and
  `push.default` is `upstream`, `tracking`, or `matching`. git parses a boolean, so `mirror` is read from git's own answer.
  `remote.<name>.push` counts only for a push with a refspec that names no destination, or with none (`_names_destinations`).
- The command check (`steering_keys`) looks at the `-c` and `--config-env` options of the same git command, in the words the
  matcher read, and reads no value: a key that starts with `remote.`, `push.`, or `branch.` may steer the push.

If either finds something, the push reads as one that may reach the default branch, with a note. Every other setting, an
included config file, the environment, and an option that acts on the server go unread (SECURITY.md, "Where a push goes").
"""

from __future__ import annotations

from aidd.kernel import git, git_calls
from aidd.risk.shell import SETTING

_SETTINGS = r"^(push\.default|remote\.pushdefault|remote\..+\.(push|mirror)|branch\..+\.(remote|pushremote))$"
_MIRRORS = r"^remote\..+\.mirror$"
# `push.default` values that send a push to a branch other than the one checked out, or to every branch.
REDIRECTING_DEFAULTS = ("upstream", "tracking", "matching")
# The push options that take the next word, which then may be the remote.
VALUE_OPTIONS = frozenset({"-o", "--push-option", "--repo", "--receive-pack", "--exec"})
# The keys of a `-c` or `--config-env` that may steer a push, by prefix.
STEERING_PREFIXES = ("remote.", "push.", "branch.", "include.", "includeif.")  # an included file may set any of the first three
UNREADABLE = "a git command whose words could not be read"
SEE_SETTINGS = "git config --get-regexp '^(push\\.default|remote\\..*\\.(push|mirror))$'"


def _read(cwd: str) -> dict[str, str | None]:
    """The settings above, as git lists them (the section and the variable in lower case); None for a key with no value, which
    git reads as true. A later file's value wins, and `remote.<name>.push` keeps every value, so only its presence is read."""
    out: dict[str, str | None] = {}
    for entry in git.run(["config", "-z", "--get-regexp", _SETTINGS], cwd, check=False).split("\0"):
        key, sep, value = entry.partition("\n")
        if key:
            out[key] = value if sep else None
    return out


def _mirrors(settings: dict[str, str | None], cwd: str) -> set[str]:
    """The remotes whose `mirror` is true, as git reads a boolean (`--type=bool`): `yes`, `on`, `1`, a key with no value. A value git
    cannot read as a boolean counts as true, and a key set twice has its last value, as in git. Asked only when a `mirror` is set."""
    keys = {k for k in settings if k.endswith(".mirror")}
    if not keys:
        return set()
    asked = git.run(["config", "--type=bool", "-z", "--get-regexp", _MIRRORS], cwd, check=False).split("\0")
    last = {e.partition("\n")[0]: e.partition("\n")[2] for e in asked if e}  # git uses the last value a key has
    return {k[len("remote.") : -len(".mirror")] for k in keys if last.get(k) != "false"}


def _names_destinations(refspecs: list[str]) -> bool:
    """Whether the push names every destination itself: it has refspecs, and each is `<src>:<dst>` with a `<dst>`. git ranks the
    refspecs of the command line above `remote.<name>.push` ("git push", DESCRIPTION, the order of precedence), and that setting
    changes a destination only for a `<src>` without a `:<dst>`, so it does not remap a push that names them all. The other two
    facts count as they did, with or without a refspec, because the boundary of this check is written once, in SECURITY.md ("Where
    a push goes"): `--mirror` is the default of a remote whose `mirror` is set, and `push.default` is documented for a push with
    no refspec. This check only raises, so keeping them costs a question, never a push."""
    return bool(refspecs) and all(r.partition(":")[2] for r in refspecs)


def steering_keys(words: list[str]) -> list[str]:
    """The `-c` and `--config-env` keys of a git command that may steer a push, from the words the matcher read for it
    (`normalize` with the settings kept): the words after any settings must start with `git`. A key counts by its prefix, in lower
    case as git compares the section and the variable, and no value is read. [] when there is none; the command's words when it
    names no git program at all, which reads as steered."""
    words = words[next((i for i, w in enumerate(words) if not SETTING.fullmatch(w)), len(words)) :]
    if not words or words[0].rsplit("/", 1)[-1] != "git":
        return [UNREADABLE]
    options = words[1:]
    keys, i = [], 0
    while i < git_calls.subcommand(options)[0]:
        name, eq, rest = options[i].partition("=")
        if name == "-c" and not eq and i + 1 < len(options):
            i += 1
            keys.append(options[i].partition("=")[0].lower())
        elif name == "--config-env":
            if not eq and i + 1 < len(options):
                i, rest = i + 1, options[i + 1]
            keys.append(rest.partition("=")[0].lower())
        i += 1
    return [k for k in keys if k.startswith(STEERING_PREFIXES)]


def redirects(words: list[str], cwd: str) -> list[str]:
    """The settings that may send the push `words` (those after `git push`) somewhere else than its words say: [] when none
    does. Raise-only: a push it names reads as one that may reach the default branch."""
    settings = _read(cwd)
    positional = [w for w in words if not w.startswith("-")]
    valued = bool(VALUE_OPTIONS & {w.partition("=")[0] for w in words})  # an option's value, or `--repo=<remote>`, may be the remote
    current = "" if positional or valued else git.current_branch(cwd)
    resolved = current and (
        settings.get(f"branch.{current}.pushremote") or settings.get("remote.pushdefault") or settings.get(f"branch.{current}.remote") or "origin"
    )
    every = sorted({k[len("remote.") : k.rindex(".")] for k in settings if k.startswith("remote.") and k.count(".") >= 2 and k != "remote.pushdefault"})
    remotes = (positional if valued else positional[:1]) if positional else ([resolved] if resolved else every)
    mirrors = _mirrors(settings, cwd)
    named = not valued and _names_destinations(positional[1:])  # with an option that takes a value, no word is known to be a refspec
    found = []
    for remote in remotes:
        if f"remote.{remote}.push" in settings and not named:
            found.append(f"remote.{remote}.push")
        if remote in mirrors:
            found.append(f"remote.{remote}.mirror")
    if settings.get("push.default") in REDIRECTING_DEFAULTS:
        found.append(f"push.default={settings['push.default']}")
    return found


def note(found: list[str]) -> str:
    """The note for a push that a setting, or a `-c` or `--config-env` key, may send elsewhere."""
    return f"{', '.join(dict.fromkeys(found))} may send this push to another branch, so it reads as one that may reach the default branch; see the settings with `{SEE_SETTINGS}`"
