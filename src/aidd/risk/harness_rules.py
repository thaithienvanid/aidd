"""The harness ask rules: each `ask` risk rule's command patterns written as a coding agent's own permission prompt, so
the agent's harness asks the person even when the agent forgets to.

Each format follows its harness's own documentation (read 2026-11-03). A pattern is a glob over one simple command
(`git push --force*`, `git push * main`); each format holds it as its harness matches commands:

- By glob, as written: Claude Code (`permissions.ask`, `Bash(<pattern>)`, `.claude/settings.json`), OpenCode v2
  (`permissions`, `{"action": "shell", "resource": "<pattern>", "effect": "ask"}`, `opencode.json`, as `opencode_rules`
  says), and Grok Build (`[permission] ask`, `Bash(<pattern>)`, `.grok/config.toml`, in a block aidd marks).
- By regular expression, exactly: VS Code's Copilot agent (`chat.tools.terminal.autoApprove`, `"/<regex>/": false`,
  `.vscode/settings.json`).
- By leading words, with no wildcard: Codex (`prefix_rule`, `.codex/rules/aidd.rules`) and Qwen Code
  (`permissions.ask`, `Bash(<prefix> *)`, `.qwen/settings.json`). A trailing `*`
  drops, a `*` between words becomes the common remotes, `origin` and `upstream` (a list where the format has one,
  else one rule each),
  and `*:main` becomes `HEAD:main`. A pattern with no such form asks at its leading words when a tool's own words
  there number three or more (`gh workflow run *release*` asks before every `gh workflow run`), so these formats ask
  more, never less; `widened` names those. Any other (`git push * +*`) is left to the skill, and `unwritten` names it
  for `aidd doctor`.

A rule narrowed by an area or a role has no command form, so only the rules an action has on its own count, and a
`git.push` rule on the `default` branch becomes patterns that name that branch, as a `deploy.run` rule for one of the
config's `environments` becomes patterns that name its branches and tags. aidd changes only what it wrote: the
entries it wrote are listed in `.aidd/harness-rules.json`. A person's own entries stay as they are, and aidd never
puts an ask where it would undo their deny.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from aidd import config
from aidd.kernel import documents, globs
from aidd.kernel import text as kernel_text
from aidd.risk import opencode_rules
from aidd.risk.commands import RUNNER_FORMS, is_local_merge, normalize
from aidd.risk.gh_api import BODY_FLAGS
from aidd.risk.rules import LEVEL_RANK, RuleSet, level_of
from aidd.risk.shell import split, wrapped


@dataclasses.dataclass(frozen=True)
class Format:
    path: str  # the file, relative to the repository's top
    match: str  # glob, regex, or words: how the harness matches a command
    shape: str  # what aidd writes there, for the docs
    # Whether its ask rules hold one for the harness's own file-read tool, `Read(<path glob>)`, beside the commands.
    reads: bool = False


FORMATS: dict[str, Format] = {
    "claude-code": Format(".claude/settings.json", "glob", "`permissions.ask`: `Bash(git push --force*)` and `Read(**/.env)`", reads=True),
    "codex": Format(".codex/rules/aidd.rules", "words", '`prefix_rule(pattern = ["git", "push", ["origin", "upstream"], "main"], decision = "prompt")`'),
    "vscode": Format(".vscode/settings.json", "regex", 'in VS Code\'s agent, `chat.tools.terminal.autoApprove`: `{"/^git push --force.*$/": false}`'),
    "opencode": Format("opencode.json", "glob", '`permissions`: `{"action": "shell", "resource": "git push --force*", "effect": "ask"}`'),
    "qwen": Format(".qwen/settings.json", "words", "`permissions.ask`: `Bash(git push --force)`, `Bash(git push --force *)`, and `Read(**/.env)`", reads=True),
    "grok": Format(".grok/config.toml", "glob", '`[permission] ask = ["Bash(git push --force*)", "Read(**/.env)"]`, in a block aidd marks', reads=True),
}
MATCHES = {"glob": "by glob, as written", "regex": "by regular expression, exactly", "words": "by leading words, with no wildcard"}
# The formats whose leading-words rules take a list of alternatives at one position; the others get one rule per remote.
ALTERNATIVES = frozenset({"codex"})
# The remotes a `*` between words stands for, beside the repository's own.
COMMON_REMOTES = ("origin", "upstream")
_PLAIN = re.compile(r"[^*]+")
_WORD = re.compile(r"[-\w.:]*\w")  # a whole word, such as `--force` or `migrate:fresh`, so a trailing `*` may drop
_SETTING = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")  # a setting before the program, such as `RAILS_ENV=production`
# The fewest of a tool's own words a leading-words format asks at in place of a pattern it cannot hold (`leading_words`).
MIN_LEADING_WORDS = 3
_TOML_BEGIN = "# >>> aidd: the ask rules aidd writes from the risk rules. `aidd upgrade` rewrites this block."
_TOML_END = "# <<< aidd"


def api_harness_names() -> str:
    """The harnesses whose ask rules hold the `gh api` set, as a phrase: every format that matches by glob or by regular
    expression, in the order of FORMATS. A leading-words format (Codex, Qwen Code) cannot hold it."""
    names = [h.label for fmt, f in FORMATS.items() if f.match != "words" for h in config.HARNESSES.values() if h.ask_rules == fmt]
    return kernel_text.series(names, "and")


def api_write_note() -> str:
    """Said when a harness asks for a `gh api` call that `aidd risk` reads, exactly, as a lower level."""
    return (
        f"{api_harness_names()} ask before any `gh api` call that may write: an explicit method, a field, an input, or "
        "GraphQL. They ask here, though `aidd risk` reads this call exactly and its level is lower."
    )


def api_write_patterns() -> list[str]:
    """The patterns that ask before any `gh api` call that may write, one set for every endpoint, the explicit methods first
    and then the fields and inputs. A harness matches command
    text, so the set names what the text shows: an explicit method (`-X`, `-iX`, which is the only run of short flags that
    can come before `X`, or `--method`), a field or an input (`-f`, `-F`, and the same after `-i`), and GraphQL, whose
    mutation the text cannot tell from a query. A flag opens after a space, so a repository named `my-fork` is no `-f`, and
    a header such as `-H "X-GitHub-Api-Version: ..."` is no method. `aidd risk --command` reads the same call exactly, so a
    harness asks for more, never less."""
    out = ["gh api* -X*", "gh api* -iX*", "gh api*--method*"]
    out += [f"gh api* {flag}*" for flag in (*BODY_FLAGS, "-iF", "-if")]
    return out + ["gh api* graphql*", "gh api*/graphql*"]


def api_write_words() -> list[str | list[str]]:
    """The leading words a leading-words format (Codex, Qwen Code) asks at for a `gh api` write: `gh api`, then an
    explicit method, a field or an input, or `graphql`. Those formats match from the start of the command, so they ask
    only when that flag comes first, before the endpoint; the skill and `aidd risk` hold the rest."""
    return ["gh", "api", ["-X", "--method", *BODY_FLAGS, "graphql"]]


def harness_patterns(rs: RuleSet, default_branch: str | Sequence[str] | None) -> list[str]:
    """The command patterns of every action that asks on any branch, the default-branch push patterns when a push to it
    asks (for each branch named, when the caller cannot tell which one is the default), and the push patterns of each environment whose `deploy.run` asks, and one set for any `gh api` write when an
    action with `api_endpoints` asks; each once, in the order of the actions. A `gh api` pattern of an action's own (a
    config's) stays unless that set already matches its text."""
    out: list[str] = []
    api = False
    for action, spec in rs.actions.items():
        # A harness cannot tell one branch from another, so an action asks there when it asks on any branch. `git.push`
        # is the one exception: a push to the agent's own branch stays allowed, and the default branch gets its own
        # patterns below.
        branches = (None,) if action == "git.push" else (None, "own", "default", "shared")
        asks = any(level_of(rs, action, branch=b)[0] == "ask" for b in branches)
        # A ref moved through the API is on no branch of the agent's own, so it asks wherever a push to another branch asks.
        pushes = action == "git.push" and any(level_of(rs, action, branch=b)[0] == "ask" for b in ("default", "shared"))
        commands = spec.get("commands", [])
        # A `git merge` lands on the branch checked out, which no harness rule can see. It is written only when it asks
        # on one's own branch too, so a merge of main into a feature branch never asks.
        if level_of(rs, action, branch="own")[0] != "ask":
            commands = [c for c in commands if not is_local_merge(c)]
        if asks:
            # The `gh api` set below holds a pattern that shows a write; the rest stay, so a harness asks for more, never less.
            out += [c for c in commands if not (c.startswith("gh api") and any(globs.match_text(p, c) for p in api_write_patterns()))]
        api = api or bool((asks or pushes) and (spec.get("api_endpoints") or any(c.startswith("gh api") for c in commands)))
    out += api_write_patterns() if api else []
    defaults = [default_branch] if isinstance(default_branch, str) else list(default_branch or [])
    if defaults and level_of(rs, "git.push", branch="default")[0] == "ask":
        for b in defaults:
            for dest in (b, f"*:{b}", f"+{b}", f"refs/heads/{b}", f"*:refs/heads/{b}"):
                out += [f"git push * {dest}", f"git push * {dest} *"]
        out += ["git push --all*", "git push --mirror*", "git push * --all*", "git push * --mirror*"]
    # A push to an environment's branch or tag is `deploy.run` there, so it gets patterns that name each glob while
    # that environment asks. A harness reads a glob's `*` across `/`, so it asks at least where aidd does.
    for env in rs.environments:
        if level_of(rs, "deploy.run", environment=env["name"])[0] != "ask":
            continue
        for b in env.get("branches") or []:
            for dest in (b, f"*:{b}", f"+{b}", f"refs/heads/{b}", f"*:refs/heads/{b}"):
                out += [f"git push * {dest}", f"git push * {dest} *"]
        for t in env.get("tags") or []:
            for dest in (t, f"+{t}", f"tags/{t}", f"refs/tags/{t}", f"*:refs/tags/{t}"):
                out += [f"git push * {dest}", f"git push * {dest} *"]
        if env.get("tags"):
            out += ["git push --tags*", "git push * --tags*", "git push --follow-tags*", "git push * --follow-tags*"]
    # A harness matches the command as typed, so each pattern is written in every runner form its tool starts through.
    # A setting before the tool (`RAILS_ENV=production rails db:*`) stays in front of each form.
    for p in list(out):
        words = p.split()
        n = len(list(itertools.takewhile(_SETTING.fullmatch, words)))
        head, rest = " ".join(words[:n] + [""]), " ".join(words[n:])
        for tool, forms in RUNNER_FORMS.items():
            if rest == tool or rest.startswith(tool + " "):
                out += [head + form + rest[len(tool) :] for form in forms]
    return list(dict.fromkeys(" ".join(p.split()) for p in out))


