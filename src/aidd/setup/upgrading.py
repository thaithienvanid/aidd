"""Bring what `aidd init` wrote up to this aidd (`aidd upgrade`). Under `--yes` it writes the vendored skill, the team files, the
text between aidd's marks, each agent's ask rules, the CI pins, and the config's `aidd_version`. It also makes three changes to
files of yours. A config field this aidd removed stays as a comment and `owners.default_team` is renamed, because this aidd
cannot load a config that holds one; that is written only when the result validates. It adds `.gitignore` lines for what tests
and builds leave. It refreshes or removes the copies of library standards you have not edited."""

from __future__ import annotations

import functools
import re
import shutil
import tomllib
from pathlib import Path

from aidd import __version__, config
from aidd.kernel import documents, globs, repo_paths, resources
from aidd.kernel.regular_files import link_on_the_way, open_for_write
from aidd.setup import (
    adoption,
    claude_plugins,
    config_template,
    detection,
    doctor_probes,
    ignore_lines,
    marked_sections,
    mcp_wiring,
    pins,
    self_updating,
    team_install,
    unread_state,
    work_item_migration,
)

_AIDD_VERSION = unread_state.CONFIG_VERSION_LINE  # the config's version line, read and rewritten as text


def _fold_work_items(root: Path, actions: list[str], *, yes: bool, collapse: bool) -> str | None:
    """Fold the Initiatives and Epics an older aidd wrote into Intents (`work_item_migration`): each file it writes or
    removes, under `yes` only on a clean tree, so `git diff` shows the whole fold. Returns the config's new text when the
    fold changes it, for the steps that read the config next."""
    cfg = root / config.CONFIG_PATH
    raw = cfg.read_text(encoding="utf-8") if cfg.is_file() else ""
    try:
        found = documents.parse_yaml(raw, config.CONFIG_PATH) if raw else {}
    except documents.DocumentError:
        found = {}
    specs_dir = globs.normal_dir(str(found.get("specs_dir") or "specs"))
    proposals_dir = globs.normal_dir(str(found.get("proposals_dir") or "proposals"))
    fold = work_item_migration.plan(root, specs_dir, proposals_dir, cfg, collapse=collapse)
    if fold.stops:
        actions += [f"note     the Initiatives and Epics stay as they are, because {stop}" for stop in fold.stops]
        return None
    if not fold.writes and not fold.removes:
        return None
    paths = sorted({p.relative_to(root).as_posix() for p in [*fold.writes, *fold.removes]})
    if yes and (dirty := work_item_migration.uncommitted(root, paths)):
        actions.append(f"note     the Initiatives and Epics stay as they are: commit {', '.join(dirty[:3])} first, so the fold is one change of its own")
        return None
    for path, text in fold.writes.items():
        actions.append(
            f"{'updated ' if yes else 'would update'} {repo_paths.shown(path.relative_to(root))} ({fold.reasons.get(path, 'the fold into Intents')})"
        )
        if yes:
            path.write_text(text, encoding="utf-8")
    for path in fold.removes:
        actions.append(
            f"{'removed ' if yes else 'would remove'} {repo_paths.shown(path.relative_to(root))} ({fold.reasons.get(path, 'folded into its Intent')})"
        )
        if yes:
            path.unlink()
    actions += [f"note     {n}" for n in fold.notes]
    return fold.writes.get(cfg)


def _not_shipped(root: Path, everything: dict[str, str], wanted: dict[str, str]) -> list[Path]:
    """Each `aidd-` file or folder in a folder the team files of any harness live in that this aidd no longer writes, such
    as a retired flow's command or skill. The folders come from the files aidd writes for every harness, so none is
    missed; the vendored skill, `aidd` with no dash, is never one."""
    folders: set[str] = set()
    for rel in everything:
        parts = rel.split("/")
        at = next((i for i, p in enumerate(parts) if p.startswith(team_install.TEAM_PREFIX)), None)
        if at:
            folders.add("/".join(parts[:at]))
    stale = []
    for d in sorted(folders):
        for found in sorted((root / d).glob(f"{team_install.TEAM_PREFIX}*")) if (root / d).is_dir() else []:
            rel = found.relative_to(root).as_posix()
            if not (rel in wanted or any(w.startswith(rel + "/") for w in wanted)):
                stale.append(found)
    return stale


