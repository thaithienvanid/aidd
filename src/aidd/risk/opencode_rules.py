"""OpenCode's ask rules in `opencode.json`, written in OpenCode v2's native `permissions` list. aidd supports
OpenCode v2 and later.

OpenCode v2 (read at v2.2.6) still reads v1's `permission` object, as the `shell` action for its `bash` key
(packages/core/src/v1/config/migrate.ts:27-31). It turns one file into one list, `[...toolRules, ...permissionRules,
...nativePermissions]` (packages/core/src/config/normalize.ts:179-182), and the last rule that matches wins
(packages/core/src/permission.ts:94-104). So every v1 entry comes before every native rule.

aidd writes its asks in the native list, in v2's form (`{"action": "shell", "resource": "<pattern>", "effect": "ask"}`,
https://opencode.ai/v2/docs/permissions), and starts the list when the file has none. Its asks go right after the
person's last native rule for every command (a resource of `*` alone), so no default of theirs, v1 or native, outranks
an ask. A native rule they wrote after that default still wins. aidd writes nothing when that default denies every
command, and never claims a pattern the person wrote after it. A person's own v1 entries stay where they are, since v2
still reads them. `shadow_warnings` names
each rule of the person's that still lets an asked command run with no prompt.

aidd also writes an `edit` ask for each test file of an approved Spec (`Edit(<resource>)` in its entries). It writes them
only when the file holds no edit rule of the person's, so there is no order to settle: it appends them. With any edit rule
of theirs, in `permission`, `tools`, an agent, or the list, it writes none and says why.
"""

from __future__ import annotations

import functools
import json
import re

from aidd.kernel import documents

ASK = "ask"
SHELL = "shell"
EDIT = "edit"
_RULE_KEYS = {"action", "resource", "effect"}
# The actions that edit a file: v2 names one, and v1 had three more, which `_action` maps to it.
_EDIT_ACTIONS = (EDIT, "write", "patch", "apply_patch")
# An entry for a file edit, as aidd records it: `Edit(<resource>)`. Any other entry is a shell pattern.
_EDIT_ENTRY = re.compile(r"Edit\((.+)\)", re.S)


def wildcard_match(text: str, pattern: str, *, fold: bool = False) -> bool:
    """Whether `text` matches `pattern` as OpenCode's `Wildcard.match` reads it (packages/core/src/util/wildcard.ts:3-14):
    `*` is any run, `?` one character, and a trailing ` *` also matches the bare command. With `fold`, case is ignored,
    as OpenCode does on Windows (wildcard.ts:13); aidd's checks fold it only where that reads stricter."""
    return _wildcard_regex(pattern, fold).fullmatch(text.replace("\\", "/")) is not None


@functools.lru_cache(maxsize=4096)
def _wildcard_regex(pattern: str, fold: bool) -> re.Pattern[str]:
    """`pattern` as a compiled regular expression, kept: doctor reads each pattern against every rule."""
    escaped = re.sub(r"[.+^${}()|\[\]\\]", lambda m: "\\" + m.group(0), pattern.replace("\\", "/"))
    escaped = escaped.replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    return re.compile(escaped, re.S | (re.I if fold else 0))


def _action(key: str) -> str:
    """A v1 key as v2 names its action (packages/core/src/v1/config/migrate.ts:27-31)."""
    return {"write": "edit", "patch": "edit", "apply_patch": "edit", "task": "subagent", "bash": SHELL}.get(key, key)


def _permission_rules(perm: object, where: str) -> list[tuple[str, str, str, str]]:
    """A v1 `permission` value as v2 reads it, in order: (action, resource, effect, how it is written, under `where`)."""
    if isinstance(perm, str):
        return [("*", "*", perm, f'`"{where}": "{perm}"`')]
    out: list[tuple[str, str, str, str]] = []
    for key, raw in perm.items() if isinstance(perm, dict) else []:
        if isinstance(raw, str):
            out.append((_action(key), "*", raw, f'`{where}.{key}: "{raw}"`'))
        elif isinstance(raw, dict):
            out += [(_action(key), res, eff, f'`"{res}": "{eff}"` in `{where}.{key}`') for res, eff in raw.items() if isinstance(eff, str)]
    return out