def _read_actions(rs: RuleSet) -> list[str]:
    """The actions with `file_reads` paths that ask on any branch, in the order of the actions."""
    return [
        a
        for a, spec in rs.actions.items()
        if (spec.get("file_reads") or {}).get("paths") and any(level_of(rs, a, branch=b)[0] == "ask" for b in (None, "own", "default", "shared"))
    ]


def harness_read_paths(rs: RuleSet) -> list[str]:
    """The path globs a harness's own file-read tool asks before: the `file_reads` paths of each action that asks on
    any branch; each once, in the order of the actions. Then, each as `!<path>`, what Claude Code carves back out after
    them: the `.env` templates and each other exclude, such as source code. A harness with no carve-out drops those, so
    there it asks for more, such as `.env.example` or `credentials.py`. Last, each as `+<path>`, an `include` that Claude
    Code writes again after the carve-outs, so the later rule takes it back in, as gitignore order reads it."""
    actions = _read_actions(rs)
    paths = [p for a in actions for p in rs.actions[a]["file_reads"]["paths"]]
    excludes = [e for a in actions for e in rs.actions[a]["file_reads"].get("exclude") or [] if e not in _NOT_CARVED]
    include = [e for a in actions for e in rs.actions[a]["file_reads"].get("include") or []]
    carve = [*CLAUDE_CODE_CARVE_OUTS, *excludes] if paths else []
    return list(dict.fromkeys(paths)) + [f"!{p}" for p in dict.fromkeys(carve)] + [f"+{p}" for p in dict.fromkeys(include)]


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON ({exc}); fix it, then run the command again") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a JSON object; fix it, then run the command again")
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(data), encoding="utf-8")


