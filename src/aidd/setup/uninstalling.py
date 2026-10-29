"""Reverse `aidd init` and `aidd init --team` (`aidd uninstall`): remove what they wrote, while it is still what they wrote."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from aidd import config
from aidd.kernel import repo_paths, resources
from aidd.setup import (
    adoption,
    antigravity_wiring,
    codex_wiring,
    config_template,
    doctor_probes,
    grok_wiring,
    hook_wiring,
    ignore_lines,
    opencode_wiring,
    pins,
    team_install,
    upgrading,
)

# The directories init may create, which uninstall removes once they are empty.
INIT_DIRS = (
    ".aidd specs .claude/commands .codex/agents .codex .github/agents .opencode/agents .opencode/commands .opencode/plugins .opencode .kiro/agents .kiro .claude/agents .claude/skills "
    ".claude .agents/agents .agents/skills .agents .grok/agents .grok/skills .grok/hooks .grok .gitlab/merge_request_templates .gitlab .github/workflows .github/rulesets .github .continue/rules .continue"
).split()


# The folders in .aidd/ that aidd writes its output into (config.layout): git ignores them, and aidd writes them again.
OUTPUT_DIRS = (config.EVIDENCE_DIR, config.VIEWS_DIR)


def _dump_or_unlink(path: Path, data: dict) -> None:
    """Write a JSON settings file back, or remove it when nothing but aidd's entries was in it."""
    if data:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        path.unlink()


