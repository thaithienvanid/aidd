"""The commands that take work off this machine, which is a person's step (METHOD.md, "Three rings"): a push, a pull or
merge request, a release, a package. Agents publish only where the config lets them (`publish: agents`), where the
person typed `publish` for the head, or under their `approve all and publish`; a release or a package is never theirs.
"""

from __future__ import annotations

import os
import re
import shlex
import urllib.parse
from pathlib import Path

from aidd import workitems
from aidd.guard import git_commands, repo_config, shell_parser
from aidd.kernel import git

GH_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject", "--author-email", "-H", "--header", "-X", "--method"}

# Text that takes work off this machine, read when the shell check cannot parse a command: it fails closed.
RAW_PUBLISH = re.compile(
    r"\bgit\b[^\n;&|]*\b(?:push|send-pack|http-push|send-email|dcommit)\b|\bgh\b[^\n;&|]*\bpr\s+create\b|\bglab\b[^\n;&|]*\bmr\s+create\b", re.I
)
API_VALUE_FLAGS = {
    "-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq", "-t", "--template",
    "--hostname", "-p", "--preview", "--cache",
}  # fmt: skip
# A platform's API calls that write a branch, a file on one, or a pull or merge request: a push or a PR/MR by another way.
_API_PUBLISH = re.compile(r"/pulls/?$|/merge_requests/?$|/git/refs\b|/contents/|/repository/(?:branches|commits|files)\b")
_GRAPHQL_PUBLISH = re.compile(r"\b(?:createPullRequest|createRef|updateRefs?|createCommitOnBranch|mergeRequestCreate|commitCreate)\b")
# git commands that write another repository, or mail the work out, with no `push` in their words; and the ones that do
# it with a word after the command (`git svn dcommit`).
_SENDS = frozenset({"send-pack", "http-push", "send-email"})
_SENDS_WITH = {"svn": ("dcommit", "commit-diff"), "p4": ("submit",), "subtree": ("push",), "lfs": ("push",)}
# A wrapper's option that runs the command in another folder (`env -C`, `sudo -D`).
_CHDIR = frozenset({"-C", "--chdir", "-D"})
UNREAD_ALIAS = (
    "this command is an alias or a git command the guard cannot read before it runs (a shell alias, `-c alias.<name>=...`, "
    "or one run in another folder), and it may take work off this machine: run the command it stands for instead"
)


PUBLISH_HELD = (
    "only a person takes work off this machine here (`publish: person`, the default): no agent pushes or opens a pull or "
    "merge request on its own. Keep the work on its branch, and ask the person: when they type `publish`, run `aidd "
    "publish`, which pushes this head and opens its PR/MR. For a team that works in pull requests, a person sets `publish: "
    "agents` in .aidd/config.yaml"
)
RELEASE_HELD = (
    "a release or a package goes out to its users, which is a person's step: they run it at their own terminal, once the "
    "work is merged. Agents never cut a release or publish a package"
)
# Package managers and registries: (program, the words that publish) as the program's first positional words.
_PACKAGE_PUBLISH = {
    "npm": (["publish"],),
    "pnpm": (["publish"],),
    "bun": (["publish"],),
    "yarn": (["publish"], ["npm", "publish"]),
    "cargo": (["publish"],),
    "twine": (["upload"],),
    "uv": (["publish"],),
    "poetry": (["publish"],),
    "hatch": (["publish"],),
    "flit": (["publish"],),
    "gem": (["push"],),
    "docker": (["push"], ["image", "push"], ["buildx", "imagetools", "create"]),
    "podman": (["push"],),
}


# A push's own options that change nothing about where it goes or what it writes; any other option (a force, a
# delete, a mirror, every branch or tag, a receive-pack program, a push option) needs the person.
_PLAIN_PUSH_OPTIONS = frozenset({"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose", "--progress", "--no-progress", "--porcelain"})


def _rewrites_where_git_goes(raw: list[str], argv: list[str], sub: int, root: str) -> bool:
    """Whether git may send this push somewhere other than its words say: a `GIT_`, `HOME`, or `XDG_CONFIG_HOME` value on the command,
    any git option before `push` (`-c url.<x>.insteadOf=...`, `--config-env`, `-C`), or URL rewriting in the
    repository's config, which an earlier command could have set. Each fails closed."""
    prefix = raw[: len(raw) - len(argv)] if raw[-len(argv) :] == argv else raw
    if any(w.split("=", 1)[0].startswith("GIT_") or w.split("=", 1)[0] in ("HOME", "XDG_CONFIG_HOME") for w in prefix if "=" in w) or sub != 1:
        return True
    rewrites = git.run(["config", "--get-regexp", r"^url\..*\.(push)?insteadof$"], root, check=False).strip()
    return bool(rewrites)