def _json_text(data: dict) -> str:
    """`data` indented, with each rule of a top-level `permissions` list on one line, as OpenCode's rules read best, and a
    third smaller. A marker that the data itself holds falls back to plain indenting."""
    rules = data.get("permissions")
    marks = [f"aidd-rule-{i}" for i in range(len(rules))] if isinstance(rules, list) else []
    plain = json.dumps(data, indent=2)
    if not marks or any(f'"{m}"' in plain for m in marks):
        return plain + "\n"
    text = json.dumps({**data, "permissions": marks}, indent=2)
    for mark, rule in zip(marks, rules or [], strict=True):
        text = text.replace(f'"{mark}"', json.dumps(rule), 1)
    return text + "\n"


def _object(data: dict, key: str, rel: str) -> dict:
    """`data[key]`, made an empty object when missing; refused when it holds something else."""
    if not isinstance(data.setdefault(key, {}), dict):
        raise ValueError(f"{rel}: `{key}` is not an object; fix it, then run the command again")
    return data[key]


def owned(root: Path) -> dict[str, list[str]]:
    """What aidd wrote before, by harness format (`.aidd/harness-rules.json`)."""
    data = _read_json(root / config.HARNESS_RULES_FILE)
    return {k: [str(x) for x in v] for k, v in data.items() if k in FORMATS and isinstance(v, list)}


