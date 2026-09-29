"""Edit-time guard for agents: is this path inside the active Spec's scope, and may this agent write it?

The gate decides at merge; this catches the same mistakes while the agent
works, where they are cheapest to fix. It runs locally, so it is a guide, not
a control: it allows when it cannot tell (no config, no git, no active Spec),
and the gate re-checks everything.

The guard answers allow or deny, never "ask": an approval prompt during the build would put a person back on
the critical path of every session running in parallel. Each deny names the route that fixes it; people
approve at Spec approval and Merge approval, and a deploy waits for its gated-command approval.

Decisions for an edit (Edit, Write, MultiEdit, NotebookEdit):
- deny: outside every Task's `scope` of the active Spec; outside an aidd-team role's write area;
  from a subagent that is not an aidd-team role (the loop contract's helper rule: a helper of another type only reads);
  a protected path outside every approved scope, or with no active Spec; a test or design file once the
  Spec's `status` says it passed Spec approval, or, before that, by a role that does not own it
- allow: everything else, including a protected path inside a Task's scope (the gate makes the change major)

Decisions for a shell command (Bash, or PowerShell, checked the same way), in a repository that has adopted aidd:
- deny: approving or merging a PR/MR (`gh pr review --approve`, `gh pr merge`, `gh api` review and merge
  calls, `glab mr approve|merge`), `aidd approve` and `aidd ship` through any wrapper (`uvx`, `uv run`, `pipx run`,
  `python -m`, `xargs`), a force push to or a deletion of main, master, trunk, or the repository's default branch
  (a push with no refspec counts as the current branch), and any command whose text carries `/aidd approve`,
  `/aidd approve-spec`, `refs/aidd/approvals`, or `Aidd-Merge-Approval` unless it only reads: agents never
  approve, merge, or post an approval
- deny: sending text that approves (`aidd approve`, `aidd ship`, `/aidd approve`, an approval record) into another
  terminal or program, or starting a program there with it, where it would run as if a person typed it: `orca terminal
  send|create|split`, `orca orchestration send|ask|reply|dispatch`, `orca computer type-text|paste-text|press-key|hotkey`,
  `tmux send-keys` (and `new-window`, `new-session`, `split-window`, `respawn-pane|window`), `screen`, `zellij run` and
  `zellij action write-chars|write|new-pane`, `open -a <terminal>`, `osascript`, `xdotool type|key`, `wtype`,
  `ydotool type`, `expect`, `kitty`, `wezterm`, a terminal emulator's command, or a write to /dev/tty* or /dev/pts/*.
  The text is matched as written, and again as the program receives it: unquoted, with tmux key names (`Space`,
  `Enter`) as the keys they send, and with the words run together, so quoting or escaping does not hide it. It would
  defeat the check that a person runs `aidd approve` in a terminal an agent did not start
- deny: for a role, a proposal part that is not its own, and an edit that adds or changes a proposal's `go_no_go`
  or `sign_off` (compared on the hook's Edit and Write input), which only a person records
- deny: a command that matches a `[[guard.gated_commands]]` entry (a production deploy, say) unless the
  environment Claude Code started with carries that entry's `requires` variable, which a person sets
- deny: for a role or a helper subagent, an obvious shell write (a `>` or `>>` redirect, `tee`, `sed -i`,
  `cp`, `mv`, `rm`, `touch`, `dd of=`, `git apply`, `patch`) whose target the edit rules above deny, or
  whose target the check cannot read (a patch from a pipe, an unexpanded `$VAR` or glob)
- allow: everything else

Decisions for an MCP tool (`mcp__<server>__<tool>`), in a repository that has adopted aidd:
- deny: a tool that merges or approves (`merge_pull_request`, `approve_merge_request`, `enable_auto_merge`, and the
  same words in camelCase or kebab-case, `mergePullRequest`, `complete-pull-request`), sets a commit status, submits a
  review whose input says APPROVE, or carries a `/aidd approve` line; a name that starts with a read verb (get, list,
  search, read, check, is, can, view, describe) only reads
- allow: every other MCP tool

The shell check is best-effort: it tokenizes with shlex and follows `&&`, `;`, `|`, `cd`, and `sh -c`, but
it does not run the shell, so a write through an interpreter (`python -c`), a variable, or a build tool
is not seen. That is why it guides and the gate's scope rule, on the real diff, decides. Program names compare as
Windows names too (`gh.exe`, `GH.EXE`, `aidd.cmd`), and a PowerShell command loses its backtick escapes first. A command
shlex cannot read is read again with its ANSI-C strings (`$'it\\'s'`) rewritten and its here-document bodies set aside
(a body a shell reads is checked as commands); one it still cannot read is denied when its raw text approves, merges,
or force-pushes, and denied outright under AIDD_HOOK_FAIL_CLOSED=1.

Each deny of the hook appends one JSON line to .aidd/work/guard.jsonl (ignored by git): when, the role, the tool,
the path or command (at most 200 characters, never a file's contents), and the reason code (REASON_CODES).
Secret-looking values in a logged command (an Authorization header, a bearer token, `*_TOKEN=`, `*_KEY=`,
`*SECRET*=`, `--password X`, a URL's `user:password@`) are replaced with `***` first. `aidd metrics --guard` counts them.
"""

from __future__ import annotations

import fnmatch
import json
import ntpath
import os
import re
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import config as cfgmod
from . import gitutil, globs, inputs, local, model, resources, rules
from .util import utc_stamp

# The guard never asks: every check answers allow or deny, so no prompt puts a person on the critical path.
Decision = Literal["allow", "deny"]
Verdict = tuple[Decision, str]


def branch_base(root: str) -> str:
    """The merge-base of HEAD and the default branch, or HEAD when there is none."""
    try:
        return gitutil.merge_base(gitutil.rev_parse(inputs.default_base(root), root), gitutil.rev_parse("HEAD", root), root)
    except (gitutil.GitError, ValueError, LookupError):
        return "HEAD"


def changed_since(root: str, base: str, *pathspec: str) -> list[str]:
    """Paths (under `pathspec`) that differ from `base`: committed on the branch, staged, unstaged, or untracked."""
    tail = ["--", *pathspec] if pathspec else []
    changed = gitutil.run(["diff", "--name-only", "-z", base, *tail], root, check=False).split("\0")
    changed += gitutil.run(["ls-files", "--others", "--exclude-standard", "-z", *tail], root, check=False).split("\0")
    return sorted({p for p in changed if p})


def _specs(root: str, cfg: cfgmod.Config) -> list[tuple[str, dict]]:
    """AIDD_SPEC, or every Spec this branch adds or changes."""
    wanted = os.environ.get("AIDD_SPEC")
    candidates = [inputs.repo_path(wanted)] if wanted else [p for p in changed_since(root, branch_base(root), cfg.specs_dir) if p.endswith(".md")]
    found = []
    for rel in candidates:
        p = Path(root) / rel
        if not p.is_file():
            continue
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), rel)
        except model.ModelError:
            continue
        if data.get("kind") == "spec":
            found.append((rel, data))
    return found


TEAM_PREFIX = "aidd-"  # `aidd init --team` installs each role as the project agent `aidd-<role>`


def role_of(event: dict) -> str | None:
    """The aidd-team role a subagent plays: `aidd-team:<role>` from the plugin, or `aidd-<role>` that
    `aidd init --team` installed as a project agent. A bare `developer` or another plugin's agent with a
    role's name is not a role: any project may have its own agent called `reviewer`."""
    agent = event.get("agent_type") or ""
    prefix, _, name = agent.rpartition(":")
    if prefix == "aidd-team" or (not prefix and name.startswith(TEAM_PREFIX)):
        name = name if prefix else name[len(TEAM_PREFIX) :]
        return name if name in resources.roles()["roles"] else None
    return None


def is_helper(event: dict) -> bool:
    """A subagent that is not an aidd-team role: the loop contract's helper rule ("Use AI as a delivery team does") lets it read, never write.

    The person running the session can lift this for their own helpers with AIDD_HELPERS_MAY_WRITE=1 in the
    environment Claude Code starts with; an agent's shell cannot set it for the hook.
    """
    return bool(event.get("agent_type")) and role_of(event) is None and os.environ.get("AIDD_HELPERS_MAY_WRITE") != "1"