def _retire_config_fields(root: Path, actions: list[str], *, yes: bool, text: str | None = None) -> bool:
    """Take out the config fields this aidd removed, so the config loads: each stays as a comment, and `owners.default_team` is
    renamed (`unread_state.retire_config_fields`). Under `yes` it writes the config, with this aidd's `aidd_version` and its
    line endings, because the ask rules read it next. Returns whether the fields can go, and in a dry run only says what it
    would do. Writes nothing when the result would not validate: the notes then say what to remove by hand."""
    cfg = root / config.CONFIG_PATH
    raw = text if text is not None else cfg.read_bytes().decode("utf-8") if cfg.is_file() else ""
    fix = unread_state.retire_config_fields(raw.replace("\r\n", "\n"), dry_run=not yes) if raw else None
    if fix is None:
        return False
    if yes:
        cfg.write_bytes((fix[0].replace("\n", "\r\n") if "\r\n" in raw else fix[0]).encode("utf-8"))
    actions += [f"{'updated ' if yes else 'would update'} {repo_paths.shown(cfg)}: {step}" for step in fix[1]]
    return True


def upgrade(root: Path, *, ref: str | None = None, yes: bool = False, collapse_unstarted: bool = False) -> list[str]:
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill and its copies, the team files already
    installed, the text between aidd's marks in AGENTS.md and in the agents' own instruction files, each coding agent's
    ask rules, the aidd refs in CI files, and the config's `aidd_version`. A field this aidd removed from your config stays
    in it as a comment. Everything else stays as you left it: REVIEW.md, the rest of your config and AGENTS.md, and your own
    steps in the CI files. It folds the Initiatives and Epics an older aidd wrote into Intents, and with
    `collapse_unstarted` turns each Spec nobody started into its slice line. A dry run unless `yes`."""
    if problem := older_than_repository(root):
        raise ValueError(problem)
    pin, release, _ = pins.resolve_pin(ref)
    ref = pin or f"v{__version__}"  # offline, without a checkout: the release tag itself
    if not pins.REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    verb = "updated " if yes else "would update"
    actions: list[str] = []

    def put(path: Path, text: str, why: str, exact: bool = False) -> None:
        """Write `text` unless the file holds it. `exact` keeps the file's line endings, which `write_text` would change."""
        if path.is_file() and (path.read_bytes().decode("utf-8") if exact else path.read_text(encoding="utf-8")) == text:
            return
        if link := link_on_the_way(root, path):  # a link could send the write outside the repository
            actions.append(f"skipped  {repo_paths.shown(path)} ({link} is a link, and aidd writes nothing through a link; remove it to update it)")
            return
        actions.append(f"{verb if path.exists() else ('added   ' if yes else 'would add')} {repo_paths.shown(path)} ({why})")
        if yes:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open_for_write(path, text=not exact) as out:
                out.write(text if not exact else text.encode("utf-8"))

    skill = root / adoption.SKILL_REL
    if skill.is_dir() and not skill.is_symlink() and doctor_probes.tree_diff(resources.data_dir("skill"), skill):
        actions.append(f"{verb} {repo_paths.shown(skill)} (the skill, to aidd {__version__})")
        if yes:
            adoption.vendor_skill(root, True, [])
    for d in adoption.DEFAULT_LINKS:  # a copy `aidd init` made where symlinks are unavailable
        link = root / d / "aidd"
        if link.is_dir() and not link.is_symlink() and (link / "SKILL.md").is_file() and doctor_probes.tree_diff(resources.data_dir("skill"), link):
            actions.append(f"{verb} {repo_paths.shown(link)} (a copy of the skill, to aidd {__version__})")
            if yes:
                shutil.rmtree(link)
                shutil.copytree(resources.data_dir("skill"), link)
    team = team_install.team_section([], False)  # with the plugin and no files of ours, as `aidd init --team` writes it
    everything = team_install.team_files(list(team_install.NATIVE_AGENT_HARNESSES), True)
    installed = [rel for rel in everything if (root / rel).is_file()]
    if installed:
        claude = any(rel.startswith(".claude/") for rel in installed)
        own = team_install.harness_paths()  # a path two harnesses share says neither was wired
        harnesses = [h for h in team_install.NATIVE_AGENT_HARNESSES if any(rel in own[h] for rel in installed)]
        wanted = team_install.team_files(harnesses, claude, team_install.agent_setting(root, "models"), team_install.agent_setting(root, "effort"))
        for rel, text in wanted.items():
            put(root / rel, text, "the delivery team")
        team = team_install.team_section(harnesses, claude)
        actions += [f"no longer shipped: {repo_paths.shown(stale)} (remove it if nothing else uses it)" for stale in _not_shipped(root, everything, wanted)]
    instruction_text, left_alone = refreshed_instruction_files(root, team, yes=yes)
    for path, text in instruction_text.items():
        put(path, text, "the text between aidd's marks; your own text stays", exact=True)
    actions += [f"note     {line}" for line in left_alone]
    mcp_wiring.refresh_mcp(root, actions, yes=yes)
    claude_plugins.follow_stable(root, actions, yes=yes)
    asks: list[str] = []
    folded_config = _fold_work_items(root, actions, yes=yes, collapse=collapse_unstarted)  # before the config's own fixes
    retired = _retire_config_fields(root, actions, yes=yes, text=None if yes else folded_config)  # before the ask rules, which read the config
    harnesses = adoption.detect_harnesses(root)
    if retired and not yes:
        if any(config.HARNESSES[key].ask_rules for key in harnesses):
            asks.append("would add   the ask rules for each agent, once `aidd upgrade --yes` has taken the retired fields out of the config")
    else:
        adoption.write_ask_rules(root, harnesses, asks, write=yes, config_text=None if yes else folded_config)
    actions += [a for a in asks if not a.startswith("kept ")]
    for ci in sorted((root / ".github" / "workflows").glob("*.y*ml")) + [root / ".gitlab-ci.yml", root / ".gitlab" / "aidd.gitlab-ci.yml"]:
        if ci.is_file():
            text = ci.read_text(encoding="utf-8")
            if "thaithienvanid/aidd" in text:
                put(ci, pins.repin(text, ref, release), f"aidd pinned at {ref}")
    # What tests and builds leave: `aidd test` counts an untracked file as a dirty tree, so each stack's outputs are ignored.
    gi = root / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if ignore_outputs := ignore_lines.missing_ignore_lines(root, text, detection.stack_names(root)):
        actions.append(
            f"{verb if gi.exists() else ('added   ' if yes else 'would add')} {repo_paths.shown(gi)} ({ignore_lines.ignore_lines_reason(ignore_outputs)})"
        )
        if yes:
            with open(gi, "a", encoding="utf-8") as fh:
                fh.write(("\n" if text and not text.endswith("\n") else "") + "".join(f"{line}\n" for line in ignore_outputs))
    cfg = root / config.CONFIG_PATH
    if cfg.is_file():
        from aidd import knowledge

        raw = cfg.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        new = _AIDD_VERSION.sub(f'aidd_version: "{__version__}"', text, count=1)
        new = config.SCHEMA_MODELINE.sub(config.schema_modeline(__version__), new, count=1)  # the editor's schema, of this release
        docs_dir = globs.normal_dir(str((documents.parse_yaml(new, config.CONFIG_PATH).get("docs") or {}).get("dir") or "docs"))
        # The copies of library standards: an unedited one is refreshed from this aidd's library, an edited one is kept.
        refreshed, files, notes = knowledge.refresh_standards(root, new, docs_dir)
        for rel, content, why in files:
            if content is None:
                if (root / rel).is_file():
                    actions.append(f"{'removed ' if yes else 'would remove'} {repo_paths.shown(root / rel)} ({why})")
                    if yes:
                        (root / rel).unlink()
            else:
                put(root / rel, content, why)
        actions.extend(notes)
        why = f"aidd_version {__version__}" + (", and the entries of the refreshed standards" if refreshed != new else "")
        if refreshed != text:  # compared apart from line endings, so a file that needs nothing is left byte for byte
            put(cfg, refreshed.replace("\n", "\r\n") if crlf else refreshed, why, exact=True)
    actions += [f"note     {message}" for _level, message in unread_state.unread_state(root, None if yes else folded_config)]
    if all(a.startswith(("no longer shipped", "kept ", "note     ")) for a in actions):
        actions.insert(0, f"nothing to update: this repository already matches aidd {__version__}")
    return actions