def _destinations(words: list[str], root: str) -> tuple[str, list[str]]:
    """(the push's target as written, or the remote a plain push picks, and every URL it pushes to), as git resolves
    a configured remote's push URLs; a target that is no remote is itself the URL or path."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()
    target = words[0] if words else git.push_remote(root, branch)
    if target in git.run(["remote"], root, check=False).split():
        return target, [u for u in git.run(["remote", "get-url", "--push", "--all", target], root, check=False).splitlines() if u]
    return target, [target]


def _on_this_machine(url: str) -> bool:
    """A path or a `file://` URL; not a network URL (`scheme://`) or an scp-like `host:path`."""
    return url.startswith("file://") or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://|^[^/\\]+:", url)


def _push_words(args: list[str]) -> list[str]:
    return shell_parser.positional_words(args[1:], {"-o", "--push-option", "--repo", "--receive-pack", "--exec"})


def _stays_on_this_machine(raw: list[str], argv: list[str], sub: int, root: str) -> bool:
    """Whether a `git push` goes only to repositories on this machine, so it is no publish (the guard's other rules still
    read it). Anything that may rewrite where git goes fails closed (_rewrites_where_git_goes)."""
    if _rewrites_where_git_goes(raw, argv, sub, root):
        return False
    words = _push_words(argv[sub:])
    if not words and not git.run(["remote"], root, check=False).split():
        return True  # nowhere to push to: git refuses it on this machine
    _target, urls = _destinations(words, root)
    return bool(urls) and all(_on_this_machine(u) for u in urls)


def _within_the_grant(raw: list[str], argv: list[str], sub: int, root: str, grant: dict) -> bool:
    """Whether a `git push` stays inside what the person let the agent publish (workitems.publish_grant): the branch they
    named, to the remote they named, by a plain push that fast-forwards it (no force, delete, mirror, every branch or
    tag, or other option), with nothing that may rewrite where git goes or what it sends."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()
    if branch != grant["branch"] or _rewrites_where_git_goes(raw, argv, sub, root):
        return False
    if git.run(["config", "--get", "core.sshCommand"], root, check=False).strip():
        return False  # the command git runs for an ssh URL may connect anywhere: it fails closed, as a URL rewrite does
    rest = argv[sub + 1 :]
    if any(a.startswith("-") and a not in _PLAIN_PUSH_OPTIONS for a in rest):
        return False
    words = _push_words(argv[sub:])
    target, urls = _destinations(words, root)
    allowed = {branch, "HEAD", f"HEAD:{branch}", f"{branch}:{branch}", f"refs/heads/{branch}", f"HEAD:refs/heads/{branch}"}
    return (
        target == grant["remote"]
        and sorted(urls) == grant["urls"]
        and all(r in allowed for r in words[1:])
        and _sends_only_the_branch(root, target, refspecs=bool(words[1:]))
    )


def _sends_only_the_branch(root: str, remote: str, *, refspecs: bool) -> bool:
    """Whether git's config leaves a push to `remote` sending the branch alone: no stored push refspec or mirror for
    the remote (each maps or widens what goes), and, with no refspec in the command, a `push.default` that sends only
    the current branch under its own name (`simple`, git's default, or `current`; never `matching` or `upstream`), with
    no tags and no submodules pushed along."""
    stored = git.run(["config", "--get-all", f"remote.{remote}.push"], root, check=False).strip()
    mirror = git.run(["config", "--type=bool", "--get", f"remote.{remote}.mirror"], root, check=False).strip()
    default = git.run(["config", "--get", "push.default"], root, check=False).strip().lower()
    tags = git.run(["config", "--type=bool", "--get", "push.followTags"], root, check=False).strip()
    submodules = git.run(["config", "--get", "push.recurseSubmodules"], root, check=False).strip().lower()
    return (
        not stored
        and mirror != "true"
        and tags != "true"  # annotated tags go too: a release is the person's
        and submodules not in ("on-demand", "only")  # each submodule's commits go to its own remote
        and (refspecs or default in ("", "simple", "current"))
    )


_BUILTINS: dict[str, frozenset[str]] = {}


def _git_builtins(root: str) -> frozenset[str]:
    """git's own commands (`git --list-cmds=main`), asked once per folder in a run: a line of many git commands asks
    once, not once for each. An empty answer is never kept."""
    if root not in _BUILTINS:
        found = frozenset(git.run(["--list-cmds=main"], root, check=False).split())
        if not found:
            return found
        _BUILTINS[root] = found
    return _BUILTINS[root]


