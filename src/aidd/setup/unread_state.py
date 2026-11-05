"""What an older aidd stored that this aidd does not read, for `aidd upgrade` and `aidd doctor` to report.

Three things carry over a version: a Spec with no `status` that commits already name, an approval in the old
`refs/aidd/approvals`, and a config field this aidd removed. The first is pre-1.0 state only: a repository with old
approvals, or a Spec an older aidd wrote. A 1.0.0 stub has no `status` by design, so a commit that names it is no note. Each is a note with its next step. Nothing here writes a
file, because a status is the agent's to set from the person's words, and an old approval is history, never a yes.
For a removed config field, `retire_config_fields` gives the text `aidd upgrade --yes` writes: each block kept as a
comment, and `owners.default_team` renamed. The caller writes it, never this module.
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd import __version__, config, workitems
from aidd.kernel import documents, git, json_schema
from aidd.setup import self_updating

APPROVALS_REF = "refs/aidd/approvals"
# The first release whose Spec has a `status`: a Spec an older aidd wrote, or old approvals, is state to carry over.
FIRST_STATUS_RELEASE = "1.0.0"
# The most commits read to count those that name a Spec.
MAX_COMMITS = 2000

# The retired fields with a direct replacement, the one table of them: (the field it moved to, or None, and what the
# note says). A field that moved within its own block is renamed by `aidd upgrade --yes`, unless the config sets the new
# one already. Every other field this aidd does not know gets the one note, _UNKNOWN.
_REPLACED: dict[str, tuple[str | None, str]] = {
    "identities": (
        None,
        "it listed bot and system accounts. aidd now reads a bot from its `[bot]` suffix or a built-in name such as `web-flow`, and an agent "
        "from an `agent:` identity or aidd's list of known agent accounts, commit emails, and names, so nothing replaces it. An account you "
        "listed that has no `[bot]` suffix and no built-in name now reads as a person: record its work under an `agent:` identity",
    ),
    "owners.default_team": ("owners.default_owner_team", "it is now `owners.default_owner_team`, the `owner_team` that `aidd new` writes"),
    "runbook_max_age_days": (
        "docs.max_runbook_age_days",
        "it set the days before a runbook counts as stale. It is now `docs.max_runbook_age_days`: re-create it there",
    ),
}
# The locks a gate-era config could name that this aidd retired with their fields, and the profiles it dropped.
_RETIRED_LOCKS = ("disable_rules", "rule_exclusions", "scope_exempt_paths", "budget_exclude_paths", "standard_changes", "tenant")
_RETIRED_PROFILES = ("org", "audited")
# What the note says of every other field this aidd does not know, whatever an older aidd used it for.
_UNKNOWN = (
    "this aidd does not read it. `aidd risk --list` shows the rules in force, and docs/CONFIG.md every field this aidd reads, if you still need what it did"
)
_UNKNOWN_FIELD = re.compile(r"^\$([^:]*): unknown field '([^']+)'$")
# The config's `aidd_version` line, which `aidd upgrade` rewrites as text so every other line keeps its form.
CONFIG_VERSION_LINE = re.compile(r"^aidd_version:[ ]*(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)", re.M)
_WORK_ID = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")


def unread_state(root: Path, config_text: str | None = None) -> list[tuple[str, str]]:
    """The notes for `root`, as (level, message): `warn` for a Spec to set and a field to remove, `info` for old approvals.
    `config_text` is the config as a dry run would leave it, in place of the file."""
    approvals = _old_approval_entries(root)
    return [*_specs_without_status(root, approvals), *_old_approvals(approvals), *_removed_config_fields(root, config_text)]


def _specs_dir(root: Path) -> str:
    """The Specs folder the config names, read as plain YAML so a config this aidd rejects still answers."""
    try:
        data = documents.parse_yaml((root / config.CONFIG_PATH).read_text(encoding="utf-8"), config.CONFIG_PATH)
    except (OSError, UnicodeDecodeError, documents.DocumentError):
        return "specs"
    return str(data.get("specs_dir") or "specs") if isinstance(data, dict) else "specs"


def _scope(data: dict) -> list[str]:
    """The paths of a Spec's Tasks, leaving out a placeholder and a path git would read as a pathspec of its own."""
    tasks = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    scope = [str(p) for t in tasks if isinstance(t.get("scope"), list) for p in t["scope"]]
    return [p for p in scope if p and "TODO" not in p and not p.startswith((":", "-"))]


