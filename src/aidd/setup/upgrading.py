"""Bring what `aidd init` wrote up to this aidd (`aidd upgrade`). Under `--yes` it writes the vendored skill, the team files, the
text between aidd's marks, each agent's ask rules, the CI pins, and the config's `aidd_version`. First it moves the config and the work items from an earlier shape of
aidd's files to today's (`migrating`). It also adds `.gitignore` lines for what tests and builds leave, and it refreshes or removes the copies of library standards you have not edited."""

from __future__ import annotations

import contextlib
import re
import shutil
import tomllib
from collections.abc import Iterable
from pathlib import Path

from aidd import __version__, config, workitems
from aidd.kernel import documents, git_reads, globs, regular_files, repo_paths, resources
from aidd.kernel.regular_files import open_for_write
from aidd.setup import (
    adoption,
    ask_rules,
    claude_plugins,
    detection,
    doctor_probes,
    files,
    ignore_lines,
    instruction_imports,
    marked_sections,
    mcp_wiring,
    migrating,
    pins,
    self_updating,
    skill_files,
    team_install,
    team_record,
    worktree_base,
)

# The config's `aidd_version` line, which `aidd upgrade` rewrites as text so every other line keeps its form.
_AIDD_VERSION = re.compile(r"^aidd_version:[ ]*(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)", re.M)


ONLY_PARTS = ("ask-rules",)  # what `aidd upgrade --only` can name: the one part it can bring up to date alone


@git_reads.shared_reads()
@team_install.rendered_once()
def upgrade(root: Path, *, ref: str | None = None, yes: bool = False, only: str | None = None) -> list[str]:
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill and its copies, the team files already
    installed, the text between aidd's marks in AGENTS.md and in the agents' own instruction files, each coding agent's
    ask rules, the aidd refs in CI files, and the config's `aidd_version`. Everything else stays as you left it: REVIEW.md,
    the rest of your config and AGENTS.md, and your own steps in the CI files. A dry run unless `yes`. With `only="ask-rules"`
    it writes each coding agent's ask rules and nothing else, as after a Spec approval, which adds the `Edit` asks for the
    Spec's frozen tests."""
    if problem := older_than_repository(root):
        raise ValueError(problem)
    if only is not None:
        if only not in ONLY_PARTS:
            raise ValueError(f"--only takes {' or '.join(ONLY_PARTS)}, not {only!r}")
        if ref:
            raise ValueError(f"--ref pins the CI files, which --only {only} leaves as they are: drop one of the two")
        said: list[str] = []
        ask_rules.write_ask_rules(root, adoption.wired_harnesses(root), said, write=yes)
        written = [a for a in said if not a.startswith("kept ")]
        return written or [f"nothing to update: this repository's ask rules already match aidd {__version__}"]
    pin, release, _ = pins.resolve_pin(ref)
    ref = pin or f"v{__version__}"  # offline, without a checkout: the release tag itself
    if not pins.REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    found = migrating.plan(root)  # the files in an earlier shape, moved to today's before the rest reads them
    if yes:
        migrating.apply(root, found)
    with contextlib.nullcontext() if yes else regular_files.reading_as(found.texts):  # a dry run reads them as the real run will
        return _bring_up(root, ref, release, yes, migrating.words(found, yes))


