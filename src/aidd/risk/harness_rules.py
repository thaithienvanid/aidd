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

Claude Code, Grok Build, and OpenCode v2 also hold a file-edit rule for each test file of an approved Spec
(`harness_edit_paths`). A shell write is no edit tool, so the rule may miss it: a person's review and a delegated merge's check hold the test then.

A rule narrowed by an area or a role has no command form, so only the rules an action has on its own count, and a
`git.push` rule on the `default` branch becomes patterns that name that branch, as a `deploy.run` rule for one of the
config's `environments` becomes patterns that name its branches and tags. aidd changes only what it wrote: the
entries it wrote are listed in `.aidd/harness-rules.json`. A person's own entries stay as they are, and aidd never
puts an ask where it would undo their deny.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from aidd import config
from aidd.kernel import documents, globs, regular_files
from aidd.kernel import text as kernel_text
from aidd.risk import grok_rules, jsonc, opencode_rules, settings_json
from aidd.risk.commands import RUNNER_FORMS, environment_push_level, is_local_merge
from aidd.risk.edit_paths import edit_writable
from aidd.risk.gh_api import BODY_FLAGS
from aidd.risk.rules import ANY_BRANCH, RuleSet, level_of
from aidd.risk.settings_json import read_json as _read_json
from aidd.risk.settings_json import settings_text as _settings_text
from aidd.risk.settings_json import write_json as _write_json


@dataclasses.dataclass(frozen=True)
class Format:
    path: str  # the file, relative to the repository's top
    match: str  # glob, regex, or words: how the harness matches a command
    shape: str  # what aidd writes there, for the docs
    # Whether its ask rules hold one for the harness's own file-read tool, `Read(<path glob>)`, beside the commands.
    reads: bool = False
    # What its file-edit rule puts before a repository path, `Edit(<anchor><path>)`; empty with none. Claude Code's `/` is the
    # project root; Grok Build's docs name no anchor, so `**/` reads any depth; OpenCode's `*` spans `/`, so one rule matches both forms.
    edits: str = ""
    # What its settings file takes, as the harness documents it (`jsonc.py`): `json`, `comments`, or `jsonc`. A file that takes
    # comments is edited in place, so a person's comments and settings stay.
    syntax: str = "json"
    # Another name its harness reads for the same settings file: the person's own file is the one aidd writes into.
    alternatives: tuple[str, ...] = ()


