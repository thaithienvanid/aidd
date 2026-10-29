"""The standards library's generic checks, which `aidd eval standards` runs over every library file: an open choice
never names the method, a standard's body stays short and says nothing a pack already says, each rule it names is
cited, each `implements` names a real choice, and each pinned tool matches the team's pins and its checked version, or
holds back on purpose until its `cooldown_until` day."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aidd import config as cfgmod
from aidd.kernel import documents
from aidd.knowledge import standards, team_registry, upkeep


def method_problems(choices: dict[str, dict]) -> list[str]:
    """An open choice that names the method (routes, approvals, the gate, commit format, `Assisted-by:`)."""
    out = []
    for ref, c in choices.items():
        text = " ".join([c["id"].replace("-", " "), c["id"], c["question"], c["default"], *c["options"]])
        words = set(re.findall(r"[a-z][a-z-]*", text.lower()))
        hit = sorted(words & standards.METHOD_WORDS)
        if hit:
            out.append(f"open choice {ref}: names the method ({', '.join(hit)}); how aidd works is never an open choice")
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'_./-]*", text.lower())


def _sentences(text: str) -> list[str]:
    """Normalised sentences of COPY_WORDS words or more, outside code blocks and front matter."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    out = []
    for chunk in re.split(r"\n|\|", text):
        for sentence in re.split(r"(?<=[.!?])\s+", chunk):
            words = [w.strip("`*") for w in _words(sentence)]
            if len(words) >= standards.COPY_WORDS:
                out.append(" ".join(words))
    return out


def _pinned_by_team(tool: str) -> list[str]:
    """The packs and practice skills whose test commands pin `tool` by version."""
    pin = re.compile(rf"(?<![\w-]){re.escape(tool)}[`'\"]?(?:==|@| \(v?)[0-9]", re.I)
    data = team_registry.roles()
    out = [f"aidd-team:{d['slug']}" for d in data["domains"] if any(pin.search(t.get("how", "")) for t in d["tests"])]

    for name, text in standards.team_texts().items():
        if name in {d["slug"] for d in data["domains"]}:
            continue
        if pin.search(documents.raw_section(text, "Test commands")):
            out.append(f"aidd-team:{name}")
    return out


def _implements_problem(ref: str) -> str | None:
    owner, _, rule = ref.partition(":")
    from aidd.knowledge import role_text

    data = team_registry.roles()
    packs_ = {d["slug"] for d in data["domains"]}
    if owner not in packs_ and owner not in role_text.practice_names():
        return f"implements {ref}: {owner} is no pack or practice skill"
    if owner == "product-defaults":
        return None if rule in cfgmod.PROJECT_DEFAULTS else f"implements {ref}: {rule} is no product default"
    return None if _clean(rule) in rule_names(standards.team_texts().get(owner, "")) else f"implements {ref}: aidd-team:{owner} has no rule {rule!r}"


def _clean(text: str) -> str:
    return " ".join(text.replace("`", "").replace("*", "").strip().rstrip(".:").split()).lower()


CITATIONS = "standards"


def rule_names(text: str) -> set[str]:
    """The whole rule names in a pack's or skill's text: its headings, its bold lead-ins (`**Name.**`), and the first
    cell of each table body row. `implements` names one of them, never a word inside a sentence. The Standards section
    cites what the field agrees on and holds no rule, so nothing in it counts, nor does a table's header row."""
    names: set[str] = set()
    lines = text.splitlines()
    citing = False
    for i, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            citing = _clean(heading.group(2)) == CITATIONS
            if not citing:
                names.add(_clean(heading.group(2)))
            continue
        if citing:
            continue
        names |= {_clean(b) for b in re.findall(r"\*\*([^*]+?)\*\*", line)}
        if line.startswith("|") and not re.match(r"^\|\s*:?-", line):
            header = i + 1 < len(lines) and re.match(r"^\|\s*:?-", lines[i + 1])
            if not header:
                names.add(_clean(line.strip("|").split("|")[0]))
    return names - {""}


# aidd's release cooldown for a library pin (aidd-team:dependency-upgrade): 3 days after a patch, 7 after a minor or a
# major. The new release is already out, so a cooldown ends at most COOLDOWN_MAX_DAYS after the day it is set.
COOLDOWN_MAX_DAYS = 7
# Days a passed cooldown warns before it fails: one run of the weekly standards check, so the move is never missed.
COOLDOWN_GRACE_DAYS = 7


