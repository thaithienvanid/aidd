"""The standards library: opinionated standards, stacks, the open choices they fill, and a company's policy.

Vocabulary (docs/GLOSSARY.md): a standard is `industry` (what the field agrees on; it lives in the registry,
`schemas/industry-standards.json`, applies everywhere, and is only waived per project) or `opinionated` (a choice a team or company
commits to). Each pack and practice skill declares its `open_choices`, with aidd's default answer. A library standard
(`standards/<group>/<topic>.md`, YAML front matter in schemas/standard.schema.json) fills one or more of them, so it
cannot overlap a pack. The library may hold several options for one choice in one ecosystem; exactly one of them is
aidd's default (`default: true`). A stack (`stacks/<name>.yaml`, schemas/stack.schema.json) lists standards that go together, plus
`project.stack` entries; it holds no rule text.

`aidd standard add` and `aidd stack add` copy library files into `<docs dir>/standards/`, write a `standards` entry
that records the id, aidd's version, and the copy's hash, write its `tests` entries (`std.<group>.<topic>.<name>`),
and follow `standards_policy` (require, exclude, replace, allow_stacks; opinionated ids only). `aidd upgrade`
refreshes an unedited copy; `aidd doctor` reports drift, edited copies, policy breaches, and deprecated or renamed ids.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aidd import __version__
from aidd import config as cfgmod
from aidd.kernel import documents, globs, json_schema, resources, strict_yaml
from aidd.kernel.text import md_cell
from aidd.knowledge import team_registry

# A library standard's body, without its front matter: a short file an agent reads whole before its step.
WORD_CAP = 300
# A sentence this long, in a library file and in a pack or skill (or another library file), restates it.
COPY_WORDS = 12
# How aidd works is the method, never a standard of either type, so never an open choice (docs/GLOSSARY.md, "Method").
METHOD_WORDS = frozenset(
    {
        *("route", "routes", "routing", "lane", "lanes", "profile", "gate"),
        *("approval", "approvals", "approve", "approver", "approvers", "sign-off", "signoff"),
        *("merge", "merges", "review", "reviews", "reviewer", "reviewers"),
        *("spec", "specs", "commit", "commits", "conventional", "assisted-by", "trailer", "trailers"),
    }
)
# Days between reviews of a library standard, by its maturity: the one table the registry uses too.
LIBRARY_REVIEW_EVERY_DAYS = team_registry.REVIEW_EVERY_DAYS
# Who checked a library standard, as `checked_by` says: an entry is checked by an agent until a person reviews it, and
# an entry without `checked_by` counts as an agent's check.
TIER_AGENT = "checked by an agent"
TIER_PERSON = "reviewed by a person"
BLOCK_START = "# aidd:standard {id}: written by `aidd standard add`; `aidd upgrade` refreshes it. Never edit the copy."
BLOCK_END = "# aidd:end {id}"


@dataclass(frozen=True)
class Standard:
    """One library standard: its id, its front matter, its body, the whole file, and its path under the library."""

    id: str
    meta: dict
    body: str
    text: str
    rel: str

    @property
    def ecosystem(self) -> str:
        return standard_ecosystem(self.id)

    @property
    def active(self) -> bool:
        return self.meta.get("status", "active") == "active"

    @property
    def sha256(self) -> str:
        return digest(self.text)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def standard_ecosystem(sid: str) -> str:
    return sid.split("/", 1)[0]


def trust_tier(meta: dict) -> str:
    """A library standard's trust tier from its `checked_by`: a person's identity (`@login` or `email:<address>`) is a
    person's review; `agent:<harness>/<model>`, or no `checked_by`, is an agent's check."""
    return TIER_PERSON if str(meta.get("checked_by", "")).startswith(("@", "email:")) else TIER_AGENT


def trust_counts(metas: list[dict]) -> dict[str, int]:
    """How many library standards are in each trust tier, both tiers always named."""
    tiers = [trust_tier(m) for m in metas]
    return {tier: tiers.count(tier) for tier in (TIER_AGENT, TIER_PERSON)}


def entry_name(sid: str) -> str:
    """The `standards` entry name of a copy: the id with `/` as `-`, such as `python-ruff-lint-format`."""
    return sid.replace("/", "-")


def test_name(sid: str, suffix: str) -> str:
    """The `tests` entry name of an enforcing command: `std.<group>.<topic>.<suffix>`. A test name is a file name in
    the evidence, so it has no `/` or `:`."""
    return "std." + sid.replace("/", ".") + "." + suffix


# ---- Reading the library ----------------------------------------------------------------------------------------------


def read_library(folder: Path | None = None) -> tuple[dict[str, Standard], list[str]]:
    """Every library standard under `folder` (default: aidd's), and every file that breaks the format."""
    folder = folder or resources.data_dir("standards")
    found: dict[str, Standard] = {}
    errors: list[str] = []
    for path in sorted(folder.rglob("*.md")):
        rel = path.relative_to(folder).as_posix()
        where = f"standards/{rel}"
        if len(path.relative_to(folder).parts) != 2:
            errors.append(f"{where}: a library standard is standards/<group>/<topic>.md")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            meta, body = documents.split_front_matter(text, where)
        except documents.DocumentError as exc:
            errors.append(f"{where}: {exc}")
            continue
        if not text.startswith("---"):
            errors.append(f"{where}: no YAML front matter between `---` lines")
            continue
        problems = json_schema.validate(meta, "standard.schema.json")
        errors += [f"{where}: {e}" for e in problems]
        sid = str(meta.get("id", ""))
        if sid and f"{sid}.md" != rel:
            errors.append(f"{where}: its id {sid!r} does not match its path; the file is standards/<group>/<topic>.md")
            continue
        if not problems:
            found[sid] = Standard(sid, meta, body, text, rel)
    return found, errors


def read_stacks(folder: Path | None = None) -> tuple[dict[str, dict], list[str]]:
    folder = folder or resources.data_dir("stacks")
    found: dict[str, dict] = {}
    errors: list[str] = []
    for path in sorted(folder.glob("*.yaml")):
        where = f"stacks/{path.name}"
        try:
            data = documents.parse_yaml(path.read_text(encoding="utf-8"), where)
        except documents.DocumentError as exc:
            errors.append(f"{where}: {exc}")
            continue
        problems = json_schema.validate(data, "stack.schema.json")
        errors += [f"{where}: {e}" for e in problems]
        if data.get("name") != path.stem:
            errors.append(f"{where}: its name {data.get('name')!r} is not its file's stem")
        elif not problems:
            found[path.stem] = data
    return found, errors


def read_renames(folder: Path | None = None) -> dict[str, str]:
    path = (folder or resources.data_dir("standards")) / "renames.yaml"
    return dict(documents.parse_yaml(path.read_text(encoding="utf-8"), "standards/renames.yaml").get("renames", {})) if path.is_file() else {}


@functools.cache
def _bundled() -> tuple[dict[str, Standard], dict[str, dict], dict[str, str]]:
    return read_library()[0], read_stacks()[0], read_renames()


def standards_library() -> dict[str, Standard]:
    """aidd's library standards by id (the files that pass the format; `aidd eval standards` names the others)."""
    return _bundled()[0]


def stacks() -> dict[str, dict]:
    return _bundled()[1]


def renames() -> dict[str, str]:
    """Old library id -> new id."""
    return _bundled()[2]


def stack_standards(name: str, known: dict[str, dict]) -> list[str]:
    """A stack's standard ids: the one stack it extends first, then its own, without repeats."""
    data = known[name]
    parent = known.get(str(data.get("extends") or "")) if data.get("extends") != name else None
    ids = list(parent["standards"]) if parent else []
    return list(dict.fromkeys(ids + list(data["standards"])))


def open_choices(roles: dict | None = None) -> dict[str, dict]:
    """Every open choice the packs and practice skills declare, by `<owner>:<id>`: the choice plus its owner and kind."""
    data = roles or team_registry.roles()
    out: dict[str, dict] = {}
    for d in data["domains"]:
        for c in d.get("open_choices", []):
            out[f"{d['slug']}:{c['id']}"] = {"owner": d["slug"], "kind": "pack", **c}
    for name, p in data.get("practices", {}).items():
        for c in p.get("open_choices", []):
            out[f"{name}:{c['id']}"] = {"owner": name, "kind": "practice", **c}
    return out


def choice_problems(roles: dict | None = None) -> list[str]:
    """An open choice declared more than once: twice by one owner, or by two owners. Each choice has one home, so a
    library standard fills it in one place."""
    data = roles or team_registry.roles()
    owners = [(d["slug"], d.get("open_choices", [])) for d in data["domains"]]
    owners += [(name, p.get("open_choices", [])) for name, p in data.get("practices", {}).items()]
    out: list[str] = []
    homes: dict[str, list[str]] = {}
    for owner, choices in owners:
        ids = [c["id"] for c in choices]
        out += [f"{owner} declares the choice {cid} {ids.count(cid)} times; keep one" for cid in sorted(set(ids)) if ids.count(cid) > 1]
        for cid in dict.fromkeys(ids):
            homes.setdefault(cid, []).append(owner)
    for cid, where in sorted(homes.items()):
        if len(where) > 1:
            out.append(f"the choice {cid} is declared by {len(where)} packs or skills ({', '.join(where)}); declare it once, where its rule is")
    return out


def _option_name(option: str) -> str:
    """The name an option goes by in a command: its text before a parenthesis (`Expo (React Native)` is `Expo`)."""
    return option.split(" (", 1)[0].strip()


def _owner_commands(owner: str, data: dict, texts: dict[str, str] | None) -> list[str]:
    """The test commands a pack or practice skill makes the team run: a pack's `tests` rows, or the rows of the table in
    a practice skill's Test commands section."""
    pack = next((d for d in data["domains"] if d["slug"] == owner), None)
    if pack is not None:
        return [f"{t['name']} {t['how']}" for t in pack["tests"]]

    text = (texts if texts is not None else team_texts()).get(owner, "")
    rows = [ln for ln in documents.raw_section(text, "Test commands").splitlines() if ln.startswith("|")]
    return rows[2:]


def deciding_problems(roles: dict | None = None, texts: dict[str, str] | None = None) -> list[str]:
    """An open choice its own pack or practice skill still decides: one of its test commands names exactly one of the
    choice's options and not the choice. A command that names the choice (`the team's e2e-test runner`) or two options
    leaves it open. Another pack may keep a tool for its own check; only the owner's commands are read."""
    data = roles or team_registry.roles()
    out: list[str] = []
    for ref, c in open_choices(data).items():
        names = {_option_name(o) for o in c["options"]}
        pats = {n: re.compile(rf"(?<![\w-]){re.escape(n)}(?![\w-])", re.I) for n in names if n}
        mention = re.compile(rf"(?<![\w-]){re.escape(c['id'])}(?![\w-])")
        for cmd in _owner_commands(c["owner"], data, texts):
            hits = sorted(n for n, p in pats.items() if p.search(cmd))
            if len(hits) == 1 and not mention.search(cmd):
                out.append(
                    f"{ref}: aidd-team:{c['owner']} opens this choice, but its test command {cmd.strip(' |')[:60]!r} names only "
                    f"{hits[0]}; name the choice (`{c['id']}`) and run the team's answer, or keep the tool and drop the choice"
                )
    return out


def team_texts() -> dict[str, str]:
    """Each pack's and practice skill's text an agent reads: its SKILL.md and references. Read once while no file
    changes (`aidd gen-docs` may rewrite a pack in the same process), since the checks ask for it many times."""
    folder = resources.data_dir("team") / "skills"
    files = {
        skill.name: [f for f in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))] if f.is_file() and f.name != "open-choices.md"]
        for skill in sorted(p for p in folder.iterdir() if p.is_dir() and p.name != "aidd-team")
    }
    stamp = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for fs in files.values() for f in fs)
    if _TEAM_TEXTS.get("stamp") != stamp:
        _TEAM_TEXTS.update(stamp=stamp, texts={name: "\n".join(f.read_text(encoding="utf-8") for f in fs) for name, fs in files.items()})
    return dict(_TEAM_TEXTS["texts"])