def _older_spec(data: dict) -> bool:
    """Whether an aidd before the first release with a Spec `status` wrote this Spec, by its `aidd_version`."""
    version = data.get("aidd_version")
    return version is not None and self_updating.version_key(str(version)) < self_updating.version_key(FIRST_STATUS_RELEASE)


def _specs_without_status(root: Path, approvals: tuple[int, set[str]]) -> list[tuple[str, str]]:
    """Each pre-1.0 Spec with no `status` whose commits name it. "Again" only for a Spec the old approvals name."""
    entries, approved = approvals
    out = []
    for path in workitems.object_files(root, _specs_dir(root)):
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())
        except (OSError, UnicodeDecodeError, documents.DocumentError):
            continue
        sid = str(data.get("id") or path.stem)
        if data.get("type") != "spec" or "status" in data or not (entries or _older_spec(data)) or not (scope := _scope(data)):
            continue
        shas = [r[0] for r in git.log_fields([f"-{MAX_COMMITS}", "--no-merges", "HEAD", "--", *scope], ["%H"], str(root), check=False)]
        named = sum(1 for m in git.messages(shas, str(root)).values() if sid in workitems.work_ids_in(m, {sid})) if shas else 0
        if named:
            out.append(
                (
                    "warn",
                    f"{sid} has no `status`, and {named} commit{'s' if named != 1 else ''} that name{'' if named != 1 else 's'} it touch{'' if named != 1 else 'es'} its Tasks' scope: "
                    f"set `status: ready` and ask for Spec approval{' again' if sid in approved else ''}, because a status past approval needs a person's yes. "
                    "Your agent sets it from your words; this report writes nothing",
                )
            )
    return out


def _old_approval_entries(root: Path) -> tuple[int, set[str]]:
    """How many entries the old approvals ref holds, and the work IDs they name."""
    refs = [line.split() for line in git.run(["for-each-ref", "--format=%(refname) %(objecttype)", APPROVALS_REF], str(root), check=False).splitlines()]
    entries, named = 0, set()
    for ref, kind in (r for r in refs if len(r) == 2):
        if kind != "commit":
            entries += 1
            continue
        entries += int(git.run(["rev-list", "--count", ref], str(root), check=False).strip() or 0)
        listed = git.run(["log", "--format=%s", ref], str(root), check=False) + git.run(["ls-tree", "-r", "--name-only", ref], str(root), check=False)
        named |= set(_WORK_ID.findall(listed))
    return entries, named


def _old_approvals(approvals: tuple[int, set[str]]) -> list[tuple[str, str]]:
    entries, named = approvals
    if not entries:
        return []
    names = f", naming {', '.join(sorted(named))}" if named else ""
    return [
        (
            "info",
            f"{APPROVALS_REF} holds {entries} {'entry' if entries == 1 else 'entries'} from an older aidd{names}. This aidd does not read them: "
            "they are history only and never a yes, so a Spec still needs its approval asked again where a risk rule asks",
        )
    ]


def _about(field: str) -> str:
    """What the note says of the removed `field`: its replacement's line, else the one line for every other field."""
    return _REPLACED[field][1] if field in _REPLACED else _UNKNOWN