def written_formats(root: Path) -> list[str]:
    """The harness formats whose ask rules aidd wrote in this repository, as `.aidd/harness-rules.json` lists them."""
    return [fmt for fmt, entries in owned(root).items() if entries]


def remotes(root: Path) -> list[str]:
    """What a `*` between words stands for: the common remote names, the same on every machine. A remote a person adds
    is in their own git config, so the files aidd commits never depend on who ran it; `root` stays for that reason only."""
    del root
    return list(COMMON_REMOTES)


def codex_words(pattern: str, remote_names: list[str]) -> list[str | list[str]] | None:
    """A pattern as leading words, each a literal or a list of literals, or None when it has no such form. A trailing
    `*` is dropped, a `*` word between words is the list of remotes, and `*:<branch>` is `HEAD:<branch>`."""
    words: list[str | list[str]] = []
    parts = pattern.split()
    for i, w in enumerate(parts):
        last = i == len(parts) - 1
        if w == "*" and not last:
            words.append(list(remote_names))
        elif w.startswith("*:") and _PLAIN.fullmatch(w[2:]):
            words.append(f"HEAD:{w[2:]}")
        elif last and w.endswith("*") and _WORD.fullmatch(w[:-1]):
            words.append(w[:-1])  # `--force*` asks at `--force`; `+*` stays unwritten, since these formats match whole words
        elif last and w == "*":
            break
        elif _PLAIN.fullmatch(w):
            words.append(w)
        else:
            return None
    return words or None


def leading_words(pattern: str) -> list[str | list[str]] | None:
    """For a pattern with no leading-words form, such as `gh workflow run *release*`, the words before its first `*`,
    which a leading-words format asks at instead: `gh workflow run`. So it asks more, never less. None unless the tool's
    own words there, past a setting and a runner (`npx`, `bundle exec`), number MIN_LEADING_WORDS or more, so no ask
    grows wider than three words of one tool: `bundle exec rails db:*RAILS_ENV=production*` stays unwritten."""
    if codex_words(pattern, list(COMMON_REMOTES)) is not None:
        return None
    lead = list(itertools.takewhile(lambda w: "*" not in w, pattern.split()))
    text = " ".join(itertools.dropwhile(_SETTING.fullmatch, lead))
    own = len(text.split())
    runners = ((form, tool) for tool, forms in RUNNER_FORMS.items() for form in forms)
    form, tool = max(((f, t) for f, t in runners if text == f or text.startswith(f + " ")), key=lambda x: len(x[0]), default=("", ""))
    own += len(tool.split()) - len(form.split())
    return list(lead) if own >= MIN_LEADING_WORDS else None


def _expanded(words: list[str | list[str]]) -> list[str]:
    """Leading words with every list of alternatives spelled out, as one command prefix each."""
    return [" ".join(c) for c in itertools.product(*[[w] if isinstance(w, str) else w for w in words])]


_REGEX_SPECIAL = frozenset("\\^$.|?*+()[]{}/")


def glob_regex(pattern: str) -> str:
    """A glob over the whole command as a regular expression that matches exactly what the glob matches: `*` is any run
    of characters, new lines too, and only the characters special in a regular expression (or the `/` around VS Code's
    key) are escaped, so the same text reads alike in Python, Go, Rust, and JavaScript, `u` flag included."""
    escape = lambda part: "".join(f"\\{c}" if c in _REGEX_SPECIAL else c for c in part)  # noqa: E731
    return "^" + "[\\s\\S]*".join(escape(part) for part in pattern.split("*")) + "$"


def _writable(pattern: str) -> bool:
    """Whether a pattern is printable ASCII, which every format holds as written: anything else is left to the skill."""
    return pattern.isascii() and pattern.isprintable() and pattern.strip() != "*"


