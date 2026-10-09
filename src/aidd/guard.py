"""The guard for agents: is this path inside the active Spec's scope, and may this agent write it?

The gate decides at merge; this catches the same mistakes while the agent
works, where they are cheapest to fix. It runs locally, so it is a guide, not
a control: it allows when it cannot tell (no config, no git repository, no active Spec),
and the gate re-checks everything. A config that exists but is invalid or cannot be read never turns it off: every
session meets the deploy and infrastructure commands `aidd init` detects (detect.default_held), a role or a helper
writes nothing, the person's own session may edit (to fix the config), and session-start names the problem. The hook runs git only from a system path, with the repository's fsmonitor,
hooks, and driver programs off (`gitutil.system_only`). In a repository that has adopted aidd, a git that cannot run or
read it is a deny. That defends against the repository's committed content, not against a local writer of
`.git/config`, HOME, or the git programs.

The guard answers allow or deny, never "ask": an approval prompt during the build would put a person back on
the critical path of every session running in parallel. Each deny names the route that fixes it; people
approve at Spec approval and Merge approval, and a deploy waits for its held-command approval.

Decisions for an edit (Edit, Write, MultiEdit, NotebookEdit):
- deny: outside every Task's `scope` of the active Spec; outside an aidd-team role's write area;
  from a subagent that is not an aidd-team role (the loop contract's helper rule: a helper of another type only reads);
  a protected path outside every approved scope, or with no active Spec; a test or design file or a frozen doc
  once the Spec's approval holds (an approval of its current hash, or a stored status at or past ready where nothing local
  records approvals), or, before that, by a role that does not own it
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
- deny: a `git config` that sets, unsets, or edits commit signing (`gpg.*`, `user.signingkey`, their sections, or the
  whole file with `--edit`): which key signs and which signatures count are a person's settings. Reading them is fine
- deny: for a role, a proposal part that is not its own, and an edit that adds or changes a proposal's `go_no_go`,
  `sign_off`, or `outcome`, an Initiative's `go_no_go`, an exploration's `outcome`, or a line of REVIEW.md that looks
  like a dismissed finding in any shape, or an edit that moves one under its heading (compared on the hook's Edit and
  Write input), which only a person records; and any other write to REVIEW.md (a shell write, a tool with no new text),
  which the dismissal check cannot read
- deny: a command that matches a `[[guard.held_commands]]` entry (a production deploy, say) unless the
  environment Claude Code started with carries that entry's `requires` variable, which a person sets
- deny: for a role or a helper subagent, an obvious shell write (a `>` or `>>` redirect, also after a subshell group
  or a command substitution, `tee`, `sed -i`, `cp`, `mv`, `rm`, `touch`, `dd of=`, `git apply`, `patch`, and the
  source of a hard link: `ln` without `-s`, `link`, `cp -l`) whose target the edit rules above deny, or whose target
  the check cannot read (a patch from a pipe, an unexpanded `$VAR` or glob); for the main session, the same writes
  that `[agents] delegate` denies
- deny: for a writer the guard holds (a role, a helper, or a main session that `delegate` denies), a command that runs
  code the parser cannot read (OPAQUE), a closed list: a command substitution or backticks where a command starts; a
  shell fed by stdin (a here-string, a here-document, an input file, or a pipe); `trap` with a command, `source`, `.`;
  `xargs`, `parallel`, `find -exec|-execdir|-ok|-okdir`. `exec`, `command`, and `builtin` are followed as wrappers, and
  a write target with a brace expansion (`src/{a,b}.py`) is unreadable like a glob. A program that writes by itself
  (an interpreter, a build tool, a package manager) stays the documented limit
- deny: a write to a file with more than one hard link, by a writer the guard holds (a role, a helper, or a main
  session that `delegate` denies): the guard cannot tell whether another name of it is repository content
- deny: `aidd autopilot start|stop` with a `--session` that is not the hook event's own `session_id`, so an agent never
  binds the lease to another session, such as the person's (anywhere, even outside an adopted repository)
- allow: everything else

Each write a tool names (an Edit's path, a shell write's target, an MCP tool's path) is judged in the repository
that holds it, found from the path itself (`locate`), never from the session's cwd: a sibling or nested worktree,
or a session started outside the repository, meets the same rules. The path follows symbolic links and takes the
case it has on disk, and a file git tracks is repository content even in an ignored folder. An edit tool never
writes inside a `.git` folder. The known limits are in SECURITY.md (the trust model).

Decisions for an MCP tool (`mcp__<server>__<tool>`), in a repository that has adopted aidd:
- deny: a tool that merges or approves (`merge_pull_request`, `approve_merge_request`, `enable_auto_merge`, and the
  same words in camelCase or kebab-case, `mergePullRequest`, `complete-pull-request`), sets a commit status, submits a
  review whose input says APPROVE, or carries a `/aidd approve` line; a name that starts with a read verb (get, list,
  search, read, check, is, can, view, describe) only reads
- deny: for a main session that `[agents] delegate` denies, a tool that writes a file of a repository: each path
  under `path`, `file_path`, `filename`, `file`, `source`, `destination`, `target`, `src`, `dest`, `old_path`,
  `new_path`, a `file:` `uri`, and in `files` or `paths`
- allow: every other MCP tool

The shell check follows a subshell group, a command substitution, and a `case` pattern's `)`, reads `cd` as bash
does (logical, `-P`, `cd -`), and reads a command with a here-document twice, with and without the bodies. It
follows `sh -c` and `eval` MAX_NESTING levels deep; deeper, or when parsing fails, a writer the guard holds is denied.
tests/test_guard_oracle.py checks its decisions against what real bash writes.

The shell check tokenizes with shlex and follows `&&`, `;`, `|`, `cd`, and `sh -c`, but it does not run the shell.
So a program that writes by itself (an interpreter such as `python -c`, a build tool, a package manager) is not seen,
nor is a write the parser reads differently from bash, nor, for a writer the guard does not hold, a target it cannot
read (`$VAR`, a glob). That is why it guides and the gate's scope rule, on the real diff, decides. Program names compare as
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
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from . import config as cfgmod
from . import gitutil, globs, inputs, local, model, resources, rules, state
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
        except (model.ModelError, OSError, RecursionError):
            continue  # one unreadable Spec is not the branch's Spec; the others still bind
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
        "{specs_dir}": [globs.under(cfg.specs_dir, "**")],
        "{proposals_dir}": [globs.under(cfg.proposals_dir, "**")],
        "{spec}": [rel for rel, _ in specs],
        "{tests}": [p for _, d in specs for p in (d.get("tests") or {}).get("files", [])],
        "{design}": [p for _, d in specs for p in (d.get("design") or {}).get("files", [])],
        "{docs}": [p for _, d in specs for p in model.frozen_docs(d)],
        **{f"{{docs:{k}}}": _docs_of(specs, k) for k in model.DOC_KINDS},
        "{scope}": [s for _, d in specs for task in d.get("tasks", []) if _mine(task, role) for s in task.get("scope", [])],
    }


def _docs_of(specs: list[tuple[str, dict]], kind: str) -> list[str]:
    """The docs of one kind the active Specs link, frozen or living: `{docs:<kind>}` in a role's write area. A frozen
    one is then frozen by Spec approval; a living one (`frozen = false`) is implementation, so it must also sit in a
    Task's scope, as the gate's scope rule reads it."""
    return [d["path"] for _, s in specs for d in s.get("docs") or [] if isinstance(d, dict) and d.get("kind") == kind and isinstance(d.get("path"), str)]


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
    raise RuntimeError(f"not fetched: the guard does not use the network ({url})")


def _held(root: str, cfg: cfgmod.Config, specs: list[tuple[str, dict]]) -> set[str]:
    """IDs of the active Specs whose Spec approval holds (`state.approval_holds`, the one check `aidd assess`, `aidd list`, and
    `aidd validate` share): a counted approval of the hash HEAD or the working tree holds, or, where nothing local
    records approvals, a stored status at or past ready."""
    obs = state.Observer(Path(root), cfg)
    return {str(d.get("id")) for rel, d in specs if state.approval_holds(obs, rel, d)}


def _frozen_by(specs: list[tuple[str, dict]], rel: str, section: str, held: set[str]) -> list[str]:
    """IDs of the active Specs that list `rel` among their `tests` or `design` files or their frozen `docs`, and whose
    Spec approval holds. An emergency Spec is a backfill: nothing on it is frozen yet."""
    return [
        str(d.get("id"))
        for _, d in specs
        if d.get("route") != "emergency"
        and str(d.get("id")) in held
        and globs.match_any(model.frozen_docs(d) if section == "docs" else (d.get(section) or {}).get("files", []), rel)
    ]


def _drafts(specs: list[tuple[str, dict]], held: set[str]) -> list[str]:
    """IDs of the active Specs that have not had Spec approval yet: their scope and tests can still change, so a path
    they miss means "add it to the Spec", never "get it approved again". A cancelled Spec is neither."""
    return [str(d.get("id")) for _, d in specs if d.get("route") != "emergency" and str(d.get("id")) not in held and state.stored(d) != "cancelled"]


# A file a test runner would pick up: the naming conventions of the common runners, or a file under a tests folder.
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|e2e|testing)/|(?:^|/)test_[^/]*\.py$|_test\.(?:py|go|rb|dart)$|\.(?:test|spec)\.[cm]?[jt]sx?$|Tests?\.(?:java|cs|kt)$|_spec\.rb$"
)


def looks_like_test(rel: str) -> bool:
    return bool(_TEST_PATH.search(rel))


def _draft_hint(rel: str, ids: str) -> str:
    """What to do with a path a not-yet-approved Spec does not cover: change the Spec, which is still open."""
    if looks_like_test(rel):
        return f"{rel} is outside the scope of {ids} and not in its tests.files: add it to tests.files in the Spec (it isn't approved yet). Then write it"
    return (
        f"{rel} is outside the scope of {ids}: add it to a Task's scope in the Spec (it isn't approved yet). "
        "Then build it after Spec approval. Or leave it alone"
    )


def _owns(role: str | None, placeholder: str, unfrozen: bool) -> bool:
    """Whether `role` writes `{tests}` or `{design}`: the tester and the product designer, and on an emergency backfill
    the developer's regression test. The session itself, with no role, plays every role."""
    return role is None or placeholder in _writes(role, unfrozen)


def _protected_deny(rel: str, protected: str, where: str) -> Verdict:
    return "deny", (
        f"{rel} is a protected path ({protected}), and {where}. A change to it becomes major and needs a specialist "
        "review, so it waits for an approved scope. Add it to a Task's scope in the Spec and get Spec approval, then edit it. "
        "Or leave it alone"
    )