def _unknown_fields(data: dict) -> list[str]:
    """Each field of the config that the schema does not know, by its dotted path such as `owners.default_team`."""
    found = (_UNKNOWN_FIELD.match(finding) for finding in json_schema.validate(data, "config.schema.json"))
    return [(m.group(1) + "." + m.group(2)).lstrip(".") for m in found if m]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _key_line(lines: list[str], key: str, window: range, floor: int) -> tuple[int, int] | None:
    """(index, indent of the key) of the first line in `window` that sets `key`, at the shallowest indent that does, deeper than `floor`.
    A `- key:` line counts at the key's own column."""
    found = []
    for i in window:
        if m := re.match(rf"(\s*)(-\s+)?(\"?){re.escape(key)}\3\s*:(\s|$)", lines[i]):
            found.append((i, len(m.group(1)) + len(m.group(2) or "")))
    found = [f for f in found if f[1] > floor]
    return min(found, key=lambda f: f[1]) if found else None


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """The index of the last line of the block whose key is on `start`: the lines after it that are deeper than `indent`, and a
    list at the key's own indent when the key holds none. A blank line or a comment, at any column, never ends a block, as the
    parser skips both. Those at its end belong to what follows."""
    rest = lines[start].split(":", 1)[1].strip()
    bare = not rest or rest.startswith("#")
    end = start
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _indent(line) > indent or (bare and _indent(line) == indent and line.lstrip().startswith("- ")):
            end = i
        else:
            break
    return end


def retired_block(text: str, field: str) -> tuple[int, int] | None:
    """The first and last line (counted from 1) of the block that sets `field` in the config `text`, or None. The block is the
    key's line and every line after it that is blank, a comment, or indented deeper than the key, up to the first line of text
    at or above it. A blank line or a comment at its very end belongs to the next block. A dotted `field` is looked up inside its parent's block.
    This reads lines, not YAML, and a list index in `field` is ignored."""
    lines = text.splitlines()
    window, floor, found = range(len(lines)), -1, None
    for key in re.sub(r"\[\d+\]", "", field).split("."):
        if (found := _key_line(lines, key, window, floor)) is None:
            return None
        end = _block_end(lines, found[0], found[1])
        window, floor = range(found[0] + 1, end + 1), found[1]
    return (found[0] + 1, end + 1) if found else None


def _span(first: int, last: int) -> str:
    return f"line {first}" if first == last else f"lines {first} to {last}"


def _renamed_to(data: dict, field: str) -> str | None:
    """The field `field` is now called, when it moved within its own block and the config does not set that one already."""
    target = _REPLACED.get(field, (None, ""))[0]
    if not target or target.rpartition(".")[0] != field.rpartition(".")[0]:
        return None
    if target.rsplit(".", 1)[-1] in (data.get(target.split(".")[0]) or {}):
        return None
    return target


def _removed_config_fields(root: Path, config_text: str | None = None) -> list[tuple[str, str]]:
    try:
        text = (root / config.CONFIG_PATH).read_text(encoding="utf-8") if config_text is None else config_text
        data = documents.parse_yaml(text, config.CONFIG_PATH)
    except (OSError, UnicodeDecodeError, documents.DocumentError):
        return []
    if not isinstance(data, dict):
        return []
    fix, problems = _retire(text, dry_run=True)
    fixable = fix is not None
    out = list(_retired_values(text, data))
    for field in _unknown_fields(data):
        key = field.split(".")[-1]
        block = retired_block(text, field)
        if block is None:
            first = f"remove `{field}` first"
        elif _renamed_to(data, field):
            first = f"rename `{key}` to `{str(_renamed_to(data, field)).split('.')[-1]}` on {_span(*block)} first"
        elif block[0] == block[1]:
            first = f"remove line {block[0]} (`{text.splitlines()[block[0] - 1].strip()}`) first"
        else:
            first = f"remove lines {block[0]} to {block[1]} (`{key}:` and the lines under it) first"
        about = _about(field)
        does = (
            " `aidd upgrade --yes` does this and keeps each block as a comment. It changes your config, so your agent asks you once first." if fixable else ""
        )
        out.append(
            ("warn", f"{config.CONFIG_PATH}: {first}, because this aidd cannot load a config that holds `{field}`. {about[0].upper() + about[1:]}.{does}")
        )
    if problems and not fixable:
        out.append(
            (
                "warn",
                f"{config.CONFIG_PATH}: `aidd upgrade --yes` leaves the retired fields as they are, because the config would still not load: "
                + "; ".join(problems),
            )
        )
    return out