# In aidd's own source, an upgrade runs from that checkout's code.
SOURCE_UPGRADE = "PYTHONPATH=src python3 -m aidd upgrade --yes"


def older_than_repository(root: Path) -> str | None:
    """Why this aidd must not write its files into `root`, or None. An upgrade writes the files of the aidd that runs it,
    so an older aidd would write older files over newer ones: one older than the version the config names, or any
    aidd but the checkout itself in aidd's own source, where the skill and the templates are the source, not copies.
    It compares versions only, so a build of another commit at the same version is not caught."""
    if aidd_source(root):
        running = resources.repo_root()
        if running is None or running.resolve() != root.resolve():
            return (
                f"{repo_paths.shown(root)} is aidd's own source, so its skill and templates are the source, not copies an upgrade "
                f"refreshes: upgrade it with its own code, `{SOURCE_UPGRADE}` there"
            )
    cfg = root / config.CONFIG_PATH
    text = cfg.read_text(encoding="utf-8") if cfg.is_file() else ""
    declared = m.group(1).strip("\"'") if (m := _AIDD_VERSION.search(text)) else ""
    if declared and not re.search(r"\d", declared):
        return f"this repository's config names aidd_version {declared!r}, which is no version: write it as {__version__!r}, then run `aidd upgrade` again"
    if declared and self_updating.version_key(declared) > self_updating.version_key(__version__):
        return (
            f"this repository's config names aidd {declared}, newer than this aidd {__version__}, so an upgrade would write "
            "older files: run `aidd self-update` first, then `aidd upgrade` again"
        )
    return None