def _doc_owner(specs: list[tuple[str, dict]], rel: str) -> tuple[str, str]:
    """A frozen doc's placeholder, `{docs:<kind>}`, and the roles whose write area names it, in words."""
    kind = next(
        (d.get("kind") for _, s in specs for d in s.get("docs") or [] if d.get("path") in model.frozen_docs(s) and globs.match_any([d["path"]], rel)), "other"
    )
    placeholder = f"{{docs:{kind}}}"
    roles = resources.roles()["roles"]
    owners = [k for k in resources.roles()["order"] if placeholder in roles[k]["writes"]]
    return placeholder, " or ".join(f"the {k.replace('-', ' ')}" for k in owners) or "the author"


def _frozen_file(specs: list[tuple[str, dict]], rel: str, role: str | None, kind: str, unfrozen: bool, held: set[str]) -> Verdict:
    """A test or design file, or a frozen doc, of the Spec: its owner writes it until Spec approval, and nobody after."""
    if kind == "doc":
        section, (placeholder, owner) = "docs", _doc_owner(specs, rel)
    else:
        section, placeholder = ("tests", "{tests}") if kind == "test" else ("design", "{design}")
        owner = "the tester" if kind == "test" else "the product designer"
    frozen = _frozen_by(specs, rel, section, held)
    if frozen:
        return "deny", (
            f"{rel} is a {kind} file of {', '.join(frozen)}, frozen by Spec approval (an approval of its current hash holds), and any "
            f"edit voids the approval. To change it, commit a change to the Spec that says what was wrong (the Spec is a draft again). "
            f"Then let {owner} change its {section}, and ask for Spec approval again on the new hash"
        )
    if not _owns(role, placeholder, unfrozen):
        return "deny", (
            f"{rel} is a {kind} file of the Spec: {owner} writes it while specifying, and after Spec approval nobody does. Hand the change to that role"
        )
    return "allow", (
        f"a {kind} file of the Spec, before Spec approval: no approval of the Spec's current hash holds, so write it now. "
        "It is frozen once the Spec is approved"
    )


# Who writes which part of a proposal's folder: the product manager and the tech writer the proposal itself, and each
# specialist only its own part. The decisions in it (go_no_go, sign_off, outcome) are a person's, never an agent's.
PROPOSAL_PARTS = {
    "product-manager": ("proposal.md",),
    "delivery-manager": ("proposal.md", "contract.md", "change-orders/"),
    "tech-writer": ("proposal.md",),
    "architect": ("architecture.md",),
    "product-designer": ("experience.md",),
    "security-engineer": ("security.md",),
    "compliance-analyst": ("compliance.md",),
    "sre": ("operations.md",),
}
PROPOSAL_RULE = (
    "in a proposal's folder the product manager, the delivery manager, and the tech writer write proposal.md. The delivery manager "
    "also writes the contract (contract.md) and its change orders (change-orders/). Each specialist writes only its own part: "
    "architect architecture.md, product designer experience.md, security engineer security.md, compliance analyst compliance.md, "
    "and SRE operations.md. In the folder, only a person records go_no_go, sign_off, and outcome"
)
PROPOSAL_DECISIONS = ("go_no_go", "sign_off", "outcome")
# The one agent that writes the feedback log: every other role drafts an entry with its source and hands it over.
FEEDBACK_WRITER = "product-manager"
_DECISION_KEY = re.compile(r"^\s*\[{1,2}\s*(?:go_no_go|sign_off|outcome)\b|^\s*(?:go_no_go|sign_off|outcome)\s*=", re.M)


def _decisions(text: str, rel: str, keys: tuple[str, ...] = PROPOSAL_DECISIONS) -> tuple | None:
    """The decisions (`keys`) a file's front matter records, or None when its front matter does not parse."""
    try:
        data, _ = model.split_front_matter(text, rel)
    except model.ModelError:
        return None
    return tuple(json.dumps(data.get(k), sort_keys=True, default=str) for k in keys)


def _changes_decisions(rel: str, old_text: str | None, new_text: str | None, keys: tuple[str, ...], named: re.Pattern) -> bool:
    """Whether the edit adds or changes one of `keys`. Front matter that does not parse cannot be compared: naming a
    decision in it (`named`) is enough."""
    if new_text is None:
        return False
    after = _decisions(new_text, rel, keys)
    if after is None:
        return bool(named.search(new_text))
    before = _decisions(old_text, rel, keys) if old_text else None
    return after != (before or ("null",) * len(keys))


def _proposal_edit(role: str, rel: str, old_text: str | None, new_text: str | None) -> Verdict:
    own = PROPOSAL_PARTS.get(role)
    if own and Path(rel).name not in own and f"{Path(rel).parent.name}/" not in own:
        return "deny", f"the {role} role writes only {', '.join(own)} of a proposal; {rel} is another part. Hand off instead: {PROPOSAL_RULE}"
    if _changes_decisions(rel, old_text, new_text, PROPOSAL_DECISIONS, _DECISION_KEY):
        return "deny", (
            f"{rel}: this edit adds or changes go_no_go, sign_off, or outcome, which only a person records. Leave them to the person "
            f"who decides, and write the rest. The rule: {PROPOSAL_RULE}"
        )
    return "allow", f"a proposal, inside the {role} role's part"


# An Initiative's go_no_go, in the proposal's shape, is a person's decision too: no aidd-team role adds or changes it.
# Its kind is read by parsing the front matter (any TOML spelling of the key and the value), and from the text only when
# the front matter does not parse, so a broken file is still known as an Initiative's.
_GO_NO_GO_KEY = re.compile(r"^\s*\[{1,2}\s*go_no_go\b|^\s*[\"']?go_no_go[\"']?\s*=", re.M)
_INITIATIVE = re.compile(r"""^\s*["']?kind["']?\s*=\s*(?:"{1,3}|'{1,3})initiative""", re.M)


def _is_initiative(text: str | None, rel: str = "") -> bool:
    if not text:
        return False
    try:
        return model.split_front_matter(text, rel)[0].get("kind") == "initiative"
    except model.ModelError:
        return bool(_INITIATIVE.search(text))


def _initiative_decision(rel: str, old_text: str | None, new_text: str | None) -> bool:
    """Whether the edit adds or changes an Initiative's go_no_go: the file is an Initiative before or after it."""
    if not (_is_initiative(old_text, rel) or _is_initiative(new_text, rel)):
        return False
    return _changes_decisions(rel, old_text, new_text, ("go_no_go",), _GO_NO_GO_KEY)


UNREADABLE_DECISION = "use the Edit or Write tool so the change can be checked"


def _decision_file(root: str, rel: str) -> str | None:
    """What a file holds that only a person decides, when it is one the guard checks on the Edit or Write tool's text:
    REVIEW.md, an Initiative (or a new file in the specs folder, which may become one), a proposal, or an exploration."""
    if rel.casefold() == REVIEW_POLICY.casefold():
        return "dismissal"
    cfg = _load(root)
    if cfg is None:
        return None
    if _exploration(cfg, rel):
        return "an exploration's outcome"
    if globs.match_any([globs.under(cfg.proposals_dir, "*/proposal.md")], rel, fold_case=True):
        return "a proposal's go_no_go, sign_off, and outcome"
    if globs.match_any([globs.under(cfg.specs_dir, "**")], rel, fold_case=True):
        path = Path(root) / rel
        if not path.exists():
            return "a new work item, which may be an Initiative with its go_no_go"
        try:
            if _is_initiative(path.read_text(encoding="utf-8", errors="replace"), rel):
                return "an Initiative's go_no_go"
        except OSError:
            return "a work item the guard cannot read"
    return None


# A spike's outcome in an exploration (`exploration.md` in docs/design/<ID>/ or docs/architecture/explore/<topic>/) is a
# person's decision too: no aidd-team role adds or changes it.
_OUTCOME_KEY = re.compile(r"^\s*\[{1,2}\s*outcome\b|^\s*outcome\s*=", re.M)


# A dismissed review finding in REVIEW.md is a person's decision too: no aidd-team role adds or changes one, so an agent
# cannot hide its own finding. A review honours only DISMISSAL_EXACT lines under the first line that reads exactly
# DISMISSAL_HEADING, up to the next line that starts with `#`. The guard is wider than that reader on purpose:
# - any added or changed line that looks like a dismissal (DISMISSAL_LIKE), in any common shape and anywhere in the file;
# - any edit that brings a dismissal-like line under a heading that names the list, however a reader finds the heading
#   and where the list ends (moving lines, removing or renaming a heading).
# Taking a line out only brings the finding back, and every other edit to REVIEW.md is left to the other rules.
REVIEW_POLICY = "REVIEW.md"
DISMISSAL_HEADING = "## Dismissed findings"
DISMISSAL_EXACT = re.compile(
    r"- (?P<file>[^|\s](?:[^|]*[^|\s])?) \| (?P<kind>[^|\s](?:[^|]*[^|\s])?) \| (?P<hash>[0-9a-f]{16}) \| "
    r"(?P<who>[^|\s](?:[^|]*[^|\s])?) \| (?P<date>\d{4}-\d{2}-\d{2}) \| (?P<why>[^|\s](?:[^|]*[^|\s])?)\Z"
)
# A bar of any common look (ASCII, fullwidth, box drawing, divides, broken bar), and a hex token of 12 to 64 characters.
_BARS = "|\uff5c\u2502\u2223\u00a6"
_HEX_TOKEN = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{12,64}(?![0-9A-Za-z])")
_LIST_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*dismiss", re.I)
_ANY_HEADING = re.compile(r"^\s{0,3}#")
DISMISSAL_DENY = (
    "this edit adds, changes, or moves a line shaped like a dismissed finding (`- <file> | <kind> | <hash> | ...`), and only "
    "a person adds a dismissal. Report the finding, and leave its dismissal to the person who decides"
)


def dismissal_like(line: str) -> bool:
    """Whether a line looks like a dismissed finding in any common shape: at least two bars and a hex token between them
    or beside them, with or without a list marker, a number, a table's bars, tabs, or backticks."""
    bars = sum(line.count(c) for c in _BARS)
    return bars >= 2 and bool(_HEX_TOKEN.search(line))


def _lines(text: str | None) -> list[str]:
    """Lines as git and a reader see them: split on a newline only (with a trailing carriage return dropped), never on
    the other breaks `str.splitlines` honours, such as U+2028, so such a break cannot cut a dismissal in two."""
    return [ln[:-1] if ln.endswith("\r") else ln for ln in (text or "").split("\n")]


def _views(text: str | None) -> list[set[str]]:
    """What each reading of the list would honour: the documented one (exact lines under the first exact heading, up to
    the next `#` line), and wider ones (dismissal-like lines under any heading that names it, to the next heading, or to
    the end of the file). An edit that grows any of them changes what some reader honours."""
    lines = _lines(text)
    exact: set[str] = set()
    near: set[str] = set()
    rest: set[str] = set()
    first = next((i for i, ln in enumerate(lines) if ln == DISMISSAL_HEADING), None)
    if first is not None:
        for ln in lines[first + 1 :]:
            if ln.startswith("#"):
                break
            if DISMISSAL_EXACT.match(ln):
                exact.add(ln)
    inside = False
    seen_heading = False
    for ln in lines:
        if _LIST_HEADING.match(ln):
            inside = seen_heading = True
            continue
        if _ANY_HEADING.match(ln):
            inside = False
        if dismissal_like(ln):
            if inside:
                near.add(ln.strip())
            if seen_heading:
                rest.add(ln.strip())
    return [exact, near, rest]