def as_git_runs(argv: list[str], sub: int, root: str, *, elsewhere: bool = False) -> tuple[list[str], int] | None:
    """`argv` as git runs it: a stored alias read to the git command it stands for (`alias.p = push`), through a few
    aliases at most. None when the guard cannot read what runs: a one-off alias (`-c alias.p=push`), a shell alias
    (`!...`), an alias that puts options before its command, or a command that is not git's own where git may read
    another repository's aliases (an option before the command, a `GIT_` value, or a `cd` before it: `elsewhere`)."""
    if git_commands.one_off_alias(argv[1:sub]):
        return None
    builtins = _git_builtins(root)
    if argv[sub] in builtins:
        return argv, sub  # git runs its own command: an alias never hides one
    if elsewhere or sub != 1:
        return None
    for _ in range(5):
        expansion = git.run(["config", "--get", f"alias.{argv[sub]}"], root, check=False).strip()
        if not expansion:
            return argv, sub  # an outside `git-<name>` program, or no command at all
        try:
            words = shlex.split(expansion)
        except ValueError:
            return None
        if expansion.startswith("!") or not words or words[0].startswith("-"):
            return None
        argv = argv[:sub] + words + argv[sub + 1 :]
        if argv[sub] in builtins:
            return argv, sub
    return None


# Each CLI's own top-level commands, which an alias never shadows: the alias file is read only for another word.
_PLATFORM_COMMANDS = {
    "gh": frozenset(
        "agent-task alias api attestation auth browse cache codespace completion config copilot extension gist gpg-key help "
        "issue label org pr preview project release repo ruleset run search secret ssh-key status variable version workflow".split()
    ),
    "glab": frozenset(
        "alias api auth changelog check-update ci cluster completion config deploy-key duo help incident issue iteration job "
        "label mr opentofu release repo schedule securefile snippet ssh-key stack token user variable version".split()
    ),
}


def _platform_alias(name: str, word: str, before: list[str], *, elsewhere: bool = False) -> str | None:
    """What `gh <word>` or `glab <word>` stands for when the person stored an alias for it (`gh alias set`), read from
    the CLI's own file; "!" when the guard cannot read it (a shell alias, or a config folder the command sets). `before`
    is what the command line holds before the program: its environment values. Where the line changes what the CLI
    reads first (`elsewhere`), a word that is not the CLI's own command is unread."""
    if word in _PLATFORM_COMMANDS[name]:
        return None
    if elsewhere:
        return "!"
    prefix = [w.split("=", 1) for w in before if "=" in w and not w.startswith("-")]
    env = {**os.environ, **{k: v for k, v in prefix if k.isupper()}}
    if any(k in ("GH_CONFIG_DIR", "GLAB_CONFIG_DIR", "XDG_CONFIG_HOME", "HOME") for k, _ in prefix):
        return "!"
    home = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if name == "gh":
        path, inside = Path(env.get("GH_CONFIG_DIR") or home / "gh") / "config.yml", True
    else:
        path, inside = Path(env.get("GLAB_CONFIG_DIR") or home / "glab-cli") / "aliases.yml", False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if inside:
        if re.search(r"^aliases:[ \t]*[^\s#]", text, re.M):
            return "!"  # a flow mapping (`aliases: {...}`): more YAML than this reader reads
        found = re.search(r"^aliases:[ \t]*\n((?:[ \t]+.*\n?)*)", text, re.M)
        text = found.group(1) if found else ""
    for line in text.splitlines():
        key, colon, value = line.strip().partition(":")
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not colon or value.strip()[:1] in ("|", ">", "{", "[", "&", "*"):
            return "!"  # a block, a flow value, an anchor: the guard reads one plain `name: command` per line only
        if key.strip("'\"") == word and value.strip():
            return value.strip().strip("'\"")
    return None


def api_write(args: list[str], endpoint: re.Pattern, graphql: re.Pattern) -> bool:
    """`gh api` or `glab api` with an endpoint `endpoint` names, called with a writing method; for GraphQL, a mutation
    `graphql` names."""
    words = shell_parser.positional_words(args, API_VALUE_FLAGS)
    target = urllib.parse.urlsplit(words[0]).path if words else ""  # `/repos/o/r/pulls?x=1` is still the pulls endpoint
    method = (shell_parser.flag_value(args, "-X", "--method") or "").upper()
    has_fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
    if target.strip("/") == "graphql":
        return bool(graphql.search(" ".join(args)))
    return bool(endpoint.search(target)) and (method in ("POST", "PUT", "PATCH") or (not method and has_fields))


def _query_unread(args: list[str]) -> bool:
    """Whether a GraphQL call's query comes from a file or stdin (`-F query=@q.graphql`, `--input`), out of the guard's
    sight."""
    return any(a in ("--input", "-") or a.startswith("--input=") or "=@" in a or a.startswith("@") for a in args)