def _v1_rules(data: dict) -> list[tuple[str, str, str, str]]:
    """The file's `tools` and `permission` as v2 reads them, in order: (action, resource, effect, how it is written)."""
    out: list[tuple[str, str, str, str]] = []
    for key, on in (data.get("tools") or {}).items() if isinstance(data.get("tools"), dict) else []:
        if isinstance(on, bool):
            out.append((_action(key), "*", "allow" if on else "deny", f"`tools.{key}: {json.dumps(on)}`"))
    return out + _permission_rules(data.get("permission"), "permission")


def _native_rules(native: list, where: str = "permissions") -> list[tuple[str, str, str, str]]:
    return [
        (r["action"], r["resource"], r["effect"], f"`{json.dumps(r)}` in `{where}`")
        for r in native
        if isinstance(r, dict) and all(isinstance(r.get(k), str) for k in _RULE_KEYS)
    ]


def _agent_rules(data: dict) -> dict[str, list[tuple[str, str, str, str]]]:
    """Each agent's own rules, which OpenCode v2 adds after the file's (packages/core/src/config/plugin/agent.ts:71-102):
    v1's `agent` and `mode` (each `permission` migrated, migrate.ts:34-52), then v2's `agents`, a later one replacing
    an agent of the same name (normalize.ts:133-163). A disabled agent has none."""
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    for key, off in (("agent", "disable"), ("mode", "disable"), ("agents", "disabled")):
        for name, item in (data.get(key) or {}).items() if isinstance(data.get(key), dict) else []:
            if not isinstance(item, dict) or item.get(off) is True:
                out.pop(name, None)
            elif key == "agents":
                native = item.get("permissions")
                out[name] = _native_rules(native if isinstance(native, list) else [], f"agents.{name}.permissions")
            else:
                out[name] = _permission_rules(item.get("permission"), f"{key}.{name}.permission")
    return out


def rule_of(entry: str) -> dict[str, str]:
    """The native rule for one of aidd's entries: an `edit` ask for `Edit(<resource>)`, else a `shell` ask for the pattern."""
    edit = _EDIT_ENTRY.fullmatch(entry)
    return {"action": EDIT, "resource": edit[1], "effect": ASK} if edit else {"action": SHELL, "resource": entry, "effect": ASK}


def _is_aidds(rule: object, before: set[str]) -> bool:
    """A native rule aidd wrote: exactly a `shell` ask for a pattern it listed, or an `edit` ask for a path it listed."""
    if not isinstance(rule, dict) or set(rule) != _RULE_KEYS or rule["effect"] != ASK or not isinstance(rule["resource"], str):
        return False
    return rule["resource"] in before if rule["action"] == SHELL else rule["action"] == EDIT and f"Edit({rule['resource']})" in before


def _native(data: dict, rel: str) -> list | None:
    native = data.get("permissions")
    if native is not None and not isinstance(native, list):
        raise ValueError(f"{rel}: `permissions` is not a list; fix it, then run the command again")
    return native


# Commands of each shape a catch-all must match: one letter, one word, and several words with options and a path.
_EVERY_COMMAND = ("x", "make", "git push --force origin main", "rm -rf /tmp/a\\b")


def _broad(action: object, resource: object, *, fold: bool = True) -> bool:
    """Whether a rule is for every shell command: an action that names `shell`, and a resource that matches a command of
    every shape, however it is spelled (`*`, `**`, `* *`, `?*`). With `fold`, as on Windows, case is ignored too."""
    return (
        isinstance(action, str)
        and isinstance(resource, str)
        and wildcard_match(SHELL, action, fold=fold)
        and all(wildcard_match(c, resource, fold=fold) for c in _EVERY_COMMAND)
    )