def _dismissal_lines(text: str | None) -> set[str]:
    """Every line of `text` that looks like a dismissed finding, stripped."""
    return {ln.strip() for ln in _lines(text) if dismissal_like(ln)}


def _changes_dismissals(rel: str, old_text: str | None, new_text: str | None) -> bool:
    """Whether the edit adds or changes a dismissal-like line anywhere in REVIEW.md, or brings one under the list's
    heading in any reading of it. A removal is not a change here: it brings a finding back, and never hides one."""
    if new_text is None or rel.casefold() != REVIEW_POLICY.casefold():
        return False
    if _dismissal_lines(new_text) - _dismissal_lines(old_text):
        return True
    return any(after - before for after, before in zip(_views(new_text), _views(old_text), strict=True))


def _exploration(cfg: cfgmod.Config, rel: str) -> bool:
    docs = cfg.docs_dir
    return globs.match_any([globs.under(docs, "design/*/exploration.md"), globs.under(docs, "architecture/explore/*/exploration.md")], rel)


def check_edit(root: str, rel: str, role: str | None = None, old_text: str | None = None, new_text: str | None = None) -> Verdict:
    """(decision, reason) for editing the repo-relative path `rel`, optionally as an aidd-team role.

    `old_text` and `new_text`, when the caller knows them (the hook's Edit and Write input), are the file before and
    after the edit: a proposal's go/no-go and sign-off are checked on them. A role first limits the paths to its own
    area; every edit then meets the same Spec rules, listed in the module docstring.
    """
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch, skip_unread=True)
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError, ValueError):
        problem = config_problem(root)
        if role and problem:  # an invalid config never disables the guard: a role writes nothing until it is fixed
            return "deny", f"{rel}: {problem}. Until then no aidd-team role writes here; hand the fix to the person"
        return "allow", "no valid .aidd/config.toml"
    roles = resources.roles()["roles"]
    if role and role not in roles:
        return "deny", f"unknown aidd-team role {role!r}; one of {', '.join(roles)}"
    protected = globs.first_match(rules.protected_paths(cfg), rel, fold_case=True)
    try:
        return _check_with_specs(root, cfg, rel, role, roles, protected, old_text, new_text)
    except Exception as exc:  # noqa: BLE001  # a protected path's deny never depends on reading a Spec
        if protected:
            return _protected_deny(rel, protected, f"the guard could not read the active Spec ({type(exc).__name__}), so no approved scope covers it")
        raise


MAX_STOP_PATHS = 500  # the stop check reads at most this many changed paths: it runs inside a hook's time limit


def forbidden_changes(root: str, cfg: cfgmod.Config) -> list[tuple[str, str]]:
    """(path, reason) for each path the branch changed that the edit rules deny, once an active Spec's approval holds.

    The edit hook sees only the harness's own edit tools; a shell write through an interpreter, a script, or a build tool
    reaches the file unseen. The stop hook calls this to name those changes after the fact. Before Spec approval
    nothing is named: the Spec is still open, and the gate's scope rule reads the real diff. A test, design file, or
    frozen doc is named only while it differs from what was approved: changed since HEAD, and not what an approval of
    the working tree's hash covers."""
    specs = _specs(root, cfg)
    held = _held(root, cfg, specs) if specs else set()
    if not held:
        return []
    roles = resources.roles()["roles"]
    fill = _fill(cfg, specs)
    frozen = fill["{tests}"] + fill["{design}"] + fill["{docs}"]
    dirty = set(gitutil.dirty(root, untracked=True, check=False))
    worktree_approved: bool | None = None
    found = []
    for rel in changed_since(root, branch_base(root))[:MAX_STOP_PATHS]:
        if globs.match_any(frozen, rel):
            if rel not in dirty:
                continue  # as committed, which the approval of HEAD's hash covers, or the gate finds stale
            if worktree_approved is None:
                worktree_approved = _worktree_approved(root, cfg, specs)
            if worktree_approved:
                continue
        protected = globs.first_match(rules.protected_paths(cfg), rel, fold_case=True)
        decision, reason = _check_with_specs(root, cfg, rel, None, roles, protected, None, None, specs=specs, held=held)
        if decision == "deny":
            found.append((rel, reason))
    return found


def _worktree_approved(root: str, cfg: cfgmod.Config, specs: list[tuple[str, dict]]) -> bool:
    """Whether a local Spec approval names the hash of an active Spec as the working tree holds it (its frozen files as
    they are on disk): then the frozen files are what was approved, committed or not."""
    obs = state.Observer(Path(root), cfg)
    if not obs.knows_approvals():
        return False
    for rel, data in specs:
        path = Path(root) / rel
        if path.is_file() and obs.approved(str(data.get("id")), obs.hash_worktree(path.read_text(encoding="utf-8", errors="replace"), data)):
            return True
    return False


def _check_with_specs(
    root: str,
    cfg: cfgmod.Config,
    rel: str,
    role: str | None,
    roles: dict,
    protected: str | None,
    old_text: str | None,
    new_text: str | None,
    *,
    specs: list[tuple[str, dict]] | None = None,
    held: set[str] | None = None,
) -> Verdict:
    specs = _specs(root, cfg) if specs is None else specs
    if not role and not specs:
        return _protected_deny(rel, protected, "there is no active Spec") if protected else ("allow", "no active Spec")
    if not role and len(specs) > 1 and not protected:
        return "allow", "several Specs on the branch; the gate's scope rule checks the diff"
    fill = _fill(cfg, specs, role)
    writes = roles[role]["writes"] if role else []
    in_scope = bool(role and roles[role].get("in_scope"))
    own_spec = "{specs_dir}" in writes and globs.match_any(fill["{specs_dir}"], rel)
    if role and _exploration(cfg, rel) and _changes_decisions(rel, old_text, new_text, ("outcome",), _OUTCOME_KEY):
        return "deny", (
            f"{rel}: this edit adds or changes an exploration's outcome, which only a person records. Write the evidence and "
            "the rest, and leave the outcome to the person who decides"
        )
    if role and _changes_dismissals(rel, old_text, new_text):
        return "deny", f"{rel}: {DISMISSAL_DENY}"
    if role and _initiative_decision(rel, old_text, new_text):
        return "deny", (
            f"{rel}: this edit adds or changes an Initiative's go_no_go, which only a person records. Leave it to the person who decides, and write the rest"
        )
    if role and "{proposals_dir}" in writes and globs.match_any(fill["{proposals_dir}"], rel):
        # A proposal comes before any Spec: nothing ships from it, and people decide it at go/no-go and sign-off.
        return _proposal_edit(role, rel, old_text, new_text)
    if role and globs.match_any([globs.under(cfg.docs_dir, "feedback/**")], rel):
        # The feedback log belongs to no Spec: one agent writes it, and a person confirms each entry.
        if role == FEEDBACK_WRITER:
            return "allow", "the feedback log, which belongs to no Spec: write each entry with its source for a person to confirm"
        return "deny", (
            f"the feedback log is the {FEEDBACK_WRITER}'s: draft the entry, with its source, in your handoff note for the {FEEDBACK_WRITER}, "
            "and a person confirms it"
        )
    if role and in_scope and not specs and not own_spec:
        # The fast and emergency lanes have no Spec: the scope lives in the Change Request block, which the gate
        # checks. Keep the role's own paths and leave the lane to the gate rather than stop to ask.
        paths = [w for w in writes if not w.startswith("{")]
        if paths and "{scope}" not in writes and not globs.match_any(paths, rel):
            return "deny", f"the {role} role writes only {_role_allows(role, rel, fill)[1]}; {rel} belongs to another role. Hand off instead."
        if protected:
            return _protected_deny(rel, protected, "there is no active Spec")
        return "allow", (
            f"no active Spec: {rel} is fine only on the fast or emergency lane, and only inside the Change Request's scope. "
            "The lane is fast or emergency when `aidd assess` shows minor or standard, or the author declared an emergency. "
            "On the spec lane, implementation waits for Spec approval"
        )
    unfrozen = bool(specs) and all(d.get("route") == "emergency" for _, d in specs)
    held = _held(root, cfg, specs) if held is None else held
    drafts = _drafts(specs, held)
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
                "the active Spec, before Spec approval: finish its scope, tests.files, and tests. Then `aidd validate` it, and "
                "ask for Spec approval (`aidd hash --line` prints the line)"
            )
        return "allow", "the active Spec"
    if globs.match_any(fill["{tests}"], rel):
        return _frozen_file(specs, rel, role, "test", unfrozen, held)
    if globs.match_any(fill["{design}"], rel):
        return _frozen_file(specs, rel, role, "design", unfrozen, held)
    if globs.match_any(fill["{docs}"], rel):
        return _frozen_file(specs, rel, role, "doc", unfrozen, held)
    if globs.match_any(fill["{scope}"] + cfg.get("scope_exempt_paths", default=[]), rel):
        if protected:
            return "allow", f"inside the approved scope; {rel} is a protected path ({protected}), so the gate makes the change major with a specialist approval"
        return "allow", "inside the scope"
    ids = ", ".join(str(d.get("id")) for _, d in specs)
    if protected:
        return _protected_deny(rel, protected, f"it is outside the scope of {ids}")
    if role and not in_scope:
        return "deny", (
            f"{rel} is outside the scope of {ids}. Record it in the Spec now; add a Task whose scope covers the file, and write it in Implement, after Spec approval. "
            "Editing the Spec after Spec approval voids that approval."
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
    'a subagent that is not an aidd-team role may only read (the loop contract\'s helper rule, "Use AI as a delivery team does"). Spawn the helper as your own '
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
    if new is None and event.get("agent_type") and _adopted(root) and (holds_decision := _decision_file(root, rel)):
        # A shell write, a git checkout, an MCP tool, or a tool that gives no new text: the decision rules cannot read
        # it, so it is denied.
        if holds_decision == "dismissal":
            return "deny", f"{rel}: {DISMISSAL_DENY}; {UNREADABLE_DECISION}"
        return "deny", f"{rel}: this file holds {holds_decision}, which only a person records; {UNREADABLE_DECISION}"
    return check_edit(root, rel, role_of(event), old, new)


# ---- [agents] delegate ------------------------------------------------------------------------------------
# The main session hands its edits of repository content to an aidd-team role. The main session is a hook event with
# no `agent_type`, which the harness writes for every subagent: a role or a helper is never the main session, and
# nothing an agent writes in a tool's input changes that. The lease that makes `auto` deny names one session id
# (`aidd autopilot start --session ID`); every other session is steered at most, never denied.


def governed(root: str, rel: str) -> bool:
    """Repository content `delegate` governs: a path inside the repository, outside .git, that git tracks (a file, or a
    folder that holds one) or does not ignore. Scratch output in an ignored folder is not; a tracked file there is."""
    if not rel or rel == ".git" or rel.startswith((".git/", "../")) or os.path.isabs(rel):
        return False
    if gitutil.ok(["--literal-pathspecs", "ls-files", "--error-unmatch", "--", rel], root):
        return True
    return not gitutil.ok(["check-ignore", "-q", "--", rel], root)


@dataclass
class Place:
    """Where a path a tool writes lives: the top of the repository that holds it ("" outside every repository), why
    git failed there (None when it answered), the path relative to that top as it is spelled on disk, and the folder
    git was asked from."""

    top: str
    why: str | None
    rel: str
    probe: Path


def _probe(real: Path) -> Path:
    """The folder to ask git from for `real`: the folder that holds the `.git` on its way, since git answers no
    work-tree question from inside a git directory, else the nearest folder that exists (`real` itself for a folder)."""
    for i, part in enumerate(real.parts):
        if part.casefold() == ".git":
            return Path(*real.parts[:i])
    return next((p for p in (real, *real.parents) if p.is_dir()), Path(real.anchor))


def _relative(real: Path, base: Path) -> str | None:
    """`real` relative to `base`, also where a case-insensitive file system spells a folder on the way another way."""
    try:
        return real.relative_to(base).as_posix()
    except ValueError:
        pass
    for n in range(len(real.parts), 0, -1):
        head = Path(*real.parts[:n])
        try:
            if head.exists() and os.path.samefile(head, base):
                return Path(*real.parts[n:]).as_posix()
        except OSError:
            continue
    return None


def _disk_case(top: Path, rel: str) -> str:
    """`rel` with each part spelled as it is on disk, where a case-insensitive file system took another case
    (`BUILD/KEEP.txt` is build/keep.txt), so git's index and ignore checks and the globs read the file that is written."""
    cur, out = top, list[str]()
    parts = [p for p in rel.split("/") if p and p != "."]
    for i, part in enumerate(parts):
        try:
            names = os.listdir(cur)
        except OSError:
            return "/".join(out + parts[i:])
        if part not in names and os.path.lexists(cur / part):
            part = next((n for n in names if n.casefold() == part.casefold()), part)
        out.append(part)
        cur = cur / part
    return "/".join(out) or "."


def locate(path: Path) -> Place:
    """The repository that holds `path`, found from the path itself and never from the session's cwd, so a sibling or
    nested worktree, or a session started outside the repository, meets the same rules as an Edit. The path is read as
    the kernel reads it: each symbolic link is followed before the `..` after it (`out/l/../x` with `l` -> repo/src is
    repo/x), never with `..` taken away as text first."""
    real = Path(os.path.realpath(Path(path).absolute()))
    probe = _probe(real)
    top, why = _repo_top(probe)
    if not top:
        return Place("", why, "", probe)
    base = Path(top).resolve()
    rel = _relative(real, base)
    if rel is None:
        return Place("", None, "", probe)
    return Place(top, None, _disk_case(base, rel), probe)


def readings(path: Path) -> list[Path]:
    """The files a tool may mean by `path`: as the kernel reads it, and, when that differs, with `..` taken away as text
    first, as a program that normalises a path before it opens it does. An edit tool's write is judged on both."""
    absolute = Path(path).absolute()
    textual = Path(os.path.normpath(absolute))
    return [absolute] if os.path.realpath(textual) == os.path.realpath(absolute) else [absolute, textual]


def _load(root: str) -> cfgmod.Config | None:
    """The repository's aidd config, or None when it has none the guard can read."""
    try:
        return cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch, skip_unread=True)
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError, ValueError):
        return None