def _mine(task: dict, role: str | None) -> bool:
    """A Task assigned to `agent:<role>` belongs to that role alone; an unassigned Task to any role that ships code."""
    who = str(task.get("assignee") or "")
    if not who.startswith("agent:") or who[len("agent:") :] not in resources.roles()["roles"]:
        return True
    return role is None or who == f"agent:{role}"


def _fill(cfg: cfgmod.Config, specs: list[tuple[str, dict]], role: str | None = None) -> dict[str, list[str]]:
    """What each role-area placeholder covers. With several Specs on the branch, it covers them all."""
    return {
        "{specs_dir}": [cfg.specs_dir.rstrip("/") + "/**"],
        "{proposals_dir}": [cfg.proposals_dir.rstrip("/") + "/**"],
        "{spec}": [rel for rel, _ in specs],
        "{tests}": [p for _, d in specs for p in (d.get("tests") or {}).get("files", [])],
        "{design}": [p for _, d in specs for p in (d.get("design") or {}).get("files", [])],
        "{scope}": [s for _, d in specs for task in d.get("tasks", []) if _mine(task, role) for s in task.get("scope", [])],
    }


def _writes(role: str, unfrozen: bool) -> list[str]:
    """The role's write area. `unfrozen`: every active Spec is an emergency backfill, where nothing is frozen yet, so
    the role's `writes_unfrozen` (the developer's regression test) joins its area."""
    r = resources.roles()["roles"][role]
    return list(r["writes"]) + (list(r.get("writes_unfrozen", [])) if unfrozen else [])


def _role_allows(role: str, rel: str, fill: dict[str, list[str]], unfrozen: bool = False) -> tuple[bool, str]:
    """Whether `rel` is in the role's area, and the area in words."""
    from .docs import role_writes

    writes = _writes(role, unfrozen)
    patterns = [p for w in writes for p in fill.get(w, [w])]
    return globs.match_any(patterns, rel), role_writes(writes)


def _offline_fetch(url: str) -> bytes:
    """Refuse an `extends` URL parent. The guard runs inside a 20-second edit hook, so a
    repo-controlled URL must never block the edit or beacon from a developer's machine."""
    raise RuntimeError(f"not fetched: the edit-time guard does not use the network ({url})")


# Spec statuses that mean Spec approval has happened (common.schema.json `status`): at `ready` a human approved the hash, and
# every later status keeps that approval. `draft` comes before Spec approval; `blocked` and `cancelled` can come from either
# side, so they say nothing, and the guard falls back to who owns the file.
FROZEN_STATUSES = frozenset({"ready", "in_progress", "in_review", "released", "done", "rolled_back"})


def _frozen_by(specs: list[tuple[str, dict]], rel: str, section: str) -> list[str]:
    """IDs of the active Specs that list `rel` among their `tests` or `design` files and whose status says they
    passed Spec approval. An emergency Spec is a backfill: nothing on it is frozen yet."""
    return [
        str(d.get("id"))
        for _, d in specs
        if d.get("route") != "emergency" and d.get("status") in FROZEN_STATUSES and globs.match_any((d.get(section) or {}).get("files", []), rel)
    ]


def _drafts(specs: list[tuple[str, dict]]) -> list[str]:
    """IDs of the active Specs that have not had Spec approval yet (status draft, the default): their scope and tests
    can still change, so a path they miss means "add it to the Spec", never "get it approved again"."""
    return [str(d.get("id")) for _, d in specs if d.get("route") != "emergency" and d.get("status", "draft") == "draft"]


# A file a test runner would pick up: the naming conventions of the common runners, or a file under a tests folder.
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|e2e|testing)/|(?:^|/)test_[^/]*\.py$|_test\.(?:py|go|rb|dart)$|\.(?:test|spec)\.[cm]?[jt]sx?$|Tests?\.(?:java|cs|kt)$|_spec\.rb$"
)


def looks_like_test(rel: str) -> bool:
    return bool(_TEST_PATH.search(rel))


def _draft_hint(rel: str, ids: str) -> str:
    """What to do with a path a not-yet-approved Spec does not cover: change the Spec, which is still open."""
    if looks_like_test(rel):
        return f"{rel} is outside the scope of {ids} and not in its tests.files: add it to tests.files in the Spec (it isn't approved yet), then write it"
    return (
        f"{rel} is outside the scope of {ids}: add it to a Task's scope in the Spec (it isn't approved yet), "
        "then build it after Spec approval; or leave it alone"
    )


def _owns(role: str | None, placeholder: str, unfrozen: bool) -> bool:
    """Whether `role` writes `{tests}` or `{design}`: the tester and the product designer, and on an emergency backfill
    the developer's regression test. The session itself, with no role, plays every role."""
    return role is None or placeholder in _writes(role, unfrozen)


def _protected_deny(rel: str, protected: str, where: str) -> Verdict:
    return "deny", (
        f"{rel} is a protected path ({protected}), and {where}. A change to it becomes major and needs a specialist "
        "review, so it waits for an approved scope: add it to a Task's scope in the Spec and get Spec approval, then edit it; "
        "or leave it alone"
    )


def _frozen_file(specs: list[tuple[str, dict]], rel: str, role: str | None, kind: str, unfrozen: bool) -> Verdict:
    """A test or design file of the Spec: its owner writes it until Spec approval, and nobody after."""
    section, placeholder = ("tests", "{tests}") if kind == "test" else ("design", "{design}")
    owner = "the tester" if kind == "test" else "the product designer"
    frozen = _frozen_by(specs, rel, section)
    if frozen:
        return "deny", (
            f"{rel} is a {kind} file of {', '.join(frozen)}, frozen by Spec approval (the Spec's status says it was approved), and any "
            f"edit voids the approval. To change it, move the Spec back to status draft (a wrong Spec), let {owner} "
            f"change its {section}, and ask for Spec approval again on the new hash"
        )
    if not _owns(role, placeholder, unfrozen):
        return "deny", (
            f"{rel} is a {kind} file of the Spec: {owner} writes it while specifying, and after Spec approval nobody does. Hand the change to that role"
        )
    return "allow", (
        f"a {kind} file of the Spec, before Spec approval: the Spec's status does not say it was approved, so write it now; "
        "it is frozen once the Spec is approved"
    )


# Who writes which part of a proposal's folder: the product manager and the tech writer the proposal itself, and each
# specialist only its own part. The decisions in it (go_no_go, sign_off) are a person's, never an agent's.
PROPOSAL_PARTS = {
    "product-manager": ("proposal.md",),
    "tech-writer": ("proposal.md",),
    "architect": ("architecture.md",),
    "product-designer": ("experience.md",),
    "security-engineer": ("security.md",),
    "compliance-analyst": ("compliance.md",),
    "sre": ("operations.md",),
}
PROPOSAL_RULE = (
    "in a proposal's folder the product manager and the tech writer write proposal.md, and each specialist only its own part "
    "(architect architecture.md, product designer experience.md, security engineer security.md, compliance analyst compliance.md, "
    "SRE operations.md); only a person records go_no_go and sign_off"
)
PROPOSAL_DECISIONS = ("go_no_go", "sign_off")
_DECISION_KEY = re.compile(r"^\s*\[{1,2}\s*(?:go_no_go|sign_off)\b|^\s*(?:go_no_go|sign_off)\s*=", re.M)


def _decisions(text: str, rel: str) -> tuple | None:
    """The go_no_go and sign_off a proposal records, or None when its front matter does not parse."""
    try:
        data, _ = model.split_front_matter(text, rel)
    except model.ModelError:
        return None
    return tuple(json.dumps(data.get(k), sort_keys=True, default=str) for k in PROPOSAL_DECISIONS)