_TEAM_TEXTS: dict = {}


# ---- The company's policy ---------------------------------------------------------------------------------------------


def _policy(cfg) -> dict:
    return dict(cfg.get("standards_policy", default={}) or {}) if cfg else {}


def policy_mark(sid: str, policy: dict) -> str:
    if sid in policy.get("exclude", []):
        return "excluded"
    if sid in (policy.get("replace") or {}):
        return f"replaced by {policy['replace'][sid]}"
    if sid in policy.get("require", []):
        return "required"
    return ""


# ---- A project's copies -----------------------------------------------------------------------------------------------


def standard_copies(entries: list[dict]) -> list[dict]:
    """The `standards` entries that are copies of library standards."""
    return [e for e in entries if isinstance(e.get("from_library"), dict)]


def defaults(lib: dict[str, Standard]) -> dict[tuple[str, str], str]:
    """aidd's default per (choice, ecosystem): the active standard marked `default: true`. The library may hold
    several options for one choice; `aidd eval standards` checks that exactly one of them is the default."""
    out: dict[tuple[str, str], str] = {}
    for s in sorted(lib.values(), key=lambda x: x.id):
        if s.active and s.meta.get("default"):
            for ref in s.meta["fills"]:
                out.setdefault((ref, s.ecosystem), s.id)
    return out