def config_problem(root: str | None) -> str | None:
    """Why an adopted repository's local config is invalid, said for the agent; None when it loads, or there is none.
    An invalid config never disables the guard: the callers hold the default commands and a role's writes on it. A URL
    parent the guard cannot fetch is expected (it runs offline by design): it is skipped with a warning, never a problem."""
    if not root or not _adopted(root):
        return None
    try:
        cfgmod.load_file(cfgmod.CONFIG_PATH, root, fetch=_offline_fetch, skip_unread=True)
        return None
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError, ValueError) as exc:
        text = str(exc).strip()
        first = text.splitlines()[0] if text else type(exc).__name__
        if "gated_commands" in text:
            first = "`[[guard.gated_commands]]` is now `[[guard.held_commands]]`: rename each table"
        return f"the aidd config is invalid: {first}; run `aidd validate`"


def holds(root: str | None, event: dict) -> bool:
    """Whether the guard holds this actor's writes in the repository `root`: a role or a helper subagent where aidd is
    adopted, or a main session that `delegate` denies there."""
    if not root or not _adopted(root):
        return False
    if role_of(event) or is_helper(event):
        return True
    cfg = _load(root)
    return cfg is not None and delegate_denies(root, event, cfg) is not None


HARD_LINK = (
    "{path} has {n} hard links, so a write to it changes the same file under every other name, and the guard cannot "
    "tell whether one of them is repository content. Write a new file instead, or leave it alone"
)


def hard_link_check(path: Path, roots: list[str | None], event: dict, cwd: Path | None = None) -> Verdict | None:
    """("deny", reason) for a write to a regular file with more than one hard link, by an actor the guard holds in
    one of `roots` (the target's repository and the session's), or in the repository of `cwd`, read only for such a
    file; else None. Removing a name is not such a write."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_nlink < 2:
        return None
    if cwd is not None:
        roots = [*roots, _session_root(cwd)]
    if not any(holds(r, event) for r in dict.fromkeys(r for r in roots if r)):
        return None
    return "deny", HARD_LINK.format(path=path, n=st.st_nlink)


def _lease_holder(root: str, event: dict) -> bool:
    """Whether the event's session holds a live autopilot lease. A lease aidd cannot read names no session here: `auto`
    never denies a session it cannot place, and `aidd autopilot next` refuses that file anyway."""
    from . import lease as leasemod

    sid = event.get("session_id")
    if not isinstance(sid, str) or not leasemod.SESSION.match(sid):
        return False
    try:
        return leasemod.for_session(root, sid) is not None
    except (leasemod.LeaseError, OSError, gitutil.GitError):
        return False


def delegate_in_force(root: str, cfg: cfgmod.Config) -> str:
    """The `delegate` mode the guard applies here. A profile's default of `always` (regulated) applies only when the
    team is installed, since there is no role to hand an edit to without it; until then the guard acts as `auto`. A
    config that sets `always` itself keeps it, team or not: the guard then denies and says to install the team."""
    mode = cfgmod.delegate_mode(cfg.raw)
    if mode == "always" and not cfgmod.delegate_set(cfg.raw) and not team_installed(root):
        return "auto"
    return mode


def delegate_denies(root: str, event: dict, cfg: cfgmod.Config) -> str | None:
    """Why `delegate` denies this main session's edits of repository content (`always`, or `auto` in the session that
    holds the autopilot lease), or None when it does not. A subagent's event is never the main session's."""
    if event.get("agent_type"):
        return None
    mode = delegate_in_force(root, cfg)
    if mode == "always":
        return '[agents] delegate = "always": the main session never edits repository content'
    if mode == "auto" and _lease_holder(root, event):
        return '[agents] delegate = "auto" and this session runs autopilot: the lead never edits repository content'
    return None


def owners_of(root: str, cfg: cfgmod.Config, rel: str) -> list[str]:
    """The aidd-team roles whose write area holds `rel`, in the registry's order."""
    fill = _fill(cfg, _specs(root, cfg))
    roles = resources.roles()
    return [r for r in roles["order"] if roles["roles"][r]["writes"] and _role_allows(r, rel, fill)[0]]


MAX_NAMED_OWNERS = 3


def hand_to(root: str, cfg: cfgmod.Config, rel: str) -> str:
    """Whom to hand an edit of `rel` to, in a sentence the agent can act on."""
    owners = owners_of(root, cfg, rel)
    if not owners:
        return (
            f"no role's area holds {rel}: a person edits it, or a Task's scope must cover it first "
            "(`/aidd-team:fix` for a small fix, `/aidd-team:specify` for a Spec)"
        )
    names = ", ".join(f"`aidd-team:{r}`" for r in owners[:MAX_NAMED_OWNERS])
    return f"hand the edit of {rel} to the role that owns it: {names} (a subagent of that type; `aidd-<role>` when `aidd init --team` installed the team)"


NO_TEAM = (
    "no aidd-team role is installed here to hand {rel} to. Install the team (`aidd init --team`, or the aidd-team "
    "plugin), or ask a person to change `[agents] delegate`. Never route around this through a shell"
)


def delegate_check(root: str, rel: str, event: dict, cfg: cfgmod.Config) -> Verdict | None:
    """("deny", reason) when `delegate` denies this main-session edit of `rel`, else None. Under `always` with no team
    installed, the reason says to install it rather than name a role that is not there."""
    why = delegate_denies(root, event, cfg)
    if why is None or not governed(root, rel):
        return None
    if cfgmod.delegate_mode(cfg.raw) == "always" and not team_installed(root):
        return "deny", f"{why}, and {NO_TEAM.format(rel=rel)}"
    return "deny", f"{why}; {hand_to(root, cfg, rel)}. Hand off instead, and never route around this through a shell"


# An MCP tool that writes a file (a filesystem server's `write_file`, a forge's `create_or_update_file` or `push_files`):
# under a `delegate` that denies, it is held to the same rule as an edit of each path its input names.
_MCP_FILE_VERBS = frozenset(
    {"write", "edit", "create", "update", "put", "move", "rename", "delete", "remove", "replace", "append", "patch", "apply", "save", "push"}
)
_MCP_FILE_NOUNS = frozenset({"file", "files"})


_MCP_PATH_KEYS = ("path", "file_path", "filename", "file", "destination", "target", "source", "src", "dest", "old_path", "new_path", "uri")


def _mcp_paths(tool_input: object) -> list[str]:
    """The file paths an MCP tool's input names (_MCP_PATH_KEYS, each of `paths`, and each of `files`); a `uri` counts
    only as a `file:` URI."""
    if not isinstance(tool_input, dict):
        return []

    def named(d: dict) -> list[str]:
        found = []
        for k in _MCP_PATH_KEYS:
            v = d.get(k)
            if isinstance(v, str) and v:
                if v.startswith("file:"):
                    v = unquote(urlparse(v).path)
                elif k == "uri" or "://" in v:
                    continue
                found.append(v)
        return found

    found = named(tool_input)
    for key in ("files", "paths"):
        for item in tool_input.get(key) or [] if isinstance(tool_input.get(key), list) else []:
            if isinstance(item, dict):
                found += named(item)
            elif isinstance(item, str):
                found.append(item)
    return found