def _bring_up(root: Path, ref: str, release: str | None, yes: bool, actions: list[str]) -> list[str]:
    """The rest of `upgrade`, after the files in an earlier shape are moved: `actions` holds the lines of that move."""
    verb = "updated " if yes else "would update"

    def put(path: Path, text: str, why: str, exact: bool = False) -> None:
        """Write `text` unless the file holds it. `exact` keeps the file's line endings, which `write_text` would change."""
        held = regular_files.repository_text(root, path.relative_to(root).as_posix())
        if held is not None and (held if exact else held.replace("\r\n", "\n").replace("\r", "\n")) == text:
            return
        if refused := regular_files.write_refusal(root, path):  # a link could send the write outside the repository
            actions.append(f"skipped  {repo_paths.shown(path)} ({refused})")
            return
        actions.append(f"{verb if path.exists() else ('added   ' if yes else 'would add')} {repo_paths.shown(path)} ({why})")
        if yes:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open_for_write(path, text=not exact, root=root) as out:
                out.write(text if not exact else text.encode("utf-8"))

    skill = root / adoption.SKILL_REL
    fresh = resources.data_dir("skill")
    if skill.is_dir() and not skill.is_symlink() and doctor_probes.tree_diff(fresh, skill) and not files.refuses_link_on_the_way(root, skill, actions):
        actions.append(f"{verb} {repo_paths.shown(skill)} (the skill, to aidd {__version__})")
        if yes:
            skill_files.vendor_skill(root, True, [])
    for d in adoption.DEFAULT_LINKS:  # a copy `aidd init` made where symlinks are unavailable
        link = root / d / "aidd"
        if (
            link.is_dir()
            and not link.is_symlink()
            and (link / "SKILL.md").is_file()
            and doctor_probes.tree_diff(fresh, link)
            and not files.refuses_link_on_the_way(root, link, actions)
        ):
            actions.append(f"{verb} {repo_paths.shown(link)} (a copy of the skill, to aidd {__version__})")
            if yes:
                shutil.rmtree(link)
                shutil.copytree(resources.data_dir("skill"), link)
    wired = adoption.wired_harnesses(root)
    plan = team_install.wanted_team_files(root)
    team = team_install.team_section([], False)  # with the plugin and no files of ours, as `aidd init --aidd-team` writes it
    plan_harnesses: list[str] = []
    claude = False
    if plan:
        wanted, plan_harnesses, claude = plan
        recorded = team_record.read_record(root)
        unrecorded: list[str] = []
        for rel, text in wanted.items():
            disk = team_record.file_text(root, rel)
            if disk is not None and disk != text:
                if rel in recorded and recorded[rel] != team_record.digest(disk):
                    actions.append(
                        f"note     kept {rel} because it changed since aidd wrote it, so remove it and run `aidd upgrade --yes` to take aidd's latest"
                    )
                    continue
                if rel not in recorded:
                    unrecorded.append(rel)
                    continue
            put(root / rel, text, "the development team")
        if unrecorded:
            kept = ", ".join(sorted(unrecorded))
            noun = "it" if len(unrecorded) == 1 else "them"
            actions.append(
                f"note     kept {kept} because {config.TEAM_FILES_FILE} has no record of what aidd wrote there, so remove {noun} and run `aidd upgrade --yes` to take aidd's latest"
            )
        retire_team_files(root, wanted, actions, yes=yes)
        team = team_install.team_section(plan_harnesses, claude)
    runs_roles = team_install.role_running_harnesses(root, wired, plan_harnesses, claude_files=claude)
    if runs_roles and (note := team_install.independent_review_note(root, runs_roles)):
        actions.append(note)
    if team_install.team_plugin_carries_roles(root) and (note := team_install.models_inert_note(root)):
        actions.append(f"note     {note}")
    actions += worktree_base.apply(root, wired, write=yes)  # where each role's worktree starts
    instruction_text, left_alone = refreshed_instruction_files(root, team, yes=yes)
    for path, text in instruction_text.items():
        why = "the text between aidd's marks; your own text stays"
        if path.relative_to(root).as_posix() in IMPORTING_FILES:
            why = "aidd's section there is the line that imports AGENTS.md, not a copy of the block, so Claude Code reads the block once; your own text stays"
        put(path, text, why, exact=True)
    actions += [f"note     {line}" for line in left_alone]
    mcp_wiring.refresh_mcp(root, actions, yes=yes)
    claude_plugins.follow_stable(root, actions, yes=yes)
    for ci in sorted((root / ".github" / "workflows").glob("*.y*ml")) + [root / ".gitlab-ci.yml", root / ".gitlab" / "aidd.gitlab-ci.yml"]:
        if ci_link := regular_files.link_on_the_way(root, ci):
            actions.append(f"skipped  {repo_paths.shown(ci)} ({ci_link} is a link, and aidd reads and writes nothing through a link; remove it to update it)")
        elif (ci_text := regular_files.repository_text(root, ci.relative_to(root).as_posix())) is not None:
            if "thaithienvanid/aidd" in ci_text:
                put(ci, pins.repin(ci_text, ref, release), f"aidd pinned at {ref}")
    # What tests and builds leave: `aidd test` counts an untracked file as a dirty tree, so each stack's outputs are ignored.
    gi = root / ".gitignore"
    found, why = regular_files.named_text(root, ".gitignore")
    text = found or ""
    if found is None and why != regular_files.MISSING:
        actions.append(f"skipped  {repo_paths.shown(gi)} ({why}: aidd neither reads it nor writes through it; replace it with the file)")
    elif ignore_outputs := ignore_lines.missing_ignore_lines(root, text, detection.language_names(root)):
        actions.append(
            f"{verb if gi.exists() else ('added   ' if yes else 'would add')} {repo_paths.shown(gi)} ({ignore_lines.ignore_lines_reason(ignore_outputs)})"
        )
        if yes:
            files.write_or_skip(
                root, gi, ("\n" if text and not text.endswith("\n") else "") + "".join(f"{line}\n" for line in ignore_outputs), actions, append=True
            )
    cfg = root / config.CONFIG_PATH
    if (raw := regular_files.repository_text(root, config.CONFIG_PATH, documents.MAX_DOCUMENT_BYTES)) is not None:
        from aidd import knowledge

        crlf = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        new = _AIDD_VERSION.sub(f'aidd_version: "{__version__}"', text, count=1)
        new = config.SCHEMA_MODELINE.sub(config.schema_modeline(__version__), new, count=1)  # the editor's schema, of this release
        docs_dir = globs.normal_dir(str((documents.parse_yaml(new, config.CONFIG_PATH).get("docs") or {}).get("dir") or "docs"))
        # The copies of library standards: an unedited one is refreshed from this aidd's library, an edited one is kept.
        refreshed, copies, notes = knowledge.refresh_standards(root, new, docs_dir)
        for rel, content, why in copies:
            if content is None:
                if (root / rel).is_file():
                    actions.append(f"{'removed ' if yes else 'would remove'} {repo_paths.shown(root / rel)} ({why})")
                    if yes:
                        (root / rel).unlink()
            else:
                put(root / rel, content, why)
        actions.extend(notes)
        why = ", ".join([f"aidd_version {__version__}"] + ["the entries of the refreshed standards"] * (refreshed != new))
        if refreshed != text:  # compared apart from line endings, so a file that needs nothing is left byte for byte
            put(cfg, refreshed.replace("\n", "\r\n") if crlf else refreshed, why, exact=True)
    asks: list[str] = []
    ask_rules.write_ask_rules(root, adoption.wired_harnesses(root), asks, write=yes)
    actions += [a for a in asks if not a.startswith("kept ")]
    if all(a.startswith(("kept ", "note     ")) for a in actions):
        actions.insert(0, f"nothing to update: this repository already matches aidd {__version__}")
    return actions + (remaining_problems(root) if yes else [])