def _retired_values(text: str, data: dict) -> list[tuple[str, str]]:
    """The notes for a profile or a lock a gate-era config named and this aidd dropped. `aidd upgrade --yes` maps neither:
    who approves is the person's choice."""
    out = []
    profile = data.get("profile")
    if profile in _RETIRED_PROFILES and (block := retired_block(text, "profile")):
        out.append(
            (
                "warn",
                f"{config.CONFIG_PATH}: line {block[0]} (`profile: {profile}`): this aidd has no `{profile}` profile, so it cannot load the config. "
                "`team` is the strictest profile now: it asks for Spec approval on normal and major changes, and a person merges through the platform's review. "
                "Choose `solo` or `team`; your agent asks you which, because who approves is your choice, and `aidd upgrade --yes` does not change it",
            )
        )
    locks = [v for v in data.get("locks") or [] if v in _RETIRED_LOCKS]
    if locks and (block := retired_block(text, "locks")):
        names = ", ".join(f"`{v}`" for v in locks)
        out.append(
            (
                "warn",
                f"{config.CONFIG_PATH}: `locks` on {_span(*block)} names {names}, which this aidd retired, so it cannot load the config. "
                "To load it, remove them from `locks`; `aidd upgrade --yes` does not change it",
            )
        )
    return out


def retire_config_fields(text: str, *, dry_run: bool = False) -> tuple[str, list[str]] | None:
    """The config `text` without the fields this aidd removed, as (the text to write, one line for each field saying what was
    done and what the field did), or None. Each removed field's block stays as a comment under a line saying when it retired,
    and `owners.default_team` is renamed when the config does not set `default_owner_team`; if it does, the old key is
    commented out and the new one kept. The text to write also carries this aidd's `aidd_version`. None when no field is
    removed, or when that exact text would fail the schema in any way: the caller then writes nothing. With `dry_run`, the
    lines say what would happen."""
    return _retire(text, dry_run)[0]


def _retire(text: str, dry_run: bool) -> tuple[tuple[str, list[str]] | None, list[str]]:
    """`retire_config_fields`, and with it the problems that stopped the fix, each as a line to show: a block it cannot bound,
    a retired key a list dash opens, or a finding the new text still has."""
    try:
        data = documents.parse_yaml(text, config.CONFIG_PATH)
    except documents.DocumentError as exc:
        return None, [str(exc)]
    fields = _unknown_fields(data) if isinstance(data, dict) else []
    lines, edits, problems = text.splitlines(), [], []
    for field in fields:
        block = retired_block(text, field)
        if block is None:
            problems.append(f"`{field}` has no block this aidd can find")
        elif lines[block[0] - 1].lstrip().startswith("-"):
            problems.append(f"`{field}` opens a list item on line {block[0]}")
        else:
            edits.append((block, field, _renamed_to(data, field)))
    if problems or not edits:
        return None, problems
    edits.sort(reverse=True)  # the last block first, so the line numbers of the others hold
    steps = []
    for (first, last), field, target in edits:
        pad, key = " " * _indent(lines[first - 1]), field.split(".")[-1]
        if target:
            lines[first - 1] = re.sub(rf"^(\s*)(\"?){re.escape(key)}\2(\s*:)", rf"\1\g<2>{target.split('.')[-1]}\g<2>\3", lines[first - 1], count=1)
            what = f"`{field}` ({_span(first, last)}) {'would be renamed' if dry_run else 'is renamed'}, and its value kept"
        else:
            note = f"{pad}# Retired in aidd {__version__}; kept as a comment, and aidd reads it no more:"
            lines[first - 1 : last] = [note] + [
                (pad + "# " + line[len(pad) :] if line.startswith(pad) else "# " + line) if line.strip() else "" for line in lines[first - 1 : last]
            ]
            what = f"`{field}` ({_span(first, last)}) {'would become a comment' if dry_run else 'is a comment now'}"
        steps.append(f"{what}. {_about(field)[0].upper() + _about(field)[1:]}.")
    new = CONFIG_VERSION_LINE.sub(f'aidd_version: "{__version__}"', "\n".join(lines) + ("\n" if text.endswith("\n") else ""), count=1)
    try:
        findings = json_schema.validate(documents.parse_yaml(new, config.CONFIG_PATH), "config.schema.json")
    except documents.DocumentError as exc:
        return None, [str(exc)]
    return (None, findings) if findings else ((new, steps[::-1]), [])