def _proposal_edit(role: str, rel: str, old_text: str | None, new_text: str | None) -> Verdict:
    own = PROPOSAL_PARTS.get(role)
    if own and Path(rel).name not in own:
        return "deny", f"the {role} role writes only {', '.join(own)} of a proposal; {rel} is another part. Hand off instead: {PROPOSAL_RULE}"
    if new_text is not None:
        after = _decisions(new_text, rel)
        if after is None:
            # Front matter that does not parse cannot be compared: naming a decision in it is enough to stop.
            changed = bool(_DECISION_KEY.search(new_text))
        else:
            before = _decisions(old_text, rel) if old_text else None
            changed = after != (before or ("null", "null"))
        if changed:
            return "deny", (
                f"{rel}: this edit adds or changes go_no_go or sign_off, which only a person records; leave them to the person "
                f"who decides and write the rest. The rule: {PROPOSAL_RULE}"
            )
    return "allow", f"a proposal, inside the {role} role's part"


def check_edit(root: str, rel: str, role: str | None = None, old_text: str | None = None, new_text: str | None = None) -> Verdict:
    """(decision, reason) for editing the repo-relative path `rel`, optionally as an aidd-team role.

    `old_text` and `new_text`, when the caller knows them (the hook's Edit and Write input), are the file before and
    after the edit: a proposal's go/no-go and sign-off are checked on them. A role first limits the paths to its own
    area; every edit then meets the same Spec rules, listed in the module docstring.
    """
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch)
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError):
        return "allow", "no valid .aidd/config.toml"
    roles = resources.roles()["roles"]
    if role and role not in roles:
        return "deny", f"unknown aidd-team role {role!r}; one of {', '.join(roles)}"
    protected = globs.first_match(rules.protected_paths(cfg), rel, fold_case=True)
    specs = _specs(root, cfg)
    if not role and not specs:
        return _protected_deny(rel, protected, "there is no active Spec") if protected else ("allow", "no active Spec")
    if not role and len(specs) > 1 and not protected:
        return "allow", "several Specs on the branch; the gate's scope rule checks the diff"
    fill = _fill(cfg, specs, role)
    writes = roles[role]["writes"] if role else []
    in_scope = bool(role and roles[role].get("in_scope"))
    own_spec = "{specs_dir}" in writes and globs.match_any(fill["{specs_dir}"], rel)
    if role and "{proposals_dir}" in writes and globs.match_any(fill["{proposals_dir}"], rel):
        # A proposal comes before any Spec: nothing ships from it, and people decide it at go/no-go and sign-off.
        return _proposal_edit(role, rel, old_text, new_text)
    if role and in_scope and not specs and not own_spec:
        # The fast and emergency lanes have no Spec: the scope lives in the Change Request block, which the gate
        # checks. Keep the role's own paths and leave the lane to the gate rather than stop to ask.
        paths = [w for w in writes if not w.startswith("{")]
        if paths and "{scope}" not in writes and not globs.match_any(paths, rel):
            return "deny", f"the {role} role writes only {_role_allows(role, rel, fill)[1]}; {rel} belongs to another role. Hand off instead."
        if protected:
            return _protected_deny(rel, protected, "there is no active Spec")
        return "allow", (
            f"no active Spec: {rel} is fine only on the fast or emergency lane (`aidd next` computed minor or standard, or the author declared an emergency) "
            "and inside the Change Request's scope; on the spec lane, implementation waits for Spec approval"
        )
    unfrozen = bool(specs) and all(d.get("route") == "emergency" for _, d in specs)
    drafts = _drafts(specs)
    if role and drafts and "{tests}" in writes and looks_like_test(rel) and not protected and not globs.match_any(fill["{tests}"] + fill["{scope}"], rel):
        # The test writer's own new file, before Spec approval: the fix is in the Spec, which is still open.
        return "deny", _draft_hint(rel, ", ".join(drafts))
    if role:
        ok, allowed = _role_allows(role, rel, fill, unfrozen)
        if not ok:
            return "deny", f"the {role} role writes only {allowed}; {rel} belongs to another role. Hand off instead."
        if own_spec:
            return "allow", f"a Spec, inside the {role} role's area"
        if not specs:
            return "deny", (
                f"no active Spec, so {rel} has no approved scope. Start Specify with `aidd new spec`, or set "
                "AIDD_SPEC=specs/<ID>.md when the branch holds several Specs"
            )
    if rel in fill["{spec}"] and not in_scope:
        if drafts:
            return "allow", (
                "the active Spec, before Spec approval: finish its scope, tests.files, and tests, then `aidd validate` it and "
                "ask for Spec approval (`aidd hash --comment` prints the line)"
            )
        return "allow", "the active Spec"
    if globs.match_any(fill["{tests}"], rel):
        return _frozen_file(specs, rel, role, "test", unfrozen)
    if globs.match_any(fill["{design}"], rel):
        return _frozen_file(specs, rel, role, "design", unfrozen)
    if globs.match_any(fill["{scope}"] + cfg.get("scope_exempt_paths", default=[]), rel):
        if protected:
            return "allow", f"inside the approved scope; {rel} is a protected path ({protected}), so the gate makes the change major with a specialist review"
        return "allow", "inside the scope"
    ids = ", ".join(str(d.get("id")) for _, d in specs)
    if protected:
        return _protected_deny(rel, protected, f"it is outside the scope of {ids}")
    if role and not in_scope:
        return "deny", (
            f"{rel} is outside the scope of {ids}. Record it in the Spec now; add a Task whose scope covers the file, and write it in Implement, after Spec approval."
        )
    if drafts and len(drafts) == len(specs):
        return "deny", _draft_hint(rel, ids)
    return "deny", (
        f"{rel} is outside the scope of {ids} ({', '.join(fill['{scope}']) or 'none'}). "
        "Stop: widen the Spec and get it approved again, or leave this file alone."
    )


def repo_relative(root: str, path: str) -> str:
    """A path as the guard compares it: relative to the repository, whether given absolute or `./`-prefixed."""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return path
    return inputs.repo_path(path)


def _edit_path(event: dict) -> str | None:
    tool_input = event.get("tool_input") or {}
    return tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")


def _adopted(root: str) -> bool:
    """The repository has an aidd config: the team's rules apply here, and nowhere else."""
    return (Path(root) / cfgmod.CONFIG_PATH).is_file()


HELPER_DENY = (
    'a subagent that is not an aidd-team role may only read (the loop contract\'s helper rule, "Use AI as a delivery team does"): spawn the helper as your own '
    "`aidd-team:<role>` type to write, or hand the edit back to the role or the author"
)


def _edit_texts(root: str, rel: str, event: dict) -> tuple[str | None, str | None]:
    """(before, after) of the file an Edit, MultiEdit, or Write event changes; (None, None) when the event does not say."""
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    if tool not in ("Edit", "MultiEdit", "Write"):
        return None, None
    path = Path(root) / rel
    try:
        old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        old = ""
    if tool == "Write":
        return old, str(ti.get("content") or "")
    edits = ti.get("edits") if tool == "MultiEdit" else [ti]
    new = old
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("old_string") or ""), str(e.get("new_string") or "")
        new = new.replace(a, b) if e.get("replace_all") else (new.replace(a, b, 1) if a else b + new)
    return old, new


def check_agent_edit(root: str, rel: str, event: dict) -> Verdict:
    """(decision, reason) for an edit by whoever `event` says is editing: a role, a helper subagent, or the session."""
    if is_helper(event) and _adopted(root):
        return "deny", f"{rel}: {HELPER_DENY}"
    old, new = _edit_texts(root, rel, event)
    return check_edit(root, rel, role_of(event), old, new)


# ---- the shell check -------------------------------------------------------------------------------------

_SEPARATOR_CHARS = set(";&|()")
_WRAPPERS = {"sudo", "command", "nohup", "time", "exec", "builtin", "nice", "stdbuf", "timeout"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
_POWERSHELLS = {"pwsh", "powershell"}
_IGNORED_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "-", ""}
_GRAPHQL_WRITES = re.compile(
    r"\b(?:mergePullRequest|addPullRequestReview|submitPullRequestReview|enablePullRequestAutoMerge|approvePullRequest|"
    r"mergeBranch|mergeMergeRequest|mergeRequestAccept|mergeRequestApprove)\b"
)
_AIDD_APPROVE = re.compile(r"/aidd\s+approve", re.I)
_APPROVAL_RECORD = re.compile(r"refs/aidd/approvals|Aidd-Merge-Approval", re.I)
_PROTECTED_BRANCHES = {"main", "master", "trunk"}