def _refusal(sid: str, policy: dict, lib: dict[str, Standard], entries: list[dict]) -> str | None:
    if sid in cfgmod.registry_ids():
        return f"{sid} is an industry standard: it lives in the registry and reaches a project through the packs, never as a copy"
    if sid not in lib:
        return f"no library standard {sid}; `aidd standard list` lists them"
    s = lib[sid]
    if not s.active:
        return f"{sid} is deprecated; add {s.meta.get('replaced_by')}"
    if sid in policy.get("exclude", []):
        return f"the company excludes {sid} (`standards_policy.exclude`)"
    if sid in (policy.get("replace") or {}):
        return f"the company replaces {sid} with its own standard {policy['replace'][sid]} (`standards_policy.replace`)"
    for e in standard_copies(entries):
        other = e["from_library"]["id"]
        if other == sid or standard_ecosystem(other) != s.ecosystem:
            continue
        shared = sorted(set(e.get("fills", [])) & set(s.meta["fills"]))
        if shared:
            return f"{e['name']} already fills {shared[0]} for {s.ecosystem}: one standard per choice; remove it first"
    return None


def entries(s: Standard, docs_dir: str, stack: str | None = None, path: str | None = None) -> tuple[dict, list[dict]]:
    """The config entries for one copy: its `standards` entry, and its `tests` entries."""
    m = s.meta
    tests = [(test_name(s.id, e["name"]), e["command"]) for e in m.get("enforced_by", [])]
    from_library: dict = {"id": s.id, "aidd_version": __version__, "sha256": s.sha256}
    if stack:
        from_library["stack"] = stack
    entry: dict = {"name": entry_name(s.id), "path": path or copy_path(s.id, docs_dir), "type": "opinionated", "fills": m["fills"], "roles": m["roles"]}
    if m.get("when_changed"):
        entry["when_changed"] = m["when_changed"]
    if tests:
        entry["enforced_by"] = [n for n, _ in tests]
    entry["from_library"] = from_library
    test_entries = [{"name": n, "command": c} | ({"when_changed": m["when_changed"]} if m.get("when_changed") else {}) for n, c in tests]
    return entry, test_entries