def unwritten(fmt: str, patterns: list[str]) -> list[str]:
    """The patterns a format cannot hold, which only the skill covers there."""
    if fmt not in FORMATS:
        return []
    words = FORMATS[fmt].match == "words"

    # Held only in part: a `*` between words stands for `origin` and `upstream` alone, so a push through another remote
    # is left to the skill; `*:<branch>` is written as `HEAD:<branch>` only; `db:drop*` asks at the whole word
    # `db:drop`, never at `db:drop:all`; and a short flag, such as `git clean -f*`, asks at `-f` alone, never at the
    # combined `-fdx`, as an abbreviation such as `--ta*` asks only at `--ta`.
    def partly(p: str) -> bool:
        last = p.split()[-1]
        return (
            "*" in p.split()[:-1]
            or any(w.startswith("*:") for w in p.split())
            or (p.endswith("*") and (":" in last or bool(re.fullmatch(r"-[A-Za-z]+\*|--[A-Za-z]{1,3}\*", last))))
        )

    def held(p: str) -> bool:
        return leading_words(p) is not None if codex_words(p, list(COMMON_REMOTES)) is None else not partly(p)

    colon = fmt in ("claude-code", "grok")
    return [p for p in patterns if not _writable(p) or (words and not held(p)) or (colon and claude_code_form(p) is None)]


def widened(fmt: str, patterns: list[str]) -> dict[str, str]:
    """The patterns a leading-words format asks at their leading words instead (`leading_words`), each with those words:
    there the harness asks more widely, such as before every `gh workflow run`."""
    if fmt not in FORMATS or FORMATS[fmt].match != "words":
        return {}
    return {p: " ".join(map(str, w)) for p in patterns if _writable(p) and (w := leading_words(p))}


def _entries(fmt: str, patterns: list[str], remote_names: list[str] | None = None, read_paths: list[str] | None = None) -> list[str]:
    """The entries a format holds for `patterns`, and for `read_paths` where its harness has a file-read rule, each
    the string aidd records it by."""
    names = remote_names or list(COMMON_REMOTES)
    patterns = [p for p in patterns if _writable(p)]
    reads = [f"Read({p})" for p in read_paths or [] if _writable(p) and not p.startswith(("!", "+"))] if FORMATS[fmt].reads else []
    if reads and fmt == "claude-code":
        reads += [f"Read({p})" for p in read_paths or [] if p.startswith("!") and _writable(p)]
        reads += [f"Read({p[1:]})" for p in read_paths or [] if p.startswith("+") and _writable(p)]  # taken back in, after the carve-outs
    return _command_entries(fmt, patterns, names) + reads


def claude_code_form(pattern: str) -> str | None:
    """A pattern as Claude Code reads it, or None when it has no form there. Claude Code reads `:*` as its older prefix
    form only at the end of a pattern, where `ls:*` is `ls *`, and reads a colon anywhere else as a literal (its
    permissions docs, read 2026-11-08). So a trailing `db:*` would read as `db *` and miss `rails db:migrate`: it drops its
    colon, and asks at `db*`, more widely, never less. A trailing `:*` that starts a word, as in `git push * :*`, would
    read as `git push * *`, every push that names a branch, so it is left to the skill. Grok Build gets the same form,
    since its docs do not say how it reads one; that is unvalidated against a live Grok Build."""
    if not pattern.endswith(":*"):
        return pattern
    if re.search(r"(?:^|[\s*]):\*$", pattern):
        return None
    return pattern[:-2] + "*"


# Claude Code's `Read(!<path>)` rules: each carves a template out of the read rules before it in the same file, so its own
# file-read tool reads `.env.example` with no prompt, as `aidd risk` allows (its permissions docs, read 2026-11-08).
CLAUDE_CODE_CARVE_OUTS = ("**/.env.example", "**/.env.sample", "**/.env.template", "**/.env.dist")
# The `file_reads` excludes Claude Code gets no carve-out for: the template suffixes, which the `.env` forms above stand for,
# and a public key. Every other exclude, such as source code (`**/*.py`), is carved out as written.
_NOT_CARVED = frozenset({"**/*.example", "**/*.sample", "**/*.template", "**/*.dist", "**/*.pub"})