def aidd_source(root: Path) -> bool:
    """Whether `root` is aidd's own source: its layout, and a pyproject.toml whose project is `aidd`."""
    if not ((root / "schemas").is_dir() and (root / "src" / "aidd").is_dir() and (root / adoption.SKILL_REL).is_dir()):
        return False
    try:
        return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {}).get("name") == "aidd"
    except (OSError, tomllib.TOMLDecodeError):
        return False


def instruction_files(root: Path) -> list[Path]:
    """The instruction files in `root` that may carry aidd's marks: AGENTS.md, and the file each agent reads in its place."""
    return [p for p in (root / rel for rel in sorted({"AGENTS.md", *(h.pointer for h in config.HARNESSES.values() if h.pointer)})) if p.is_file()]


def refreshed_instruction_files(root: Path, team: str, *, yes: bool = False) -> tuple[dict[Path, str], list[str]]:
    """Each instruction file with aidd's marks, as it reads once the text between the marks is this aidd's (aidd's
    section, and `team` for the team section), with a line for each section left alone. A file keeps its line endings, and
    one that differs only outside the marks is not listed. A section an older aidd wrote, with no end mark, is replaced
    only when its text is one aidd shipped, because its end is a guess."""
    changed: dict[Path, str] = {}
    left: list[str] = []
    for path in instruction_files(root):
        raw = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        text = new = raw.replace("\r\n", "\n")
        found = marked_sections.sections(new, adoption.AGENTS_MARK)
        plugin = bool(found) and marked_sections.PLUGIN_PHRASE in new[found[0].start : found[0].end]
        pairs = [(adoption.AGENTS_MARK, adoption.agents_snippet(root, not plugin))]
        if path.name == "AGENTS.md":
            pairs.append((config.TEAM_MARK, team))
        blocks = [config_template.verification_block(config_template.configured_tests(root)), config_template.verification_block([])]
        shipped = {
            m: functools.partial(marked_sections.lead_is_shipped, blocks=blocks) if m == adoption.AGENTS_MARK else (lambda _old: False) for m, _ in pairs
        }
        for mark, section in pairs:
            new = marked_sections.refresh(new, mark, section, shipped[mark])
        # The lines a note names are those of the file the person edits next: as it is now in a dry run, as written under `yes`.
        basis = new if yes else text
        for mark, section in pairs:
            command = "aidd init" if mark == adoption.AGENTS_MARK else "aidd init --team"
            for found_section in marked_sections.left_alone(basis, mark, section, shipped[mark]):
                first, last = marked_sections.line_range(basis, found_section)
                lines = f"line {first}" if first == last else f"lines {first} to {last}"
                left.append(
                    f"{repo_paths.shown(path)}: the section at {mark} ({lines}) has no end mark and is not exactly a text aidd shipped, so it was left alone. "
                    f"To take this aidd's, delete that section and run `{command}`; your own text outside the marks stays"
                )
        if new != text:
            changed[path] = new.replace("\n", "\r\n") if crlf else new
    return changed, left


def strip_marked_section(text: str, mark: str) -> str:
    """Remove the first section that starts at `mark` (its heading and body), up to its end mark, or for an older one up to
    the next `#` or `##` heading. A mark in a code fence is no mark. A mark with no heading after it loses its own line only."""
    found = marked_sections.sections(text, mark)
    if found:
        start, end = found[0].start, found[0].end
    elif lines := marked_sections.mark_lines(text, mark):
        start, end = lines[0]
        return text[:start] + text[end:]
    else:
        return text
    before, after = text[:start].rstrip("\n"), text[end:].lstrip("\n")
    out = ((before + "\n\n" + after) if before and after else (before or after)).strip("\n")
    return out + "\n" if out else ""