def add_block(text: str, s: Standard, docs_dir: str, stack: str | None = None) -> str:
    """`text` (a config) with one copy's entries added: its `standards` entry and its `tests`, each list's part between
    the markers `aidd upgrade` finds."""
    entry, tests = entries(s, docs_dir, stack)
    marks = {"before": BLOCK_START.format(id=s.id), "after": BLOCK_END.format(id=s.id)}
    text = strict_yaml.append_items(text, "standards", [entry], **marks)
    return strict_yaml.append_items(text, "tests", tests, **marks) if tests else text


def copy_path(sid: str, docs_dir: str) -> str:
    return globs.under(docs_dir, f"standards/{sid}.md")


def _inside(root: Path, rel: str) -> bool:
    """Whether `rel` names a file inside the repository and no link leads out of it, so a copy is never written elsewhere."""
    path = root / rel
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        return False
    return path.resolve().is_relative_to(root.resolve())


def _read(path: Path) -> str | None:
    """A copy's text, or None when it is not a readable file. Bytes that are not UTF-8 read as replacement characters, so
    such a copy counts as edited, never as a crash."""
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    except OSError:
        return None


def _foreign(root: Path, rel: str, text: str) -> bool:
    """Whether a file someone else wrote is at `rel`: something is there, and it is not `text`."""
    path = root / rel
    return (path.exists() or path.is_symlink()) and _read(path) != text


FOREIGN = "{rel} exists and is not aidd's copy; move it, or name it in `standards_policy.replace`"


def commit(root: Path, writes: list[tuple[str, str]]) -> None:
    """Write every file, or none: each goes to a temporary file in its own folder first, and only when every one is
    written are they all moved into place. On any error, the temporary files and any folder made for them are removed,
    and ValueError names the file that could not be written."""
    staged: list[tuple[Path, Path]] = []
    made: list[Path] = []
    rel = ""
    try:
        for rel, text in writes:
            dest = root / rel
            missing = [p for p in (dest.parent, *dest.parent.parents) if p.is_relative_to(root) and p != root and not p.exists()]
            for folder in reversed(missing):
                folder.mkdir()
                made.append(folder)
            fd, tmp = tempfile.mkstemp(prefix=".aidd-", suffix=".tmp", dir=dest.parent)
            staged.append((Path(tmp), dest))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        for tmp_path, dest in staged:
            os.replace(tmp_path, dest)
    except OSError as exc:
        for tmp_path, _ in staged:
            tmp_path.unlink(missing_ok=True)
        for folder in reversed(made):
            with contextlib.suppress(OSError):
                folder.rmdir()
        raise ValueError(f"nothing added: cannot write {rel}: {exc.strerror or type(exc).__name__}") from None


def _block_re(sid: str) -> re.Pattern[str]:
    """One marked part of a copy's entries: its `standards` entry, or its `tests`, at the list's indent."""
    return re.compile(rf"^( *)# aidd:standard {re.escape(sid)}:.*?^ *# aidd:end {re.escape(sid)}[ \t]*\n?", re.M | re.S)


def _list_of(text: str, at: int) -> str:
    """The top-level key whose block holds position `at`: the last line at the left margin above it that is a key."""
    keys = re.findall(r"^([A-Za-z_][A-Za-z0-9_.-]*):", text[:at], re.M)
    return keys[-1] if keys else ""


def replace_blocks(text: str, sid: str, s: Standard, docs_dir: str, stack: str | None, dest: str) -> str | None:
    """`text` with every marked part of `sid`'s entries written again from `s`; None when no part is marked."""
    found = list(_block_re(sid).finditer(text))
    if not found:
        return None
    entry, tests = entries(s, docs_dir, stack, dest)
    for m in reversed(found):
        indent = len(m.group(1))
        items = [entry] if _list_of(text, m.start()) == "standards" else tests
        lines = [" " * indent + BLOCK_START.format(id=s.id), *strict_yaml.item_lines(items, indent), " " * indent + BLOCK_END.format(id=s.id)]
        text = text[: m.start()] + "\n".join(lines) + "\n" + text[m.end() :]
    return text