def _after_default(rules: list[tuple[str, str, str, str]]) -> tuple[str | None, list[tuple[str, str, str, str]]]:
    """The effect of the person's last rule for every shell command (None without one), and the rules after it, which
    alone outrank aidd's asks. Each side takes the stricter reading of case: the default is the last rule that is one on
    every platform, case as written, so a mis-cased deny that OpenCode ignores off Windows never stops an ask; and the
    rules after it start past the last one on any platform, case folded, where aidd's asks go."""
    strict = max((i for i, (action, res, _, _) in enumerate(rules) if _broad(action, res, fold=False)), default=-1)
    at = max((i for i, (action, res, _, _) in enumerate(rules) if _broad(action, res)), default=-1)
    return (rules[strict][2] if strict >= 0 else None), rules[at + 1 :]


def evaluate(rules: list[tuple[str, str, str, str]], command: str, *, fold: bool = False) -> tuple[str, str]:
    """What OpenCode does with a shell `command`: the effect of the last rule that matches, and how that rule is written;
    `ask` when none does (packages/core/src/permission.ts:94-104). With `fold`, case is ignored, as on Windows
    (wildcard.ts:13)."""
    hits = [(eff, how) for action, res, eff, how in rules if wildcard_match(SHELL, action, fold=fold) and wildcard_match(command, res, fold=fold)]
    return hits[-1] if hits else (ASK, "")


def merge(data: dict, entries: list[str], before: set[str], rel: str, done: list[str]) -> list[str]:
    """Bring aidd's asks in `data`'s `permissions` list up to `entries`, keeping a person's own rules; the patterns aidd
    owns afterwards. Every v1 `permission` entry is the person's own: OpenCode v2 still reads them, and aidd writes none."""
    perm = data.get("permission")
    if perm is not None and not isinstance(perm, (dict, str)):
        raise ValueError(f"{rel}: `permission` is not an object; fix it, then run the command again")
    native = _native(data, rel)
    theirs = [r for r in native or [] if not _is_aidds(r, before)]
    edits = [e for e in entries if _EDIT_ENTRY.fullmatch(e)]
    # A person's rule for one of aidd's patterns counts only after their last default, where it still decides.
    wanted = _wanted(_v1_rules(data) + _native_rules(theirs), [e for e in entries if e not in edits], rel, done)
    broad = [i for i, r in enumerate(theirs) if isinstance(r, dict) and _broad(r.get("action"), r.get("resource"))]
    at = broad[-1] + 1 if broad else 0
    own_edits = _wanted_edits(data, theirs, edits, rel, done)
    rules = theirs[:at] + [rule_of(e) for e in wanted] + theirs[at:] + [rule_of(e) for e in own_edits]
    wanted += own_edits
    if rules or native is not None:
        data["permissions"] = rules
    return wanted


def _own_edit_rules(data: dict, theirs: list) -> list[str]:
    """Each edit rule of the person's in the file, how it is written: in `permission` or `tools` (v1's `write`, `patch`, and
    `apply_patch` count), in an agent's own rules, or in the `permissions` list (`theirs` is that list without aidd's rules).
    A rule for every action counts, since it covers an edit."""
    out = [how for action, _res, _eff, how in _v1_rules(data) if wildcard_match(EDIT, action, fold=True)]
    out += [how for rules in _agent_rules(data).values() for action, _res, _eff, how in rules if wildcard_match(EDIT, action, fold=True)]
    named = [
        r for r in theirs if isinstance(r, dict) and isinstance(r.get("action"), str) and any(wildcard_match(n, r["action"], fold=True) for n in _EDIT_ACTIONS)
    ]
    return [documents.one_line(how) for how in out + [f"`{json.dumps(r)}` in `permissions`" for r in named]]


def _wanted_edits(data: dict, theirs: list, edits: list[str], rel: str, done: list[str]) -> list[str]:
    """The `edit` asks aidd writes. OpenCode applies the last rule that matches, so an ask among a person's own edit rules
    raises ordering cases: a deny it would turn into an ask, an allow it would not outrank. So aidd writes the asks only when
    the file holds no edit rule of the person's, and then appends them. Otherwise it writes none, and says why."""
    own = _own_edit_rules(data, theirs) if edits else []
    if own:
        done.append(
            f"kept     {rel} (it has edit rules of your own, such as {own[0]}, so aidd writes no ask for the frozen tests of an approved Spec: "
            "it would have to order its asks around yours. a person's review of the pull request, and a delegated merge's check, are the controls)"
        )
    return [] if own else edits


