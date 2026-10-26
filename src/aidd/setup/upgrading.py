"""Bring what `aidd init` wrote up to this aidd (`aidd upgrade`)."""

from __future__ import annotations

import os
import re
import shutil
import tomllib
from pathlib import Path

from aidd import __version__, config
from aidd.kernel import documents, globs, repo_paths, resources
from aidd.setup import (
    adoption,
    antigravity_wiring,
    codex_wiring,
    detection,
    doctor_probes,
    grok_wiring,
    hook_wiring,
    hooks_file,
    ignore_lines,
    opencode_wiring,
    pins,
    self_updating,
    team_install,
)

# The config's `aidd_version` line, read and rewritten as text, so every other line keeps its form.
_AIDD_VERSION = re.compile(r"^aidd_version:[ ]*(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)", re.M)


def upgrade(root: Path, *, ref: str | None = None, yes: bool = False) -> list[str]:
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill and its copies, the team files already installed, the
    guard aidd wired into each coding agent's own files (`_refresh_guards`), the aidd refs in CI files, and the config's `aidd_version`. Everything else stays as you left it: your config, REVIEW.md,
    AGENTS.md, and your own steps in the CI files. A dry run unless `yes`."""
    if problem := older_than_repository(root):
        raise ValueError(problem)
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
        own = team_install.harness_paths()  # a path two harnesses share says neither was wired
        harnesses = [h for h in team_install.NATIVE_AGENT_HARNESSES if any(rel in own[h] for rel in installed)]
        wanted = team_install.team_files(harnesses, claude, team_install.configured_models(root))
        for rel, text in wanted.items():
            put(root / rel, text, "the delivery team")
        for d in (".claude/agents", ".claude/commands", ".claude/skills"):
            for stale in sorted((root / d).glob(f"{team_install.TEAM_PREFIX}*")) if (root / d).is_dir() else []:
                rel = str(stale.relative_to(root)) + ("/SKILL.md" if stale.is_dir() else "")
                if rel not in wanted:
                    actions.append(f"no longer shipped: {repo_paths.shown(stale)} (remove it if nothing else uses it)")
    _refresh_guards(root, actions, verb, yes, put)
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

        text = cfg.read_text(encoding="utf-8")
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
        put(cfg, refreshed, why)
    if all(a.startswith(("no longer shipped", "kept ")) for a in actions):
        actions.insert(0, f"nothing to update: this repository already matches aidd {__version__}")
    return actions


def older_than_repository(root: Path) -> str | None:
    """Why this aidd must not write its files into `root`, or None. An upgrade writes the files of the aidd that runs it,
    so an older aidd would write older files over newer ones: one older than the version the config names, or any
    aidd but the checkout itself in aidd's own source, where the skill and the templates are the source, not copies.
    It compares versions only, so a build of another commit at the same version is not caught (BACKLOG R99)."""
    if _aidd_source(root):
        running = resources.repo_root()
        if running is None or running.resolve() != root.resolve():
            return (
                f"{repo_paths.shown(root)} is aidd's own source, so its skill and templates are the source, not copies an upgrade "
                "refreshes: upgrade it with its own code, `PYTHONPATH=src python3 -m aidd upgrade --yes` there"
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


def _aidd_source(root: Path) -> bool:
    """Whether `root` is aidd's own source: its layout, and a pyproject.toml whose project is `aidd`."""
    if not ((root / "schemas").is_dir() and (root / "src" / "aidd").is_dir() and (root / adoption.SKILL_REL).is_dir()):
        return False
    try:
        return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {}).get("name") == "aidd"
    except (OSError, tomllib.TOMLDecodeError):
        return False


def _refresh_guards(root: Path, actions: list[str], verb: str, yes: bool, put) -> None:
    """The guard aidd wired into a coding agent's own files, where aidd's entries are there: the OpenCode plugin, the
    hook files of Codex, Grok Build, and Antigravity, and Claude Code's repository hooks. Each keeps every hook and
    setting that is not aidd's."""
    if opencode_wiring.state(root) == "stale":
        for rel, text in opencode_wiring.files().items():
            put(root / rel, text, "the OpenCode guard plugin and its terminal half")
    hook_files = [(w.path, w.label, w.wired, w.hook_command, hooks_file.EVENTS, w.install) for w in (codex_wiring.FILE, grok_wiring.FILE)]
    hook_files.append(
        (
            antigravity_wiring.HOOKS_FILE,
            config.HARNESSES["antigravity"].label,
            antigravity_wiring.wired,
            antigravity_wiring.hook_command,
            antigravity_wiring.EVENTS,
            antigravity_wiring.install,
        )
    )
    stale_mcp = os.name != "nt" and bool(antigravity_wiring.wired(root)) and not antigravity_wiring.mcp_configured(root)
    for rel, label, wired_in, command, events, install in hook_files:
        wired = wired_in(root)
        if wired and any(wired.get(event) != command(sub) for event, sub in events.items()):
            actions.append(f"{verb} {repo_paths.shown(root / rel)} (the {label} hooks, to aidd {__version__})")
            if yes:
                install(root, [])
    if stale_mcp:
        actions.append(f"{verb} {repo_paths.shown(root / antigravity_wiring.PLUGIN_MCP_FILE)} (the aidd MCP server, in `.agents/plugins/aidd/`)")
        if yes and not antigravity_wiring.mcp_configured(root):
            antigravity_wiring.install_mcp(root, [])
    stale, kept = hook_wiring.refresh_claude_hooks(root, write=False)
    settings = repo_paths.shown(root / ".claude" / "settings.json")
    if stale:
        actions.append(f"{verb} {settings} (the aidd hooks for {', '.join(stale)}, to aidd {__version__})")
        if yes:
            if os.name != "nt":  # the sh commands start the user launcher, which must start this aidd
                hook_wiring.install_user_launcher(root, hook_wiring.launcher(), [])
            hook_wiring.refresh_claude_hooks(root, write=True)
    for theirs in kept:
        actions.append(
            f"kept     {settings} (left as you wrote it: {theirs}. To run this aidd's own hook there, run "
            "`aidd init --claude-hooks`, which replaces that whole command, then add your own step back as a hook of its own)"
        )


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