def merge_radar(text: str, entries: dict[str, list[str]]) -> str:
    """`text` (a config) with `entries` added to `project.stack`: each list merged in place, or made when missing."""
    entries = {k: v for k, v in entries.items() if v}
    if not entries:
        return text
    current = (documents.parse_yaml(text, "config").get("project") or {}).get("stack") or {}
    for name, add in entries.items():
        have = list(current.get(name, []))
        merged = have + [x for x in add if x not in have]
        if merged != have:
            try:
                text = strict_yaml.set_entry(text, ("project", "stack"), name, merged)
            except ValueError as exc:
                raise ValueError(f"{exc}; add the stack's entries to project.stack by hand") from None
    return text


def add_standards(root: Path, ids: list[str], *, stack: str | None = None) -> list[str]:
    """Copy library standards into the repository at `root`, all or nothing; ValueError names every refusal."""
    from aidd import config

    cfg_path = root / config.CONFIG_PATH
    if not cfg_path.is_file():
        raise ValueError(f"no {config.CONFIG_PATH}; run `aidd init` first")
    cfg = config.load_file(config.CONFIG_PATH, str(root))
    text = cfg_path.read_text(encoding="utf-8")
    lib, policy, moved = standards_library(), _policy(cfg), renames()
    entries = list(cfg.standards)
    notes: list[str] = []
    problems: list[str] = []
    radar: dict[str, list[str]] = {}
    if stack is not None:
        known = stacks()
        if stack not in known:
            raise ValueError(f"no stack {stack}; `aidd stack list` lists them")
        allowed = policy.get("allow_stacks")
        if allowed is not None and stack not in allowed:
            raise ValueError(f"the company allows only the stacks {', '.join(allowed) or 'none'} (`standards_policy.allow_stacks`)")
        ids = stack_standards(stack, known)
        radar = dict((known[stack].get("project") or {}).get("stack") or {})
        parent = known.get(str(known[stack].get("extends") or ""))
        for k, v in ((parent or {}).get("project") or {}).get("stack", {}).items():
            radar[k] = list(dict.fromkeys(list(v) + radar.get(k, [])))
    wanted: list[Standard] = []
    have = {e["from_library"]["id"] for e in standard_copies(entries)}
    names = {e.get("name") for e in entries}
    test_names = {x.get("name") for x in cfg.get("tests", default=[]) or []}
    for raw in dict.fromkeys(ids):
        sid = moved.get(raw, raw)
        if sid != raw:
            notes.append(f"{raw} was renamed to {sid}")
        if sid in have:
            notes.append(f"already added: {sid} ({entry_name(sid)}); `aidd upgrade` refreshes it")
            continue
        why = _refusal(sid, policy, lib, entries)
        if why:
            problems.append(why)
            continue
        s = lib[sid]
        clash = [f"the config already has a `standards` entry named {entry_name(sid)}"] if entry_name(sid) in names else []
        clash += [
            f"the config already has a `tests` entry named {n}" for n in (test_name(sid, e["name"]) for e in s.meta.get("enforced_by", [])) if n in test_names
        ]
        rel = copy_path(sid, cfg.docs_dir)
        if not _inside(root, rel):
            clash.append(f"{rel} is outside the repository or behind a link")
        elif _foreign(root, rel, s.text):
            clash.append(FOREIGN.format(rel=rel))
        if clash:
            problems += clash
            continue
        wanted.append(s)
        entries.append({"name": entry_name(sid), "fills": lib[sid].meta["fills"], "from_library": {"id": sid}})
        have.add(sid)
    if problems:
        raise ValueError("nothing added: " + "; ".join(problems))
    new = text
    if wanted:
        for s in wanted:
            new = add_block(new, s, cfg.docs_dir, stack)
    new = merge_radar(new, radar)
    if new == text:
        return notes + ["nothing to add"]
    errors = json_schema.validate(documents.parse_yaml(new, config.CONFIG_PATH), "config.schema.json")
    if errors:
        raise ValueError(f"nothing added: the config would not be valid: {errors[0]}")
    # Every copy and the config together, or nothing.
    commit(root, [(copy_path(s.id, cfg.docs_dir), s.text) for s in wanted] + [(config.CONFIG_PATH, new)])
    actions = []
    for s in wanted:
        tests = len(s.meta.get("enforced_by", []))
        actions.append(f"added {copy_path(s.id, cfg.docs_dir)} and its `standards` entry {entry_name(s.id)}, with {tests} `tests` entries")
    if radar and merge_radar(text, radar) != text:
        actions.append(f"added the stack's entries to project.stack: {', '.join(f'{k} {v}' for k, v in radar.items())}")
    return notes + actions


# ---- Doctor and upgrade -----------------------------------------------------------------------------------------------