def _prog(word: str) -> str:
    """A program word as the guard compares it: its basename on either path separator, lowercased, without a Windows
    launcher suffix, so `gh.exe`, `C:\\tools\\GH.EXE`, and `aidd.cmd` are `gh` and `aidd`."""
    name = ntpath.basename(word).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _powershell_plain(command: str) -> str:
    """A PowerShell command with its backtick escapes undone (`` mer`ge `` is `merge`): the text PowerShell runs."""
    return re.sub(r"`(.)", r"\1", re.sub(r"`\r?\n", " ", command), flags=re.S)


def _tokens(command: str) -> list[str]:
    # A newline ends a command like `;` does; inside quotes it only changes text this check never executes.
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    return list(lex)


def _is_separator(tok: str) -> bool:
    return bool(tok) and set(tok) <= _SEPARATOR_CHARS


def _is_redirect(tok: str) -> bool:
    return bool(tok) and set(tok) <= set("<>&|") and (">" in tok or "<" in tok)


@dataclass
class _Simple:
    """One simple command: its words, the files it redirects output to, and the files it reads as input."""

    argv: list[str] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    inp: list[str] = field(default_factory=list)


_ANSI_C = re.compile(r"\$'((?:\\.|[^'\\])*)'", re.S)
_ANSI_C_ESCAPES = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_ANSI_C_CODE = re.compile(r"\\(?:x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([0-7]{1,3})|(.))", re.S)
# `<<EOF`, `<<-EOF`, `<<'EOF'`, `<< "EOF"`, `<<\EOF`; never the here-string `<<<`.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z0-9_.-]+))")
_SHELL_OPENER = re.compile(r"(?:^|[\s;&|(/\\])(?:sh|bash|zsh|dash|ksh|fish|pwsh|powershell)(?:\.exe)?\b[^\n]*?(?<!<)<<(?!<)", re.I)


def _ansi_c_char(m: re.Match) -> str:
    hexa, uni, uni8, octal, other = m.groups()
    if hexa or uni or uni8 or octal:
        code = int(hexa or uni or uni8, 16) if (hexa or uni or uni8) else int(octal, 8)
        return chr(code) if code < 0x110000 else ""
    return _ANSI_C_ESCAPES.get(other, other if other in "\\'\"?" else "\\" + other)


def _plain_ansi_c(command: str) -> str:
    """`command` with each bash ANSI-C string (`$'it\\'s'`) rewritten as the single-quoted word it stands for, which shlex reads."""
    return _ANSI_C.sub(lambda m: shlex.quote(_ANSI_C_CODE.sub(_ansi_c_char, m.group(1))), command)


def _split_heredocs(command: str) -> tuple[str, list[str]]:
    """(`command` without its here-document bodies, the bodies a shell reads as commands). A body is text for the
    program it feeds (a commit message, a file), except when that program is a shell, which runs it."""
    lines = command.split("\n")
    kept: list[str] = []
    shell_bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        openers = list(_HEREDOC.finditer(line))
        for n, m in enumerate(openers):
            strip_tabs, word = m.group(1) == "-", next(g for g in m.groups()[1:] if g is not None)
            body: list[str] = []
            while i < len(lines) and (lines[i].lstrip("\t") if strip_tabs else lines[i]) != word:
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            if n == 0 and _SHELL_OPENER.search(line):
                shell_bodies.append("\n".join(body))
    return "\n".join(kept), shell_bodies


def _simple_commands(command: str, depth: int = 0, broken: list[str] | None = None) -> list[_Simple]:
    """Split a command line into simple commands, following `sh -c`, `bash -c`, and `eval` one level at a time.

    A command shlex cannot read (an ANSI-C string `$'it\\'s'`, a here-document with an apostrophe in it) is read again
    with those rewritten; one it still cannot read is added to `broken`, so the caller never takes "nothing parsed"
    for "nothing to deny"."""
    extra: list[_Simple] = []
    try:
        toks = _tokens(command)
    except ValueError:
        stripped, bodies = _split_heredocs(command)
        try:
            toks = _tokens(_plain_ansi_c(stripped))
        except ValueError:
            if broken is not None:
                broken.append(command)
            return []
        for body in bodies if depth < 3 else []:
            extra += _simple_commands(body, depth + 1, broken)
    out: list[_Simple] = []
    cur = _Simple()
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if _is_redirect(tok):
            target = toks[i] if i < len(toks) else ""
            i += 1
            # `2>&1` and `>&2` duplicate a descriptor; the digit after `>&` is not a file.
            if not (tok.endswith("&") and target.isdigit()):
                (cur.inp if "<" in tok else cur.out).append(target)
        elif _is_separator(tok):
            if cur.argv:
                out.append(cur)
            cur = _Simple()
        else:
            cur.argv.append(tok)
    if cur.argv:
        out.append(cur)
    expanded: list[_Simple] = []
    for sc in out:
        expanded.append(sc)
        argv = _program_argv(sc.argv)
        if depth < 3 and argv:
            name = _prog(argv[0])
            flag = next((a for a in argv[1:] if a == "-c" or (name in _POWERSHELLS and a.lower() in ("-c", "-command"))), None)
            if name in _SHELLS | _POWERSHELLS and flag and argv.index(flag) + 1 < len(argv):
                expanded += _simple_commands(" ".join(argv[argv.index(flag) + 1 :]) if name in _POWERSHELLS else argv[argv.index(flag) + 1], depth + 1, broken)
            elif name == "eval":
                expanded += _simple_commands(" ".join(argv[1:]), depth + 1, broken)
    return expanded + extra


def _program_argv(argv: list[str]) -> list[str]:
    """The words after environment assignments and wrappers such as `sudo`, `env`, `command`, and `timeout 10`."""
    i = 0
    while i < len(argv):
        word = argv[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", word):
            i += 1
        elif _prog(word) == "env":
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i]):
                i += 1
        elif _prog(word) in _WRAPPERS:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or (_prog(argv[i - 1]) == "timeout" and argv[i][:1].isdigit())):
                i += 1
        else:
            break
    return argv[i:]