def _command_entries(fmt: str, patterns: list[str], names: list[str]) -> list[str]:
    """The entries a format holds for the command patterns."""
    if fmt == "claude-code":
        return list(dict.fromkeys(f"Bash({q})" for p in patterns if (q := claude_code_form(p))))
    if fmt == "grok":
        return list(dict.fromkeys(f"Bash({q})" for p in patterns if (q := claude_code_form(p))))
    if fmt == "opencode":
        return list(patterns)
    if FORMATS[fmt].match == "regex":
        return list(dict.fromkeys(glob_regex(p) for p in patterns))
    words = [w for w in (codex_words(p, names) or leading_words(p) for p in patterns) if w]
    words += [api_write_words()] if any(p in api_write_patterns() for p in patterns) else []
    if fmt in ALTERNATIVES:
        return list(dict.fromkeys(json.dumps(w) for w in words))
    prefixes = list(dict.fromkeys(e for w in words for e in _expanded(w)))
    return [e for p in prefixes for e in (f"Bash({p})", f"Bash({p} *)")]  # qwen: the bare command, and with arguments


def _codex_text(entries: list[str]) -> str:
    lines = [
        "# Written by aidd from the ask risk rules (`aidd risk --list`). `aidd upgrade` rewrites this file, so put your",
        "# own rules in another file in this folder.",
    ]
    lines += [f'prefix_rule(pattern = {e}, decision = "prompt")' for e in entries]
    return "\n".join(lines) + "\n"


def _toml_block(entries: list[str]) -> str:
    return f"{_TOML_BEGIN}\n[permission]\nask = {json.dumps(entries)}\n{_TOML_END}\n"


def _toml_span(text: str) -> tuple[int, int] | None:
    start = text.find(_TOML_BEGIN)
    end = text.find(_TOML_END, start)
    return (start, end + len(_TOML_END) + (1 if text[end + len(_TOML_END) : end + len(_TOML_END) + 1] == "\n" else 0)) if start >= 0 and end >= 0 else None


def _grok_conflict(outside: str, block: str | None, before: set[str]) -> str | None:
    """Why aidd must leave `.grok/config.toml` alone, or None: the person's part does not parse, it sets `permission`
    itself (one table per file), or they changed aidd's block."""
    try:
        theirs = tomllib.loads(outside)
    except tomllib.TOMLDecodeError as exc:
        return f"it does not parse ({exc})"
    if "permission" in theirs:
        return "it has a `permission` table of its own"
    if block is not None:
        try:
            ours = tomllib.loads(block)
        except tomllib.TOMLDecodeError:
            return "aidd's block in it was changed"
        ask = ours.get("permission", {}).get("ask") if isinstance(ours.get("permission"), dict) else None
        if ours != {"permission": {"ask": ask}} or not isinstance(ask, list) or not all(isinstance(a, str) for a in ask) or set(ask) != before:
            return "aidd's block in it was changed"
    return None


def _grok_whole(text: str, span: tuple[int, int] | None) -> str | None:
    """Why the whole `.grok/config.toml` stops aidd, or None: it must parse, and its `permission` table must be exactly
    aidd's block, so no line of the person's after the block reads as part of it."""
    if span is None:
        return None
    try:
        whole = tomllib.loads(text)
        block = tomllib.loads(text[span[0] : span[1]])
    except tomllib.TOMLDecodeError as exc:
        return f"it does not parse ({exc})"
    return None if whole.get("permission") == block.get("permission") else "its `permission` table holds more than aidd's block"


def _claude_code_theirs(current: list[str], entries: list[str], before: set[str]) -> list[str]:
    """The person's own entries in Claude Code's `permissions.ask`, in their order: every entry but aidd's, which are each
    string aidd wrote before, as many times as it writes it now, from the start. A person's copy of one of aidd's rules
    stays theirs, so it sits after aidd's carve-outs, which never lift it."""
    want = {e: entries.count(e) for e in set(entries)}
    seen: dict[str, int] = {}
    theirs = []
    for e in current:
        if e in before and seen.get(e, 0) < want.get(e, 0):
            seen[e] = seen.get(e, 0) + 1  # aidd's own copy
        elif not (e in before and e not in want):  # an entry aidd wrote before and no longer wants goes
            theirs.append(e)
    return theirs


