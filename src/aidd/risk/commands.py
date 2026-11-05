"""Which actions a shell command is, from the actions' `commands` patterns, and which branch or environment a `git
push` reaches.

A pattern matches a whole simple command, with `*` for any run of characters (`git push --force*`). A command line is
split at `&&`, `||`, `;`, `|`, and new lines outside quotes, and each part is matched alone, so `make && git push -f`
is `git.push.force`. Git's own options before its subcommand (`git -C repo -c k=v push`), the runner a tool starts
through (`npx prisma`, `bundle exec rails`, RUNNER_FORMS), and settings before the program (`FOO=1 git push`) are set
aside first. The part is matched again with its settings kept, so `RAILS_ENV=production rails db:*` can match.

This is advice, never a control: an alias, a script, or a variable gets past any pattern. SECURITY.md says so.
"""

from __future__ import annotations

import re
import shlex

from aidd.kernel import git, globs
from aidd.risk.rules import LEVEL_RANK, RuleSet, level_of, winning_rule

# Git's options that take a value before the subcommand, and those that take none.
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--attr-source"}
_GIT_FLAG_OPTIONS = {"--no-pager", "-p", "--paginate", "--bare", "--no-replace-objects", "--literal-pathspecs", "--no-optional-locks", "-P"}


def split(line: str) -> list[str]:
    """The simple commands of a command line, split at `&&`, `||`, `;`, `|`, and new lines outside quotes."""
    parts, buf, quote, i = [], [], "", 0
    while i < len(line):
        c = line[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"' and i + 1 < len(line):
                buf.append(line[i + 1])
                i += 1
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c == "\\" and i + 1 < len(line):
            buf.append(line[i : i + 2])
            i += 1
        elif line.startswith(("&&", "||"), i):
            parts.append("".join(buf))
            buf = []
            i += 1
        elif c in ";|\n":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


# The usual ways to start a tool, each read as the tool's own command: `npx prisma migrate reset` is `prisma migrate
# reset`. A pattern names the tool's form, and each harness's ask rules get every form here (harness_rules).
_NODE = ("npx", "pnpm", "pnpm exec", "pnpm dlx", "bunx", "yarn")
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
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
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


def _pattern(p: str) -> re.Pattern[str]:
    return re.compile("".join(".*" if ch == "*" else re.escape(ch) for ch in " ".join(p.split())) + r"\Z", re.S)


def matching_actions(rs: RuleSet, line: str) -> list[tuple[str, str]]:
    """Each (action, simple command) the command line matches, in the order of the line."""
    out: list[tuple[str, str]] = []
    for part in split(line):
        simple = normalize(part)
        typed = normalize(part, keep_settings=True)  # so a pattern can name a setting (`RAILS_ENV=production rails db:*`)
        for action, spec in rs.actions.items():
            if any(_pattern(p).match(simple) or _pattern(p).match(typed) for p in spec.get("commands", [])):
                out.append((action, simple))
    return out


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


def push_reach(simple: str, cwd: str = ".", environments: list[dict] | None = None) -> tuple[str | None, list[str]]:
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
    default = _default_branch(cwd)
    current = git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()
    refspecs = args[1:] if len(args) > 1 else []
    if not refspecs:
        if not current:
            return None, list(dict.fromkeys(deployed))
        hit = deploys_to(envs, "branches", current)
        where = "default" if current == default else None if hit else "own"
        return where, list(dict.fromkeys(deployed + hit))
    reached = []
    deleting = bool({"--delete", "-d"} & options)
    for spec in refspecs:
        body = spec.lstrip("+")
        src, dest = body.partition(":")[0], body.split(":")[-1]
        if deleting or (":" in body and not src):
            # A deletion deploys nothing: it stays a push to a shared branch (or the default one), which asks.
            name = dest.removeprefix("refs/heads/")
            reached.append("default" if default and name == default else "shared")
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
        if default and dest == default:
            reached.append("default")
        elif not hit:
            reached.append("own" if dest and dest == current else "shared")
    where = next((b for b in ("default", "shared", "own") if b in reached), None)
    return where, list(dict.fromkeys(deployed))


def _is_tag(src: str, cwd: str) -> bool:
    """Whether a push's source names a tag: `refs/tags/<name>`, `tags/<name>`, a tag's own name, or a tag object's id."""
    if src.startswith(("refs/tags/", "tags/")):
        return True
    for ref in (f"refs/tags/{src}", f"{src}^{{tag}}"):
        if git.run(["rev-parse", "--verify", "-q", ref], cwd, check=False).strip():
            return True
    return False


def _default_branch(cwd: str) -> str | None:
    """The repository's default branch by name (`main`), or None when git cannot tell."""
    try:
        return git.default_base(cwd).split("/", 1)[-1]
    except (git.GitError, OSError, ValueError):
        return None


def command_level(rs: RuleSet, line: str, *, branch: str | None = None, role: str | None = None, cwd: str = ".") -> dict:
    """What a command line is: each action it matches, with its level and the rule that decided it, and the highest
    level of them all (`allow` when it matches no action). A push to a branch or tag of one of the config's
    `environments` is also `deploy.run` to that environment. It stands in place of `git.push` to a shared branch only
    when a rule names that environment and no locked rule decides `git.push` there, so it is never looser by accident."""
    found: list[dict] = []
    for action, simple in matching_actions(rs, line):
        where = branch
        envs: list[str] = []
        if action.startswith("git.push") and (branch is None or rs.environments):
            reached, envs = push_reach(simple, cwd, rs.environments)
            where = branch or reached
        if where is None and envs:
            shared = winning_rule(rs, action, branch="shared", role=role)
            named = all(getattr(winning_rule(rs, "deploy.run", role=role, environment=e), "environment", None) == e for e in envs)
            # Only `git.push` gives way to the environment's own rule; `git.push.force` and the rest read it as shared.
            where = None if action == "git.push" and named and not (shared and shared.locked) else "shared"
        steps: list[tuple[str, str | None, str | None]] = [] if action == "git.push" and envs and where is None else [(action, where, None)]
        steps += [("deploy.run", None, env) for env in envs] if action == "git.push" else []
        for step, on, env in steps:
            level, rule = level_of(rs, step, branch=on, role=role, environment=env)
            found.append(
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
    top = max((str(a["level"]) for a in found), key=LEVEL_RANK.__getitem__, default="allow")
    return {"command": line, "level": top, "actions": found}