UPGRADE_PROBLEM = "problem  "  # starts each line of `remaining_problems`


def remaining_problems(root: Path) -> list[str]:
    """What `aidd validate` still finds in the repository after an upgrade wrote its changes, one `problem` line for each
    error, which names its file. Warnings and notes are not listed: `aidd validate` shows them."""
    if not (root / config.CONFIG_PATH).is_file():
        return []
    try:
        errors, _ = workitems.check_repo(root)
    except (OSError, RuntimeError, ValueError) as exc:
        return [UPGRADE_PROBLEM + documents.one_line(f"aidd validate could not run ({exc}): fix that, then run `aidd validate`", 1000)]
    return [UPGRADE_PROBLEM + documents.one_line(e, 1000) for e in errors]  # a file name can hold control characters


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
    text = regular_files.repository_text(root, config.CONFIG_PATH, documents.MAX_DOCUMENT_BYTES) or ""
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
        return tomllib.loads(regular_files.repository_text(root, "pyproject.toml") or "").get("project", {}).get("name") == "aidd"
    except (OSError, tomllib.TOMLDecodeError):
        return False


# The files whose section is the line that imports AGENTS.md: the pointer of each agent that reads an import.
IMPORTING_FILES = frozenset(name for h in config.HARNESSES.values() if h.imports for name in h.pointer_names)


def instruction_files(root: Path) -> list[Path]:
    """The instruction files in `root` that may carry aidd's marks: AGENTS.md, and the file each agent reads in its place."""
    names = sorted({"AGENTS.md", *(name for h in config.HARNESSES.values() for name in h.pointer_names)})
    return [root / rel for rel in names if regular_files.repository_text(root, rel) is not None]