def _words(args: list[str], value_flags: set[str]) -> list[str]:
    """Positional words, skipping flags and the values of the flags that take one."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            skip = a in value_flags
            continue
        out.append(a)
    return out


_GH_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject", "--author-email", "-H", "--header", "-X", "--method"}
_GH_API_VALUE_FLAGS = {
    "-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq", "-t", "--template",
    "--hostname", "-p", "--preview", "--cache",
}  # fmt: skip


def _flag_value(args: list[str], *names: str) -> str | None:
    for i, a in enumerate(args):
        for n in names:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(n + "=") and n.startswith("--"):
                return a.split("=", 1)[1]
            if not n.startswith("--") and a.startswith(n) and len(a) > len(n):
                return a[len(n) :]
    return None


def _api_write(args: list[str], merge: re.Pattern, review: re.Pattern) -> bool:
    """`gh api` or `glab api` with an endpoint that merges or approves, called with a writing method."""
    words = _words(args, _GH_API_VALUE_FLAGS)
    endpoint = words[0] if words else ""
    method = (_flag_value(args, "-X", "--method") or "").upper()
    has_fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
    writes = method in ("POST", "PUT", "PATCH") or (not method and has_fields)
    if endpoint.strip("/") == "graphql":
        return bool(_GRAPHQL_WRITES.search(" ".join(args)))
    # A GET of the merge endpoint only asks whether the PR merged; a review listing only reads approvals.
    return bool(merge.search(endpoint) or review.search(endpoint)) and writes


_GH_MERGE = re.compile(r"/pulls/[^/]+/merge\b|/merges\b|/pulls/[^/]+/update-branch\b")
_GH_REVIEW = re.compile(r"/pulls/[^/]+/reviews\b")
_GL_MERGE = re.compile(r"/merge_requests/[^/]+/merge\b")
_GL_REVIEW = re.compile(r"/merge_requests/[^/]+/(?:approve|unapprove)\b")


_SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "head", "tail", "less", "more", "wc", "awk"}


def _only_reads(argv: list[str]) -> bool:
    """A search or a view, which may name `/aidd approve` without posting it: `grep -rn '/aidd approve' docs/`."""
    if not argv:
        return True
    name, args = _prog(argv[0]), argv[1:]
    if name == "sed":
        return not any(a == "-i" or a.startswith(("-i", "--in-place")) for a in args)
    if name == "git":
        return _words(args, {"-C", "-c"})[:1] in (["grep"], ["log"], ["show"], ["diff"], ["blame"])
    return name in _SEARCHERS


# The modules `python -m` runs aidd's command line from.
_AIDD_MODULES = frozenset({"aidd", "aidd.cli", "aidd.__main__"})


def _aidd_decision(argv: list[str]) -> str | None:
    """`approve` or `ship` when a simple command runs aidd with it, through any wrapper: `uvx aidd`, `uv run aidd`,
    `pipx run aidd`, `python -m aidd` (or `-m aidd.cli`, `-maidd`), `xargs aidd`, `script -c 'aidd ...'`. Every word
    naming the aidd program (its basename, or the module after `-m`) is followed to its first positional word."""
    if not argv or _prog(argv[0]) in _SEARCHERS | {"echo", "printf"}:
        return None
    for i, word in enumerate(argv):
        if _prog(word) == "aidd":
            start = i + 1
        elif word == "-m" and i + 1 < len(argv) and argv[i + 1] in _AIDD_MODULES:
            start = i + 2
        elif word.startswith("-m") and word[2:] in _AIDD_MODULES:
            start = i + 1
        else:
            continue
        first = _words(argv[start:], set())[:1]
        if first and first[0] in ("approve", "ship"):
            return first[0]
    return None


def _push_denial(args: list[str], root: str | None) -> str | None:
    """Why a `git push` rewrites or deletes a protected branch, or None. `root` resolves a push with no refspec (the
    current branch) and adds the repository's default branch to the protected set."""
    rest = args[args.index("push") + 1 :]
    protected = set(_PROTECTED_BRANCHES)
    current = ""
    if root:
        try:
            protected.add(inputs.default_base(root).removeprefix("origin/"))
        except gitutil.GitError:
            pass
        current = gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()

    def short(flag: str, letter: str) -> bool:
        return flag.startswith("-") and not flag.startswith("--") and letter in flag[1:]

    forced = any(a in ("--force", "--force-if-includes") or a.startswith("--force-with-lease") or short(a, "f") or a.startswith("+") for a in rest)
    deleting = any(a == "--delete" or short(a, "d") for a in rest)
    if "--mirror" in rest or (forced and "--all" in rest) or ("--prune" in rest and "--all" in rest):
        return "a mirror, or a push of every branch that rewrites or deletes: it reaches the protected branches"
    refspecs = _words(rest, {"-o", "--push-option", "--repo", "--receive-pack", "--exec"})[1:]
    targets: set[str] = set()
    deleted: set[str] = set()
    for r in refspecs:
        src, colon, dst = r.lstrip("+").rpartition(":")
        name = (dst if colon else r.lstrip("+")).removeprefix("refs/heads/")
        if name == "HEAD":
            name = current
        (deleted if (colon and not src) or deleting else targets).add(name)
        if r.startswith("+"):
            forced = True
    if not refspecs and forced and current:
        targets.add(current)  # no refspec: git pushes the current branch
    if deleted & protected:
        return f"deleting the protected branch {', '.join(sorted(deleted & protected))}: history on the default branch is never removed by an agent"
    if forced and targets & protected:
        return "a force push to a protected branch: history on the default branch is never rewritten by an agent"
    return None


# Text that approves when a person's terminal runs it: `aidd approve`, `aidd ship` (also as `python -m aidd.cli`),
# `/aidd approve`, and the local approval records.
_APPROVAL_TEXT = re.compile(r"\baidd(?:\.cli|\.__main__)?\s+(?:approve|ship)\b|/aidd\s+approve|refs/aidd/approvals|Aidd-Merge-Approval", re.I)
# The same text as the program receives it, after the quoting and escaping a raw match misses: the words may run
# together (`"aid""d approve"`, `aidd Space approve`), so no word boundary is required before `aidd`; the word after
# `approve` or `ship` must end there, as it must for a shell to run it.
_APPROVAL_RECEIVED = re.compile(r"aidd(?:\.cli|\.__main__)?\s+(?:approve|ship)(?![A-Za-z0-9_-])|/aidd\s+approve|refs/aidd/approvals|Aidd-Merge-Approval", re.I)
_TTY_DEVICES = ("/dev/tty", "/dev/pts/", "/dev/console")
_KEY_SENDERS = {"xdotool": {"type", "key", "keydown", "keyup"}, "ydotool": {"type", "key"}}
# tmux commands that send text to a pane, or start a program in a new or respawned one.
_TMUX_SENDS = {
    "send-keys", "send", "paste-buffer", "pasteb", "set-buffer", "setb", "load-buffer", "loadb",
    "new-window", "neww", "new-session", "new", "split-window", "splitw", "respawn-pane", "respawnp",
    "respawn-window", "respawnw", "run-shell", "run", "display-popup", "popup",
}  # fmt: skip
# The key names tmux (and `orca computer press-key`) turns into the characters they type.
_KEY_NAMES = {"Space": " ", "Enter": "\n", "KPEnter": "\n", "Return": "\n", "C-m": "\n", "C-j": "\n", "Tab": "\t"}
# orca subcommands that type into a terminal or an app, start a program in a terminal, or hand text to another agent.
_ORCA_SENDS = {
    "terminal": {"send", "create", "split"},
    "orchestration": {"send", "ask", "reply", "dispatch", "worker-start"},
    "computer": {"type-text", "paste-text", "press-key", "hotkey", "set-value"},
    "emulator": {"type"},
    "worktree": {"create"},
    "automations": {"create", "edit"},
    "type": set(),
}
# Terminal emulators and multiplexers that run the command they are given in a new terminal.
_TERMINALS = {
    "gnome-terminal", "xterm", "konsole", "alacritty", "x-terminal-emulator", "xfce4-terminal", "terminator", "tilix",
    "ghostty", "foot", "urxvt", "rxvt", "st", "wt", "kitty", "kitten", "wezterm", "screen", "osascript", "wtype", "expect",
}  # fmt: skip


def _sends_input(sc: _Simple) -> bool:
    """Whether a simple command sends text into another terminal or program, or starts a program in another terminal,
    where it would run as if a person typed it (the module docstring lists the senders)."""
    argv = _program_argv(sc.argv)
    if any(t.startswith(_TTY_DEVICES) for t in sc.out):
        return True
    if not argv:
        return False
    name, args = _prog(argv[0]), argv[1:]
    if name == "xargs":  # `... | xargs tmux send-keys -t 0`: the command xargs runs
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-I", "-n", "-L", "-P", "-d", "-E", "-s", "-a") else 1
        return _sends_input(_Simple(args[i:]))
    if name == "tee":
        return any(a.startswith(_TTY_DEVICES) for a in args)
    if name == "orca":
        words = _words(args, set())
        if not words or words[0] not in _ORCA_SENDS:
            return False
        subs = _ORCA_SENDS[words[0]]
        return not subs or bool(subs & set(words[1:2]))
    if name == "tmux":
        return bool(_TMUX_SENDS & set(args))
    if name == "zellij":
        return bool({"run", "action", "edit"} & set(args))
    if name == "open":
        return any(a in ("-a", "-b", "--args") or (a[:2] in ("-a", "-b") and not a.startswith("--")) for a in args)
    if name in _TERMINALS:
        return True
    if name in _KEY_SENDERS:
        return bool(_KEY_SENDERS[name] & set(args))
    return False