def _lags(meta: dict) -> bool:
    """Whether `pin` is behind `checked_version`: neither the same version nor a prefix of it."""
    pin, checked = str(meta.get("pin") or "").lstrip("v"), str(meta.get("checked_version") or "").lstrip("v")
    return bool(pin and checked) and not (checked == pin or checked.startswith(pin + "."))


def _held_text(meta: dict) -> str:
    """What a cooldown keeps back: the pin, and the release it lags; or the checked version where there is no pin."""
    tool = meta["tool"]["name"]
    if meta.get("pin"):
        return f"it pins {tool} {meta['pin']}" + (f", checked at {meta['checked_version']}" if _lags(meta) else "")
    return f"it names {tool} {meta['checked_version']}"


def cooldown_findings(sid: str, meta: dict, today: dt.date) -> tuple[list[str], list[str]]:
    """A standard's `cooldown_until`, as (problems, warnings). A cooldown waits out a new release, so it ends at most
    COOLDOWN_MAX_DAYS ahead. Once it ends, it warns for COOLDOWN_GRACE_DAYS, and then it fails like any pin left behind."""
    held = meta.get("cooldown_until")
    if not held:
        return [], []
    until = dt.date.fromisoformat(held)
    problems = []
    if (until - today).days > COOLDOWN_MAX_DAYS:
        problems.append(
            f"{sid}: cooldown_until {held} is over {COOLDOWN_MAX_DAYS} days away, longer than any release cooldown. "
            "Keep a longer pin with `version_policy: pinned` and its reason in the body"
        )
    late = (today - until).days
    if late <= 0:
        return problems, []
    ago = f", {late} days ago," if late > COOLDOWN_GRACE_DAYS else ","
    step = (
        f"its cooldown ended on {held}{ago} and {_held_text(meta)}. Read the release feed again and move each version the cooldown kept back. "
        "Then re-read `source` and `evidence`, set `checked` to today, and remove `cooldown_until`"
    )
    if late > COOLDOWN_GRACE_DAYS:
        return [*problems, f"{sid}: {step}"], []
    return problems, [f"{sid}: {step}. From {until + dt.timedelta(days=COOLDOWN_GRACE_DAYS + 1)} this fails"]


def library_warnings(folder: Path | None = None, *, today: dt.date | None = None) -> list[str]:
    """What `aidd eval standards` prints without failing: each cooldown that ended in the last COOLDOWN_GRACE_DAYS days."""
    today = today or dt.date.today()
    lib, _ = standards.read_library(folder)
    return [w for sid, s in sorted(lib.items()) for w in cooldown_findings(sid, s.meta, today)[1]]


def ended_cooldowns(folder: Path | None = None, *, today: dt.date | None = None) -> list[str]:
    """Each cooldown that has ended, warning or failing: what `aidd list --upkeep` lists, so a pin is moved on its day."""
    today = today or dt.date.today()
    lib, _ = standards.read_library(folder)
    return [x for sid, s in sorted(lib.items()) for x in sum(cooldown_findings(sid, s.meta, today), []) if "its cooldown ended" in x]


