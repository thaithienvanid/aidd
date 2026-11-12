"""Reverse `aidd init` and `aidd init --aidd-team` (`aidd uninstall`): remove what they wrote, while it is still what they wrote."""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config, risk
from aidd.kernel import documents, git_reads, regular_files, repo_paths, resources
from aidd.setup import adoption, config_template, doctor_probes, files, ignore_lines, mcp_wiring, pins, team_install, team_record, upgrading, worktree_base

# The directories init may create, which uninstall removes once they are empty.
INIT_DIRS = (
    ".aidd specs .claude/commands .codex/agents .codex/rules .codex .github/agents .opencode/agents .opencode/commands .opencode .kiro/agents .kiro .claude/agents .claude/skills "
    ".claude .agents/agents .agents/skills .agents/roles .agents .grok/agents .grok/skills .grok .gitlab/merge_request_templates .gitlab .github/workflows .github/rulesets .github .qwen .vscode"
).split()


# The folders in .aidd/ that aidd writes its output into (config.layout): git ignores them, and aidd writes them again.
OUTPUT_DIRS = (config.EVIDENCE_DIR, config.VIEWS_DIR)


def drop_empty_settings(root: Path, rel: str) -> None:
    """Remove a settings file that holds nothing now that aidd took its ask rules out, and its folder when that is empty.
    One aidd reads no text from, such as a link, is left as it is."""
    path = root / rel
    try:
        data = json.loads(regular_files.repository_text(root, rel) or "")
    except (ValueError, OSError):
        return
    if not isinstance(data, dict) or not documents.holds_nothing(data):
        return
    path.unlink()
    if path.parent != path.parent.parent and not any(path.parent.iterdir()):
        path.parent.rmdir()


def _held(root: Path, path: Path) -> str | None:
    """A repository file's text through the safe reader, with its line endings as a text read gives them; None when
    it is missing or aidd refuses it."""
    text = regular_files.repository_text(root, path.relative_to(root).as_posix())
    return None if text is None else text.replace("\r\n", "\n").replace("\r", "\n")