def _delegate_mcp(root: str | None, cwd: str, name: str, tool_input: object, event: dict) -> Verdict | None:
    """("deny", reason) for an MCP tool that writes a file of a repository while `delegate` denies the main session's
    edits there. Each path is judged in the repository that holds it; a relative one is read from `root`, the
    session's repository, else from `cwd`."""
    words = _mcp_words(name.rsplit("__", 1)[-1])
    if not words or words[0] in _MCP_READ_VERBS:
        return None
    if not (_MCP_FILE_VERBS & set(words)) or not (_MCP_FILE_NOUNS & set(words)):
        return None
    # The main session meets `delegate`; a role or a helper meets the edit rules, as for a shell write.
    lead_only = not event.get("agent_type")
    for raw in _mcp_paths(tool_input):
        for path in readings(Path(raw) if os.path.isabs(raw) else Path(root or cwd) / raw.lstrip("/")):
            verdict = _judge_write(path, root, event, lead_only=lead_only)
            if verdict is not None and verdict[0] == "deny":
                return "deny", f"MCP tool {name}: {verdict[1]}"
    return None


def _judge_write(path: Path, root: str | None, event: dict, *, lead_only: bool = False, content: bool = True) -> Verdict | None:
    """The verdict on a write to `path` by whoever `event` says writes, in the repository that holds the path (never the
    session's): a role or a helper meets the edit rules, a main session `delegate`. `root` is the session's own
    repository, which also holds a hard link's write. `lead_only` checks only `delegate` (an MCP tool), and `content`
    is false for a write that only removes or renames a name. None when nothing applies."""
    place = locate(path)
    failed = _git_failed_reason(place.probe, place.why)
    if failed:
        return "deny", failed[0]
    verdict: Verdict | None = None
    if place.top and _adopted(place.top):
        if not lead_only and (role_of(event) or is_helper(event)):
            verdict = check_agent_edit(place.top, place.rel, event)
        elif not event.get("agent_type"):
            cfg = _load(place.top)
            verdict = delegate_check(place.top, place.rel, event, cfg) if cfg is not None else None
    if (verdict is None or verdict[0] == "allow") and content:
        verdict = hard_link_check(path, [place.top, root], event) or verdict
    return verdict


def team_installed(root: str) -> bool:
    """The aidd-team roles are there to hand to: the plugin is on (`aidd-team@aidd`), or `aidd init --team` installed them."""
    from . import repo

    if any((Path(root) / ".claude" / "agents").glob(f"{TEAM_PREFIX}*.md")):
        return True
    return f"aidd-team@{repo.MARKETPLACE}" in repo.plugins_enabled(Path(root))


def delegate_steer(root: str, rel: str, event: dict, cfg: cfgmod.Config) -> str | None:
    """Under `auto`, outside the lease holder's session: a note to the agent, never a denial, naming the role that owns
    `rel`. Said once per session and role, only when the team is installed; None otherwise."""
    from . import lease as leasemod

    sid = event.get("session_id")
    if event.get("agent_type") or delegate_in_force(root, cfg) != "auto" or not isinstance(sid, str) or not leasemod.SESSION.match(sid):
        return None
    if not governed(root, rel) or not team_installed(root):
        return None
    owners = owners_of(root, cfg, rel)
    if not leasemod.say_once(root, sid, f"delegate {owners[0] if owners else '-'}"):
        return None
    if not owners:
        # Information only: this session may edit the file. It must never read as a reason to refuse a harmless edit.
        return (
            f'aidd: [agents] delegate = "auto" (a note, not a denial): no aidd-team role\'s area holds {rel}, so there is no role '
            "to hand it to. This session may edit it. This note comes once per session and role."
        )
    return f'aidd: [agents] delegate = "auto": prefer the team over editing yourself; {hand_to(root, cfg, rel)}. This note comes once per session and role.'


# ---- the shell check -------------------------------------------------------------------------------------