def _as_platform_runs(name: str, argv: list[str], words: list[str], raw: list[str], elsewhere: bool) -> tuple[list[str], list[str]] | None:
    """`gh` or `glab` as it runs, with a stored alias read to what it stands for: (argv, its positional words), or None
    when the guard cannot read it (_platform_alias)."""
    before = raw[: len(raw) - len(argv)] if raw[-len(argv) :] == argv else raw
    alias = _platform_alias(name, words[0], before, elsewhere=elsewhere) if words else None
    if not alias:
        return argv, words
    try:
        stands_for = shlex.split(alias) if not alias.startswith("!") else []
    except ValueError:
        stands_for = []
    if not stands_for:
        return None
    argv = [argv[0], *stands_for, *argv[argv.index(words[0]) + 1 :]]
    return argv, shell_parser.positional_words(argv[1:], GH_VALUE_FLAGS)


def _sends(name: str, argv: list[str], words: list[str], sub: int | None) -> bool:
    """Whether a command other than `git push` writes another repository or opens a PR/MR: `gh pr create`, `glab mr
    create`, `gh repo create --push`, a platform API call that does (_API_PUBLISH; a GraphQL query it cannot read
    counts), or a git command that sends work out (_SENDS)."""
    if name in ("gh", "glab"):
        if words[:2] in (["pr", "create"], ["mr", "create"]):
            return True
        if words[:2] == ["repo", "create"] and any(a == "--push" or a.startswith("--push=") for a in argv):
            return True
        if words[:1] != ["api"]:
            return False
        args = argv[argv.index("api") + 1 :]
        target = shell_parser.positional_words(args, API_VALUE_FLAGS)[:1]
        return api_write(args, _API_PUBLISH, _GRAPHQL_PUBLISH) or (target[:1] != [] and target[0].strip("/") == "graphql" and _query_unread(args))
    if sub is None:
        return False
    after = shell_parser.positional_words(argv[sub + 1 :], set())[:1]
    return argv[sub] in _SENDS or (argv[sub] in _SENDS_WITH and after[:1] != [] and after[0] in _SENDS_WITH[argv[sub]])


def leaves_this_machine(name: str, argv: list[str], root: str, raw: list[str] | None = None, *, elsewhere: bool = False) -> str | None:
    """Why a command takes work off this machine, which is a person's step, or None. A release or a package publish is
    always the person's. A `git push`, `gh pr create`, or `glab mr create` is theirs too, unless the config lets agents
    publish (`publish: agents`), or the push stays inside what the person let the agent publish
    (workitems.publish_grant: their `publish`, or `approve all and publish`), where a pull or merge request opens only
    through `aidd publish`. `raw` is the command's words as written, environment values included. `elsewhere`: the
    command line changes folder, a config folder, or git's config or remotes before this command runs
    (approval_commands.runs_elsewhere), so what the guard reads now is not what the command meets."""
    from aidd import gate

    raw = raw if raw is not None else argv
    words = shell_parser.positional_words(argv[1:], GH_VALUE_FLAGS) if name in ("gh", "glab") else shell_parser.positional_words(argv[1:], set())
    if name in ("gh", "glab"):  # an alias first, so `gh rc` for `release create` is a release too
        if (read := _as_platform_runs(name, argv, words, raw, elsewhere)) is None:
            return None if gate.agents_publish(root) else PUBLISH_HELD
        argv, words = read
    if (name in ("gh", "glab") and words[:2] == ["release", "create"]) or any(words[: len(w)] == w for w in _PACKAGE_PUBLISH.get(name, ())):
        return RELEASE_HELD
    sub = git_commands.sub_index(argv) if name == "git" else None
    if sub is not None:
        before = raw[: len(raw) - len(argv)]
        moved = elsewhere or any(
            w.split("=", 1)[0].startswith("GIT_") or w.split("=", 1)[0] in ("HOME", "XDG_CONFIG_HOME") or w in _CHDIR or w.startswith("--chdir=")
            for w in before
        )
        if (ran := as_git_runs(argv, sub, root, elsewhere=moved)) is None:
            return None if gate.agents_publish(root) else UNREAD_ALIAS
        argv, sub = ran
    pushes = sub is not None and argv[sub] == "push"
    if not (pushes or _sends(name, argv, words, sub)) or gate.agents_publish(root):
        return None
    if elsewhere or any(w in _CHDIR or w.startswith("--chdir=") for w in raw[: len(raw) - len(argv)]):
        return PUBLISH_HELD  # the remote, its URLs, and the branch may be another repository's, or changed on this line
    if pushes and sub is not None and _stays_on_this_machine(raw, argv, sub, root):
        return None
    head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()
    grant = workitems.publish_grant(repo_config.load_config(root), root, head, branch) if head else None
    # Under a person's grant the pull request opens through `aidd publish`, which names the repository itself: `gh` and
    # `glab` pick theirs from the remotes and the environment.
    if grant and pushes and sub is not None and _within_the_grant(raw, argv, sub, root, grant):
        return None
    return PUBLISH_HELD