def _received_forms(argv: list[str]) -> list[str]:
    """The text a sender's words make once the receiving program has them: joined with spaces and run together,
    with tmux key names as their characters, and each word parsed again as the shell that runs it would parse it.
    Whitespace runs collapse to one space."""
    keys = [_KEY_NAMES.get(a, a) for a in argv]
    forms = [" ".join(keys), "".join(keys)]
    for a in argv:
        try:
            toks = _tokens(a)
        except ValueError:
            continue
        forms += [" ".join(toks), "".join(toks)]
    return [re.sub(r"\s+", " ", f) for f in forms]


def _types_approval(sc: _Simple) -> bool:
    """A simple command that sends input, whose text carries an approval once quoting and escaping are undone."""
    return _sends_input(sc) and any(_APPROVAL_RECEIVED.search(f) for f in _received_forms(_program_argv(sc.argv)))


# Checks on the raw text of a command the shell check cannot parse: each is a denial the parsed checks would make.
_RAW_MERGE = re.compile(r"\b(?:gh|glab)(?:\.exe)?\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?(?:pr|mr)\s+(?:merge|review|approve|accept)\b", re.I)
_RAW_API = re.compile(
    r"\b(?:gh|glab)(?:\.exe)?\s+api\b[^\n;&|]*(?:/pulls/[^/\s]+/(?:merge|reviews|update-branch)\b|/merges\b|/merge_requests/[^/\s]+/(?:merge|approve|unapprove)\b)",
    re.I,
)
_RAW_FORCE_PUSH = re.compile(r"\bgit(?:\.exe)?\b[^\n;&|]*\spush\b[^\n;&|]*\s(?:--force\b|--force-with-lease|--mirror\b|--delete\b|-[A-Za-z]*[fd]\b|\+\S)", re.I)
FAIL_CLOSED_ENV = "AIDD_HOOK_FAIL_CLOSED"


def _raw_denial(command: str) -> str | None:
    """Why a command the shell check cannot parse is denied anyway, by its text alone, or None."""
    if _APPROVAL_TEXT.search(command):
        return "the shell check cannot parse the command, and its text carries an approval (`aidd approve`, `aidd ship`, `/aidd approve`, or an approval record): agents never approve or merge"
    if _RAW_MERGE.search(command) or _RAW_API.search(command) or _GRAPHQL_WRITES.search(command):
        return "the shell check cannot parse the command, and its text approves, reviews, or merges a pull or merge request: agents never approve or merge"
    if _RAW_FORCE_PUSH.search(command):
        return "the shell check cannot parse the command, and its text force-pushes or deletes a branch, maybe a protected branch: history on the default branch is never rewritten by an agent"
    return None


def forbidden_action(command: str, root: str | None = None, *, powershell: bool = False) -> str | None:
    """Why an agent may not run `command`, or None. Agents never approve, merge, or post an approval.

    `root`, the repository the command runs in, lets a push with no refspec resolve to the current branch and adds the
    repository's default branch to the protected ones. `powershell` undoes PowerShell's backtick escapes first.
    A command the check cannot parse is held to its raw text, and under AIDD_HOOK_FAIL_CLOSED=1 denied outright."""
    if powershell:
        command = _powershell_plain(command)
    broken: list[str] = []
    simple = _simple_commands(command, broken=broken)
    if broken:
        why = _raw_denial(command)
        if why:
            return why
        if os.environ.get(FAIL_CLOSED_ENV) == "1":
            return (
                f"the shell check cannot parse the command (an unbalanced quote), and {FAIL_CLOSED_ENV}=1 denies what it cannot check: "
                "rewrite it with balanced quotes, or put the text in a file"
            )
    reads = all(_only_reads(_program_argv(sc.argv)) for sc in simple)
    if (_APPROVAL_TEXT.search(command) and any(_sends_input(sc) for sc in simple)) or any(_types_approval(sc) for sc in simple):
        return (
            "the command types an approval (`aidd approve`, `aidd ship`, `/aidd approve`, or an approval record) into another terminal "
            "or program: an approval is a person's, typed by that person in a terminal an agent did not start and does not drive"
        )
    if _AIDD_APPROVE.search(command) and not reads:
        return "the command carries `/aidd approve`: an approval is a human's to post, never an agent's"
    if _APPROVAL_RECORD.search(command) and not reads:
        return (
            f"the command names {local.APPROVALS_REF} or {local.MERGE_TRAILER}, where local approvals are recorded: an approval is a "
            "person's, recorded with `aidd approve` in a terminal an agent did not start; an agent only reads them"
        )
    for sc in simple:
        argv = _program_argv(sc.argv)
        if not argv:
            continue
        name, args = _prog(argv[0]), argv[1:]
        what = _aidd_decision(argv)
        if what:
            return f"`aidd {what}`: agents never approve or merge; a person runs it in a terminal an agent did not start"
        if name == "gh":
            words = _words(args, _GH_VALUE_FLAGS)
            if words[:2] == ["pr", "review"] and any(a in ("--approve", "-a") or a.startswith("--approve=") for a in args):
                return "`gh pr review --approve`: agents never approve; a human approves at Spec approval and Merge approval"
            if words[:2] == ["pr", "merge"]:
                return "`gh pr merge`: agents never merge; a human merges once `aidd/gate` passes"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GH_MERGE, _GH_REVIEW):
                return "a `gh api` call that approves or merges: agents never approve or merge"
        elif name == "glab":
            words = _words(args, _GH_VALUE_FLAGS)
            if words[:1] == ["mr"] and len(words) > 1 and words[1] in ("approve", "merge", "accept"):
                return f"`glab mr {words[1]}`: agents never approve or merge; a human does, once `aidd/gate` passes"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GL_MERGE, _GL_REVIEW):
                return "a `glab api` call that approves or merges: agents never approve or merge"
        elif name == "git" and _words(args, {"-C", "-c"})[:1] == ["push"]:
            why = _push_denial(args, root)
            if why:
                return why
    return None


def _patch_targets(text: str, strip: int, git_style: bool) -> list[str]:
    targets = []
    for line in text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path = line[4:].split("\t", 1)[0].strip()
            if path in ("/dev/null", ""):
                continue
            parts = path.split("/")
            parts = parts[1:] if git_style and parts[0] in ("a", "b") else parts[strip:]
            if parts:
                targets.append("/".join(parts))
    return list(dict.fromkeys(targets))


def _write_targets(sc: _Simple, cwd: Path) -> tuple[list[str], list[str]]:
    """(paths a simple command writes, reasons it cannot tell) — best-effort, for the obvious writers only."""
    argv = _program_argv(sc.argv)
    targets = list(sc.out)
    unknown: list[str] = []
    if not argv:
        return targets, unknown
    name, args = _prog(argv[0]), argv[1:]
    plain = [a for a in args if not a.startswith("-")]
    if name == "tee":
        targets += plain
    elif name == "sed":
        inplace = any(
            a in ("-i", "--in-place") or a.startswith(("-i", "--in-place=")) or (a[:1] == "-" and a[1:2] != "-" and "i" in a[1:] and a[1:].isalpha())
            for a in args
        )
        if inplace:
            has_script_flag = any(a in ("-e", "-f", "--expression", "--file") or a.startswith(("--expression=", "--file=")) for a in args)
            words = _words(args, {"-e", "-f", "--expression", "--file"})
            targets += words if has_script_flag else words[1:]
    elif name in ("cp", "mv", "install", "ln"):
        dest = _flag_value(args, "-t", "--target-directory")
        sources = plain if dest else plain[:-1]
        dest = dest or (plain[-1] if len(plain) >= 2 else None)
        if dest:
            d = (cwd / dest) if not os.path.isabs(dest) else Path(dest)
            targets += [str(d / os.path.basename(s)) for s in sources] if d.is_dir() else [dest]
        if name == "mv":
            targets += sources
    elif name in ("rm", "touch", "truncate", "shred", "unlink", "rmdir"):
        targets += _words(args, {"-s", "--size", "-r", "--reference"}) if name == "truncate" else plain
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name in ("patch",) or (name == "git" and args[:1] == ["apply"]):
        git_style = name == "git"
        files = [a for a in (args[1:] if git_style else args) if not a.startswith("-")]
        if git_style:
            files = files or sc.inp
        else:
            files = [f for f in files if f.endswith((".diff", ".patch"))] or sc.inp or [f for f in (_flag_value(args, "-i", "--input"),) if f]
        strip = int(_flag_value(args, "-p") or (1 if git_style else 0)) if (_flag_value(args, "-p") or "0").isdigit() else 0
        if not files:
            unknown.append(f"`{name}` reads the patch from a pipe, so its target files are unknown")
        for f in files:
            try:
                text = ((cwd / f) if not os.path.isabs(f) else Path(f)).read_text(encoding="utf-8", errors="replace")
            except OSError:
                unknown.append(f"cannot read the patch {f} to see which files it changes")
                continue
            targets += _patch_targets(text, strip, git_style and strip == 1)
    return targets, unknown