FORMATS: dict[str, Format] = {
    "claude-code": Format(
        ".claude/settings.json", "glob", "`permissions.ask`: `Bash(git push --force*)`, `Read(**/.env)`, and `Edit(/tests/test_a.py)`", reads=True, edits="/"
    ),
    "codex": Format(".codex/rules/aidd.rules", "words", '`prefix_rule(pattern = ["git", "push", ["origin", "upstream"], "main"], decision = "prompt")`'),
    # VS Code's settings files are JSONC: comments and trailing commas (code.visualstudio.com/docs/languages/json, read 2026-11-11).
    "vscode": Format(
        ".vscode/settings.json", "regex", 'in VS Code\'s agent, `chat.tools.terminal.autoApprove`: `{"/^git push --force.*$/": false}`', syntax="jsonc"
    ),
    "opencode": Format(
        "opencode.json",
        "glob",
        '`permissions`: `{"action": "shell", "resource": "git push --force*", "effect": "ask"}` and `{"action": "edit", "resource": "*tests/test_a.py", "effect": "ask"}`',
        edits="*",
        # `opencode.jsonc` takes comments and trailing commas (opencode.ai/docs/config, read 2026-11-11). Whether `opencode.json`
        # does is unconfirmed, so aidd reads that one as strict JSON. Both names in one folder: the docs do not say which wins.
        alternatives=("opencode.jsonc",),
    ),
    # Qwen Code reads its settings as `JSON.parse(stripJsonComments(stripUtf8Bom(text)))` (QwenLM/qwen-code, packages/cli/src/config/settings.ts,
    # read 2026-11-11): comments and a byte order mark, no trailing comma. It backs up a workspace file that does not parse and resets it
    # to `{}`, so aidd never writes a trailing comma there.
    "qwen": Format(
        ".qwen/settings.json",
        "words",
        "`permissions.ask`: `Bash(git push --force)`, `Bash(git push --force *)`, and `Read(**/.env)`",
        reads=True,
        syntax="comments",
    ),
    "grok": Format(
        ".grok/config.toml",
        "glob",
        '`[permission] ask = ["Bash(git push --force*)", "Read(**/.env)", "Edit(**/tests/test_a.py)"]`, in a block aidd marks',
        reads=True,
        edits="**/",
    ),
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


def api_harness_names() -> str:
    """The harnesses whose ask rules hold the `gh api` set, as a phrase: every format that matches by glob or by regular
    expression, in the order of FORMATS. A leading-words format (Codex, Qwen Code) cannot hold it."""
    names = [h.reader or h.label for fmt, f in FORMATS.items() if f.match != "words" for h in config.HARNESSES.values() if h.ask_rules == fmt]
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


API_LABEL = "gh api writes"  # what the one `gh api` set stands for, in the lines that say which rules changed


def harness_patterns(rs: RuleSet, default_branch: str | Sequence[str] | None) -> list[str]:
    """The command patterns of every action that asks on any branch, the default-branch push patterns when a push to it
    asks (for each branch named, when the caller cannot tell which one is the default), and the push patterns of each environment whose `deploy.run` asks, and one set for any `gh api` write when an
    action with `api_endpoints` asks; each once, in the order of the actions. A `gh api` pattern of an action's own (a
    config's) stays unless that set already matches its text."""
    return list(dict.fromkeys(p for _, p in labelled_patterns(rs, default_branch)))


def pattern_actions(rs: RuleSet, default_branch: str | Sequence[str] | None) -> dict[str, str]:
    """Each command pattern with the action it comes from, for the lines that say which ask rules changed: the patterns
    `harness_patterns` lists, then the commands of every other action, so a rule that stopped asking still names its action."""
    by_pattern: dict[str, str] = {}
    for action, pattern in labelled_patterns(rs, default_branch):
        by_pattern.setdefault(pattern, action)
    rest = [(a, c) for a, spec in rs.actions.items() for c in spec.get("commands", [])]
    for action, pattern in _runner_forms(rest):
        by_pattern.setdefault(" ".join(pattern.split()), action)
    # The families a rule writes only while it asks, so a rule that stopped asking still names where it came from.
    defaults = [default_branch] if isinstance(default_branch, str) else list(default_branch or [])
    for action, pattern in [*_default_pushes(defaults), *((API_LABEL, p) for p in api_write_patterns())]:
        by_pattern.setdefault(pattern, action)
    return by_pattern


def _default_pushes(defaults: list[str]) -> list[tuple[str, str]]:
    """The patterns of a push to each default branch named, and of a push of every branch, each with `git.push`."""
    out = [
        ("git.push", f"git push * {d}{tail}") for b in defaults for d in (b, f"*:{b}", f"+{b}", f"refs/heads/{b}", f"*:refs/heads/{b}") for tail in ("", " *")
    ]
    return out + [("git.push", p) for p in ("git push --all*", "git push --mirror*", "git push * --all*", "git push * --mirror*")]


def labelled_patterns(rs: RuleSet, default_branch: str | Sequence[str] | None) -> list[tuple[str, str]]:
    """`harness_patterns`, each with the action it comes from (`API_LABEL` for the `gh api` set)."""
    out: list[tuple[str, str]] = []
    api = False
    for action, spec in rs.actions.items():
        # A harness cannot tell one branch from another, so an action asks there when it asks on any branch. `git.push`
        # is the one exception: a push to the agent's own branch stays allowed, and the default branch gets its own
        # patterns below.
        branches = (None,) if action == "git.push" else ANY_BRANCH
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
            out += [(action, c) for c in commands if not (c.startswith("gh api") and any(globs.match_text(p, c) for p in api_write_patterns()))]
        api = api or bool((asks or pushes) and (spec.get("api_endpoints") or any(c.startswith("gh api") for c in commands)))
    out += [(API_LABEL, p) for p in api_write_patterns()] if api else []
    defaults = [default_branch] if isinstance(default_branch, str) else list(default_branch or [])
    if defaults and level_of(rs, "git.push", branch="default")[0] == "ask":
        out += _default_pushes(defaults)
    # A push to an environment's branch or tag gets patterns that name each glob while it asks, as `aidd risk` reads it.
    # A harness reads a glob's `*` across `/`, so it asks at least where aidd does.
    for env in rs.environments:
        if environment_push_level(rs, str(env["name"])) != "ask":
            continue
        for b in env.get("branches") or []:
            for dest in (b, f"*:{b}", f"+{b}", f"refs/heads/{b}", f"*:refs/heads/{b}"):
                out += [("deploy.run", f"git push * {dest}"), ("deploy.run", f"git push * {dest} *")]
        for t in env.get("tags") or []:
            for dest in (t, f"+{t}", f"tags/{t}", f"refs/tags/{t}", f"*:refs/tags/{t}"):
                out += [("deploy.run", f"git push * {dest}"), ("deploy.run", f"git push * {dest} *")]
        if env.get("tags"):
            out += [("deploy.run", p) for p in ("git push --tags*", "git push * --tags*", "git push --follow-tags*", "git push * --follow-tags*")]
    return list(dict.fromkeys((a, " ".join(p.split())) for a, p in _runner_forms(out)))


def _runner_forms(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The pairs of (action, pattern), then each pattern written in every runner form its tool starts through, as a harness
    matches the command as typed. A setting before the tool (`RAILS_ENV=production rails db:*`) stays in front of each form."""
    out = list(pairs)
    for action, p in pairs:
        words = p.split()
        n = len(list(itertools.takewhile(_SETTING.fullmatch, words)))
        head, rest = " ".join(words[:n] + [""]), " ".join(words[n:])
        for tool, forms in RUNNER_FORMS.items():
            if rest == tool or rest.startswith(tool + " "):
                out += [(action, head + form + rest[len(tool) :]) for form in forms]
    return out


def _read_actions(rs: RuleSet) -> list[str]:
    """The actions with `file_reads` paths that ask on any branch, in the order of the actions."""
    return [
        a for a, spec in rs.actions.items() if (spec.get("file_reads") or {}).get("paths") and any(level_of(rs, a, branch=b)[0] == "ask" for b in ANY_BRANCH)
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


def _object(data: dict, key: str, rel: str) -> dict:
    """`data[key]`, made an empty object when missing; refused when it holds something else."""
    if not isinstance(data.setdefault(key, {}), dict):
        raise ValueError(f"{rel}: `{key}` is not an object; fix it, then run the command again")
    return data[key]


def owned(root: Path) -> dict[str, list[str]]:
    """What aidd wrote before, by harness format (`.aidd/harness-rules.json`)."""
    data = _read_json(root, root / config.HARNESS_RULES_FILE)
    return {k: [str(x) for x in v] for k, v in data.items() if k in FORMATS and isinstance(v, list)}


def written_formats(root: Path) -> list[str]:
    """The harness formats whose ask rules aidd wrote in this repository, as `.aidd/harness-rules.json` lists them."""
    return [fmt for fmt, entries in owned(root).items() if entries]


def rule_files(fmt: str) -> tuple[str, ...]:
    """Every file a harness reads its ask rules from for `fmt`: the one aidd writes first, then its other names."""
    return (FORMATS[fmt].path, *FORMATS[fmt].alternatives)


def rules_file(root: Path, fmt: str) -> str:
    """The file aidd writes `fmt`'s ask rules into: the one a person keeps. The first name, unless only another of the
    harness's names is there (OpenCode's `opencode.jsonc`), so aidd never writes a second file beside the person's."""
    first, *rest = rule_files(fmt)
    return first if regular_files.is_file_or_held(root, first) else next((r for r in rest if regular_files.is_file_or_held(root, r)), first)


def syntax_of(fmt: str, rel: str) -> str:
    """What the file `rel` takes for `fmt` (`Format.syntax`); a name ending `.jsonc` takes comments and trailing commas."""
    return "jsonc" if rel.endswith(".jsonc") else FORMATS[fmt].syntax


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
    def partly(pattern: str) -> bool:
        last = pattern.split()[-1]
        return (
            "*" in pattern.split()[:-1]
            or any(w.startswith("*:") for w in pattern.split())
            or (pattern.endswith("*") and (":" in last or bool(re.fullmatch(r"-[A-Za-z]+\*|--[A-Za-z]{1,3}\*", last))))
        )

    def held(pattern: str) -> bool:
        return leading_words(pattern) is not None if codex_words(pattern, list(COMMON_REMOTES)) is None else not partly(pattern)

    colon = fmt in ("claude-code", "grok")
    return [p for p in patterns if not _writable(p) or (words and not held(p)) or (colon and claude_code_form(p) is None)]


def widened(fmt: str, patterns: list[str]) -> dict[str, str]:
    """The patterns a leading-words format asks at their leading words instead (`leading_words`), each with those words:
    there the harness asks more widely, such as before every `gh workflow run`."""
    if fmt not in FORMATS or FORMATS[fmt].match != "words":
        return {}
    return {p: " ".join(map(str, w)) for p in patterns if _writable(p) and (w := leading_words(p))}


def _entries(
    fmt: str,
    patterns: list[str],
    remote_names: list[str] | None = None,
    read_paths: list[str] | None = None,
    edit_paths: list[str] | None = None,
) -> list[str]:
    """The entries a format holds for `patterns`, for `read_paths` where its harness has a file-read rule, and for
    `edit_paths` (`edit_paths.harness_edit_paths`) where it has a file-edit rule, each the string aidd records it by."""
    names = remote_names or list(COMMON_REMOTES)
    patterns = [p for p in patterns if _writable(p)]
    reads = [f"Read({p})" for p in read_paths or [] if _writable(p) and not p.startswith(("!", "+"))] if FORMATS[fmt].reads else []
    if reads and fmt == "claude-code":
        reads += [f"Read({p})" for p in read_paths or [] if p.startswith("!") and _writable(p)]
        reads += [f"Read({p[1:]})" for p in read_paths or [] if p.startswith("+") and _writable(p)]  # taken back in, after the carve-outs
    edits = [f"Edit({FORMATS[fmt].edits}{p})" for p in edit_paths or [] if edit_writable(p)] if FORMATS[fmt].edits else []
    return command_entries(fmt, patterns, names) + reads + edits


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


def command_entries(fmt: str, patterns: list[str], names: list[str]) -> list[str]:
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


def _claude_code_theirs(current: list[str], before: Counter[str]) -> list[str]:
    """The person's own entries in Claude Code's `permissions.ask`, in their order: every entry but aidd's. aidd's copies come
    first, as many of each string as the record (`before`) holds, from the start. So a person's copy of one of aidd's
    rules, which sits after them, stays theirs and stays after aidd's carve-outs, which never lift it, even when aidd drops
    its own."""
    left = Counter(before)
    theirs = []
    for e in current:
        if left[e] > 0:
            left[e] -= 1  # aidd's own copy; its block holds what it wants now
        else:
            theirs.append(e)
    return theirs


def _merge(fmt: str, data: dict, entries: list[str], recorded: Counter[str], done: list[str]) -> list[str]:
    """Bring aidd's entries in `data` up to `entries`, keeping a person's own; the entries aidd owns afterwards."""
    rel = FORMATS[fmt].path
    before = set(recorded)
    if fmt in ("claude-code", "qwen"):
        node = _object(data, "permissions", rel)
        current = [e for e in node.get("ask", []) if isinstance(e, str)]
        if fmt == "claude-code":
            # aidd's block comes first, and a person's entry stays after it even when it is the same as one of aidd's, so a
            # `Read(!...)` carve-out lifts only aidd's own read rules, never a person's.
            node["ask"] = entries + _claude_code_theirs(current, recorded)
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


def apply_harness_rules(
    root: Path,
    fmt: str,
    patterns: list[str],
    *,
    read_paths: list[str] | None = None,
    edit_paths: list[str] | None = None,
    write: bool = True,
    by_pattern: Mapping[str, str] | None = None,
) -> list[str]:
    """Bring one harness's ask rules up to `patterns`, `read_paths` (`harness_read_paths`), and `edit_paths`
    (`harness_edit_paths`; None keeps the edit asks aidd wrote): add what is missing, remove what aidd wrote and no longer
    wants, keep the rest. What it did (or would do, without `write`), one line each, with the rules added and removed by
    action when `by_pattern` (`pattern_actions`) says which action each pattern comes from. The line is one computation, so a
    dry run and a real run say the same."""
    root = Path(root)
    mine = owned(root)
    recorded = Counter(mine.get(fmt, []))
    before = set(recorded)
    entries = _entries(fmt, patterns, remotes(root), read_paths, edit_paths)
    if edit_paths is None and FORMATS[fmt].edits:  # the Specs are unknown (one does not parse): the edit asks stay as they were
        entries += [e for e in mine.get(fmt, []) if e.startswith("Edit(")]
    rel = rules_file(root, fmt)
    path = root / rel
    done: list[str] = []
    verb = "wrote" if write else "would write"
    if fmt in ("codex", "grok"):
        text = _settings_text(root, rel)
        if fmt == "codex":
            new_text = _codex_text(entries)
        else:
            new_text, kept = grok_rules.merged(text, entries, before, rel)
            if kept:
                done.append(kept)
                return done
        claimed = list(entries)
        if new_text != text:
            done.append(f"{verb} ask rules into {rel}: {_change_summary(fmt, before, claimed, by_pattern, remotes(root))}")
            if write:
                regular_files.write_text_safely(root, path, new_text)
    else:
        was = settings_json.read_settings(root, path, syntax_of(fmt, rel))
        data = copy.deepcopy(was.data)
        claimed = _merge(fmt, data, entries, recorded, done)
        if data != was.data or (was.syntax == "json" and json.dumps(data) != json.dumps(was.data)):  # a file that takes comments keeps its own key order
            done.append(f"{verb} ask rules into {rel}: {_change_summary(fmt, before, claimed, by_pattern, remotes(root))}")
            if write:
                settings_json.save(root, path, was, data)
    if write and _record(root, fmt, claimed, done):
        done.append(f"wrote {config.HARNESS_RULES_FILE} (which ask rules aidd wrote, so a later run changes only those)")
    return done


def _change_summary(fmt: str, before: set[str], after: list[str], by_pattern: Mapping[str, str] | None, names: list[str]) -> str:
    """The entries a write adds and removes, by action: `added 2 (`git.tag.create` 2); removed 1 (`data.delete` 1)`. The
    entries of `before` (what aidd wrote last) and `after` (what it owns once this run is done) are all it reads."""
    owner: dict[str, str] = {}
    for pattern, action in (by_pattern or {}).items():
        for entry in command_entries(fmt, [pattern] if _writable(pattern) else [], names):
            owner.setdefault(entry, action)

    def count(entries: list[str]) -> str:
        by = Counter(owner.get(e) or ("secret.use" if e.startswith("Read(") else "code.edit" if e.startswith("Edit(") else "other") for e in entries)
        return f"{len(entries)} ({', '.join(f'`{a}` {n}' for a, n in sorted(by.items(), key=lambda x: (-x[1], x[0])))})"

    kept = set(after)
    added = [e for e in dict.fromkeys(after) if e not in before]
    removed = [e for e in sorted(before) if e not in kept]
    parts = [f"{word} {count(entries)}" for word, entries in (("added", added), ("removed", removed)) if entries]
    return "; ".join(parts) or "none added or removed, only their order or the file's text changes"


def _record(root: Path, fmt: str, claimed: list[str], done: list[str]) -> bool:
    """List the entries aidd owns in `fmt` in `.aidd/harness-rules.json`, when they or the file changed; whether it wrote."""
    mine = owned(root)
    # Claude Code's block may hold one entry twice (a re-include), so its record keeps each copy.
    claimed = list(claimed) if fmt == "claude-code" else sorted(set(claimed))
    if any(not d.startswith("kept") for d in done) or sorted(mine.get(fmt, [])) != sorted(claimed):
        mine[fmt] = sorted(claimed)
        # A key that names no format, such as the delegation's hooks, is another writer's, so it stays as it was.
        others = {k: v for k, v in _read_json(root, root / config.HARNESS_RULES_FILE).items() if k not in FORMATS}
        _write_json(root, root / config.HARNESS_RULES_FILE, {**others, **mine})
        return True
    return False


def _remove(fmt: str, data: dict, entries: list[str]) -> bool:
    """Take aidd's entries out of `data`; whether anything changed."""
    if fmt in ("claude-code", "qwen"):
        node = data.get("permissions")
        if not isinstance(node, dict) or not isinstance(node.get("ask"), list):
            return False
        # aidd's copies come first, as many as it wrote, so a later copy of one of its entries is the person's own.
        count = Counter(entries)
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
    """Each rule of the person's in `opencode.json` or `opencode.jsonc` that lets a command run with no prompt where the risk
    rules `patterns` ask, as `aidd doctor` says it (`opencode_rules.shadow_warnings`), and a note when both files are there."""
    here = [rel for rel in rule_files("opencode") if (Path(root) / rel).is_file()]
    out = []
    for rel in here:
        data = _read_json(root, Path(root) / rel, syntax_of("opencode", rel))
        out += opencode_rules.shadow_warnings(data, _entries("opencode", patterns), rel)
    if len(here) > 1:
        out.append(
            f"{' and '.join(here)} are both here, and OpenCode's docs do not say which wins; aidd writes its asks into {here[0]}. Merge them into one file"
        )
    return out


def remove_harness_rules(root: Path, *, write: bool = True) -> list[str]:
    """Take out every ask rule aidd wrote, and its record (`aidd uninstall`). What it did, one line each."""
    root = Path(root)
    mine = owned(root)
    done: list[str] = []
    verb = "removed" if write else "would remove"
    for fmt, entries in mine.items():
        for rel in rule_files(fmt):
            path = root / rel
            if not path.is_file():
                continue
            if refused := regular_files.write_refusal(root, path):  # never read, removed, or written through
                done.append(f"kept     {rel} ({refused})")
                continue
            if fmt == "codex":
                done.append(f"{verb} {rel}")
                if write:
                    path.unlink()
                continue
            if fmt == "grok":
                rest, why = grok_rules.without_block(_settings_text(root, rel), set(entries))
                if rest is None:
                    continue
                if why:
                    done.append(f"kept     aidd's block in {rel} ({why}); take it out by hand")
                    continue
                done.append(f"{verb} aidd's ask rules from {rel}")
                if write:
                    regular_files.write_text_safely(root, path, rest) if rest.strip() else path.unlink()
                continue
            was = settings_json.read_settings(root, path, syntax_of(fmt, rel))
            data = copy.deepcopy(was.data)
            if _remove(fmt, data, list(entries)):
                done.append(f"{verb} aidd's ask rules from {rel}")
                if write and documents.holds_nothing(data) and not jsonc.has_comments(was.text):
                    path.unlink()  # a file left holding only empty objects and lists, and no comment, was aidd's alone: it goes
                elif write:
                    settings_json.save(root, path, was, data)
    record = root / config.HARNESS_RULES_FILE
    if mine and record.is_file():
        done.append(f"{verb} {config.HARNESS_RULES_FILE}")
        if write:
            # A key that names no format, such as the MCP tools aidd allowed, is another writer's: it stays for that writer to take out.
            others = {k: v for k, v in _read_json(root, record).items() if k not in FORMATS}
            _write_json(root, record, others) if others else record.unlink()
    return done
