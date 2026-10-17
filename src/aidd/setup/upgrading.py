"""Bring what `aidd init` wrote up to this aidd (`aidd upgrade`)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from aidd import __version__, config
from aidd.kernel import documents, globs, repo_paths, resources
from aidd.setup import adoption, doctor_probes, pins, team_install


def upgrade(root: Path, *, ref: str | None = None, yes: bool = False) -> list[str]:
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill and its copies, the team files already installed, the
    aidd refs in CI files, and the config's `aidd_version`. Everything else stays as you left it: your config, REVIEW.md,
    AGENTS.md, and your own steps in the CI files. A dry run unless `yes`."""
    pin, release, _ = pins.resolve_pin(ref)
    ref = pin or f"v{__version__}"  # offline, without a checkout: the release tag itself
    if not pins.REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    verb = "updated " if yes else "would update"
    actions: list[str] = []

    def put(path: Path, text: str, why: str) -> None:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return
        actions.append(f"{verb if path.exists() else ('added   ' if yes else 'would add')} {repo_paths.shown(path)} ({why})")
        if yes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

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
    everything = team_install.team_files(list(team_install.NATIVE_AGENT_HARNESSES), True)
    installed = [rel for rel in everything if (root / rel).is_file()]
    if installed:
        claude = any(rel.startswith(".claude/") for rel in installed)
        harnesses = [
            h
            for h in team_install.NATIVE_AGENT_HARNESSES
            if any(rel in team_install.team_files([h], False) and rel != team_install.TEAM_ROLES_REF for rel in installed)
        ]
        wanted = team_install.team_files(harnesses, claude, team_install.configured_models(root))
        for rel, text in wanted.items():
            put(root / rel, text, "the delivery team")
        for d in (".claude/agents", ".claude/commands", ".claude/skills"):
            for stale in sorted((root / d).glob(f"{team_install.TEAM_PREFIX}*")) if (root / d).is_dir() else []:
                rel = str(stale.relative_to(root)) + ("/SKILL.md" if stale.is_dir() else "")
                if rel not in wanted:
                    actions.append(f"no longer shipped: {repo_paths.shown(stale)} (remove it if nothing else uses it)")
    for ci in sorted((root / ".github" / "workflows").glob("*.y*ml")) + [root / ".gitlab-ci.yml", root / ".gitlab" / "aidd.gitlab-ci.yml"]:
        if ci.is_file():
            text = ci.read_text(encoding="utf-8")
            if "thaithienvanid/aidd" in text:
                put(ci, pins.repin(text, ref, release), f"aidd pinned at {ref}")
    cfg = root / config.CONFIG_PATH
    if cfg.is_file():
        from aidd import knowledge

        text = cfg.read_text(encoding="utf-8")
        new = re.sub(r"^aidd_version:[ ]*(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)", f'aidd_version: "{__version__}"', text, count=1, flags=re.M)
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
        put(cfg, refreshed, why)
    if all(a.startswith("no longer shipped") for a in actions):
        actions.insert(0, f"nothing to update: this repository already matches aidd {__version__}")
    return actions


def strip_marked_section(text: str, mark: str) -> str:
    """Remove the section that starts at `mark` (its heading and body) up to the next `## ` heading."""
    start = text.find(mark)
    if start == -1:
        return text
    line_end = text.find("\n", start)
    line_end = len(text) if line_end == -1 else line_end + 1
    heading = re.match(r"## ", text[line_end:])
    if not heading:  # the mark without its heading on the next line: drop the mark line only
        return text[:start] + text[line_end:]
    m = re.search(r"^#{1,2} ", text[line_end + heading.end() :], re.M)
    end = line_end + heading.end() + m.start() if m else len(text)
    before, after = text[:start].rstrip("\n"), text[end:].lstrip("\n")
    out = (before + "\n\n" + after) if before and after else (before or after)
    out = out.strip("\n")
    return out + "\n" if out else ""
