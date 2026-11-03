"""The harness ask rules: each `ask` risk rule's command patterns written as a coding agent's own permission prompt, so
the agent's harness asks the person even when the agent forgets to.

Each format follows its harness's own documentation (read 2026-11-03). A pattern is a glob over one simple command
(`git push --force*`, `git push * main`); each format holds it as its harness matches commands:

- By glob, as written: Claude Code (`permissions.ask`, `Bash(<pattern>)`, `.claude/settings.json`), OpenCode
  (`permission.bash`, `"<pattern>": "ask"`, `opencode.json`), and Grok Build (`[permission] ask`, `Bash(<pattern>)`,
  `.grok/config.toml`, in a block aidd marks).
- By regular expression, exactly: Augment's CLI (`toolPermissions`, `shellInputRegex` with `ask-user`,
  `.augment/settings.json`) and VS Code's Copilot agent (`chat.tools.terminal.autoApprove`, `"/<regex>/": false`,
  `.vscode/settings.json`).
- By leading words, with no wildcard: Codex (`prefix_rule`, `.codex/rules/aidd.rules`), Factory Droid
  (`permissionRules`, `match.prefix`, `.factory/settings.json`), Devin's CLI (`permissions.ask`, `Exec(<prefix>)`,
  `.devin/config.json`), and Qwen Code (`permissions.ask`, `Bash(<prefix> *)`, `.qwen/settings.json`). A trailing `*`
  drops, a `*` between words becomes the common remotes, `origin` and `upstream` (a list where the format has one,
  else one rule each),
  and `*:main` becomes `HEAD:main`. A pattern with no such form (`git push * +*`) is left to the skill, and
  `unwritten` names it for `aidd doctor`.

A rule narrowed by an area or a role has no command form, so only the rules an action has on its own count, and a
`git.push` rule on the `default` branch becomes patterns that name that branch. aidd changes only what it wrote: the
entries it wrote are listed in `.aidd/harness-rules.json`. A person's own entries stay as they are, and aidd never
puts an ask where it would undo their deny.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import re
import tomllib
from pathlib import Path

from aidd import config
from aidd.kernel import documents
from aidd.risk.rules import RuleSet, level_of


@dataclasses.dataclass(frozen=True)
class Format:
    path: str  # the file, relative to the repository's top
    match: str  # glob, regex, or words: how the harness matches a command
    shape: str  # what aidd writes there, for the docs


FORMATS: dict[str, Format] = {
    "claude-code": Format(".claude/settings.json", "glob", "`permissions.ask`: `Bash(git push --force*)`"),
    "opencode": Format("opencode.json", "glob", '`permission.bash`: `{"git push --force*": "ask"}`'),
    "codex": Format(".codex/rules/aidd.rules", "words", '`prefix_rule(pattern = ["git", "push", ["origin", "upstream"], "main"], decision = "prompt")`'),
    "grok": Format(".grok/config.toml", "glob", '`[permission] ask = ["Bash(git push --force*)"]`, in a block aidd marks'),
    "qwen": Format(".qwen/settings.json", "words", "`permissions.ask`: `Bash(git push --force)` and `Bash(git push --force *)`"),
    "devin": Format(".devin/config.json", "words", "in its CLI, `permissions.ask`: `Exec(git push --force)`"),
    "factory": Format(".factory/settings.json", "words", '`permissionRules`: `{"id": "aidd/...", "decision": "ask", "match": {"prefix": [...]}}`'),
    "augment": Format(
        ".augment/settings.json",
        "regex",
        'in its `auggie` CLI, `toolPermissions`: `{"toolName": "bash", "shellInputRegex": "...", "permission": {"type": "ask-user"}}`',
    ),
    "vscode": Format(".vscode/settings.json", "regex", 'in VS Code\'s agent, `chat.tools.terminal.autoApprove`: `{"/^git push --force.*$/": false}`'),
}
MATCHES = {"glob": "by glob, as written", "regex": "by regular expression, exactly", "words": "by leading words, with no wildcard"}
# The formats whose leading-words rules take a list of alternatives at one position; the others get one rule per remote.
ALTERNATIVES = frozenset({"codex", "factory"})
# The remotes a `*` between words stands for, beside the repository's own.
COMMON_REMOTES = ("origin", "upstream")
_PLAIN = re.compile(r"[^*]+")
_WORD = re.compile(r"[-\w.]*\w")  # a whole word, so a trailing `*` may drop
_TOML_BEGIN = "# >>> aidd: the ask rules aidd writes from the risk rules. `aidd upgrade` rewrites this block."
_TOML_END = "# <<< aidd"


def harness_patterns(rs: RuleSet, default_branch: str | None) -> list[str]:
    """The command patterns of every action that asks on any branch, and the default-branch push patterns when a push
    to it asks; each once, in the order of the actions."""
    out: list[str] = []
    for action, spec in rs.actions.items():
        # A harness cannot tell one branch from another, so an action asks there when it asks on any branch. `git.push`
        # is the one exception: a push to the agent's own branch stays allowed, and the default branch gets its own
        # patterns below.
        branches = (None,) if action == "git.push" else (None, "own", "default", "shared")
        if any(level_of(rs, action, branch=b)[0] == "ask" for b in branches):
            out += spec.get("commands", [])
    if default_branch and level_of(rs, "git.push", branch="default")[0] == "ask":
        b = default_branch
        for dest in (b, f"*:{b}", f"+{b}", f"refs/heads/{b}", f"*:refs/heads/{b}"):
            out += [f"git push * {dest}", f"git push * {dest} *"]
        out += ["git push --all*", "git push --mirror*", "git push * --all*", "git push * --mirror*"]
    return list(dict.fromkeys(" ".join(p.split()) for p in out))


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
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _object(data: dict, key: str, rel: str) -> dict:
    """`data[key]`, made an empty object when missing; refused when it holds something else."""
    if not isinstance(data.setdefault(key, {}), dict):
        raise ValueError(f"{rel}: `{key}` is not an object; fix it, then run the command again")
    return data[key]


def owned(root: Path) -> dict[str, list[str]]:
    """What aidd wrote before, by harness format (`.aidd/harness-rules.json`)."""
    data = _read_json(root / config.HARNESS_RULES_FILE)
    return {k: [str(x) for x in v] for k, v in data.items() if k in FORMATS and isinstance(v, list)}


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
    # is left to the skill; and `*:<branch>` is written as `HEAD:<branch>` only.
    partly = lambda p: "*" in p.split()[:-1] or any(w.startswith("*:") for w in p.split())  # noqa: E731
    return [p for p in patterns if not _writable(p) or (words and (codex_words(p, list(COMMON_REMOTES)) is None or partly(p)))]


def _entries(fmt: str, patterns: list[str], remote_names: list[str] | None = None) -> list[str]:
    """The entries a format holds for `patterns`, each the string aidd records it by."""
    names = remote_names or list(COMMON_REMOTES)
    patterns = [p for p in patterns if _writable(p)]
    if fmt in ("claude-code", "grok"):
        return [f"Bash({p})" for p in patterns]
    if fmt == "opencode":
        return list(patterns)
    if FORMATS[fmt].match == "regex":
        return list(dict.fromkeys(glob_regex(p) for p in patterns))
    words = [w for w in (codex_words(p, names) for p in patterns) if w]
    if fmt in ALTERNATIVES:
        return list(dict.fromkeys(json.dumps(w) for w in words))
    prefixes = list(dict.fromkeys(e for w in words for e in _expanded(w)))
    if fmt == "devin":
        return [f"Exec({p})" for p in prefixes]
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


def _factory_rule(entry: str) -> dict:
    words = json.loads(entry)
    first = _expanded(words)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:40]
    digest = hashlib.sha256(entry.encode("utf-8")).hexdigest()[:10]
    return {
        "id": f"aidd/{slug}-{digest}",
        "decision": "ask",
        "match": {"prefix": words},
        "reason": "an ask risk rule (`aidd risk --list`)",
        "tests": {"match": [first], "noMatch": ["aidd-never-a-command"]},
    }


def _merge(fmt: str, rel: str, data: dict, entries: list[str], before: set[str], done: list[str]) -> list[str]:
    """Bring aidd's entries in `data` up to `entries`, keeping a person's own; the entries aidd owns afterwards."""
    if fmt in ("claude-code", "qwen", "devin"):
        node = _object(data, "permissions", rel)
        current = [e for e in node.get("ask", []) if isinstance(e, str)]
        kept = [e for e in current if e not in before or e in entries]
        node["ask"] = kept + [e for e in entries if e not in kept]
        return [e for e in entries if e in before or e not in current]
    if fmt == "opencode":
        perm = _object(data, "permission", rel)
        old = perm.get("bash")
        bash = dict(old) if isinstance(old, dict) else ({"*": old} if isinstance(old, str) else {})
        # OpenCode applies the last rule that matches. The person's entries keep their order; aidd's asks go right
        # after their `*` (first, without one), so a rule they wrote after it still wins and their `*` never does. aidd
        # writes nothing when their `*` denies every command.
        theirs = {k: v for k, v in bash.items() if not (k in before and v == "ask")}
        default = theirs.get("*")
        wanted: list[str] = [] if default == "deny" else [e for e in entries if e not in theirs]
        if default == "deny":
            done.append(f"kept     {rel} (its default denies every command, which is stricter than aidd's ask rules)")
        kept_own = [e for e in entries if e in theirs and theirs[e] != "ask"]
        if kept_own:
            done.append(f"kept     your own {rel} rules for {', '.join(f'`{e}`' for e in kept_own)}")
        keys = list(theirs)
        at = keys.index("*") + 1 if "*" in theirs else 0
        merged = {k: theirs[k] for k in keys[:at]} | {e: "ask" for e in wanted} | {k: theirs[k] for k in keys[at:]}
        if list(merged.items()) != list(bash.items()):
            perm["bash"] = merged
        return wanted
    if fmt == "vscode":
        # A `false` rule asks, and always wins over a `true` one, so order does not matter; a person's key stays theirs.
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
    if fmt == "augment":
        # Rules match top to bottom, the first one deciding. The person's rules keep their order, and aidd's asks go
        # after their leading deny rules. Where a deny of theirs comes after another rule, an ask before it could undo
        # it, so aidd writes nothing and says so.
        arules = data.get("toolPermissions", [])
        if not isinstance(arules, list):
            raise ValueError(f"{rel}: `toolPermissions` is not a list; fix it, then run the command again")

        def kind(r: object) -> str:
            return str((r.get("permission") or {}).get("type")) if isinstance(r, dict) else ""

        def mine(r: object) -> bool:
            return isinstance(r, dict) and r.get("shellInputRegex") in before and kind(r) == "ask-user"

        atheirs = [r for r in arules if not mine(r)]
        lead = next((i for i, r in enumerate(atheirs) if kind(r) != "deny"), len(atheirs))
        if any(kind(r) == "deny" for r in atheirs[lead:]):
            done.append(
                f"kept     {rel} (a deny rule of yours follows another rule, so an ask before it could undo it; add aidd's ask rules by hand: `aidd risk --list`)"
            )
            if atheirs != arules:
                data["toolPermissions"] = atheirs
            return []
        own_asks = {r.get("shellInputRegex") for r in atheirs if kind(r) == "ask-user" and isinstance(r, dict)}
        wanted = [e for e in entries if e not in own_asks]  # a person's identical rule stays theirs
        aasks = [{"toolName": "bash", "shellInputRegex": e, "permission": {"type": "ask-user"}} for e in wanted]
        if aasks or arules:
            data["toolPermissions"] = atheirs[:lead] + aasks + atheirs[lead:]
        return wanted
    # factory: rules by id, accumulated with the person's; `block` beats `ask` beats `allow`, so order does not matter.
    fnode = _object(data, "permissionRules", rel)
    if fnode.get("version", 1) != 1:
        raise ValueError(f"{rel}: `permissionRules` version {fnode.get('version')!r} is not one aidd writes; add the ask rules by hand")
    fnode["version"] = 1
    fcurrent = [r for r in fnode.get("rules", []) if isinstance(r, dict)]
    fours = [_factory_rule(e) for e in entries]
    ids = {r["id"] for r in fours}
    ftheirs = [r for r in fcurrent if not (str(r.get("id", "")).startswith("aidd/") and json.dumps(r.get("match", {}).get("prefix")) in before)]
    clash = [str(r["id"]) for r in ftheirs if isinstance(r.get("id"), str) and r.get("id") in ids]
    if clash:
        done.append(f"kept     your own {rel} rules with the ids {', '.join(clash)}, so aidd's rules of those ids are not written")
    fours = [r for r in fours if r["id"] not in clash]
    fnode["rules"] = ftheirs + fours
    return [json.dumps(r["match"]["prefix"]) for r in fours]


def apply_harness_rules(root: Path, fmt: str, patterns: list[str], *, write: bool = True) -> list[str]:
    """Bring one harness's ask rules up to `patterns`: add what is missing, remove what aidd wrote before and no longer
    wants, and keep everything else. What it did (or would do, without `write`), one line each."""
    root = Path(root)
    mine = owned(root)
    before = set(mine.get(fmt, []))
    entries = _entries(fmt, patterns, remotes(root))
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
    if write and (any(not d.startswith("kept") for d in done) or sorted(before) != sorted(claimed)):
        mine[fmt] = sorted(set(claimed))
        _write_json(root / config.HARNESS_RULES_FILE, mine)
    return done


def _remove(fmt: str, data: dict, entries: set[str]) -> bool:
    """Take aidd's entries out of `data`; whether anything changed."""
    if fmt in ("claude-code", "qwen", "devin"):
        node = data.get("permissions")
        if not isinstance(node, dict) or not isinstance(node.get("ask"), list):
            return False
        left = [e for e in node["ask"] if e not in entries]
        if left == node["ask"]:
            return False
        node["ask"] = left
        if not left:
            node.pop("ask")
        return True
    if fmt == "opencode":
        perm = data.get("permission")
        bash = perm.get("bash") if isinstance(perm, dict) else None
        gone = [e for e in entries if isinstance(bash, dict) and bash.get(e) == "ask"]
        for e in gone:
            del bash[e]  # type: ignore[union-attr]
        return bool(gone)
    if fmt == "vscode":
        node = data.get("chat.tools.terminal.autoApprove")
        gone = [k for k in (node or {}) if isinstance(node, dict) and k[1:-1] in entries and node[k] is False]
        for k in gone:
            del node[k]  # type: ignore[union-attr]
        return bool(gone)
    if fmt == "augment":
        rules = data.get("toolPermissions")
        if not isinstance(rules, list):
            return False
        left = [r for r in rules if not (isinstance(r, dict) and r.get("shellInputRegex") in entries and (r.get("permission") or {}).get("type") == "ask-user")]
        data["toolPermissions"] = left
        return len(left) != len(rules)
    node = data.get("permissionRules")
    if not isinstance(node, dict) or not isinstance(node.get("rules"), list):
        return False
    left = [
        r
        for r in node["rules"]
        if not (isinstance(r, dict) and str(r.get("id", "")).startswith("aidd/") and json.dumps(r.get("match", {}).get("prefix")) in entries)
    ]
    changed = len(left) != len(node["rules"])
    node["rules"] = left
    return changed


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
        if _remove(fmt, data, set(entries)):
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