_SEPARATOR_CHARS = set(";&|()")
_WRAPPERS = {"sudo", "command", "nohup", "time", "exec", "builtin", "nice", "stdbuf", "timeout", "setsid", "ionice", "caffeinate", "chrt", "taskset"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
_POWERSHELLS = {"pwsh", "powershell"}
# Wrapper options that take the next word as their value, when that value is not a number: `stdbuf -o L make`. No such
# list is ever complete, so `held_command` scans past a wrapper for a held program first (`_as_run`), and a word
# shaped like a number, a duration, a CPU list, or a mask (`5`, `10s`, `0-3`, `0x3`) is skipped as a value too.
_WRAPPER_VALUE_OPTIONS = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "nice": frozenset({"-n"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "timeout": frozenset({"-s", "-k", "--signal", "--kill-after"}),
}
_VALUE_WORD = re.compile(r"0x[0-9a-f]+|[0-9][0-9.,-]*[smhd]?", re.I)
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
    """One simple command: its words, the files it redirects output to, and the files it reads as input. `depth` is how
    many subshell groups or command substitutions hold it: a `cd` inside one ends with it. A redirect after a group
    (`(echo y) > f`, `echo $(cat x) > f`) is a simple command with no words of its own."""

    argv: list[str] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    inp: list[str] = field(default_factory=list)
    depth: int = 0
    after: str = ""  # the separator before it: `|` when a pipe feeds it

    def __bool__(self) -> bool:
        return bool(self.argv or self.out or self.inp)


_PUNCTUATION_PIECE = re.compile(r";;&?|;&|[();]|[&|<>]+")


def _pieces(tok: str) -> list[str]:
    """A token of shell punctuation cut where a shell cuts it: `)>` is a group's end and a redirect, `);` two
    separators. A word is left whole."""
    if not tok or not set(tok) <= _SEPARATOR_CHARS | set("<>"):
        return [tok]
    return _PUNCTUATION_PIECE.findall(tok)


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


MAX_NESTING = 3  # levels of `sh -c` and `eval` the shell check follows; a deeper one is a command it cannot read


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
        for body in bodies if depth < MAX_NESTING else []:
            for found in _simple_commands(body, depth + 1, broken):
                found.depth += 1  # a shell that reads a here-document is a child shell
                extra.append(found)
    toks = [piece for tok in toks for piece in _pieces(tok)]
    out: list[_Simple] = []
    group = 0  # open subshell groups and command substitutions; `depth` stays the nesting of `sh -c` and `eval`
    cases = 0  # open `case ... esac` blocks
    pattern = False  # inside a case, the next `)` ends a pattern, never a group
    cur = _Simple()
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if pattern and tok in ("(", ")"):
            if tok == ")":
                pattern = False
                cur = _Simple(depth=group)  # the pattern's words are not a command
        elif _is_redirect(tok):
            target = toks[i] if i < len(toks) else ""
            i += 1
            if target == "(":  # a process substitution, `>(cmd)`: the command inside is read as a group
                i -= 1
            # `2>&1` and `>&2` duplicate a descriptor; the digit after `>&` is not a file.
            elif not (tok.endswith("&") and target.isdigit()):
                (cur.inp if "<" in tok else cur.out).append(target)
        elif _is_separator(tok):
            if cur:
                out.append(cur)
            if cases and tok in (";;", ";&", ";;&"):
                pattern = True
            group = max(0, group + tok.count("(") - tok.count(")"))
            cur = _Simple(depth=group, after=tok)
        else:
            if tok == "esac" and cases and not cur.argv:
                cases, pattern = cases - 1, False
            cur.argv.append(tok)
            if cur.argv[0] == "case" and len(cur.argv) == 3 and tok == "in":
                cases, pattern = cases + 1, True
    if cur:
        out.append(cur)
    expanded: list[_Simple] = []
    for sc in out:
        expanded.append(sc)
        argv = _program_argv(sc.argv)
        if not argv:
            continue
        name = _prog(argv[0])
        flag = next((a for a in argv[1:] if a.lower() in ("-c", "-command")), None) if name in _POWERSHELLS else None
        inline, at = _shell_operand(name, argv[1:]) if name in _SHELLS else (False, None)
        if inline and at is not None:
            inner, shift = argv[1 + at], sc.depth + 1  # a child shell: its `cd` ends with it
        elif flag and argv.index(flag) + 1 < len(argv):
            inner, shift = " ".join(argv[argv.index(flag) + 1 :]), sc.depth + 1
        elif name == "eval":
            inner, shift = " ".join(argv[1:]), sc.depth  # eval runs in this shell
        else:
            continue
        if depth >= MAX_NESTING:
            if broken is not None:
                broken.append(f"nested more than {MAX_NESTING} levels of `sh -c` or `eval`")
            continue
        for found in _simple_commands(inner, depth + 1, broken):
            found.depth += shift
            expanded.append(found)
    return expanded + extra


# Shell options that take the next word as their argument: `bash -o pipefail`, `bash --rcfile x.rc`.
_SHELL_ARG_OPTIONS = frozenset({"--rcfile", "--init-file"})


def _shell_operand(name: str, args: list[str]) -> tuple[bool, int | None]:
    """How the POSIX shell `name` (one of _SHELLS) reads the words after its name: (inline, i). `inline` is true when a short-option cluster
    holds `c` (`-c`, `-lc`, `-cx`, `-euxc`). args[i] is then the command string, else the script file; i is None when
    no operand follows. It skips `--`, long options, and the argument of `-o`, `-O`, `+o`, `+O`, and of an `o` or `O`
    in a cluster (`-euo pipefail`). The splitter and `_as_run` both use it, so they never disagree on what runs."""
    if name not in _SHELLS:
        return False, None
    inline, i = False, 0
    while i < len(args):
        word = args[i]
        if word == "--":
            return inline, i + 1 if i + 1 < len(args) else None
        if word.startswith("--"):
            i += 2 if word in _SHELL_ARG_OPTIONS else 1
        elif len(word) > 1 and word[0] in "-+":
            inline = inline or (word[0] == "-" and "c" in word[1:])
            i += 1 + word.count("o") + word.count("O")
        else:
            return inline, i
    return inline, None


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
                i += 2 if argv[i] in _WRAPPER_VALUE_OPTIONS["env"] else 1
        elif _prog(word) == "busybox" and i + 1 < len(argv) and _prog(argv[i + 1]) in _SHELLS:
            i += 1  # `busybox sh -c ...` runs the shell
        elif _prog(word) in _WRAPPERS:
            takes = _WRAPPER_VALUE_OPTIONS.get(_prog(word), frozenset())
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or _VALUE_WORD.fullmatch(argv[i])):
                i += 2 if argv[i] in takes else 1
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


def _aidd_runs(argv: list[str]) -> list[list[str]]:
    """The words after each place a simple command runs aidd, through any wrapper: `uvx aidd`, `uv run aidd`, `pipx run
    aidd`, `python -m aidd` (or `-m aidd.cli`, `-maidd`), `xargs aidd`, `script -c 'aidd ...'`. A word naming the aidd
    program (its basename, or the module after `-m`) starts one. A search or an `echo` runs nothing."""
    if not argv or _prog(argv[0]) in _SEARCHERS | {"echo", "printf"}:
        return []
    runs = []
    for i, word in enumerate(argv):
        if _prog(word) == "aidd":
            runs.append(argv[i + 1 :])
        elif word == "-m" and i + 1 < len(argv) and argv[i + 1] in _AIDD_MODULES:
            runs.append(argv[i + 2 :])
        elif word.startswith("-m") and word[2:] in _AIDD_MODULES:
            runs.append(argv[i + 1 :])
    return runs


def _aidd_decision(argv: list[str]) -> str | None:
    """`approve` or `ship` when a simple command runs aidd with it (`_aidd_runs`), as its first positional word."""
    for rest in _aidd_runs(argv):
        first = _words(rest, set())[:1]
        if first and first[0] in ("approve", "ship"):
            return first[0]
    return None


# The options of `aidd autopilot` that take a value, and the spellings argparse takes for `--session` (a unique prefix).
_AUTOPILOT_VALUE_FLAGS = {"--work", "--session", "--timebox", "--goal", "--spec", "--tokens", "--cost", "--currency", "--merged"}
_SESSION_FLAGS = frozenset("--session"[:n] for n in range(3, len("--session") + 1))  # `--s` is unique for `stop`
_RAW_AUTOPILOT = re.compile(r"\bautopilot\b[^\n;&|]*\b(?:start|stop)\b[^\n;&|]*--se", re.I)
AUTOPILOT_SESSION = (
    "the command starts or stops autopilot for another session ({named}), not this one. A lease bound to another session, "
    "such as the person's own, makes `delegate = \"auto\"` deny that session's edits. Start and stop autopilot only for this "
    "session, with the id the harness gives it (`${{CLAUDE_SESSION_ID}}` in Claude Code)"
)


def _session_values(args: list[str]) -> list[str]:
    """Every value `args` give `--session` (or a prefix argparse takes for it), as `--session X` or `--session=X`."""
    found = []
    for i, a in enumerate(args):
        name, eq, value = a.partition("=")
        if name in _SESSION_FLAGS:
            found.append(value if eq else (args[i + 1] if i + 1 < len(args) else ""))
    return found


def autopilot_session_denial(command: str, event: dict) -> str | None:
    """Why `command` may not run: it starts or stops autopilot (`aidd autopilot start|stop`) with a `--session` that is
    not the hook event's own `session_id`, which the harness writes. An agent that read the person's session id from
    the git directory could otherwise bind the lease to the person's session. None when it does not."""
    own = event.get("session_id")
    own = own if isinstance(own, str) and own else None
    broken: list[str] = []
    named: list[str] = []
    for sc in _simple_commands(command, broken=broken):
        for rest in _aidd_runs(_program_argv(sc.argv)):
            pos = _words(rest, _AUTOPILOT_VALUE_FLAGS | _SESSION_FLAGS)
            if pos[:1] == ["autopilot"] and pos[1:2] in (["start"], ["stop"]):
                named += [v for v in _session_values(rest) if v != own]
    if broken and _RAW_AUTOPILOT.search(command):
        named.append("a session the check cannot read")
    if not named:
        return None
    return AUTOPILOT_SESSION.format(named=", ".join(f"`{n}`" for n in dict.fromkeys(named)) + ("" if own else "; the hook event names no session"))


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


# git subcommands that put new commits on the checked-out branch, or move it.
_LANDS = {"merge", "commit", "cherry-pick", "revert", "am", "rebase", "reset"}
_RESET_MOVES = {"--hard", "--soft", "--mixed", "--keep", "--merge"}
_GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def _base_branch_denial(simple: list[_Simple], root: str) -> str | None:
    """Why a command lands an agent's work on the base branch, or None; only where the local gate is the gate (no remote,
    or no CI gate), since a platform protects its own branch. It follows `git checkout`/`git switch` through the simple
    commands in order, so `git checkout main && git merge feat` is seen as a merge on main."""
    from .localctx import platform_of

    if platform_of(root) != "local":
        return None
    protected = set(_PROTECTED_BRANCHES)
    try:
        protected.add(inputs.default_base(root).removeprefix("origin/"))
    except gitutil.GitError:
        pass
    current = gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()

    def lands(what: str, branch: str) -> str:
        return (
            f"`git {what}` lands work on the base branch {branch}. With no platform, the local gate is the gate. Work reaches "
            f"{branch} only through `aidd ship`, which a person runs at their own terminal"
        )

    for sc in simple:
        argv = _program_argv(sc.argv)
        if not argv or _prog(argv[0]) != "git":
            continue
        words = _words(argv[1:], _GIT_VALUE_FLAGS)
        if not words:
            continue
        sub, rest = words[0], argv[argv.index(words[0]) + 1 :]
        pos = _words(rest, {"-m", "-F", "-b", "-B", "-c", "-C", "--orphan", "-X", "-s", "--strategy", "--onto"})
        if sub in ("checkout", "switch"):
            new = _flag_value(rest, "-b", "-B", "-c", "-C", "--orphan")
            if new:
                current = new
            elif "--detach" in rest or "-d" in rest:
                current = ""
            elif "--" not in rest and len(pos) == 1:
                current = pos[0]
        elif sub in _LANDS and current in protected:
            if sub == "reset" and not (set(rest) & _RESET_MOVES) and (not pos or "--" in rest or (Path(root) / pos[0]).exists()):
                continue  # unstaging paths moves no branch
            return lands(sub, current)
        elif sub == "push":
            targets = {(r.lstrip("+").rpartition(":")[2] or r).removeprefix("refs/heads/") for r in pos[1:]}
            targets = {current if t == "HEAD" else t for t in targets} or ({current} if current else set())
            hit = sorted(targets & protected)
            if hit:
                return lands("push", hit[0])
        elif sub == "branch" and set(rest) & {"-f", "--force", "-M", "-D", "-d", "--delete", "-m", "--move", "-C", "-c", "--copy"}:
            hit = sorted(set(pos) & protected)
            if hit:
                return lands("branch", hit[0])
        elif sub == "update-ref":
            hit = sorted({w.removeprefix("refs/heads/") for w in pos if w.startswith("refs/heads/")} & protected)
            if hit:
                return lands("update-ref", hit[0])
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
        return "the shell check cannot parse the command, and its text force-pushes or deletes a branch, maybe a protected branch. An agent never rewrites history on the default branch"
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
                f"the shell check cannot parse the command (an unbalanced quote), and {FAIL_CLOSED_ENV}=1 denies what it cannot check. "
                "Rewrite it with balanced quotes, or put the text in a file"
            )
    reads = all(_only_reads(_program_argv(sc.argv)) for sc in simple)
    if (_APPROVAL_TEXT.search(command) and any(_sends_input(sc) for sc in simple)) or any(_types_approval(sc) for sc in simple):
        return (
            "the command types an approval (`aidd approve`, `aidd ship`, `/aidd approve`, or an approval record) into another terminal "
            "or program. An approval is a person's: that person types it in a terminal an agent did not start and does not drive"
        )
    if _AIDD_APPROVE.search(command) and not reads:
        return "the command carries `/aidd approve`: an approval is a human's to post, never an agent's"
    if _APPROVAL_RECORD.search(command) and not reads:
        return (
            f"the command names {local.APPROVALS_REF} or {local.MERGE_TRAILER}, where local approvals are recorded. An approval is a "
            "person's, recorded with `aidd approve` in a terminal an agent did not start. An agent only reads those approvals"
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
        elif name == "git" and _words(args, {"-C", "-c"})[:1] == ["config"]:
            why = _signing_config_denial(args[args.index("config") + 1 :])
            if why:
                return why
    return _base_branch_denial(simple, root) if root else None


# `git config` options that take a value, and the ones that only read.
_CONFIG_VALUE_FLAGS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value"}
_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color", "--get-colorbool", "--list", "-l"}


def _signing_key(key: str) -> bool:
    """A config key (or section) that decides which key signs or which signatures git counts as good."""
    k = key.lower()
    return k in ("gpg", "user", "user.signingkey") or k.startswith("gpg.")


def _signing_config_denial(rest: list[str]) -> str | None:
    """Why a `git config` command (its words after `config`) changes commit signing, or None when it only reads or
    changes another key. An agent that points `gpg.ssh.program` at a script, or `gpg.ssh.allowedSignersFile` at its own
    list, would make this machine call any signature good."""
    flags, pos, skip = [], [], False
    for a in rest:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            flags.append(a.split("=", 1)[0])
            skip = a in _CONFIG_VALUE_FLAGS
        else:
            pos.append(a)
    if (pos[:1] in (["get"], ["list"])) or _CONFIG_READS & set(flags):
        return None
    if {"-e", "--edit"} & set(flags) or pos[:1] == ["edit"]:
        keys = ["gpg"]  # the whole file, signing included
    elif pos[:1] in (["set"], ["unset"], ["rename-section"], ["remove-section"]):
        keys = pos[1:2]
    elif {"--unset", "--unset-all", "--remove-section", "--rename-section", "--add", "--replace-all"} & set(flags) or len(pos) >= 2:
        keys = pos[:1]
    else:
        return None  # `git config <key>` reads it
    if any(_signing_key(k) for k in keys):
        return (
            "the command changes commit signing in git's config (gpg.*, user.signingkey). Which key signs, and which signatures "
            "count as good, are a person's settings: an agent never changes them"
        )
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


# Writers whose own targets (not their redirects) only add, remove, or rename a name: the file under another hard link
# keeps its content.
_NAME_ONLY = frozenset({"rm", "unlink", "rmdir", "mv", "ln", "link"})


def _short_flag(args: list[str], letter: str, long: str) -> bool:
    """Whether `args` hold the short option `letter` (alone or in a cluster such as `-sf`) or the long option `long`."""
    return any(a == long or (a.startswith("-") and not a.startswith("--") and letter in a[1:]) for a in args)


def _write_targets(sc: _Simple, cwd: Path) -> tuple[list[str], list[str]]:
    """(paths a simple command writes, reasons it cannot tell) — best-effort, for the obvious writers only. A hard
    link's source counts as written (`ln`, `link`, `cp -l`): the new name writes the same file."""
    argv = _program_argv(sc.argv)
    targets = list(sc.out)
    unknown: list[str] = []
    if not argv:
        return targets, unknown
    name, args = _prog(argv[0]), argv[1:]
    plain = [a for a in args if not a.startswith("-")]
    if name == "link":
        return targets + plain, unknown
    if name == "tee":
        targets += plain
    elif name == "sed":
        inplace = any(
            a in ("-i", "--in-place") or a.startswith(("-i", "--in-place=")) or (a[:1] == "-" and a[1:2] != "-" and "i" in a[1:] and a[1:].isalpha())
            for a in args
        )
        if inplace:
            # BSD sed (macOS) takes the backup suffix as the next word: `sed -i '' 's/x/y/' f` keeps no backup.
            args = [a for k, a in enumerate(args) if not (a == "" and k and args[k - 1] == "-i")]
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
        if name == "mv" or (name == "ln" and not _short_flag(args, "s", "--symbolic")) or (name == "cp" and _short_flag(args, "l", "--link")):
            targets += sources
    elif name in ("rm", "touch", "truncate", "shred", "unlink", "rmdir"):
        targets += _words(args, {"-s", "--size", "-r", "--reference"}) if name == "truncate" else plain
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name == "git" and _words(args, {"-C", "-c"})[:1] in (["checkout"], ["restore"]):
        # `git checkout <ref> -- <paths>` and `git restore <paths>` write the named files from another commit.
        at = args.index(_words(args, {"-C", "-c"})[0])
        rest, base = args[at + 1 :], _flag_value(args[:at], "-C")
        if "--" in rest:
            paths = rest[rest.index("--") + 1 :]
        elif args[at] == "restore":
            paths = _words(rest, {"-s", "--source"})
        else:
            paths = _words(rest, {"-b", "-B", "--orphan"})[1:]  # one word alone switches branches
        targets += [str(Path(base) / p) if base and not os.path.isabs(p) else p for p in paths]
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
    simple command, any other pattern a substring of it. A glob that ends in ` *` also matches a command that ends
    just before it: `make* deploy *` matches `make deploy` and `make deploy -j4`, never `make deployment`."""
    text = text.lower()

    def one(p: str) -> bool:
        if not any(c in p for c in "*?["):
            return p in text
        return fnmatch.fnmatchcase(text, p) or (p.endswith(" *") and fnmatch.fnmatchcase(text + " ", p))

    return bool(patterns) and all(one(p.lower()) for p in patterns)


# Programs that run the script named by their first word that is not a flag, and package runners that run the program
# named the same way (`npx --yes wrangler@3 deploy` runs wrangler).
_INTERPRETERS = _SHELLS | _POWERSHELLS | {"source", ".", "py", "node", "ts-node", "tsx", "bun", "deno", "ruby", "perl"}  # and python3.12
_INLINE_FLAGS = {"-c", "-e", "-m", "--eval", "-command", "-encodedcommand", "-p", "--print"}
_RUNNERS = {"npx": (), "bunx": (), "pnpx": (), "pnpm": ("exec", "dlx"), "yarn": ("exec", "dlx"), "npm": ("exec",)}
# `_as_run` reads at most this much of a simple command; the match on the command as written reads all of it.
AS_RUN_MAX = 64 * 1024


class CommandTooLong(ValueError):
    """The program a command runs lies past AS_RUN_MAX, so the held-command check cannot see it."""


def _as_run(argv: list[str], programs: frozenset[str] = frozenset()) -> str:
    """The simple command as the program it runs: after environment assignments, wrappers such as `sudo`, and package
    runners such as `npx`, with the program's path cut to its name, a script run by an interpreter taken as the script,
    and `NAME=value` words left out. `AWS_PROFILE=prod ./bin/terraform apply` is `terraform apply`,
    `bash -x scripts/deploy.sh` is `deploy.sh`, and `make deploy ENV=production` is `make deploy`."""
    capped, budget = [], AS_RUN_MAX
    for word in argv:
        budget -= len(word) + 1
        if budget < 0:
            break
        capped.append(word)
    cut = len(capped) < len(argv)
    too_long = CommandTooLong(f"its program lies past the first {AS_RUN_MAX // 1024} KiB")
    words = _program_argv(capped)
    lead = next((k for k, w in enumerate(capped) if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)), len(capped))
    if programs and lead < len(capped) and _prog(capped[lead]) in _WRAPPERS | {"env"}:
        # After a wrapper, the first word that names a held program is the program, whatever options came before it.
        words = next((capped[k:] for k in range(lead + 1, len(capped)) if _prog(capped[k]) in programs), words)
    for _ in range(3):
        if not words:
            if cut:
                raise too_long
            return ""
        name, rest = _prog(words[0]), words[1:]
        interpreter = name in _INTERPRETERS or re.fullmatch(r"python[0-9.]*", name) is not None
        if name in _SHELLS:
            inline, at = _shell_operand(name, rest)
            if at is None and cut:
                raise too_long
            if inline or at is None:
                break  # an inline script is its own simple command, which the splitter reads
            words = rest[at:]
            continue
        if name in _RUNNERS and (not _RUNNERS[name] or (bool(rest) and rest[0] in _RUNNERS[name])):
            rest = rest[1:] if _RUNNERS[name] else rest
        elif interpreter and not any(a.lower() in _INLINE_FLAGS for a in rest):
            rest = rest[1:] if name in ("bun", "deno") and rest[:1] == ["run"] else rest
        else:
            break
        rest = [a for a in rest if a != "--"]
        rest = rest[next((i for i, a in enumerate(rest) if not a.startswith("-")), len(rest)) :]
        if not rest and cut:
            raise too_long
        if not rest or (interpreter and not re.search(r"[./\\]", rest[0])):
            break
        words = [re.sub(r"(?<=.)@[^/]*$", "", rest[0]), *rest[1:]]
    return " ".join([_prog(words[0]), *(w for w in words[1:] if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w))])


def _held_programs(gates: list[dict]) -> frozenset[str]:
    """The programs the entries name: the first word of each `match` pattern, without a trailing `*`, such as
    `terraform` from `terraform* apply *` and `deploy.sh` from `deploy.sh *`. A word that is an option or still a glob
    names no program."""
    out = set()
    for gate in gates:
        for pattern in gate.get("match", []):
            first = (pattern.split() or [""])[0].lower().rstrip("*")
            if first and not first.startswith("-") and not any(c in first for c in "*?["):
                out.add(first)
    return frozenset(out)


def held_command(cfg: cfgmod.Config, command: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why `command` waits for a person, or None: it matches a `[[guard.held_commands]]` entry and the entry's
    `requires` variable is unset or empty in the environment the session started with. The variable must come
    from there, set by the person who approves: a command that names it proves nothing, so it never counts.
    An entry matches each simple command as written and as the program it runs (`_as_run`), unless one of its
    `unless` patterns matches that same text."""
    return _held_by(cfg.get("guard", "held_commands", default=[]) or [], command, environ)


def _held_by(gates: list[dict], command: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why `command` waits for a person under the held-command entries `gates`, or None (see held_command)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    simple = _simple_commands(command)
    programs = _held_programs(gates)
    # Every reading only adds a match: as written, as run with the held-program scan, and as run without it (so an
    # option value named like a held program, as in `env -C infra/terraform make deploy`, cannot hide the real one).
    readings = (lambda argv: " ".join(argv), lambda argv: _as_run(argv, programs=programs), _as_run)
    texts = [t for sc in simple for t in dict.fromkeys(read(sc.argv) for read in readings) if t] or [command]
    for gate in gates:
        unless = list(gate.get("unless", []))
        if not any(_gate_matches(list(gate.get("match", [])), t) and not any(_gate_matches([u], t) for u in unless) for t in texts):
            continue
        name, env_label, var = gate.get("name", "held command"), gate.get("environment"), gate.get("requires")
        what = f"`{name}` is a held command" + (f" for {env_label}" if env_label else "")
        note = f" {gate['message']}" if gate.get("message") else ""
        if not var:
            return f"{what}: agents never run it.{note} A person runs it outside the agent session."
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(var)}(?![A-Za-z0-9_])", command):
            return (
                f"{what}, and the command names {var}. The approval must come from the environment Claude Code started with, "
                f"set by the person who approves, never from the command itself.{note}"
            )
        if not (env.get(var) or "").strip():
            return (
                f"{what} and needs approval.{note} Ask the person who approves the release to set {var} in the environment "
                f"Claude Code starts with, such as `{var}=CHG-1234 claude`. Its value can be a change or ticket reference. "
                "Or ask that person to run the command themselves. An agent cannot set it."
            )
    return None


def check_command(root: str | None, cwd: str, command: str, event: dict | None = None) -> Verdict:
    """(decision, reason) for running `command` from `cwd`, for whoever `event` says is running it. `root` is the
    adopted repository the session works in, or None outside one: then only the writes are checked. Each obvious shell
    write is judged in the repository that holds its target: for an aidd-team role or a helper subagent, by the edit
    rules; for the main session, by `delegate`."""
    event = event or {}
    if event.get("tool_name") == "PowerShell":
        command = _powershell_plain(command)
    why = autopilot_session_denial(command, event)
    if why:
        return "deny", why
    if root:
        why = forbidden_action(command, root)
        if why:
            return "deny", why
        cfg = _load(root)  # None outside an aidd repository, or with a config that does not load
        problem = None if cfg else config_problem(root)
        try:
            if cfg:
                held = held_command(cfg, command)
            elif problem:  # an invalid config never disables the guard: hold what `aidd init` could detect
                from . import detect

                held = _held_by(detect.default_held(), command)
                held = f"{problem}. Until then the guard holds the commands `aidd init` detects. {held}" if held else None
            else:
                held = None
        except Exception as exc:  # noqa: BLE001  # a held command never runs because the check broke
            kind = str(exc) if isinstance(exc, CommandTooLong) else type(exc).__name__
            return "deny", f"aidd could not check this command against the held commands: {kind}; a person runs it, or fix the config"
        if held:
            return "deny", held
    return shell_writes(root, cwd, command, event)


def _cd(here: Path, before: Path, args: list[str]) -> Path:
    """The folder bash's `cd` moves to: logical by default (`cd out/l/..` is out, with `..` taken as text), physical
    with -P, the folder before with `-`, and HOME with no folder."""
    physical = False
    while args and args[0].startswith("-") and len(args[0]) > 1 and args[0] != "--" and set(args[0][1:]) <= set("LPe@"):
        physical = physical or "P" in args[0]
        args = args[1:]
    args = args[1:] if args[:1] == ["--"] else args
    dest = args[0] if args else str(Path.home())
    if dest == "-":
        return before
    target = (here / dest) if not os.path.isabs(dest) else Path(dest)
    return Path(os.path.realpath(target)) if physical else Path(os.path.normpath(target))


def shell_writes(root: str | None, cwd: str, command: str, event: dict) -> Verdict:
    """(decision, reason) for the obvious shell writes of `command`, each judged in the repository that holds its
    target (`_judge_write`). A target the check cannot read (a patch from a pipe, an unexpanded `$VAR` or glob), or a
    command it cannot read whole, is denied where the guard holds the actor in `root`. A `cd` inside a subshell group
    or a child shell ends with it. A command with a here-document is read twice, with the bodies and without them, so
    a body's text can neither hide a write nor shift the groups."""
    held = holds(root, event) if root else False
    worst: Decision = "allow"
    reasons: list[str] = []
    broken: list[str] = []
    stripped, _ = _split_heredocs(command)
    for text in dict.fromkeys((command, stripped)):
        dirs = [(Path(cwd), Path(cwd))]  # per group: (the folder, the one `cd -` returns to)
        for sc in _simple_commands(text, broken=broken):
            dirs = (dirs + [dirs[-1]] * sc.depth)[: sc.depth + 1]
            here = dirs[-1][0]
            argv = _program_argv(sc.argv)
            if argv and _prog(argv[0]) == "cd":
                dirs[-1] = (_cd(here, dirs[-1][1], argv[1:]), here)
                continue
            if held and _opaque(sc, argv):
                worst = "deny"
                reasons.append(OPAQUE)
            for decision, reason in _target_verdicts(sc, argv, here, root, event, held):
                worst = decision
                reasons.append(reason)
    if held and _substitutes_a_program(command):
        worst = "deny"
        reasons.append(OPAQUE)
    if broken and held:
        worst = "deny"
        reasons.append(f"the shell check cannot read all of the command ({broken[0][:80]}); write it plainly, so its targets can be checked")
    return worst, "; ".join(dict.fromkeys(reasons)) or "no shell write the guard can see"


OPAQUE = "this command runs code the guard cannot read; use the Edit or Write tool, or split the command"
# A command substitution or backticks where a command starts: what runs is known only when the shell runs it.
_SUBSTITUTED_PROGRAM = re.compile(r"(?:^|[;&|\n(]|\b(?:then|do|else)\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*\"?(?:\$\(|`)")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_RUNS_COMMANDS = frozenset({"xargs", "parallel"})
_FIND_RUNS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_BRACES = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")


def _opaque(sc: _Simple, argv: list[str]) -> bool:
    """Whether a simple command runs a command string the parser never sees (the closed list in the module docstring):
    a shell fed by stdin (a here-string, a here-document, an input file, or a pipe), `trap` with a command, `source` or
    `.`, `xargs`, `parallel`, and `find -exec`. `exec`, `command`, and `builtin` are followed as wrappers."""
    if not argv:
        return False
    name, args = _prog(argv[0]), argv[1:]
    if name in _SHELLS:
        inline, at = _shell_operand(name, args)
        return not inline and at is None and bool(sc.inp or sc.after in ("|", "|&"))
    if name in _POWERSHELLS:
        return not any(a.lower() in ("-c", "-command", "-file", "-f") for a in args) and bool(sc.inp or sc.after in ("|", "|&"))
    if name == "trap":
        pos = [a for a in args if not a.startswith("-") or a == "-"]
        return bool(pos) and pos[0] not in ("", "-") and len(pos) > 1
    if name in ("source", "."):
        return True
    if name in _RUNS_COMMANDS:
        return True
    return name == "find" and bool(_FIND_RUNS & set(args))


def _substitutes_a_program(command: str) -> bool:
    """A command substitution or backticks in the program position. Here-document bodies and the text inside quotes
    are not commands: a quoted word keeps only its first two characters, so `"$(cmd)" -c ...` is still seen."""
    stripped, _ = _split_heredocs(command)
    masked = _QUOTED.sub(lambda m: m.group(0)[:3] + m.group(0)[-1] if m.group(0)[0] == '"' else "''", stripped)
    return bool(_SUBSTITUTED_PROGRAM.search(masked))


def _target_verdicts(sc: _Simple, argv: list[str], here: Path, root: str | None, event: dict, held: bool) -> list[Verdict]:
    """The denials for the write targets of one simple command run from `here`."""
    found: list[Verdict] = []
    targets, unknown = _write_targets(sc, here)
    name_only = set(targets[len(sc.out) :]) if argv and _prog(argv[0]) in _NAME_ONLY else set()
    for u in unknown if held else []:
        found.append(("deny", f"{u}; save the patch to a file and apply that file, so its targets can be checked"))
    for t in targets:
        if t in _IGNORED_TARGETS or t.startswith("/dev/"):
            continue
        if "$" in t or "`" in t or any(c in t for c in "*?[") or _BRACES.search(t):
            if not held:
                continue
            verdict: Verdict | None = ("deny", f"cannot tell which file `{t}` names, because the shell check does not expand it; name the file literally")
        else:
            path = (here / t) if not os.path.isabs(t) else Path(t)
            verdict = _judge_write(path, root, event, content=t not in name_only)
        if verdict is not None and verdict[0] != "allow":
            found.append((verdict[0], f"shell write to {t}: {verdict[1]}"))
    return found


def pre_tool_hook(stdin=None, stdout=None) -> int:
    """Claude Code PreToolUse hook: reads the event JSON, prints a permission decision when it denies.

    It allows when it cannot tell: any failure of its own exits 0 without a decision, never a block, unless
    AIDD_HOOK_FAIL_CLOSED=1 (the regulated managed settings) is set, when the failure is a deny.
    """
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    try:
        with gitutil.system_only():  # a git the session's PATH or GIT_* names never answers for the guard
            return _pre_tool(stdin, stdout)
    except Exception as exc:  # noqa: BLE001  # the guard's own crash allows, unless the organization requires the guard
        if os.environ.get(FAIL_CLOSED_ENV) == "1":
            return _decide(stdout, "deny", f"the guard could not check this tool call ({type(exc).__name__}), and {FAIL_CLOSED_ENV}=1 requires the guard")
        return 0


# Each deny reason's family, for the denial log and `aidd metrics --guard`: the first entry whose text the reason
# contains names it. The texts are the fixed parts of the reasons above; a new deny reason needs a row here.
REASON_CODES: tuple[tuple[str, str], ...] = (
    ("the aidd config is invalid", "config_invalid"),
    ("autopilot for another session", "autopilot_session"),
    ("runs code the guard cannot read", "shell_opaque"),
    ("hard links, so a write to it changes", "hard_link"),
    ("inside the git directory", "git_dir"),
    ("[agents] delegate", "delegate"),
    ("may only read (the loop contract's helper rule", "helper_read_only"),
    ("types an approval", "approval_typed"),
    ("denies what it cannot check", "shell_unparsed"),
    ("the guard could not", "guard_failed"),
    ("unknown aidd-team role", "unknown_role"),
    ("go_no_go, sign_off, or outcome, which only a person records", "proposal_decision"),
    ("an Initiative's go_no_go, which only a person records", "initiative_decision"),
    ("of a proposal; ", "proposal_part"),
    ("an exploration's outcome, which only a person records", "exploration_decision"),
    ("only a person adds a dismissal", "review_dismissal"),
    ("which only a person records; use the Edit or Write tool", "decision_unreadable"),
    ("against the held commands", "guard_failed"),
    ("is a held command", "held_command"),
    ("carries `/aidd approve`", "approval_post"),
    ("where local approvals are recorded", "approval_record"),
    ("agents never approve or merge", "approve_or_merge"),
    ("agents never approve;", "approve_or_merge"),
    ("agents never merge;", "approve_or_merge"),
    ("changes commit signing", "signing_config"),
    ("lands work on the base branch", "base_branch"),
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


GIT_FAILED = (
    "the guard could not run git in this repository ({why}). It never reads a git failure as no repository where aidd "
    "is adopted, so it denies until git runs here. It runs only a git at {gits} that answers `git --version`, never one "
    "from the session's PATH"
)


def _repo_top(probe: Path) -> tuple[str, str | None]:
    """(the repository's top level, or "" outside one; why git failed, or None when it answered)."""
    if not probe.is_dir():
        return "", None
    try:
        return gitutil.toplevel(str(probe), check=True), None
    except gitutil.GitError as exc:
        return "", str(exc)


def _git_failed_reason(probe: Path, why: str | None) -> tuple[str, str] | None:
    """After git failed in `probe`: (the deny reason, the adopted folder) when the folder above it that holds the aidd
    config is a repository (it holds `.git`), so a git that cannot run or read it never turns the guard off; else None."""
    if why is None:
        return None
    start = probe.resolve()
    for d in (start, *start.parents):
        if _adopted(str(d)):
            if (d / ".git").exists():
                return GIT_FAILED.format(why=why.strip()[:300], gits=", ".join(gitutil.SYSTEM_GITS)), str(d)
            return None
    return None


def _session_root(cwd: Path) -> str | None:
    """The adopted repository the session works in (its cwd's), or None."""
    top, _ = _repo_top(cwd)
    return top if top and _adopted(top) else None


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


def _pre_tool(stdin, stdout) -> int:
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
        top, why = _repo_top(cwd)
        failed = None if top else _git_failed_reason(cwd, why)
        if failed:
            return _decide(stdout, "deny", failed[0], failed[1], event)
        # The session's own repository, when it adopted aidd. Outside one, only the writes are checked: each in the
        # repository that holds its target.
        root = top if top and _adopted(top) else None
        if tool_name.startswith("mcp__"):
            decision, reason = check_mcp_tool(tool_name, tool_input) if root else ("allow", "not an aidd repository")
            if decision == "allow":
                decision, reason = _delegate_mcp(root, str(cwd), tool_name, tool_input, event) or (decision, reason)
            return _decide(stdout, decision, reason, root, event)
        command = tool_input.get("command") or ""
        if not command:
            return 0
        try:
            verdict = check_command(root, str(cwd), command, event)
        except Exception as exc:  # a parse that breaks never turns into an allow for a writer the guard holds
            if not (role_of(event) or is_helper(event) or holds(root, event)):
                raise
            verdict = ("deny", f"the guard could not check this command ({type(exc).__name__}); write it plainly, or in a file it can read")
        return _decide(stdout, *verdict, root, event)
    target = _edit_path(event)
    if not target:
        return 0
    path = Path(target) if os.path.isabs(target) else cwd / target
    paths = readings(path)
    for reading in paths:
        denial = _edit_denial(reading, cwd, event)
        if denial is not None:
            return _decide(stdout, "deny", denial[0], denial[1], event)
    note = _edit_steer(paths[0], event)
    if note:
        # Context for the agent only, with no permissionDecision: the person's own permission settings still decide.
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}, stdout)
    return 0