def _merge(fmt: str, rel: str, data: dict, entries: list[str], before: set[str], done: list[str]) -> list[str]:
    """Bring aidd's entries in `data` up to `entries`, keeping a person's own; the entries aidd owns afterwards."""
    if fmt in ("claude-code", "qwen"):
        node = _object(data, "permissions", rel)
        current = [e for e in node.get("ask", []) if isinstance(e, str)]
        if fmt == "claude-code":
            # aidd's block comes first, and a person's entry stays after it even when it is the same as one of aidd's, so a
            # `Read(!...)` carve-out lifts only aidd's own read rules, never a person's.
            node["ask"] = entries + _claude_code_theirs(current, entries, before)
            return list(entries)
        kept = [e for e in current if e not in before or e in entries]
        node["ask"] = kept + [e for e in entries if e not in kept]
        return [e for e in entries if e in before or e not in current]
    if fmt == "opencode":
        # v2's `permissions` list, after the person's default (opencode_rules says why).
        return opencode_rules.merge(data, entries, before, rel, done)
    # vscode: a `false` rule asks, and always wins over a `true` one, so order does not matter; a person's key stays theirs.
    vmap = data.get("chat.tools.terminal.autoApprove")
    if vmap is not None and not isinstance(vmap, dict):
        raise ValueError(f"{rel}: `chat.tools.terminal.autoApprove` is not an object; fix it, then run the command again")
    vmap = dict(vmap or {})
    vkeys = {f"/{e}/": e for e in entries}
    vtheirs = {k: v for k, v in vmap.items() if not (k[1:-1] in before and v is False)}
    vnew = vtheirs | {k: False for k in vkeys if k not in vtheirs}
    if vnew or "chat.tools.terminal.autoApprove" in data:
        data["chat.tools.terminal.autoApprove"] = vnew
    return [e for k, e in vkeys.items() if k not in vtheirs]


def apply_harness_rules(root: Path, fmt: str, patterns: list[str], *, read_paths: list[str] | None = None, write: bool = True) -> list[str]:
    """Bring one harness's ask rules up to `patterns`, and its file-read rules up to `read_paths`
    (`harness_read_paths`): add what is missing, remove what aidd wrote before and no longer wants, and keep everything
    else. What it did (or would do, without `write`), one line each."""
    root = Path(root)
    mine = owned(root)
    before = set(mine.get(fmt, []))
    entries = _entries(fmt, patterns, remotes(root), read_paths)
    rel = FORMATS[fmt].path
    path = root / rel
    done: list[str] = []
    verb = "wrote" if write else "would write"
    if fmt in ("codex", "grok"):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if fmt == "codex":
            new_text = _codex_text(entries)
        else:
            span = _toml_span(text)
            outside = text if span is None else text[: span[0]] + text[span[1] :]
            why = _grok_conflict(outside, text[span[0] : span[1]] if span else None, before) or _grok_whole(text, span)
            if why:
                done.append(f"kept     {rel} ({why}; add aidd's ask rules by hand: `aidd risk --list`)")
                return done
            block = _toml_block(entries)
            new_text = (text[: span[0]] + block + text[span[1] :]) if span else (text.rstrip("\n") + ("\n\n" if text.strip() else "") + block)
            try:
                parsed = tomllib.loads(new_text)
                expected = tomllib.loads(outside) | {"permission": {"ask": entries}}
            except tomllib.TOMLDecodeError as exc:
                done.append(f"kept     {rel} (aidd's block would not parse there: {exc})")
                return done
            if parsed != expected:
                done.append(f"kept     {rel} (aidd's block would change how the rest of it reads)")
                return done
        claimed = list(entries)
        if new_text != text:
            done.append(f"{verb} {len(entries)} ask rules into {rel}")
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_text, encoding="utf-8")
    else:
        data = _read_json(path)
        snapshot = json.dumps(data, sort_keys=True)
        claimed = _merge(fmt, rel, data, entries, before, done)
        if json.dumps(data, sort_keys=True) != snapshot or (path.is_file() and json.dumps(_read_json(path)) != json.dumps(data)):
            done.append(f"{verb} {len(claimed)} ask rules into {rel}")
            if write:
                _write_json(path, data)
    # Claude Code's block may hold one entry twice (a re-include), so its record keeps each copy.
    claimed = list(claimed) if fmt == "claude-code" else sorted(set(claimed))
    if write and (any(not d.startswith("kept") for d in done) or sorted(mine.get(fmt, [])) != sorted(claimed)):
        mine[fmt] = sorted(claimed)
        # A key that names no format, such as the delegation's hooks, is another writer's, so it stays as it was.
        others = {k: v for k, v in _read_json(root / config.HARNESS_RULES_FILE).items() if k not in FORMATS}
        _write_json(root / config.HARNESS_RULES_FILE, {**others, **mine})
    return done