def _edited(text: str | None, v: dict, lib: Standard | None) -> bool:
    """Whether a copy was edited: its text differs from the hash its entry records, or, when this aidd wrote it, from
    this aidd's library text, whatever hash the entry records (a hash in the config can be edited too)."""
    if text is None:
        return False
    if digest(text) != v.get("sha256"):
        return True
    return v.get("aidd_version") == __version__ and lib is not None and digest(text) != lib.sha256


def _expected(s_meta: dict, sid: str, path: str) -> tuple[dict, dict[str, dict]]:
    """The `standards` entry (without `from_library`) and the `tests` entries a copy of `sid` brings."""
    entry: dict = {"name": entry_name(sid), "path": path, "type": "opinionated", "fills": list(s_meta["fills"]), "roles": list(s_meta["roles"])}
    tests: dict[str, dict] = {}
    for e in s_meta.get("enforced_by", []):
        name = test_name(sid, e["name"])
        test: dict = {"name": name, "command": list(e["command"])}
        if s_meta.get("when_changed"):
            test["when_changed"] = list(s_meta["when_changed"])
        tests[name] = test
    if s_meta.get("when_changed"):
        entry["when_changed"] = list(s_meta["when_changed"])
    if tests:
        entry["enforced_by"] = list(tests)
    return entry, tests


def weakened(e: dict, s_meta: dict, suite: list[dict]) -> list[str]:
    """What in a copy's config entry, or in the `tests` entries it brought, no longer matches the standard it copies."""
    sid = e["from_library"]["id"]
    entry, tests = _expected(s_meta, sid, e["path"])
    have = {k: v for k, v in e.items() if k != "from_library"}
    out = [f"the `standards` entry's {k}" for k in sorted(set(entry) | set(have)) if entry.get(k) != have.get(k)]
    by_name = {x.get("name"): x for x in suite}
    out += [f"the `tests` entry {name}" for name, want in tests.items() if by_name.get(name) != want]
    return out


def standard_doctor_checks(root: Path, cfg) -> list[tuple[str, str]]:
    """The copies' drift, edits, and deprecated or renamed ids; the policy's breaches; and `fills` that name no choice."""
    out: list[tuple[str, str]] = []
    lib, moved, policy = standards_library(), renames(), _policy(cfg)
    choices = open_choices()
    entries = list(cfg.standards)
    for e in entries:
        for ref in e.get("fills", []):
            if ref not in choices:
                out.append(("warn", f"standards {e['name']!r}: fills {ref}, which no pack or practice skill declares (`aidd standard list` names them)"))
    seen: dict[tuple[str, str], str] = {}
    clean = 0
    picks = defaults(lib)
    for e in standard_copies(entries):
        v, name = e["from_library"], e["name"]
        sid = v["id"]
        where = f"standards {name!r}"
        for ref in e.get("fills", []):
            slot = (ref, standard_ecosystem(sid))
            if slot in seen:
                hint = f" (aidd's default: {picks[slot]})" if slot in picks else ""
                out.append(("warn", f"{where}: {seen[slot]} already fills {ref} for {standard_ecosystem(sid)}; keep one standard per choice{hint}"))
            seen[slot] = name
        path = root / e["path"]
        text = _read(path)
        edited = _edited(text, v, lib.get(sid))
        required = sid in policy.get("require", [])
        # The entry and its tests must still say what the standard says: compare them with the copy (or the library's text).
        source = lib[sid].meta if (edited or text is None) and sid in lib else None
        if source is None and text is not None:
            try:
                source = documents.split_front_matter(text, e["path"])[0]
            except documents.DocumentError:
                source = lib[sid].meta if sid in lib else None
        if isinstance(source, dict) and json_schema.validate(source, "standard.schema.json"):
            source = lib[sid].meta if sid in lib else None
        weak = weakened(e, source, list(cfg.get("tests", default=[]) or [])) if isinstance(source, dict) else []
        if weak and required:
            out.append(
                (
                    "fail",
                    f"standards policy: {name}: its config entry no longer matches {sid} ({', '.join(weak)}), which the company requires as it is; restore it",
                )
            )
        elif weak:
            out.append(
                (
                    "warn",
                    f"{where}: its config entry no longer matches {sid} ({', '.join(weak)}); restore it between its `# aidd:standard` markers, "
                    "or remove the entry and run `aidd standard add` again",
                )
            )
        if edited and required:
            out.append(("fail", f"standards policy: {name} is an edited copy of {sid}, which the company requires as it is; restore the copy"))
        elif edited:
            out.append(
                (
                    "warn",
                    f"{where}: the copy of {sid} was edited; never edit a copy: restore it, or write your own standard and name it in `standards_policy.replace`",
                )
            )
        if sid in moved:
            out.append(("warn", f"{where}: {sid} was renamed to {moved[sid]}; `aidd upgrade --yes` moves the copy"))
        elif sid not in lib:
            out.append(("warn", f"{where}: {sid} is no longer in aidd's library; keep it as your own standard, or remove it"))
        elif not lib[sid].active:
            new = lib[sid].meta.get("replaced_by")
            out.append(("warn", f"{where}: {sid} is deprecated, replaced by {new}; `aidd standard add {new}`, then remove this one"))
        elif lib[sid].sha256 != v["sha256"] and not edited:
            out.append(("warn", f"{where}: aidd {__version__} ships a newer {sid}; `aidd upgrade --yes` refreshes the copy"))
        elif not edited and not weak and path.is_file():
            clean += 1
        if sid in policy.get("exclude", []):
            out.append(("fail", f"standards policy: {name} copies {sid}, which the company excludes; remove it"))
        if sid in (policy.get("replace") or {}):
            out.append(("fail", f"standards policy: {name} copies {sid}, which the company replaces with its own standard {policy['replace'][sid]}"))
        allowed = policy.get("allow_stacks")
        if v.get("stack") and allowed is not None and v["stack"] not in allowed:
            out.append(
                (
                    "fail",
                    f"standards policy: {name} came with the stack {v['stack']}, which the company does not allow (allow_stacks: {', '.join(allowed) or 'none'})",
                )
            )
    present = {e["from_library"]["id"] for e in standard_copies(entries)}
    for sid in policy.get("require", []):
        if sid not in present:
            out.append(("fail", f"standards policy: the company requires {sid}; `aidd standard add {sid}`"))
    named = {e["name"] for e in entries}
    for sid, name in sorted((policy.get("replace") or {}).items()):
        if name not in named:
            out.append(("warn", f"standards policy: {sid} is replaced by {name}, which is no `standards` entry here"))
    for key in ("require", "exclude"):
        for sid in policy.get(key, []):
            if sid not in lib and sid not in moved:
                out.append(("warn", f"standards policy: {key} names {sid}, which is no library standard of aidd {__version__}"))
    if clean and not any(level != "ok" for level, _ in out):
        out.append(("ok", f"library standards: {clean} copies match aidd {__version__}"))
    return out