def _gate_matches(patterns: list[str], text: str) -> bool:
    """Every pattern matches `text`, ignoring case: a pattern with `*`, `?`, or `[` is a glob over the whole
    simple command, any other pattern a substring of it."""
    text = text.lower()
    return bool(patterns) and all(fnmatch.fnmatchcase(text, p.lower()) if any(c in p for c in "*?[") else p.lower() in text for p in patterns)


def gated_command(cfg: cfgmod.Config, command: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why `command` waits for a person, or None: it matches a `[[guard.gated_commands]]` entry and the entry's
    `requires` variable is unset or empty in the environment the session started with. The variable must come
    from there, set by the person who approves: a command that names it proves nothing, so it never counts."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    simple = _simple_commands(command)
    texts = [" ".join(sc.argv) for sc in simple] or [command]
    for gate in cfg.get("guard", "gated_commands", default=[]) or []:
        if not any(_gate_matches(list(gate.get("match", [])), t) for t in texts):
            continue
        name, env_label, var = gate.get("name", "gated command"), gate.get("environment"), gate.get("requires")
        what = f"`{name}` is a gated command" + (f" for {env_label}" if env_label else "")
        note = f" {gate['message']}" if gate.get("message") else ""
        if not var:
            return f"{what}: agents never run it.{note} A person runs it outside the agent session."
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(var)}(?![A-Za-z0-9_])", command):
            return (
                f"{what}, and the command names {var}: the approval must come from the environment Claude Code started with, "
                f"set by the person who approves, never from the command itself.{note}"
            )
        if not (env.get(var) or "").strip():
            return (
                f"{what} and needs approval.{note} Ask the person who approves the release to set {var} (a change or "
                f"ticket reference, say) in the environment Claude Code starts with, such as `{var}=CHG-1234 claude`, "
                "or to run the command themselves. An agent cannot set it."
            )
    return None


def check_command(root: str, cwd: str, command: str, event: dict | None = None) -> Verdict:
    """(decision, reason) for running `command` from `cwd`, for whoever `event` says is running it. For an aidd-team
    role or a helper subagent, each obvious shell write is held to the same rules as an edit of that path."""
    event = event or {}
    if event.get("tool_name") == "PowerShell":
        command = _powershell_plain(command)
    why = forbidden_action(command, root)
    if why:
        return "deny", why
    try:
        gated = gated_command(cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch), command)
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError):
        gated = None
    if gated:
        return "deny", gated
    role, helper = role_of(event), is_helper(event)
    if not role and not helper:
        return "allow", "not a role or a helper; the gate's scope rule checks the diff"
    here = Path(cwd)
    top = Path(root).resolve()
    worst: Decision = "allow"
    reasons: list[str] = []
    for sc in _simple_commands(command):
        argv = _program_argv(sc.argv)
        if argv and _prog(argv[0]) == "cd":
            dest = argv[1] if len(argv) > 1 else str(Path.home())
            here = (here / dest) if not os.path.isabs(dest) else Path(dest)
            continue
        targets, unknown = _write_targets(sc, here)
        for u in unknown:
            worst = "deny"
            reasons.append(f"{u}; save the patch to a file and apply that file, so its targets can be checked")
        for t in targets:
            if t in _IGNORED_TARGETS or t.startswith("/dev/"):
                continue
            if "$" in t or "`" in t or any(c in t for c in "*?["):
                decision: Decision = "deny"
                reason = f"cannot tell which file `{t}` names, because the shell check does not expand it; name the file literally"
            else:
                path = (here / t) if not os.path.isabs(t) else Path(t)
                try:
                    rel = path.resolve().relative_to(top).as_posix()
                except ValueError:
                    continue  # outside the repository: a scratch file is none of the gate's business
                decision, reason = check_agent_edit(root, rel, event)
            if decision != "allow":
                worst = decision
                reasons.append(f"shell write to {t}: {reason}")
    return worst, "; ".join(reasons) or "no shell write the guard can see"


def pre_edit_hook(stdin=None, stdout=None) -> int:
    """Claude Code PreToolUse hook: reads the event JSON, prints a permission decision when it denies.

    It allows when it cannot tell: any failure of its own exits 0 without a decision, never a block, unless
    AIDD_HOOK_FAIL_CLOSED=1 (the regulated managed settings) is set, when the failure is a deny.
    """
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    try:
        return _pre_edit(stdin, stdout)
    except Exception as exc:  # noqa: BLE001  # the guard's own crash allows, unless the organization requires the guard
        if os.environ.get(FAIL_CLOSED_ENV) == "1":
            return _decide(stdout, "deny", f"the guard could not check this tool call ({type(exc).__name__}), and {FAIL_CLOSED_ENV}=1 requires the guard")
        return 0


# Each deny reason's family, for the denial log and `aidd metrics --guard`: the first entry whose text the reason
# contains names it. The texts are the fixed parts of the reasons above; a new deny reason needs a row here.
REASON_CODES: tuple[tuple[str, str], ...] = (
    ("may only read (the loop contract's helper rule", "helper_read_only"),
    ("types an approval", "approval_typed"),
    ("denies what it cannot check", "shell_unparsed"),
    ("the guard could not", "guard_failed"),
    ("unknown aidd-team role", "unknown_role"),
    ("go_no_go or sign_off, which only a person records", "proposal_decision"),
    ("of a proposal; ", "proposal_part"),
    ("is a gated command", "gated_command"),
    ("carries `/aidd approve`", "approval_post"),
    ("where local approvals are recorded", "approval_record"),
    ("agents never approve or merge", "approve_or_merge"),
    ("agents never approve;", "approve_or_merge"),
    ("agents never merge;", "approve_or_merge"),
    ("protected branch", "protected_branch"),
    ("reaches the protected branches", "protected_branch"),
    ("the shell check does not expand it", "shell_unknown_target"),
    ("so its target files are unknown", "shell_unknown_target"),
    ("cannot read the patch", "shell_unknown_target"),
    ("is a protected path", "protected_path"),
    ("frozen by Spec approval", "frozen_file"),
    ("writes it while specifying, and after Spec approval nobody does", "not_owner"),
    ("belongs to another role", "role_area"),
    ("no active Spec, so", "no_active_spec"),
    ("is outside the scope of", "out_of_scope"),
)
GUARD_LOG = ".aidd/work/guard.jsonl"
_LOG_FIELD_MAX = 200
# Secret-looking values a logged command may carry; each keeps its name and loses its value.
_SECRETS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:(bearer|basic|token|bot)\s+)?[^\s'\"]+"), "AUTH"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
    (re.compile(r"(?i)\b([A-Z0-9_.-]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?)[A-Z0-9_.-]*)=(\"[^\"]*\"|'[^']*'|[^\s'\"]+)"), r"\1=***"),
    (
        re.compile(r"(?i)(--(?:password|passwd|pass|token|api-key|apikey|secret|client-secret|auth-token|access-token)(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1***",
    ),
    # Any other option whose name says it carries a secret: --aws-secret-access-key X, --private-key=...
    (
        re.compile(r"(?i)(--[a-z0-9-]*(?:password|passwd|token|secret|api-?key|access-key|private-key)[a-z0-9-]*(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1***",
    ),
    # A header whose name says it carries a secret: X-Api-Key: ..., Private-Token: ..., X-Auth-Token: ...
    (re.compile(r"(?i)(\b(?!authorization\s*:)[a-z0-9-]*(?:api-?key|token|secret|password|auth)[a-z0-9-]*\s*:\s*)[^\s'\"]+"), r"\1***"),
    # curl -u user:password, --user=user:password (the user stays, the password goes)
    (re.compile(r"(?i)((?:^|[\s;|&(])(?:-u|--user|--proxy-user)(?:=|\s*))([\"']?)([^\s:'\"]*):([^\s'\"]+)"), r"\1\2\3:***"),
    # mysql -pSECRET (the password attached to -p)
    (re.compile(r"(?i)(\b(?:mysql\w*|mariadb\w*)\b[^|;&\n]*?\s-p)(?=[^\s-])(\"[^\"]*\"|'[^']*'|[^\s'\"]+)"), r"\1***"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@'\"]*):[^/\s@'\"]+@"), r"\1:***@"),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})"
        ),
        "***",
    ),
)