def _remove(fmt: str, data: dict, entries: list[str]) -> bool:
    """Take aidd's entries out of `data`; whether anything changed."""
    if fmt in ("claude-code", "qwen"):
        node = data.get("permissions")
        if not isinstance(node, dict) or not isinstance(node.get("ask"), list):
            return False
        # aidd's copies come first, as many as it wrote, so a later copy of one of its entries is the person's own.
        count = {e: entries.count(e) for e in set(entries)}
        left = []
        for e in node["ask"]:
            if count.get(e, 0):
                count[e] -= 1
            else:
                left.append(e)
        if left == node["ask"]:
            return False
        node["ask"] = left
        if not left:
            node.pop("ask")
        return True
    if fmt == "opencode":
        return opencode_rules.remove(data, entries)
    # vscode
    node = data.get("chat.tools.terminal.autoApprove")
    gone = [k for k in (node or {}) if isinstance(node, dict) and k[1:-1] in entries and node[k] is False]
    for k in gone:
        del node[k]  # type: ignore[union-attr]
    return bool(gone)


def opencode_shadow_warnings(root: Path, patterns: list[str]) -> list[str]:
    """Each rule of the person's in `opencode.json` that lets a command run with no prompt where the risk rules
    `patterns` ask, as `aidd doctor` says it (`opencode_rules.shadow_warnings`)."""
    rel = FORMATS["opencode"].path
    path = Path(root) / rel
    return opencode_rules.shadow_warnings(_read_json(path), _entries("opencode", patterns), rel) if path.is_file() else []


def remove_harness_rules(root: Path, *, write: bool = True) -> list[str]:
    """Take out every ask rule aidd wrote, and its record (`aidd uninstall`). What it did, one line each."""
    root = Path(root)
    mine = owned(root)
    done: list[str] = []
    verb = "removed" if write else "would remove"
    for fmt, entries in mine.items():
        rel = FORMATS[fmt].path
        path = root / rel
        if not path.is_file():
            continue
        if fmt == "codex":
            done.append(f"{verb} {rel}")
            if write:
                path.unlink()
            continue
        if fmt == "grok":
            text = path.read_text(encoding="utf-8")
            span = _toml_span(text)
            if span is None:
                continue
            rest = text[: span[0]].rstrip("\n") + ("\n" if text[: span[0]].strip() else "") + text[span[1] :]
            why = _grok_conflict("", text[span[0] : span[1]], set(entries)) or _grok_whole(text, span)
            if not why:
                try:
                    if tomllib.loads(rest) != {k: v for k, v in tomllib.loads(text).items() if k != "permission"}:
                        why = "taking aidd's block out would change how the rest of it reads"
                except tomllib.TOMLDecodeError:
                    why = "taking aidd's block out would leave it unparsable"
            if why:
                done.append(f"kept     aidd's block in {rel} ({why}); take it out by hand")
                continue
            done.append(f"{verb} aidd's ask rules from {rel}")
            if write:
                path.write_text(rest, encoding="utf-8") if rest.strip() else path.unlink()
            continue
        data = _read_json(path)
        if _remove(fmt, data, list(entries)):
            done.append(f"{verb} aidd's ask rules from {rel}")
            if write:
                # A file left holding only empty objects and lists was aidd's alone: it goes, so uninstall leaves no trace.
                path.unlink() if documents.holds_nothing(data) else _write_json(path, data)
    record = root / config.HARNESS_RULES_FILE
    if mine and record.is_file():
        done.append(f"{verb} {config.HARNESS_RULES_FILE}")
        if write:
            record.unlink()
    return done


def command_notes(rs: RuleSet, answer: dict) -> list[str]:
    """What a person should know about a command line's answer that no action says. Today it is one: a part of the line
    that the harnesses' `gh api` patterns match as typed, while `aidd risk` reads it exactly as a lower level than `ask`,
    such as a GET with a field or a GraphQL query. `answer` is `command_level`'s."""
    asked = [p for p in harness_patterns(rs, None) if p.startswith("gh api")]
    notes = []
    for part in split(answer["command"]):
        typed = {normalize(c) for c in (part, *wrapped(part))}
        levels = [a["level"] for a in answer["actions"] if a["command"] in typed]
        if max(levels, key=LEVEL_RANK.__getitem__, default="allow") != "ask" and any(globs.match_text(p, part) for p in asked):
            notes.append(api_write_note())
    return list(dict.fromkeys(notes))