def refresh_standards(root: Path, text: str, docs_dir: str) -> tuple[str, list[tuple[str, str | None, str]], list[str]]:
    """What `aidd upgrade` does to the copies: the new config text, the files to write (None: remove), and notes.
    An unedited copy is refreshed from the library, and a renamed one moves; an edited copy is kept and named."""
    lib, moved = standards_library(), renames()
    raw = documents.parse_yaml(text, "config")
    files: list[tuple[str, str | None, str]] = []
    notes: list[str] = []
    if standard_copies(list(raw.get("standards") or [])) and json_schema.validate(raw, "config.schema.json"):
        return text, files, ["the config is not valid, so no library standard was refreshed; `aidd validate` names the problem"]
    for e in standard_copies(list(raw.get("standards") or [])):
        folder = globs.under(docs_dir, "standards/")
        v = e["from_library"]
        sid, rel = v["id"], e["path"]
        path = root / rel
        if not rel.startswith(folder):
            notes.append(f"{rel}: not under {folder}, so it is not refreshed; a copy lives there")
            continue
        if _edited(_read(path), v, lib.get(sid)):
            notes.append(f"kept {rel}: the copy was edited, so it is not refreshed; restore it, or replace it with your own standard")
            continue
        new_id = moved.get(sid, sid)
        s = lib.get(new_id)
        if s is None:
            notes.append(f"{rel}: {sid} is no longer in aidd's library; keep it as your own standard, or remove it")
            continue
        if new_id == sid and s.sha256 == v["sha256"] and path.is_file():
            continue
        if not _block_re(sid).search(text):
            notes.append(f"{rel}: its config entry has no `# aidd:standard {sid}` markers; refresh it by hand (`aidd standard add` writes them)")
            continue
        dest = rel if new_id == sid else copy_path(new_id, docs_dir)
        if not (_inside(root, dest) and _inside(root, rel)):
            notes.append(f"{rel}: outside the repository or behind a link, so it is not refreshed")
            continue
        if new_id != sid and _foreign(root, dest, s.text):
            notes.append(FOREIGN.format(rel=dest) + f"; {sid} was renamed to {new_id}, so the copy stays at {rel}")
            continue
        text = replace_blocks(text, sid, s, docs_dir, v.get("stack"), dest) or text
        why = f"{sid} renamed to {new_id}" if new_id != sid else f"{sid}, to aidd {__version__}"
        files.append((dest, s.text, why))
        if new_id != sid:
            files.append((rel, None, f"{sid} renamed to {new_id}"))
        if not s.active:
            notes.append(f"{new_id} is deprecated, replaced by {s.meta.get('replaced_by')}: `aidd standard add {s.meta.get('replaced_by')}`")
    return text, files, notes


# ---- Lists for the commands and the docs ------------------------------------------------------------------------------