def _edit_denial(path: Path, cwd: Path, event: dict) -> tuple[str, str | None] | None:
    """(why, the repository to log in) when an edit tool's write to `path` is denied; None when it is allowed."""
    place = locate(path)
    top, rel = place.top, place.rel
    if not top:
        failed = _git_failed_reason(place.probe, place.why)
        if failed:
            return failed
        # Outside every repository: only a hard link into one is the guard's business.
        link = hard_link_check(path, [], event, cwd)
        return (link[1], None) if link else None
    if _adopted(top) and any(part.casefold() == ".git" for part in Path(rel).parts):
        return f"{rel} is inside the git directory: an edit tool never writes there, only git and aidd commands do", top
    decision, reason = check_agent_edit(top, rel, event)
    if decision != "allow":
        return reason, top
    cfg = _load(top) if _adopted(top) else None
    if cfg is None:
        return None  # check_edit already allowed for want of a valid config; the gate reports it
    lead = delegate_check(top, rel, event, cfg) or hard_link_check(path, [top], event, cwd)
    return (lead[1], top) if lead is not None else None


def _edit_steer(path: Path, event: dict) -> str | None:
    """`delegate`'s note for an allowed edit of `path`, or None."""
    place = locate(path)
    cfg = _load(place.top) if place.top and _adopted(place.top) else None
    if cfg is None:
        return None
    try:
        return delegate_steer(place.top, place.rel, event, cfg)
    except Exception:  # noqa: BLE001  # a steer is a courtesy: it never turns an allow into a failure
        return None