def retire_team_files(root: Path, wanted: dict[str, str], actions: list[str], *, yes: bool) -> None:
    """Remove each team file aidd wrote and no longer writes, while it holds what aidd wrote, and record what it writes now
    (`.aidd/team-files.json`). A changed one stays, with a note, because it is the person's now."""
    every = {rel: next(iter(texts)) for rel, texts in team_install.team_file_variants().items()}
    found, ignored = team_record.stale(root, every)
    actions += [
        f"note     ignored {rel} in {config.TEAM_FILES_FILE}: it names no path this aidd writes, so it removes nothing there; remove the file yourself if you no longer use it"
        for rel in ignored
    ]
    for rel, unchanged in found:
        if not unchanged:
            actions.append(f"note     kept {rel}: aidd no longer writes it, and it changed since aidd wrote it; remove it when you are done with it")
        elif not yes:
            actions.append(f"would remove {rel} (a team file this aidd no longer writes)")
        elif team_record.remove(root, rel):
            actions.append(f"removed  {rel} (a team file this aidd no longer writes)")
        else:
            actions.append(f"note     kept {rel}: a link is on its way, and aidd removes nothing through a link")
    if yes:
        team_record.write_record(root, wanted, actions)


def refreshed_instruction_files(root: Path, team: str, *, yes: bool = False) -> tuple[dict[Path, str], list[str]]:
    """Each instruction file with aidd's marks, as it reads once the text between the marks is this aidd's (aidd's
    section, and `team` for the team section), with a line for each section left alone. A file keeps its line endings, and
    one that differs only outside the marks is not listed. A section with no end mark is left alone, because its end is a guess."""
    changed: dict[Path, str] = {}
    left: list[str] = []
    for path in instruction_files(root):
        raw = regular_files.repository_text(root, path.relative_to(root).as_posix()) or ""
        crlf = "\r\n" in raw
        text = new = raw.replace("\r\n", "\n")
        rel = path.relative_to(root).as_posix()
        found = marked_sections.sections(new, adoption.AGENTS_MARK)
        plugin = bool(found) and marked_sections.PLUGIN_PHRASE in new[found[0].start : found[0].end]
        pairs = [(adoption.AGENTS_MARK, adoption.agents_snippet(root, not plugin))]
        if rel in IMPORTING_FILES:  # Claude Code's file imports AGENTS.md, so a copy of the block there, or a second import, goes
            pairs = [(adoption.AGENTS_MARK, instruction_imports.import_section(rel))]
            if found and found[0].closed and instruction_imports.person_imports(new, rel):
                new, pairs = strip_marked_section(new, adoption.AGENTS_MARK), []
        if path.name == "AGENTS.md":
            pairs.append((config.TEAM_MARK, team))
        for mark, section in pairs:
            new = marked_sections.refresh(new, mark, section)
        # The lines a note names are those of the file the person edits next: as it is now in a dry run, as written under `yes`.
        basis = new if yes else text
        for mark, section in pairs:
            command = "aidd init" if mark == adoption.AGENTS_MARK else "aidd init --aidd-team"
            for found_section in marked_sections.left_alone(basis, mark, section):
                first, last = marked_sections.line_range(basis, found_section)
                lines = f"line {first}" if first == last else f"lines {first} to {last}"
                left.append(
                    f"{repo_paths.shown(path)}: the section at {mark} ({lines}) has no end mark, so its end is a guess and it was left alone. "
                    f"To take this aidd's, delete that section and run `{command}`; your own text outside the marks stays"
                )
        if new != text:
            changed[path] = new.replace("\n", "\r\n") if crlf else new
    return changed, left


def dirty_tree_ignore_fix(root: Path, paths: Iterable[str]) -> str:
    """When every listed dirty path matches a `.gitignore` line `aidd upgrade --yes` would add for a detected language,
    the next step naming `aidd upgrade --yes` instead of committing generated files; else ""."""
    listed = [p for p in paths if p]
    if not listed:
        return ""
    text, why = regular_files.named_text(root, ".gitignore")
    if text is None and why != regular_files.MISSING:
        return ""
    added = ignore_lines.missing_ignore_lines(root, text or "", detection.language_names(root))
    lines = [line for line in added if line not in (ignore_lines.TEST_OUTPUTS_MARK, ignore_lines.OS_FILES_MARK, *ignore_lines.OS_FILES)]
    if not lines or not all(ignore_lines.matches_any_line(p, lines) for p in listed):
        return ""
    return "run `aidd upgrade --yes`, commit `.gitignore`, then run `aidd test` again"


def strip_marked_section(text: str, mark: str) -> str:
    """Remove the first section that starts at `mark` (its heading and body), up to its end mark, or when it has none up to
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