def uninstall(root: Path, *, links: list[str] | None = None, yes: bool = False) -> list[str]:
    """Reverse `aidd init` and `aidd init --team`: remove what they wrote, when it is still what they wrote. A dry run
    unless `yes`; it never touches Specs, and it keeps any file the user changed, saying so."""
    actions: list[str] = []
    verb = "removed " if yes else "would remove"
    tpl = resources.data_dir("templates")
    bundled_skill = resources.data_dir("skill")

    def same(path: Path, text: str) -> bool:
        return path.is_file() and path.read_text(encoding="utf-8") == text

    def remove(path: Path, note: str = "") -> None:
        actions.append(f"{verb} {repo_paths.shown(path)}" + (f" ({note})" if note else ""))
        if not yes:
            return
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def keep(path: Path, why: str) -> None:
        actions.append(f"kept     {repo_paths.shown(path)} ({why})")

    def remove_if(path: Path, unchanged: bool, why: str = "changed since init") -> None:
        if unchanged:
            remove(path)
        elif path.is_file():
            keep(path, why)

    def template(*parts: str) -> str:
        return tpl.joinpath(*parts).read_text(encoding="utf-8")

    cfg = root / config.CONFIG_PATH
    if cfg.is_file():
        remove_if(cfg, config_template.written_by_init(cfg.read_text(encoding="utf-8")))
    # aidd's output for this worktree: never committed, and written again on the next run. The state every worktree
    # shares (config.state_dir) stays in the git directory, which init never wrote.
    for rel in OUTPUT_DIRS:
        out = root / rel
        if out.is_symlink() or out.is_dir():
            remove(out, "aidd's output, which it writes again")
    remove_if(root / "specs" / "README.md", same(root / "specs" / "README.md", template("specs-README.md")))
    remove_if(
        root / adoption.REVIEW_POLICY,
        same(root / adoption.REVIEW_POLICY, template(adoption.REVIEW_POLICY)),
        "the repository's review policy, changed since init",
    )
    skill = root / adoption.SKILL_REL
    if skill.exists() and skill.resolve() != bundled_skill.resolve():
        remove(skill) if skill.is_symlink() or not doctor_probes.tree_diff(bundled_skill, skill) else keep(skill, "changed since init")
    for d in list(adoption.DEFAULT_LINKS) + list(links or []):
        link = root / d / "aidd"
        if link.is_symlink():
            remove(link)
        elif link.is_dir():
            remove(link, "a copy of the skill") if not doctor_probes.tree_diff(bundled_skill, link) else keep(link, "changed since init")
    for name in adoption.DEVCONTAINER_FILES:  # what `aidd init --devcontainer` wrote
        remove_if(root / ".devcontainer" / name, same(root / ".devcontainer" / name, template("devcontainer", name)))
    for rel, texts in team_install.team_file_variants(team_install.agent_setting(root, "models"), team_install.agent_setting(root, "effort")).items():
        remove_if(root / rel, any(same(root / rel, text) for text in texts))
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            data = None
            keep(settings, "not valid JSON; remove the aidd hook by hand")
        ours = {("PreToolUse", "pre-tool"), *hook_wiring.SESSION_EVENTS.items()}
        hooks = data.get("hooks", {}) if data else {}
        kept = {
            event: [e for e in entries if not any((event, hook_wiring.aidd_hook(h.get("command"))) in ours for h in e.get("hooks", []))]
            for event, entries in hooks.items()
            if isinstance(entries, list)
        }
        removed = [event for event, entries in kept.items() if len(entries) != len(hooks[event])]
        if removed:
            actions.append(f"{verb} the aidd hooks ({', '.join(removed)}) from {repo_paths.shown(settings)}")
            if yes:
                for event in removed:
                    data["hooks"][event] = kept[event]
                    if not kept[event]:
                        del data["hooks"][event]
                if not data["hooks"]:
                    del data["hooks"]
                _dump_or_unlink(settings, data)
    mcp_file = root / ".mcp.json"
    if mcp_file.is_file():
        try:
            data = json.loads(mcp_file.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
            keep(mcp_file, "not valid JSON; remove the aidd server by hand")
        if "aidd" in data.get("mcpServers", {}):
            actions.append(f"{verb} the aidd server from {repo_paths.shown(mcp_file)}")
            if yes:
                del data["mcpServers"]["aidd"]
                if not data["mcpServers"]:
                    del data["mcpServers"]
                _dump_or_unlink(mcp_file, data)
    antigravity_wiring.uninstall(root, actions, yes=yes, verb=verb, keep=keep)
    grok_wiring.uninstall(root, actions, yes=yes, verb=verb, keep=keep)
    codex_wiring.uninstall(root, actions, yes=yes, verb=verb, keep=keep)
    opencode_wiring.uninstall(root, actions, yes=yes, verb=verb, keep=keep)
    if hook_wiring.user_launcher_path().is_file():  # every repository on this machine may start aidd through it
        actions.append(
            f"kept     {hook_wiring.USER_LAUNCHER_SHOWN} (the aidd hooks of every repository on this machine start there; "
            "remove it once no repository here uses aidd)"
        )

    def ci_same(path: Path, *parts: str) -> bool:  # compared with the pin taken out; the gate workflow may be advisory
        text = pins.unpinned(template(*parts))
        allowed = {text, re.sub(r"(mode:\s*)enforce", r"\1advisory", text, count=1)} if parts[-1] == "aidd-gate.yml" else {text}
        return path.is_file() and pins.unpinned(path.read_text(encoding="utf-8")) in allowed

    for name in (*adoption.GITHUB_WORKFLOWS, adoption.SECURITY_WORKFLOW):
        remove_if(root / ".github" / "workflows" / name, ci_same(root / ".github" / "workflows" / name, "github", name))
    for name in adoption.GITHUB_RULESETS:
        remove_if(root / ".github" / "rulesets" / name, same(root / ".github" / "rulesets" / name, template("github", "rulesets", name)))
    remove_if(root / config_template.DEPENDABOT, same(root / config_template.DEPENDABOT, config_template.dependabot_text(root)))
    pr_tpl = template("github", "pull_request_template.md")
    for path in (root / ".github" / "pull_request_template.md", root / ".gitlab" / "merge_request_templates" / "Default.md"):
        remove_if(path, same(path, pr_tpl))
    for name in ("aidd.gitlab-ci.yml", adoption.GITLAB_SECURITY):
        remove_if(root / ".gitlab" / name, ci_same(root / ".gitlab" / name, "gitlab", name))
    gi = root / ".gitignore"
    if gi.is_file():
        lines = gi.read_text(encoding="utf-8").splitlines()
        if (rest := ignore_lines.without_blocks(lines)) != lines or adoption.GITIGNORE_LINE in lines or adoption.ENV_MARK in lines:
            actions.append(f"{verb} the aidd lines from {repo_paths.shown(gi)}")
            if yes:
                aidd_lines = {adoption.GITIGNORE_LINE, adoption.ENV_MARK, *(adoption.ENV_IGNORE if adoption.ENV_MARK in lines else ())}
                rest = [x for x in rest if x not in aidd_lines]
                if any(x.strip() for x in rest):
                    gi.write_text("\n".join(rest).rstrip("\n") + "\n", encoding="utf-8")
                else:
                    gi.unlink()
    for rel, header in config.pointer_files():
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if adoption.AGENTS_MARK not in text and config.TEAM_MARK not in text:
            continue
        stripped = upgrading.strip_marked_section(upgrading.strip_marked_section(text, config.TEAM_MARK), adoption.AGENTS_MARK)
        if stripped.strip() in ("", header):
            remove(path)
        else:
            actions.append(f"{verb} the aidd sections from {repo_paths.shown(path)}")
            if yes:
                path.write_text(stripped, encoding="utf-8")
    if yes:
        # Directories init created, emptied by the removals above: deepest first, so a parent empties before its turn.
        skill_dirs = [q for base in (".claude/skills", ".agents/skills", ".grok/skills") for q in (root / base).glob("*") if q.is_dir()]
        skill_dirs += [q / "agents" for q in skill_dirs if (q / "agents").is_dir()]  # Codex's metadata folder in a skill
        candidates = [root / d for d in INIT_DIRS] + skill_dirs
        for empty in sorted(candidates, key=lambda q: -len(q.parts)):
            if empty.is_dir() and not empty.is_symlink() and not any(empty.iterdir()):
                empty.rmdir()
    if not yes:
        actions.append("dry run: nothing was removed; run `aidd uninstall --yes` to remove the items above")
    actions.append(
        "then, by hand:\n"
        "  - on the platform: drop `aidd/gate` from the branch ruleset, uninstall the gate App, and delete the `aidd-gate` environment\n"
        f"  - in Claude Code: `claude plugin uninstall aidd@{config.MARKETPLACE}` (and `aidd-team@{config.MARKETPLACE}`, `aidd-mods@{config.MARKETPLACE}`)"
    )
    return actions