@git_reads.shared_reads()
@team_install.rendered_once()
def uninstall(root: Path, *, links: list[str] | None = None, yes: bool = False) -> list[str]:
    """Reverse `aidd init` and `aidd init --aidd-team`: remove what they wrote, when it is still what they wrote. A dry run
    unless `yes`; it never touches Specs, and it keeps any file the user changed, saying so."""
    actions: list[str] = []
    verb = "removed " if yes else "would remove"
    tpl = resources.data_dir("templates")
    bundled_skill = resources.data_dir("skill")

    def same(path: Path, text: str) -> bool:
        return _held(root, path) == text

    def remove(path: Path, note: str = "") -> None:  # never through a link on the way, which would land somewhere else
        files.remove_safely(root, path, f"{verb} {repo_paths.shown(path)}" + (f" ({note})" if note else ""), yes, actions)

    def keep(path: Path, why: str) -> None:
        actions.append(f"kept     {repo_paths.shown(path)} ({why})")

    def remove_if(path: Path, unchanged: bool, why: str = "changed since init") -> None:
        if unchanged:
            remove(path)
        elif path.is_file() and not files.refuses_link_on_the_way(root, path, actions):  # one behind a link is named as that
            keep(path, why)

    def template(*parts: str) -> str:
        return tpl.joinpath(*parts).read_text(encoding="utf-8")  # aidd's own: the bundled templates

    cfg = root / config.CONFIG_PATH
    if (cfg_text := _held(root, cfg)) is not None:
        remove_if(cfg, config_template.written_by_init(cfg_text))
    # aidd's output for this worktree: never committed, and written again on the next run. The state every worktree
    # shares (config.state_dir) stays in the git directory, which init never wrote.
    for rel in OUTPUT_DIRS:
        out = root / rel
        if out.is_symlink() or out.is_dir():
            remove(out, "aidd's output, which it writes again")
    remove_if(root / "specs" / "README.md", same(root / "specs" / "README.md", template("specs-README.md")))
    remove_if(
        root / adoption.REVIEW_POLICY,
        any(same(root / adoption.REVIEW_POLICY, template(adoption.REVIEW_POLICY) + extra) for extra in ("", adoption.REVIEW_SKILL_BLOCK)),
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
    for path, unchanged in team_files_to_remove(root):
        remove_if(path, unchanged)
    try:
        from aidd.setup import delegation_wiring

        actions += delegation_wiring.remove(root, write=yes)
        actions += worktree_base.remove(root, write=yes)
        actions += risk.remove_harness_rules(root, write=yes)
    except (ValueError, OSError) as exc:
        actions.append(f"kept     the ask rules aidd wrote in the agents' settings ({exc})")
    mcp_wiring.remove_mcp(root, actions, yes=yes)  # before the empty files go: it takes the MCP tools aidd allowed out too
    if yes:
        for rel in (".claude/settings.json", "opencode.json"):
            drop_empty_settings(root, rel)
    if mcp_wiring.user_launcher_path().is_file():  # every repository on this machine may start aidd through it
        actions.append(
            f"kept     {mcp_wiring.USER_LAUNCHER_SHOWN} (the aidd MCP server of every repository on this machine starts there; "
            "remove it once no repository here uses aidd)"
        )

    def ci_same(path: Path, *parts: str) -> bool:  # compared with the pin taken out
        return (text := _held(root, path)) is not None and pins.unpinned(text) == pins.unpinned(template(*parts))

    for name in (*adoption.GITHUB_WORKFLOWS, adoption.SECURITY_WORKFLOW):
        remove_if(root / ".github" / "workflows" / name, ci_same(root / ".github" / "workflows" / name, "github", name))
    for name in adoption.GITHUB_RULESETS:
        ruleset = root / ".github" / "rulesets" / name
        remove_if(ruleset, any(same(ruleset, adoption.ruleset_text(template("github", "rulesets", name), p)) for p in ("solo", "team")))
    remove_if(root / config_template.DEPENDABOT, same(root / config_template.DEPENDABOT, config_template.dependabot_text(root)))
    pr_tpl = template("github", "pull_request_template.md")
    for path in (root / ".github" / "pull_request_template.md", root / ".gitlab" / "merge_request_templates" / "Default.md"):
        remove_if(path, same(path, pr_tpl))
    for name in ("aidd.gitlab-ci.yml", adoption.GITLAB_SECURITY):
        remove_if(root / ".gitlab" / name, ci_same(root / ".gitlab" / name, "gitlab", name))
    gi = root / ".gitignore"
    if (gi_text := _held(root, gi)) is not None:
        lines = gi_text.splitlines()
        if (rest := ignore_lines.without_blocks(lines)) != lines or adoption.GITIGNORE_LINE in lines or adoption.ENV_MARK in lines:
            actions.append(f"{verb} the aidd lines from {repo_paths.shown(gi)}")
            if yes:
                aidd_lines = {adoption.GITIGNORE_LINE, adoption.ENV_MARK, *(adoption.ENV_IGNORE if adoption.ENV_MARK in lines else ())}
                rest = [x for x in rest if x not in aidd_lines]
                if any(x.strip() for x in rest):
                    files.write_or_skip(root, gi, "\n".join(rest).rstrip("\n") + "\n", actions)
                else:
                    gi.unlink()
    for rel, header in config.pointer_files():
        path = root / rel
        if (text := _held(root, path)) is None:
            continue
        if adoption.AGENTS_MARK not in text and config.TEAM_MARK not in text:
            continue
        stripped = upgrading.strip_marked_section(upgrading.strip_marked_section(text, config.TEAM_MARK), adoption.AGENTS_MARK)
        if stripped.strip() in ("", header):
            remove(path)
        else:
            actions.append(f"{verb} the aidd sections from {repo_paths.shown(path)}")
            if yes:
                crlf = "\r\n" in (regular_files.repository_text(root, path.relative_to(root).as_posix()) or "")  # the person's line endings stay
                files.write_or_skip(root, path, stripped.replace("\n", "\r\n") if crlf else stripped, actions)
    if yes:
        # Directories init created, emptied by the removals above: deepest first, so a parent empties before its turn.
        skill_dirs = [q for base in (".claude/skills", ".agents/skills", ".grok/skills") for q in (root / base).glob("*") if q.is_dir()]
        skill_dirs += [d for q in skill_dirs if not q.is_symlink() for d in q.rglob("*") if d.is_dir()]  # a skill's `references/` and Codex's `agents/`
        candidates = [root / d for d in INIT_DIRS] + skill_dirs
        for empty in sorted(candidates, key=lambda q: -len(q.parts)):
            if empty.is_dir() and not regular_files.link_on_the_way(root, empty) and not any(empty.iterdir()):
                empty.rmdir()
    if not yes:
        actions.append("dry run: nothing was removed; run `aidd uninstall --yes` to remove the items above")
    actions.append(
        "then, by hand:\n"
        "  - on the platform: drop the aidd `tests` check from the branch ruleset, if you made it required\n"
        f"  - in Claude Code: `claude plugin uninstall aidd@{config.MARKETPLACE}` (and `aidd-team@{config.MARKETPLACE}`, `aidd-packs@{config.MARKETPLACE}`, `aidd-cli@{config.MARKETPLACE}`)"
    )
    return actions


def team_files_to_remove(root: Path) -> list[tuple[Path, bool]]:
    """Each team file aidd wrote, with whether it still holds what aidd wrote: the ones this aidd writes, the ones
    it no longer writes (the record names them), and the record itself last."""
    variants = team_install.team_file_variants(team_install.agent_setting(root, "models"), team_install.agent_settings(root))
    out = [(root / rel, any(_held(root, root / rel) == text for text in texts)) for rel, texts in variants.items()]
    found, _ignored = team_record.stale(root, {rel: next(iter(texts)) for rel, texts in variants.items()})  # a path aidd never wrote stays
    out += [(root / rel, unchanged) for rel, unchanged in found]
    record = root / config.TEAM_FILES_FILE
    return out + [(record, _held(root, record) is not None)]