def redact(text: str) -> str:
    """`text` with every secret-looking value _SECRETS matches replaced by `***`."""
    for pattern, repl in _SECRETS:
        if repl == "AUTH":
            text = pattern.sub(lambda m: m.group(1) + (m.group(2) + " " if m.group(2) else "") + "***", text)
        else:
            text = pattern.sub(repl, text)
    return text


def reason_code(reason: str) -> str:
    """The stable code of a deny reason (REASON_CODES), or "other"."""
    for text, code in REASON_CODES:
        if text in reason:
            return code
    return "other"


def log_denial(root: str, event: dict, reason: str) -> None:
    """Append one JSON line for a deny to GUARD_LOG (the module docstring says what it holds); a failure to write is ignored."""
    ti = event.get("tool_input") or {}
    tool = str(event.get("tool_name") or "")
    entry: dict = {
        "ts": utc_stamp(),
        "decision": "deny",
        "role": role_of(event),
        "helper": is_helper(event),
        "tool": tool,
        "reason": reason_code(reason),
    }
    if tool in SHELL_TOOLS:
        entry["command"] = redact(str(ti.get("command") or ""))[:_LOG_FIELD_MAX]
    elif not tool.startswith("mcp__"):  # an MCP tool's name says what was denied; its input may hold anything
        target = _edit_path(event) or ""
        entry["path"] = (repo_relative(root, target) if target else "")[:_LOG_FIELD_MAX]
    try:
        work = Path(root) / GUARD_LOG
        work.parent.mkdir(parents=True, exist_ok=True)
        ignore = work.parent / ".gitignore"
        if not ignore.exists():
            ignore.write_text("# aidd's local working files: never committed\n*\n", encoding="utf-8")
        with open(work, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def _decide(stdout, decision: str, reason: str, root: str | None = None, event: dict | None = None) -> int:
    if decision != "allow":
        if root and event is not None:
            try:
                log_denial(root, event, reason)
            except Exception:  # noqa: BLE001  # the log is a convenience: it must never turn a deny into an allow
                pass
        json.dump(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": f"aidd: {reason}"}}, stdout
        )
    return 0


def _toplevel(probe: Path) -> str:
    return gitutil.toplevel(str(probe)) if probe.is_dir() else ""


SHELL_TOOLS = ("Bash", "PowerShell")
# An MCP tool whose name says it merges or approves, or sets a commit status (the gate's own channel). The name is
# split into lowercase words whatever its style (merge_pull_request, mergePullRequest, merge-pull-request).
_MCP_READ_VERBS = frozenset({"get", "list", "search", "read", "check", "is", "can", "view", "describe"})
_MCP_WRITE_VERBS = frozenset({"set", "create", "post", "update", "add", "put", "write"})
_MCP_REQUEST_NOUNS = frozenset({"pull", "pr", "prs", "mr", "mrs", "request", "requests", "merge"})


def _mcp_words(tool: str) -> list[str]:
    """The words of an MCP tool name: `approvePullRequest`, `approve-pull-request`, and `approve_pull_request` are
    all approve, pull, request."""
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", tool)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def _mcp_merges(words: list[str]) -> bool:
    """A tool whose words merge or approve (merge, approve, or an accept or complete of a pull or merge request);
    `merge request` is a noun, and a name that starts with a read verb only reads."""
    if not words or words[0] in _MCP_READ_VERBS:
        return False
    actions = [w for i, w in enumerate(words) if not (w == "merge" and words[i + 1 : i + 2] in (["request"], ["requests"]))]
    if any(w in ("merge", "approve") or w.endswith("merge") for w in actions):
        return True
    return any(w in ("accept", "complete") for w in actions) and bool(_MCP_REQUEST_NOUNS & set(words))


def _mcp_sets_status(words: list[str]) -> bool:
    """A tool that sets, creates, posts, or updates a (commit) status."""
    if not words or words[0] in _MCP_READ_VERBS:
        return False
    after_verb = any(
        w in _MCP_WRITE_VERBS and (words[i + 1 : i + 2] == ["status"] or words[i + 1 : i + 3] == ["commit", "status"]) for i, w in enumerate(words)
    )
    return after_verb or ("status" in words and "commit" in words and bool(_MCP_WRITE_VERBS & set(words)))


_APPROVAL_LINE = re.compile(r"(?mi)^[ \t>]*/aidd[ \t]+approve")


def _strings(value, depth: int = 0):
    """Every string in a tool input, a few levels deep."""
    if isinstance(value, str):
        yield value
    elif depth < 4 and isinstance(value, dict):
        for v in value.values():
            yield from _strings(v, depth + 1)
    elif depth < 4 and isinstance(value, list):
        for v in value[:100]:
            yield from _strings(v, depth + 1)


def check_mcp_tool(name: str, tool_input: dict) -> tuple[str, str]:
    """allow or deny for an MCP tool call (`mcp__<server>__<tool>`), by the rules in the module docstring."""
    words = _mcp_words(name.rsplit("__", 1)[-1])
    values = list(_strings(tool_input if isinstance(tool_input, dict) else {}))
    if _mcp_merges(words):
        return "deny", f"MCP tool {name} approves or merges: agents never approve or merge; a person does, once `aidd/gate` passes"
    if _mcp_sets_status(words):
        return "deny", f"MCP tool {name} sets a commit status: agents never approve or merge, and `aidd/gate` is the gate's own status"
    if {"review", "reviews"} & set(words) and any(v.strip().upper() in ("APPROVE", "APPROVED") for v in values):
        return "deny", f"MCP tool {name} submits an approving review: agents never approve or merge; a person reviews"
    if any(_APPROVAL_LINE.search(v) for v in values):
        return "deny", f"MCP tool {name} carries `/aidd approve`: agents never approve; the author or an Approver posts it"
    return "allow", "MCP tool that neither approves nor merges"


def _pre_edit(stdin, stdout) -> int:
    try:
        event = json.load(stdin)
    except ValueError:
        if os.environ.get(FAIL_CLOSED_ENV) == "1":
            return _decide(stdout, "deny", f"the guard could not read the tool call, and {FAIL_CLOSED_ENV}=1 requires the guard")
        return 0
    if not isinstance(event, dict):
        raise TypeError("the hook event is not a JSON object")
    cwd = Path(event.get("cwd") or ".")
    tool_name, tool_input = str(event.get("tool_name") or ""), event.get("tool_input") or {}
    if tool_name.startswith("mcp__") or tool_name in SHELL_TOOLS:  # PowerShell commands get the same checks as Bash
        top = _toplevel(cwd)
        if not top or not _adopted(top):
            return 0
        if tool_name.startswith("mcp__"):
            return _decide(stdout, *check_mcp_tool(tool_name, tool_input), top, event)
        command = tool_input.get("command") or ""
        return _decide(stdout, *check_command(top, str(cwd), command, event), top, event) if command else 0
    target = _edit_path(event)
    if not target:
        return 0
    path = Path(target) if os.path.isabs(target) else cwd / target
    probe = path.parent if path.parent.is_dir() else cwd
    top = _toplevel(probe)
    if not top:
        return 0
    try:
        rel = path.resolve().relative_to(Path(top).resolve()).as_posix()
    except ValueError:
        return 0
    return _decide(stdout, *check_agent_edit(top, rel, event), top, event)