def library_problems(folder: Path | None = None, stacks_folder: Path | None = None, *, today: dt.date | None = None) -> list[str]:
    """Every break of the library's rules, over every file: adding a standard or a stack needs no new test code."""
    today = today or dt.date.today()
    lib, out = standards.read_library(folder)
    known_stacks, stack_errors = standards.read_stacks(stacks_folder)
    out += stack_errors
    choices = standards.open_choices()
    out += method_problems(choices)
    out += standards.choice_problems()
    out += standards.deciding_problems()
    roles = set(team_registry.roles()["order"])
    team = standards.team_texts()
    team_sentences = {s: name for name, text in team.items() for s in _sentences(text)}
    seen_sentences: dict[str, str] = {}
    by_choice: dict[tuple[str, str], list[str]] = {}
    by_tool: dict[str, list[str]] = {}
    for sid, s in sorted(lib.items()):
        m = s.meta
        for ref in m["fills"]:
            if ref not in choices:
                out.append(f"{sid}: fills {ref}, which no pack or practice skill declares")
            if s.active:
                by_choice.setdefault((ref, s.ecosystem), []).append(sid)
        if m.get("implements") and (why := _implements_problem(m["implements"])):
            out.append(f"{sid}: {why}")
        unknown = [r for r in m["roles"] if r != "*" and r not in roles]
        if unknown:
            out.append(f"{sid}: unknown role {', '.join(unknown)}")
        for key in ("reviewed", "checked"):
            if m.get(key) and dt.date.fromisoformat(m[key]) > today:
                out.append(f"{sid}: {key} {m[key]} is in the future")
        cadence = upkeep.spread(sid, standards.LIBRARY_REVIEW_EVERY_DAYS[m["maturity"]])
        if (today - dt.date.fromisoformat(m["reviewed"])).days > cadence:
            out.append(f"{sid}: reviewed {m['reviewed']}, over {cadence} days ago; judge the choice again and set the date")
        words = len(_words(s.body))
        if words > standards.WORD_CAP:
            out.append(f"{sid}: its body is {words} words; the cap is {standards.WORD_CAP}")
        for sentence in _sentences(s.body):
            if sentence in team_sentences:
                out.append(f"{sid}: restates aidd-team:{team_sentences[sentence]} ({sentence[:60]}...); link the rule with `implements`")
            if sentence in seen_sentences:
                out.append(f"{sid} repeats {seen_sentences[sentence]} ({sentence[:60]}...)")
            seen_sentences.setdefault(sentence, sid)
        if m["status"] == "deprecated":
            if m.get("default"):
                out.append(f"{sid}: a deprecated standard is never a default; set `default: true` on the standard that replaces it")
            new = m.get("replaced_by")
            if new and (new not in lib or not lib[new].active or new == sid):
                out.append(f"{sid} is replaced by {new}, which is no active library standard")
        if m.get("version_policy") in ("current_stable", "latest_lts") and _lags(m) and not m.get("cooldown_until"):
            out.append(
                f"{sid}: pins {m['pin']}, but the version it checked is {m['checked_version']}: move the pin, "
                "set `cooldown_until` while the release waits out its cooldown, or keep it for good with `version_policy: pinned`"
            )
        out += cooldown_findings(sid, m, today)[0]
        tool = (m.get("tool") or {}).get("name")
        if tool and s.active:
            by_tool.setdefault(tool, []).append(sid)
            pin = str(m.get("pin") or "")
            for e in m.get("enforced_by", []):
                for arg in e["command"]:
                    hit = re.fullmatch(rf"{re.escape(tool)}(?:==|@)(.+)", arg)
                    if hit and pin and hit.group(1) != pin:
                        out.append(f"{sid}: its test {e['name']} runs {tool} {hit.group(1)}, not its pin {pin}")
    for (ref, eco), ids in sorted(by_choice.items()):
        defaults = [sid for sid in ids if lib[sid].meta.get("default")]
        if not defaults:
            out.append(f"{ref} for {eco} has no default; set `default: true` on one of {', '.join(ids)}")
        elif len(defaults) > 1:
            out.append(f"{ref} for {eco} has {len(defaults)} defaults ({', '.join(defaults)}); keep one")
    for tool, ids in sorted(by_tool.items()):
        if len(ids) > 1:
            out.append(f"the tool {tool} is owned by {len(ids)} library standards ({', '.join(ids)}); one standard owns each tool")
        for owner in _pinned_by_team(tool):
            out.append(f"{ids[0]}: {owner} already pins the tool {tool}; the pack keeps it, or opens a choice for it")
    names = standards.read_renames(folder)
    for old, new in sorted(names.items()):
        if old in lib:
            out.append(f"renames.yaml renames {old}, which is still a library file")
        if new not in lib:
            out.append(f"renames.yaml renames to {new}, which is no library standard")
        if new in names:
            out.append(f"renames.yaml renames {old} to {new}, which is renamed again; point it at the last id")
    for name, data in sorted(known_stacks.items()):
        parent = data.get("extends")
        if parent == name:
            out.append(f"stack {name} extends itself")
        elif parent and parent not in known_stacks:
            out.append(f"stack {name} extends {parent}, which is no stack")
        elif parent and known_stacks[parent].get("extends"):
            out.append(f"stack {name} extends {parent}, which extends {known_stacks[parent]['extends']}: a stack extends one other stack, one level")
        # One standard per choice, whatever folder each one lives in.
        picked: dict[str, str] = {}
        for sid in standards.stack_standards(name, known_stacks):
            if sid not in lib:
                out.append(f"stack {name}: {sid} is no library standard")
                continue
            if not lib[sid].active:
                out.append(f"stack {name}: {sid} is deprecated; use {lib[sid].meta.get('replaced_by')}")
            for ref in lib[sid].meta["fills"]:
                if ref in picked:
                    out.append(f"stack {name}: {picked[ref]} and {sid} both fill {ref}; a stack picks one")
                picked[ref] = sid
    return out