def _wanted(rules: list[tuple[str, str, str, str]], entries: list[str], rel: str, done: list[str]) -> list[str]:
    """The patterns aidd writes, given the person's own rules: none under a default that denies every command, and none
    the person wrote for `shell` after that default, where their rule decides."""
    default, after = _after_default(rules)
    if default == "deny":
        done.append(f"kept     {rel} (its default denies every command, which is stricter than aidd's ask rules)")
        return []
    own = {res: eff for action, res, eff, _ in after if action == SHELL}
    kept_own = [e for e in entries if e in own and own[e] != ASK]
    if kept_own:
        done.append(f"kept     your own {rel} rules for {', '.join(f'`{e}`' for e in kept_own)}")
    return [e for e in entries if e not in own]


def remove(data: dict, entries: list[str]) -> bool:
    """Take aidd's asks out of `data`'s `permissions` list; whether anything changed. A list aidd empties goes."""
    before = set(entries)
    native = data.get("permissions")
    if isinstance(native, list) and any(_is_aidds(r, before) for r in native):
        left = [r for r in native if not _is_aidds(r, before)]
        data["permissions"] = left
        if not left:
            del data["permissions"]
        return True
    return False


def _shadowing(rules: list[tuple[str, str, str, str]], entries: list[str]) -> dict[str, list[str]]:
    """Each allow that lets a command an ask pattern names run with no prompt, by how it is written: the last rule that
    matches the pattern read as a command, and any narrower allow after an ask for that pattern whose resource, read
    as a command, the pattern matches (`git push origin main` after `git push * main`)."""
    out: dict[str, list[str]] = {}
    for p in entries:
        for fold in (False, True):  # an allow on either platform, case as written or folded as on Windows
            effect, how = evaluate(rules, p, fold=fold)
            if effect == "allow" and p not in out.get(how, []):
                out.setdefault(how, []).append(p)
    asked = {res: i for i, (action, res, eff, _) in reversed(list(enumerate(rules))) if eff == ASK and action == SHELL}
    for i, (action, res, eff, how) in enumerate(rules):
        if eff != "allow" or not wildcard_match(SHELL, action, fold=True):
            continue
        for p in entries:
            if asked.get(p, i) < i and wildcard_match(res, p, fold=True) and p not in out.get(how, []):
                out.setdefault(how, []).append(p)
    return out


def shadow_warnings(data: dict, entries: list[str], rel: str) -> list[str]:
    """Each rule of the person's in `rel`, the file's own or an agent's, that lets a command an ask pattern names run
    with no prompt, since OpenCode applies the last rule that matches: one line per rule, with the next step. An
    agent's rules come after the file's (packages/core/src/config/plugin/agent.ts:71-102), so each agent is read with
    them. aidd reads no other OpenCode config, and each line says so."""
    native = data.get("permissions")
    rules = _v1_rules(data) + _native_rules(native if isinstance(native, list) else [])
    out = []
    for agent, extra in [(None, [])] + list(_agent_rules(data).items()):
        own = {r[3] for r in extra}
        for how, hit in _shadowing(rules + extra, entries).items():
            if agent is not None and how not in own:
                continue  # the file's own rule, named once without an agent
            named = ", ".join(f"`{p}`" for p in hit[:3]) + (f" and {len(hit) - 3} more" if len(hit) > 3 else "")
            out.append(
                f"your rule {documents.one_line(how)} in {rel}{f' (the `{documents.one_line(agent, 80)}` agent)' if agent else ''} lets {named} run with no prompt, though "
                "the risk rules ask for them, because OpenCode applies the last rule that matches. If they should ask, delete "
                "that rule or move it before aidd's asks. aidd reads only this file: the system and global config, `.opencode/`, "
                "`opencode.jsonc`, managed preferences, agent files, and a session's rules can also come after its asks"
            )
    return out