# The version of `aidd standard list --json` and `aidd stack list --json` (schemas/standard-list.schema.json,
# schemas/stack-list.schema.json): a new key keeps it, a renamed or removed one bumps it.
LIST_SCHEMA_VERSION = "1"


def standard_rows(cfg) -> dict:
    """`aidd standard list --json`: the open choices, and each library standard with its policy mark and whether it is here."""
    policy = _policy(cfg)
    present = {e["from_library"]["id"] for e in standard_copies(list(cfg.standards))} if cfg else set()
    lib = standards_library()
    fills: dict[str, list[str]] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            fills.setdefault(ref, []).append(s.id)
    picks = defaults(lib)
    return {
        "schema_version": LIST_SCHEMA_VERSION,
        "open_choices": [
            {
                "ref": ref,
                "pack": c["owner"],
                "question": c["question"],
                "default_answer": c["default"],
                "options": c["options"],
                "filled_by": sorted(fills.get(ref, [])),
                "default_by_ecosystem": {eco: sid for (r, eco), sid in sorted(picks.items()) if r == ref},
            }
            for ref, c in open_choices().items()
        ],
        "standards": [
            {
                "id": s.id,
                "fills": s.meta["fills"],
                "tool": (s.meta.get("tool") or {}).get("name"),
                "checked_version": s.meta.get("checked_version"),
                "checked": s.meta.get("checked"),
                "status": s.meta["status"],
                "default": bool(s.meta.get("default")) and s.active,
                "trust": trust_tier(s.meta),
                "policy": policy_mark(s.id, policy),
                "added": s.id in present,
            }
            for s in sorted(lib.values(), key=lambda x: x.id)
        ],
    }


def stack_rows(cfg) -> dict:
    policy = _policy(cfg)
    allowed = policy.get("allow_stacks")
    known = stacks()
    return {
        "schema_version": LIST_SCHEMA_VERSION,
        "stacks": [
            {
                "name": name,
                "description": data["description"],
                "extends": data.get("extends"),
                "standards": stack_standards(name, known),
                "allowed": allowed is None or name in allowed,
            }
            for name, data in sorted(known.items())
        ],
    }


def open_choices_table(owner: str) -> str:
    """One pack's or skill's open choices as a table: the choice, the question, aidd's default, and the options."""
    rows_ = [c for c in open_choices().values() if c["owner"] == owner]
    lines = ["| Choice | Question | aidd's default | Options |", "| --- | --- | --- | --- |"]
    lines += [f"| `{c['id']}` | {md_cell(c['question'])} | {md_cell(c['default'])} | {md_cell(', '.join(c['options']))} |" for c in rows_]
    return "\n".join(lines)


def catalog_choices() -> str:
    """docs/STANDARDS.md: every open choice, its default, and the library standards that fill it. Where an ecosystem has
    several options for a choice, aidd's default among them is marked."""
    lib = standards_library()
    picks = set(defaults(lib).items())
    options: dict[tuple[str, str], int] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            options[(ref, s.ecosystem)] = options.get((ref, s.ecosystem), 0) + s.active
    fills: dict[str, list[str]] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            mark = " (default)" if options[(ref, s.ecosystem)] > 1 and ((ref, s.ecosystem), s.id) in picks else ""
            fills.setdefault(ref, []).append(f"`{s.id}`{mark}")
    lines = ["| Choice | Question | aidd's default | Library standards |", "| --- | --- | --- | --- |"]
    for ref, c in open_choices().items():
        lines.append(f"| `{ref}` | {md_cell(c['question'])} | {md_cell(c['default'])} | {', '.join(sorted(fills.get(ref, []))) or '—'} |")
    return "\n".join(lines)


def catalog_library() -> str:
    """docs/STANDARDS.md: the library by ecosystem, with each tool's checked version and date."""
    by_eco: dict[str, list[Standard]] = {}
    for s in sorted(standards_library().values(), key=lambda x: x.id):
        by_eco.setdefault(s.ecosystem, []).append(s)
    parts = []
    for eco, items in sorted(by_eco.items()):
        lines = [f"### {eco}", "", "| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for s in items:
            m = s.meta
            tool = (m.get("tool") or {}).get("name", "—")
            status = m["status"] + (f", replaced by `{m['replaced_by']}`" if m.get("replaced_by") else "")
            lines.append(
                f"| `{s.id}` | {', '.join(f'`{r}`' for r in m['fills'])} | {tool} | {m.get('checked_version', '—')} | {m.get('checked', '—')} | {m['reviewed']} | {status} |"
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def catalog_stacks() -> str:
    known = stacks()
    lines = ["| Stack | For | Extends | Standards |", "| --- | --- | --- | --- |"]
    for name, data in sorted(known.items()):
        ids = ", ".join(f"`{x}`" for x in stack_standards(name, known))
        lines.append(f"| `{name}` | {md_cell(data['description'])} | {('`' + data['extends'] + '`') if data.get('extends') else '—'} | {ids} |")
    return "\n".join(lines)
