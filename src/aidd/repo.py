"""Adopt, check, and extend a repository: init, doctor, new, validate."""

from __future__ import annotations

import datetime as dt
import filecmp
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePath

from . import __version__, agentmodels, docs, gitutil, model, resources, rules, util, workitems
from . import config as cfgmod
from .harnesses import HARNESSES, pointer_files
from .model import section
from .util import toml_list

SKILL_REL = ".agents/skills/aidd"
DEFAULT_LINKS = (".claude/skills",)
AGENTS_MARK = "<!-- aidd -->"
GITIGNORE_LINE = "aidd-evidence/"
GITHUB_WORKFLOWS = ("aidd-tests.yml", "aidd-gate.yml", "aidd-relay.yml")
# `aidd init --devcontainer`: the optional dev container with default-deny egress, copied from templates/devcontainer/.
DEVCONTAINER_FILES = ("devcontainer.json", "Dockerfile", "init-firewall.sh")
MARKETPLACE_REPO = "thaithienvanid/aidd"
MARKETPLACE = "aidd"
PLUGIN_RUNNER = subprocess.run


def _shown(p: object) -> str:
    """A path as aidd prints it: forward slashes on every OS, like the docs and the config."""
    return p.as_posix() if isinstance(p, PurePath) else str(p)


def detect_harnesses(root: Path) -> list[str]:
    """The coding agents this repository uses: a folder or file of theirs in it. Never what this machine has installed,
    so init and doctor say the same thing on every teammate's machine; `--harness` names the rest."""
    return [key for key, h in HARNESSES.items() if any((root / x).exists() for x in h.repo)]


def installed_harnesses(*, home: Path | None = None, path: str | None = None) -> list[str]:
    """The coding agents this machine has (a folder in the home directory, or a binary on PATH): only a hint that
    init prints for the ones whose wiring matters and that the repository does not show yet."""
    home = home if home is not None else Path.home()
    env_path = os.environ.get("PATH", "") if path is None else path
    return [key for key, h in HARNESSES.items() if any((home / x).exists() for x in h.home) or any(shutil.which(b, path=env_path) is not None for b in h.bins)]


def fill(text: str, **values: str) -> str:
    """Replace every {{token}}; a token left over means the template and the code drifted apart."""
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    left = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)))
    if left:
        raise ValueError(f"template tokens without a value: {', '.join(left)}")
    return text


LOGIN_PROBES: tuple[tuple[str, ...], ...] = (("git", "config", "github.user"), ("gh", "config", "get", "-h", "github.com", "user"))


EMAIL_PROBE: tuple[str, ...] = ("git", "config", "user.email")
# What an empty owners.approvers means, said the same way by the generated config, `aidd doctor`, `aidd validate`,
# and the gate (gates.gate_config fails config.no_approvers, and an empty pool matches nobody): nothing merges.
EMPTY_APPROVERS = "an empty list means no change can merge: the gate fails closed until you name one"


def _probe(cmd: tuple[str, ...], root: Path) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        r = subprocess.run(list(cmd), cwd=str(root), capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def operator_login(root: Path) -> str | None:
    """The operator's GitHub login from local configuration only: `git config github.user`, then gh's stored user."""
    for cmd in LOGIN_PROBES:
        login = (_probe(cmd, root) or "").lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
            return login
    return None


def operator_email(root: Path) -> str | None:
    """The email the operator's commits carry (`git config user.email`): a solo approver with no platform login, which
    is what local approvals (`aidd approve`) are checked against."""
    email = _probe(EMAIL_PROBE, root) or ""
    return email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None


# The CI templates name the aidd action and reusable workflow at the release tag, on the line after an `aidd-pin:` comment.
_PIN = re.compile(r"(thaithienvanid/aidd(?:/\.github/workflows/gate\.yml)?)@v(\d+\.\d+\.\d+)")
_GITLAB_PIN = re.compile(r'(aidd_pin="thaithienvanid/aidd@)[^"\s]+(")')
# The label a commit pin carries: the release tag when the commit is that tag's, else `aidd <short sha>`.
_PIN_LABEL = r"(?:v\d+\.\d+\.\d+|aidd [0-9a-f]{7,40})"
# Not inside the GitLab pin's shell string: a ` # v1.0.0` comment there would become part of the ref.
_ANY_PIN = re.compile(rf'(?<!aidd_pin=")(thaithienvanid/aidd(?:/\.github/workflows/gate\.yml)?)@[\w.\-/]+(?: # {_PIN_LABEL})?')
# A workflow that checks out aidd's source (aidd-watch.yml): `repository: thaithienvanid/aidd` and, on the next line, `ref:`.
_CHECKOUT_PIN = re.compile(rf"(repository:[ \t]*thaithienvanid/aidd[ \t]*\r?\n[ \t]*ref:[ \t]*)([\w.\-/]+)(?:[ \t]+# {_PIN_LABEL})?")
RELEASE_REPO_URL = "https://github.com/thaithienvanid/aidd"
_REF = re.compile(r"[0-9a-f]{40}|v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")


def installed_ref() -> str | None:
    """The commit this aidd runs from, when it runs from a git checkout of aidd; None from an installed wheel."""
    src = resources.repo_root()
    if src is None or not (src / ".git").exists():
        return None
    try:
        sha = gitutil.run(["rev-parse", "HEAD"], str(src), timeout=10).strip()
    except gitutil.GitError:
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def release_tag_of(sha: str) -> str | None:
    """The release tag (`vX.Y.Z`) that names exactly this commit in the aidd checkout this aidd runs from, if any."""
    src = resources.repo_root()
    if src is None or not (src / ".git").exists() or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    try:
        tags = gitutil.run(["tag", "--points-at", sha], str(src), timeout=10, check=False).split()
    except gitutil.GitError:
        return None
    return next((t for t in sorted(tags, reverse=True) if re.fullmatch(r"v\d+\.\d+\.\d+", t)), None)


def pin_label(ref: str, release: str | None = None) -> str:
    """The comment a commit pin carries, so a reader knows what it is: ` # v1.0.0` only when the commit is that release
    (`release`, or a tag on it in this aidd's checkout), else ` # aidd <short sha>`. A tag pin needs no comment."""
    if len(ref) != 40:
        return ""
    tag = f"v{release}" if release else release_tag_of(ref)
    return f" # {tag}" if tag else f" # aidd {ref[:12]}"


def pin_workflow(text: str, ref: str | None, release: str | None = None) -> str:
    """A CI template with its release-tag aidd refs set to `ref`, as `repin` sets them; None leaves the release tag."""
    if not ref:
        return text
    if not _REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    return repin(text, ref, release, pattern=_PIN)


def release_commit(version: str = __version__, timeout: int = 5) -> str | None:
    """The commit the release tag `v<version>` names on GitHub, so an installed aidd pins CI to a commit rather than a
    tag that can move. None when offline, when AIDD_OFFLINE=1, or when the tag is not there: the caller keeps the tag."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return None
    tag = f"refs/tags/v{version}"
    refs = remote_refs(RELEASE_REPO_URL, timeout, f"{tag}^{{}}", tag) or {}
    sha = refs.get(f"{tag}^{{}}") or refs.get(tag)  # an annotated tag peels to its commit; a lightweight one is it
    return sha if sha and re.fullmatch(r"[0-9a-f]{40}", sha) else None


_PINNED_REF = re.compile(r"thaithienvanid/aidd(?:/\.github/workflows/[\w.-]+)?@([\w.\-/]+)|aidd_pin=\"thaithienvanid/aidd@([^\"\s]+)\"")


def pinned_refs(root: Path) -> list[str]:
    """The aidd refs the repository's CI files pin: the action, the reusable gate workflow, and the GitLab include."""
    files = sorted((root / ".github" / "workflows").glob("*.y*ml")) + [root / ".gitlab" / "aidd.gitlab-ci.yml", root / ".gitlab-ci.yml"]
    refs: list[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8") if f.is_file() else ""
        except (OSError, UnicodeDecodeError):
            continue
        refs += [m.group(1) or m.group(2) for m in _PINNED_REF.finditer(text)]
        refs += [m.group(2) for m in _CHECKOUT_PIN.finditer(text)]
    return list(dict.fromkeys(refs))


def remote_refs(url: str = RELEASE_REPO_URL, timeout: int = 5, *patterns: str) -> dict[str, str] | None:
    """The ref names (all, or those matching `patterns`) at `url` and the object each names, or None when it cannot be reached."""
    try:
        out = gitutil.run(["ls-remote", url, *patterns], ".", timeout=timeout, env={**os.environ, **gitutil.FETCH_ENV})
    except gitutil.GitError:
        return None
    return {name: sha for sha, _, name in (line.partition("\t") for line in out.splitlines()) if name}


def pin_checks(root: Path) -> list[tuple[str, str]]:
    """Best effort, online only: every aidd ref the CI files pin exists at thaithienvanid/aidd, since a pin nobody can
    fetch breaks every CI run. Skipped with AIDD_OFFLINE=1, without a GitHub remote, and when GitHub cannot be reached."""
    refs = pinned_refs(root)
    if not refs or os.environ.get("AIDD_OFFLINE") == "1":
        return []
    remotes = gitutil.run(["remote", "-v"], str(root), check=False, timeout=10) if (root / ".git").exists() else ""
    if "github.com" not in remotes:
        return []
    found = remote_refs()
    if found is None:
        return [("ok", "the aidd pin was not checked: GitHub could not be reached")]
    shas = set(found.values())
    out = []
    for ref in refs:
        if len(ref) == 40 and ref in shas:
            continue
        if len(ref) != 40 and (f"refs/tags/{ref}" in found or f"refs/heads/{ref}" in found):
            continue
        what = "commit is not the tip of any branch or tag" if len(ref) == 40 else "tag does not exist"
        why = f"the CI files pin aidd at {ref}, but that {what} at {RELEASE_REPO_URL}; CI fails if it cannot fetch it. "
        out.append(("warn", why + "Pin a pushed commit or a release: `aidd upgrade --ref <sha> --yes`"))
    many = len(refs) > 1
    return out or [("ok", f"the aidd pin{'s' if many else ''} {', '.join(r[:12] for r in refs)} exist{'' if many else 's'} at {RELEASE_REPO_URL}")]


def unpinned(text: str) -> str:
    """A CI file with its aidd refs blanked, so uninstall recognises it whichever ref init wrote."""
    return _CHECKOUT_PIN.sub(r"\1REF", _GITLAB_PIN.sub(r"\1REF\2", _ANY_PIN.sub(r"\1@REF", text)))


def config_supports_mode() -> bool:
    """Whether this aidd's config schema has the top-level `mode` key, which the base branch's config uses to decide the gate's mode."""
    return "mode" in resources.load_json("config.schema.json").get("properties", {})


MODE_COMMENT = (
    '# mode = "advisory"   # the gate\'s mode, read from the base branch: advisory reports without blocking; enforce blocks.\n'
    "#                      # It wins over the CI file's input, so a pipeline variable cannot make an enforcing gate advisory."
)


GOAL_COMMENT = "one sentence every agent weighs an open choice against; `aidd owners` shows it"


def config_text(
    profile: str,
    *,
    approvers: list[str] | None = None,
    reviewers: dict[str, list[str]] | None = None,
    test: list[str] | None = None,
    policy: list[str] | None = None,
    mode: str | None = None,
    goal: str | None = None,
) -> str:
    """The starting .aidd/config.toml, filled from the skill's template. `mode` writes the gate's mode key when the schema has it."""
    tpl = (resources.data_dir("skill") / "assets" / "config.toml").read_text(encoding="utf-8")
    pools = "\n".join(f"{pool} = {toml_list(who)}" for pool, who in (reviewers or {}).items())
    if mode and config_supports_mode():
        mode_line = f"mode = \"{mode}\"   # the gate's mode, read from the base branch; it wins over the CI file's input"
    else:
        mode_line = MODE_COMMENT
    return fill(
        tpl,
        profile=profile,
        mode=mode_line,
        approvers=toml_list(approvers)
        if approvers
        else f'[]   # TODO: name who may approve, such as ["@org/leads"], or ["email:you@example.com"] to approve locally; {EMPTY_APPROVERS}',
        reviewers=f"[owners.reviewers]\n{pools}" if pools else '# [owners.reviewers]\n# security = ["@org/security"]',
        tests=f'[[tests]]\nname = "unit"\ncommand = {toml_list(test)}' if test else '# [[tests]]\n# name = "unit"\n# command = ["npm", "test"]',
        policy=f"[policy]\ncommand = {toml_list(policy)}" if policy else '# [policy]\n# command = ["./scripts/aidd-policy"]',
        goal=f"goal = {json.dumps(goal, ensure_ascii=False)}   # {GOAL_COMMENT}"
        if goal
        else f'# goal = "make onboarding succeed on the first try"   # {GOAL_COMMENT}',
    )


def _write(path: Path, text: str, force: bool, actions: list[str]) -> None:
    if path.exists() and not force:
        actions.append(f"kept     {_shown(path)} (exists; --force replaces it)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    actions.append(f"wrote    {_shown(path)}")


REVIEW_POLICY = "REVIEW.md"


def write_review_policy(root: Path, actions: list[str]) -> None:
    """The review policy every reviewer reads, written once and never replaced, even with --force: after init it is the
    repository's own policy, and uninstall removes it only unchanged."""
    path = root / REVIEW_POLICY
    if path.exists():
        actions.append(f"kept     {_shown(path)} (the repository's review policy)")
        return
    _write(path, (resources.data_dir("templates") / REVIEW_POLICY).read_text(encoding="utf-8"), False, actions)


def vendor_skill(root: Path, force: bool, actions: list[str]) -> None:
    src = resources.data_dir("skill")
    dest = root / SKILL_REL
    if dest.resolve() == src.resolve():
        actions.append(f"kept     {_shown(dest)} (this is the source)")
        return
    if dest.exists() and not force:
        actions.append(f"kept     {_shown(dest)} (exists; --force upgrades it)")
        return
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    actions.append(f"vendored {_shown(dest)} (aidd {__version__})")


def link_skill(root: Path, link_dir: str, actions: list[str], force: bool = False) -> None:
    link = root / link_dir / "aidd"
    target = os.path.relpath(root / SKILL_REL, link.parent)
    if link.is_symlink() and os.readlink(link) == target:
        actions.append(f"kept     {_shown(link)} -> {_shown(target)}")
        return
    if link.is_symlink() or link.exists():
        if not force:
            why = "a link elsewhere; --force replaces it" if link.is_symlink() else "a real directory; --force refreshes it"
            actions.append(f"kept     {_shown(link)} ({why})")
            return
        if link.is_symlink():
            link.unlink()
        else:
            shutil.rmtree(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        actions.append(f"linked   {_shown(link)} -> {_shown(target)}")
    except OSError:
        shutil.copytree(root / SKILL_REL, link)
        actions.append(f"copied   {_shown(link)} (symlinks unavailable; `aidd doctor` checks it stays equal)")


def init(
    root: Path,
    *,
    profile: str,
    ci: str,
    links: list[str],
    skill: bool = True,
    force: bool = False,
    approvers: list[str] | None = None,
    reviewers: dict[str, list[str]] | None = None,
    test: list[str] | None = None,
    policy: list[str] | None = None,
    goal: str | None = None,
    enforce: bool = False,
    agent_hooks: bool | None = None,
    team: bool = False,
    harnesses: list[str] | None = None,
    claude_plugins: bool = False,
    ref: str | None = None,
    devcontainer: bool = False,
) -> list[str]:
    """Adopt. The gate starts in advisory mode (observe first) unless enforce is set; the CI files are pinned by `_resolve_pin`.

    Coding agents are detected (or given as `harnesses`) and each one is wired the way it reads instructions (`harnesses.py`):
    Claude Code gets the `.claude/skills` link, the edit-time hook, and the MCP server, unless `agent_hooks` is False or the
    plugins are installed instead (`claude_plugins`); an agent with its own instruction file gets a pointer file; the rest read AGENTS.md.
    `links` are extra skill directories to link whatever was detected. `devcontainer` also writes .devcontainer/ from
    templates/devcontainer/: a container that denies outbound traffic except to an allow-list, a starting point only.
    """
    actions: list[str] = []
    tpl = resources.data_dir("templates")
    detected = detect_harnesses(root) if harnesses is None else list(harnesses)
    source = " (--harness)" if harnesses is not None else " (their files in this repository)"
    none = "no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them"
    actions.append("detected " + (", ".join(HARNESSES[h].label for h in detected) + source if detected else none))
    if harnesses is None:
        # Installed here but not visible in the repository: named only where init would wire something for it.
        wired = [h for h in installed_harnesses() if h not in detected and (h == "claude-code" or (HARNESSES[h].pointer and not HARNESSES[h].only_if_present))]
        if wired:
            labels, flags = ", ".join(HARNESSES[h].label for h in wired), " ".join(f"--harness {h}" for h in wired)
            actions.append(f"next     this machine has {labels}: wire {'it' if len(wired) == 1 else 'them'} with {flags}")
    claude = "claude-code" in detected
    if claude_plugins and not install_claude_plugins(root, actions, team=team):
        claude_plugins = False
    if not approvers and profile == "solo":
        # Solo still needs a listed approver: the operator, found without the network.
        # Without a platform login, the email the commits carry.
        login = operator_login(root)
        email = None if login else operator_email(root)
        approvers = [f"@{login}"] if login else ([f"email:{email}"] if email else None)
        if login:
            actions.append(f"approver @{login} (the operator, from the local git and gh config)")
        elif email:
            actions.append(f"approver email:{email} (the operator, from `git config user.email`; --approvers @you names a platform login)")
        else:
            actions.append("next     name the approver: `aidd init --approvers @you --force`")
    mode = "enforce" if enforce else "advisory"
    cfg_text = config_text(profile, approvers=approvers, reviewers=reviewers, test=test, policy=policy, mode=mode, goal=goal)
    _write(root / cfgmod.CONFIG_PATH, cfg_text, force, actions)
    _write(root / "specs" / "README.md", (tpl / "specs-README.md").read_text(encoding="utf-8"), force, actions)
    write_review_policy(root, actions)
    if skill:
        vendor_skill(root, force, actions)
        for d in dict.fromkeys([*DEFAULT_LINKS, *links]) if claude and not claude_plugins else links:
            if claude_plugins and d in DEFAULT_LINKS:
                actions.append(f"skipped  {_shown(d)}/aidd (the aidd plugin ships the skill; a link would load it twice)")
                continue
            link_skill(root, d, actions, force)
    snippet = (tpl / "AGENTS.snippet.md").read_text(encoding="utf-8")
    if not skill:
        snippet = snippet.replace("load the skill at `.agents/skills/aidd/SKILL.md`", "load the `aidd` skill (installed as a plugin)")
    snippet = snippet.rstrip("\n") + "\n\n" + verification_block(configured_tests(root))
    _pointer(root / "AGENTS.md", "# Agents\n\n", snippet, actions)
    if ci in ("github", "gitlab"):
        pin, release, why = _resolve_pin(ref)
        if pin:
            label = pin_label(pin, release)
            actions.append(f"pinned   the aidd workflows to {pin}" + why + (f", labelled `{label[3:]}`" if label.startswith(" # aidd ") else ""))
        else:
            actions.append(f"next     pin the aidd workflows to a commit SHA: `aidd init --ref <sha> --force` (they name v{__version__})")
    if devcontainer:
        for name in DEVCONTAINER_FILES:
            _write(root / ".devcontainer" / name, (tpl / "devcontainer" / name).read_text(encoding="utf-8"), force, actions)
    pr_tpl = (tpl / "github" / "pull_request_template.md").read_text(encoding="utf-8")
    if ci == "github":
        for name in GITHUB_WORKFLOWS:
            text = pin_workflow((tpl / "github" / name).read_text(encoding="utf-8"), pin, release)
            if name == "aidd-gate.yml" and not enforce:
                text = re.sub(r"(mode:\s*)enforce", r"\1advisory", text, count=1)
            _write(root / ".github" / "workflows" / name, text, force, actions)
        _write(root / ".github" / "pull_request_template.md", pr_tpl, force, actions)
    elif ci == "gitlab":
        # The mode is the config's `mode` key, read from the base branch; a pipeline variable cannot change it.
        text = pin_workflow((tpl / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8"), pin, release)
        _write(root / ".gitlab" / "aidd.gitlab-ci.yml", text, force, actions)
        _write(root / ".gitlab" / "merge_request_templates" / "Default.md", pr_tpl, force, actions)
        actions.append("next     add `include: { local: .gitlab/aidd.gitlab-ci.yml }` to .gitlab-ci.yml")
    wire = agent_hooks if agent_hooks is not None else (claude and not claude_plugins)
    if wire:
        install_agent_hooks(root, actions)
    if team:
        install_team(root, actions, force, claude_files=not claude_plugins, harnesses=detected)
    for h in (HARNESSES[k] for k in detected):
        if h.pointer and (not h.only_if_present or (root / h.pointer).is_file()):
            _pointer(root / h.pointer, h.header, snippet, actions)
    gi = root / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if GITIGNORE_LINE not in text.splitlines():
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(("\n" if text and not text.endswith("\n") else "") + GITIGNORE_LINE + "\n")
        actions.append(f"updated  {_shown(gi)}")
    return actions


VERIFY_HEADING = "### Verifying your work"


def configured_tests(root: Path) -> list[list[str]]:
    """The `[[tests]]` commands of the repository's config as init left it: `--test`, or what an existing config already names."""
    try:
        raw = model.parse_toml((root / cfgmod.CONFIG_PATH).read_text(encoding="utf-8"), "config")
    except (OSError, UnicodeDecodeError, model.ModelError):
        return []
    tests = raw.get("tests")
    return [[str(a) for a in t["command"]] for t in tests if isinstance(t, dict) and isinstance(t.get("command"), list)] if isinstance(tests, list) else []


def verification_block(commands: list[list[str]]) -> str:
    """What "done" means: the commands to run and paste before reporting a task complete, as a `###` subsection of
    aidd's AGENTS.md section, so uninstall removes it with the rest."""
    steps = [f"`{shlex.join(c)}`: the repository's tests" for c in commands] or [
        "the repository's tests (none configured yet: add `[[tests]]` to `.aidd/config.toml`)"
    ]
    steps += ["`aidd test`: the Spec's tests, red on base and green on head", "`aidd gate`: the local preflight; only approvals may still be pending"]
    lines = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    return (
        f"{VERIFY_HEADING}\n\nBefore you report any task complete, run these and paste their output:\n\n{lines}\n\n"
        "`aidd test` and `aidd gate` find the Spec in the diff; name it with `--spec specs/<ID>.md`, or an inline block with `--body-file`. "
        "If a test fails, fix the code, not the test: never skip, weaken, or delete a failing test.\n"
    )


def _pointer(path: Path, header: str, snippet: str, actions: list[str]) -> None:
    """A harness-specific instruction file that carries the same marked section as AGENTS.md."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + snippet, encoding="utf-8")
        actions.append(f"wrote    {_shown(path)}")
    elif AGENTS_MARK not in path.read_text(encoding="utf-8"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n" + snippet)
        actions.append(f"appended {_shown(path)}")
    else:
        actions.append(f"kept     {_shown(path)} (already points at the skill)")


def install_claude_plugins(root: Path, actions: list[str], *, team: bool) -> bool:
    """Install the aidd plugins for this user through the Claude Code CLI (user scope), instead of repository files;
    whether every install ran, so init can fall back to repository wiring when one did not."""
    claude = shutil.which("claude")
    if claude is None:
        actions.append(
            "skipped  Claude Code plugins: no `claude` on PATH. In Claude Code run "
            f"/plugin marketplace add {MARKETPLACE_REPO}, then /plugin install aidd@{MARKETPLACE}"
            + (f" and /plugin install aidd-team@{MARKETPLACE}" if team else "")
        )
        return False
    commands = [[claude, "plugin", "marketplace", "add", MARKETPLACE_REPO], [claude, "plugin", "install", f"aidd@{MARKETPLACE}"]]
    if team:
        commands.append([claude, "plugin", "install", f"aidd-team@{MARKETPLACE}"])
    for cmd in commands:
        shown = " ".join(["claude", *cmd[1:]])
        try:
            r = PLUGIN_RUNNER(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(root))
        except (OSError, subprocess.TimeoutExpired) as exc:
            actions.append(f"failed   {shown}: {exc}; wiring the repository instead")
            return False
        output = (r.stderr or r.stdout or "").strip()
        if r.returncode != 0 and not (cmd[2] == "marketplace" and "already" in output.lower()):
            actions.append(f"failed   {shown}: {output.splitlines()[-1] if output else 'exit ' + str(r.returncode)}; wiring the repository instead")
            return False
        actions.append(f"ran      {shown}")
    return True


TEAM_MARK = "<!-- aidd-team -->"
TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`


def _team_text(text: str) -> str:
    """A plugin file as a project file: `aidd-team:<name>` becomes `aidd-<name>`, and the front matter's `name` gains the prefix.
    Project agents and skills are not namespaced by a plugin, so an unprefixed `code-review` or `developer` would
    collide with a built-in or a project's own agent, and the guard treats only `aidd-<role>` as a role.
    """
    text = text.replace("aidd-team:", TEAM_PREFIX)
    # The aidd skill is `aidd:aidd` in the plugin and the project skill `aidd` that `aidd init` vendors.
    text = text.replace(f"\n  - {docs.CORE_SKILL}\n", "\n  - aidd\n")
    if text.startswith("---\n"):
        end = text.index("\n---", 4)
        front = re.sub(r"^name: (?!aidd-)", f"name: {TEAM_PREFIX}", text[:end], count=1, flags=re.M)
        text = front + text[end:]
    return text


def _front_and_body(text: str) -> tuple[dict[str, str], str]:
    end = text.index("\n---", 4)
    front = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([\w-]+): (.*)$", line)
        if m:
            value = m.group(2).strip()
            front[m.group(1)] = json.loads(value) if value.startswith('"') else value
    return front, text[end + 4 :].lstrip("\n")


ADVISORY = (
    "Outside Claude Code this team is advisory: no hook checks this role's writes or stops an approval, so follow the "
    "write area and the loop contract below yourself; the `aidd/gate` check decides what merges."
)


def _native_agent(harness: str, name: str, front: dict[str, str], body: str, model: str | None = None) -> tuple[str, str]:
    """(path, text) of one role as `harness`'s own agent file, in the format its documentation gives (checked 2026-09-28).

    `model`, the role's `provider/model` from `[agents.models]`, goes into the harness's own model field when it can
    run it (`agentmodels`); otherwise the file says why the harness's default runs instead."""
    tools = {t.strip() for t in front.get("tools", "").split(",") if t.strip()}
    writes, shell = bool(tools & {"Write", "Edit"}), "Bash" in tools
    desc = front["description"]
    prompt = ADVISORY + "\n\n" + body
    value = agentmodels.harness_model(harness, model) if model else None
    note = agentmodels.unsupported_note(model) if model and not value else None
    if harness == "codex":  # .codex/agents/<name>.toml: name, description, developer_instructions, and `model`
        lines = [f"name = {json.dumps(name)}", f"description = {json.dumps(desc)}"]
        if value:
            lines.append(f"model = {json.dumps(value)}")
        if note:
            lines.append(f"# {note}")
        if not writes and not shell:
            lines.append('sandbox_mode = "read-only"')
        lines.append(f"developer_instructions = {json.dumps(prompt, ensure_ascii=False)}")
        return f".codex/agents/{name}.toml", "\n".join(lines) + "\n"
    extra = (f"model: {value}\n" if value else "") + (f"# {note}\n" if note else "")
    if harness == "copilot":  # .github/agents/<name>.agent.md: YAML front matter (description required), body is the prompt
        return f".github/agents/{name}.agent.md", f"---\nname: {name}\ndescription: {json.dumps(desc)}\n{extra}---\n\n{prompt}"
    if harness == "opencode":  # .opencode/agents/<name>.md: description, mode, model, permission; the file name is the agent name
        perms = f"  edit: {'allow' if writes else 'deny'}\n  bash: {'ask' if shell else 'deny'}"
        return f".opencode/agents/{name}.md", f"---\ndescription: {json.dumps(desc)}\nmode: subagent\n{extra}permission:\n{perms}\n---\n\n{prompt}"
    if harness == "kiro":  # .kiro/agents/<name>.json: name, description, prompt, tools, and `model`
        kiro_tools = ["read"] + (["write"] if writes else []) + (["shell"] if shell else [])
        data: dict = {"name": name, "description": desc, "prompt": prompt, "tools": kiro_tools}
        if value:
            data["model"] = value
        return f".kiro/agents/{name}.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    raise KeyError(harness)


def _claude_agent(text: str, model: str | None) -> str:
    """A Claude Code agent file with the role's configured model in its `model:` field, or a note when the configured
    model is not Claude's, in which case the tier's value stays."""
    if not model:
        return text
    value = agentmodels.harness_model("claude-code", model)
    line = f"model: {value}" if value else r"\g<0>\n# " + agentmodels.unsupported_note(model)
    return re.sub(r"^model: .*$", line, text, count=1, flags=re.M)


def configured_models(root: Path) -> dict[str, str]:
    """`[agents.models]` from the repository's config: tier or role name to `provider/model`; empty without a config."""
    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
    except (OSError, cfgmod.ConfigError, model.ModelError, RuntimeError):
        return {}
    return dict(cfg.get("agents", "models", default={}) or {})


NATIVE_AGENT_HARNESSES = ("codex", "copilot", "opencode", "kiro")


def team_files(harnesses: list[str], claude_files: bool = True, models: dict[str, str] | None = None) -> dict[str, str]:
    """Every file `aidd init --team` writes, by repository path: what install writes and uninstall compares against.

    `models` is `[agents.models]`; each role's resolved model goes into each harness's own model field."""
    team = resources.data_dir("team")
    out: dict[str, str] = {}
    agents = sorted((team / "agents").glob("*.md"))
    chosen = {src.stem: agentmodels.resolve(models or {}, src.stem) for src in agents}
    if claude_files:
        for src in agents:
            out[f".claude/agents/{TEAM_PREFIX}{src.name}"] = _claude_agent(_team_text(src.read_text(encoding="utf-8")), chosen[src.stem])
        for pack in sorted(p for p in (team / "skills").glob("*/SKILL.md") if p.parent.name != "aidd-team"):
            out[f".claude/skills/{TEAM_PREFIX}{pack.parent.name}/SKILL.md"] = _team_text(pack.read_text(encoding="utf-8"))
        for src in sorted((team / "commands").glob("*.md")):
            out[f".claude/commands/{TEAM_PREFIX}{src.name}"] = _team_text(src.read_text(encoding="utf-8"))
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        for src in agents:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
            path, text = _native_agent(h, front["name"], front, body, chosen[src.stem])
            out[path] = text
    return out


def team_section(harnesses: list[str], claude_files: bool = True) -> str:
    """The short AGENTS.md section: where the role files are, that the team is advisory outside Claude Code, and one row per role."""
    roles = resources.roles()
    claude = f"`.claude/agents/{TEAM_PREFIX}<role>.md` (Claude Code; plain Markdown any agent can read)"
    where = [claude if claude_files else "the aidd-team plugin (`aidd-team:<role>`) for Claude Code"]
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        path, _ = _native_agent(h, f"{TEAM_PREFIX}<role>", {"description": ""}, "")
        where.append(f"`{path}` ({HARNESSES[h].label})")
    lines = [
        TEAM_MARK,
        "## Team roles (aidd-team)",
        "",
        "The aidd-team roles are agent files, one per role: " + "; ".join(where) + ". "
        "When you are asked to act as a role, read its file first and follow its playbook and loop contract; "
        "write only its area and hand off everything else. No role approves, merges, or chooses the route.",
        "",
        "Outside Claude Code the team is advisory: no hook checks a role's writes or stops an approval, so each role "
        "only follows its instructions, and the `aidd/gate` check decides what merges.",
        "",
        "| Role | Loop steps | Writes |",
        "| --- | --- | --- |",
    ]
    for key in roles["order"]:
        r = roles["roles"][key]
        lines.append(f"| `{TEAM_PREFIX}{key}` | {docs.role_loop(r)} | {docs.role_writes(r['writes'])} |")
    return "\n".join(lines) + "\n"


def install_team(root: Path, actions: list[str], force: bool = False, claude_files: bool = True, harnesses: list[str] | None = None) -> None:
    """The aidd-team roles without the plugin: Claude Code project agents, commands, domain packs, and practice skills
    named `aidd-<name>`; the roles as native agent files for Codex, Copilot, OpenCode, and Kiro when they are in use; and a
    short AGENTS.md section that points at them."""
    wanted = list(harnesses or [])
    for rel, text in team_files(wanted, claude_files, configured_models(root)).items():
        _write(root / rel, text, force, actions)
    agents = root / "AGENTS.md"
    current = agents.read_text(encoding="utf-8") if agents.exists() else "# Agents\n"
    if TEAM_MARK in current:
        actions.append(f"kept     {_shown(agents)} (already has the team section)")
        return
    with open(agents, "w", encoding="utf-8") as fh:
        fh.write(current.rstrip("\n") + "\n\n" + team_section(wanted, claude_files))
    actions.append(f"updated  {_shown(agents)} (team roles)")


def _resolve_pin(ref: str | None) -> tuple[str | None, str | None, str]:
    """(pin, release, why) for the CI files: `ref`, else the commit this aidd runs from, else (an installed wheel) the
    commit the release tag names, so CI does not follow a tag that can move; None offline."""
    if ref:
        return ref, None, ""
    if pin := installed_ref():
        return pin, None, " (the commit this aidd runs from; make sure it is on GitHub)"
    pin = release_commit()
    return pin, __version__ if pin else None, f" (the commit of release v{__version__})"


def repin(text: str, ref: str, release: str | None = None, *, pattern: re.Pattern = _ANY_PIN) -> str:
    """Every aidd ref in a CI file that `pattern` finds (by default any: a tag, a commit, or a commit with its label
    comment) set to `ref`. A commit gets its `pin_label`; the GitLab pin never does, because it sits inside a shell string."""
    comment = pin_label(ref, release)
    text = _GITLAB_PIN.sub(lambda m: m.group(1) + ref + m.group(2), text)  # first: no comment inside the shell string
    text = _CHECKOUT_PIN.sub(lambda m: m.group(1) + ref + comment, text)
    return pattern.sub(lambda m: f"{m.group(1)}@{ref}{comment}", text)


def upgrade(root: Path, *, ref: str | None = None, yes: bool = False) -> list[str]:
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill, the team files already installed, the
    aidd refs in CI files, and the config's `aidd_version`. Everything else stays as you left it: your config, REVIEW.md,
    AGENTS.md, and your own steps in the CI files. A dry run unless `yes`."""
    pin, release, _ = _resolve_pin(ref)
    ref = pin or f"v{__version__}"  # offline, without a checkout: the release tag itself
    if not _REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    verb = "updated " if yes else "would update"
    actions: list[str] = []

    def put(path: Path, text: str, why: str) -> None:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return
        actions.append(f"{verb if path.exists() else ('added   ' if yes else 'would add')} {_shown(path)} ({why})")
        if yes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    skill = root / SKILL_REL
    if skill.is_dir() and not skill.is_symlink() and _tree_diff(resources.data_dir("skill"), skill):
        actions.append(f"{verb} {_shown(skill)} (the skill, to aidd {__version__})")
        if yes:
            vendor_skill(root, True, [])
    everything = team_files(list(NATIVE_AGENT_HARNESSES), True)
    installed = [rel for rel in everything if (root / rel).is_file()]
    if installed:
        claude = any(rel.startswith(".claude/") for rel in installed)
        harnesses = [h for h in NATIVE_AGENT_HARNESSES if any(rel in team_files([h], False) for rel in installed)]
        wanted = team_files(harnesses, claude, configured_models(root))
        for rel, text in wanted.items():
            put(root / rel, text, "the delivery team")
        for d in (".claude/agents", ".claude/commands", ".claude/skills"):
            for stale in sorted((root / d).glob(f"{TEAM_PREFIX}*")) if (root / d).is_dir() else []:
                rel = str(stale.relative_to(root)) + ("/SKILL.md" if stale.is_dir() else "")
                if rel not in wanted:
                    actions.append(f"no longer shipped: {_shown(stale)} (remove it if nothing else uses it)")
    for ci in sorted((root / ".github" / "workflows").glob("*.y*ml")) + [root / ".gitlab-ci.yml", root / ".gitlab" / "aidd.gitlab-ci.yml"]:
        if ci.is_file():
            text = ci.read_text(encoding="utf-8")
            if "thaithienvanid/aidd" in text:
                put(ci, repin(text, ref, release), f"aidd pinned at {ref}")
    cfg = root / cfgmod.CONFIG_PATH
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8")
        put(cfg, re.sub(r'^aidd_version = "[^"]*"', f'aidd_version = "{__version__}"', text, count=1, flags=re.M), f"aidd_version {__version__}")
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


# The directories init may create, which uninstall removes once they are empty.
INIT_DIRS = (
    ".aidd specs .claude/commands .codex/agents .codex .github/agents .opencode/agents .opencode .kiro/agents .kiro .claude/agents .claude/skills "
    ".claude .agents/skills .agents .gitlab/merge_request_templates .gitlab .github/workflows .github .continue/rules .continue"
).split()


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
        actions.append(f"{verb} {_shown(path)}" + (f" ({note})" if note else ""))
        if not yes:
            return
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def keep(path: Path, why: str) -> None:
        actions.append(f"kept     {_shown(path)} ({why})")

    def remove_if(path: Path, unchanged: bool, why: str = "changed since init") -> None:
        if unchanged:
            remove(path)
        elif path.is_file():
            keep(path, why)

    def template(*parts: str) -> str:
        return tpl.joinpath(*parts).read_text(encoding="utf-8")

    cfg = root / cfgmod.CONFIG_PATH
    if cfg.is_file():
        try:
            raw = model.parse_toml(cfg.read_text(encoding="utf-8"), "config")
            owners, tests, pol = raw.get("owners") or {}, raw.get("tests", []), (raw.get("policy") or {}).get("command")
            t_cmd = tests[0].get("command") if tests and isinstance(tests, list) and isinstance(tests[0], dict) else None
            appr, rev = owners.get("approvers", []), owners.get("reviewers")
            expected = config_text(
                raw.get("profile", "solo"), approvers=appr, reviewers=rev, test=t_cmd, policy=pol, mode=raw.get("mode"), goal=raw.get("goal")
            )
            unmodified = same(cfg, expected)
        except Exception:
            unmodified = False
        remove_if(cfg, unmodified)
    remove_if(root / "specs" / "README.md", same(root / "specs" / "README.md", template("specs-README.md")))
    remove_if(root / REVIEW_POLICY, same(root / REVIEW_POLICY, template(REVIEW_POLICY)), "the repository's review policy, changed since init")
    skill = root / SKILL_REL
    if skill.exists() and skill.resolve() != bundled_skill.resolve():
        remove(skill) if skill.is_symlink() or not _tree_diff(bundled_skill, skill) else keep(skill, "changed since init")
    for d in list(DEFAULT_LINKS) + list(links or []):
        link = root / d / "aidd"
        if link.is_symlink():
            remove(link)
        elif link.is_dir():
            remove(link, "a copy of the skill") if not _tree_diff(bundled_skill, link) else keep(link, "changed since init")
    for name in DEVCONTAINER_FILES:  # what `aidd init --devcontainer` wrote
        remove_if(root / ".devcontainer" / name, same(root / ".devcontainer" / name, template("devcontainer", name)))
    for rel, text in team_files(list(NATIVE_AGENT_HARNESSES), True, configured_models(root)).items():  # what install_team wrote
        remove_if(root / rel, same(root / rel, text))
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            data = None
            keep(settings, "not valid JSON; remove the aidd hook by hand")
        ours = {("PreToolUse", "pre-edit"), *SESSION_EVENTS.items()}
        hooks = data.get("hooks", {}) if data else {}
        kept = {
            event: [e for e in entries if not any((event, aidd_hook(h.get("command"))) in ours for h in e.get("hooks", []))]
            for event, entries in hooks.items()
            if isinstance(entries, list)
        }
        removed = [event for event, entries in kept.items() if len(entries) != len(hooks[event])]
        if removed:
            actions.append(f"{verb} the aidd hooks ({', '.join(removed)}) from {_shown(settings)}")
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
            actions.append(f"{verb} the aidd server from {_shown(mcp_file)}")
            if yes:
                del data["mcpServers"]["aidd"]
                if not data["mcpServers"]:
                    del data["mcpServers"]
                _dump_or_unlink(mcp_file, data)

    def ci_same(path: Path, *parts: str) -> bool:  # compared with the pin taken out; the gate workflow may be advisory
        text = unpinned(template(*parts))
        allowed = {text, re.sub(r"(mode:\s*)enforce", r"\1advisory", text, count=1)} if parts[-1] == "aidd-gate.yml" else {text}
        return path.is_file() and unpinned(path.read_text(encoding="utf-8")) in allowed

    for name in GITHUB_WORKFLOWS:
        remove_if(root / ".github" / "workflows" / name, ci_same(root / ".github" / "workflows" / name, "github", name))
    pr_tpl = template("github", "pull_request_template.md")
    for path in (root / ".github" / "pull_request_template.md", root / ".gitlab" / "merge_request_templates" / "Default.md"):
        remove_if(path, same(path, pr_tpl))
    remove_if(root / ".gitlab" / "aidd.gitlab-ci.yml", ci_same(root / ".gitlab" / "aidd.gitlab-ci.yml", "gitlab", "aidd.gitlab-ci.yml"))
    gi = root / ".gitignore"
    if gi.is_file():
        lines = gi.read_text(encoding="utf-8").splitlines()
        if GITIGNORE_LINE in lines:
            actions.append(f"{verb} the aidd line from {_shown(gi)}")
            if yes:
                rest = [x for x in lines if x != GITIGNORE_LINE]
                if any(x.strip() for x in rest):
                    gi.write_text("\n".join(rest).rstrip("\n") + "\n", encoding="utf-8")
                else:
                    gi.unlink()
    for rel, header in pointer_files():
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if AGENTS_MARK not in text and TEAM_MARK not in text:
            continue
        stripped = strip_marked_section(strip_marked_section(text, TEAM_MARK), AGENTS_MARK)
        if stripped.strip() in ("", header):
            remove(path)
        else:
            actions.append(f"{verb} the aidd sections from {_shown(path)}")
            if yes:
                path.write_text(stripped, encoding="utf-8")
    if yes:
        # Directories init created, emptied by the removals above: deepest first, so a parent empties before its turn.
        candidates = [root / d for d in INIT_DIRS] + [q for q in (root / ".claude" / "skills").glob("*") if q.is_dir()]
        for empty in sorted(candidates, key=lambda q: -len(q.parts)):
            if empty.is_dir() and not empty.is_symlink() and not any(empty.iterdir()):
                empty.rmdir()
    if not yes:
        actions.append("dry run: nothing was removed; run `aidd uninstall --yes` to remove the items above")
    actions.append(
        "then: drop `aidd/gate` from the branch ruleset, uninstall the gate App, delete the `aidd-gate` environment; "
        f"Claude Code plugin users run `claude plugin uninstall aidd@{MARKETPLACE}` (and `aidd-team@{MARKETPLACE}`)"
    )
    return actions


HOOK_COMMAND = "aidd hook pre-edit"  # the bare form, written when `aidd` is on PATH; every form ends with it
# The same tools the aidd plugin's hooks/hooks.json matches: the edits, Bash and PowerShell for the shell check, and every
# MCP tool (the guard denies only those that merge, approve, or set a commit status).
HOOK_MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*"
# The session hooks: advisory helpers, so each fails open (`|| true`, `; exit 0` in PowerShell): an aidd too old to know the hook, or missing,
# never blocks a session or a stop. `aidd hook stop` at level strict blocks through its JSON decision, which Claude
# Code reads on exit 0. PreCompact is not wired: its output cannot add context (see aidd.hooks).
SESSION_EVENTS = {"SessionStart": "session-start", "Stop": "stop", "SubagentStop": "stop"}
# On Windows, Claude Code runs a hook command in Git Bash when it is installed and in PowerShell otherwise, so init
# names the shell: PowerShell, which every Windows machine has. Its syntax differs: `$env:NAME = '...';` sets the
# environment, `&` calls a quoted program, and `; exit 0` fails open (Windows PowerShell 5.1 has no `||`).
WINDOWS_HOOK_SHELL = "powershell"
_FAIL_OPEN = {"sh": " || true", "powershell": "; exit 0"}


def _hook_shell() -> str:
    return WINDOWS_HOOK_SHELL if os.name == "nt" else "sh"


# The commands with the bare launcher, `aidd` on PATH.
SESSION_HOOKS = {event: f"aidd hook {sub}{_FAIL_OPEN[_hook_shell()]}" for event, sub in SESSION_EVENTS.items()}
SESSION_HOOK_TIMEOUT = 10
_AIDD_HOOK = re.compile(r"(?<![\w-])aidd hook (pre-edit|session-start|stop)(?![\w-])")


def aidd_hook(command) -> str | None:
    """Which aidd hook a settings command runs (`pre-edit`, `session-start`, `stop`), whatever launcher it names; else None."""
    m = _AIDD_HOOK.search(command) if isinstance(command, str) else None
    return m.group(1) if m else None


def _on_default_path(directory: str) -> bool:
    """Whether a fresh interpreter imports from `directory` without PYTHONPATH: a site-packages directory."""
    import site

    dirs = list(site.getsitepackages()) + [site.getusersitepackages()]
    return any(Path(d).resolve() == Path(directory).resolve() for d in dirs if d)


def launcher() -> tuple[list[str], dict[str, str]]:
    """How a hook or the MCP server starts this aidd, resolved when init runs: `aidd` when it is on PATH; otherwise this
    interpreter with `-m aidd`, and PYTHONPATH naming the source it runs from when that is not installed (the
    pre-release install from a checkout). (argv, extra environment)."""
    if shutil.which("aidd"):
        return ["aidd"], {}
    src = str(Path(__file__).resolve().parent.parent)
    python = os.path.normpath(os.path.abspath(sys.executable))  # never resolved: a venv's python is a link into it
    return [python, "-m", "aidd"], ({} if _on_default_path(src) else {"PYTHONPATH": src})


def _ps_quote(word: str) -> str:
    """A PowerShell single-quoted string: literal, backslashes included; a quote doubles."""
    return "'" + word.replace("'", "''") + "'"


def _shell_launcher(argv: list[str], env: dict[str, str], shell: str = "sh") -> str:
    if shell == WINDOWS_HOOK_SHELL:
        words = [a if shlex.quote(a) == a else _ps_quote(a) for a in argv]  # quoted where sh would quote it too
        call = ("& " if words[0].startswith("'") else "") + " ".join(words)
        return "".join(f"$env:{k} = {_ps_quote(v)}; " for k, v in env.items()) + call
    return " ".join([f"{k}={shlex.quote(v)}" for k, v in env.items()] + [shlex.quote(a) for a in argv])


def hook_command(sub: str, resolved: tuple[list[str], dict[str, str]] | None = None, shell: str | None = None) -> str:
    """The settings command for one aidd hook, in the syntax of the shell Claude Code runs it with (PowerShell on
    Windows, see WINDOWS_HOOK_SHELL); the session hooks fail open."""
    argv, env = resolved or launcher()
    shell = shell or _hook_shell()
    return f"{_shell_launcher(argv, env, shell)} hook {sub}" + ("" if sub == "pre-edit" else _FAIL_OPEN[shell])


def _hook_entry(command: str, timeout: int) -> dict:
    """A settings hook entry; on Windows it names the shell its command is written for."""
    return _rewire({"type": "command", "command": "", "timeout": timeout}, command)


def _rewire(hook: dict, command: str) -> dict:
    """Point a settings hook entry at `command`, naming the shell on Windows and dropping one that no longer applies."""
    hook["command"] = command
    if _hook_shell() == WINDOWS_HOOK_SHELL:
        hook["shell"] = WINDOWS_HOOK_SHELL
    else:
        hook.pop("shell", None)
    return hook


def mcp_server(resolved: tuple[list[str], dict[str, str]] | None = None) -> dict:
    """The .mcp.json entry that starts `aidd mcp`."""
    argv, env = resolved or launcher()
    entry: dict = {"command": argv[0], "args": [*argv[1:], "mcp"]}
    if env:
        entry["env"] = dict(env)
    return entry


_PS_ENV = re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*'((?:[^']|'')*)'[ \t]*;[ \t]*")
_PS_WORD = re.compile(r"'((?:[^']|'')*)'|([^\s']+)")


def _hook_words(command: str) -> tuple[list[str], dict[str, str]] | None:
    """A hook command as (argv, environment), in either syntax init writes: POSIX sh (`NAME=value 'prog' ... || true`)
    or PowerShell (`$env:NAME = 'value'; & 'prog' ...; exit 0`). None when it does not parse. On Windows a backslash
    is a path separator, never an escape, in both."""
    text, env = command.strip(), {}
    if text.startswith(("&", "$env:")) or re.search(r";[ \t]*exit[ \t]+0[ \t]*$", text):
        while m := _PS_ENV.match(text):
            env[m.group(1)] = m.group(2).replace("''", "'")
            text = text[m.end() :]
        text = re.sub(r";[ \t]*exit[ \t]+0[ \t]*$", "", text).removeprefix("&").strip()
        return [m.group(1).replace("''", "'") if m.group(1) is not None else m.group(2) for m in _PS_WORD.finditer(text)], env
    try:
        words = util.split_command(re.sub(r"[ \t]*\|\|[ \t]*true[ \t]*$", "", text))
    except ValueError:
        return None
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        k, _, v = words.pop(0).partition("=")
        env[k] = v
    return words, env


def _command_program(command: str) -> str | None:
    """The program a hook command starts, after any environment it sets."""
    parsed = _hook_words(command)
    return parsed[0][0] if parsed and parsed[0] else None


def _resolves(program: str | None) -> bool:
    return bool(program) and shutil.which(program) is not None  # type: ignore[arg-type]


def session_hooks_missing(settings: Path) -> list[str]:
    """The SESSION_EVENTS a Claude Code settings file does not wire, with whatever launcher."""
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError):
        return list(SESSION_EVENTS)
    return [
        event
        for event, sub in SESSION_EVENTS.items()
        if not any(aidd_hook(h.get("command")) == sub for e in hooks.get(event, []) or [] if isinstance(e, dict) for h in e.get("hooks", []) or [])
    ]


def plugin_enabled(root: Path) -> bool:
    """The aidd Claude Code plugin is enabled for this project (`enabledPlugins` in .claude/settings.json or
    settings.local.json names `aidd@aidd`): its hooks/hooks.json then carries the session hooks itself."""
    for name in ("settings.json", "settings.local.json"):
        try:
            enabled = json.loads((root / ".claude" / name).read_text(encoding="utf-8")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(enabled, dict) and enabled.get(f"aidd@{MARKETPLACE}") is True:
            return True
    return False


def session_hooks_wired(settings: Path) -> list[str]:
    """The SESSION_EVENTS a Claude Code settings file wires."""
    missing = session_hooks_missing(settings)
    return [event for event in SESSION_EVENTS if event not in missing]


def install_agent_hooks(root: Path, actions: list[str]) -> None:
    """Claude Code: the edit-time guard as a PreToolUse hook, and `aidd mcp` as a project MCP server. Both start aidd through `launcher()`, resolved now: `aidd` on PATH, or this interpreter with `-m aidd`. Both files
    are merged, never overwritten; an aidd entry whose program does not resolve on this machine is repaired. The
    plugin ships the same wiring for plugin users; when the project enables the aidd plugin, the session hooks are
    left to it, so they do not run twice.
    """
    resolved = launcher()
    pre_command = hook_command("pre-edit", resolved)
    settings = root / ".claude" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except ValueError:
        actions.append(f"kept     {_shown(settings)} (not valid JSON; add the aidd hook by hand)")
        data = None
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", []) if data is not None else None
    ours = [entry for entry in pre or [] if any(aidd_hook(h.get("command")) == "pre-edit" for h in entry.get("hooks", []))]
    changed = False
    if pre is not None and ours:
        notes = []
        if not all(entry.get("matcher") == HOOK_MATCHER for entry in ours):
            # An older init matched fewer tools (edits only, or no PowerShell and MCP tools).
            for entry in ours:
                entry["matcher"] = HOOK_MATCHER
            notes.append("the aidd hook now matches every tool it checks")
        for h in (h for entry in ours for h in entry.get("hooks", []) if aidd_hook(h.get("command")) == "pre-edit"):
            if not _resolves(_command_program(h["command"])):
                _rewire(h, pre_command)
                notes.append(f"the aidd hook's launcher did not resolve here; it runs {pre_command}")
        if notes:
            changed = True
            actions.append(f"updated  {_shown(settings)} ({'; '.join(dict.fromkeys(notes))})")
        else:
            actions.append(f"kept     {_shown(settings)} (the aidd hook is there)")
    elif pre is not None:
        pre.append({"matcher": HOOK_MATCHER, "hooks": [_hook_entry(pre_command, 20)]})
        changed = True
        actions.append(f"updated  {_shown(settings)} (PreToolUse: {pre_command})")
    if data is not None and plugin_enabled(root):
        actions.append(f"kept     {_shown(settings)} (the aidd plugin is enabled and runs the session hooks; they are not added twice)")
    elif data is not None:
        added = []
        for event, sub in SESSION_EVENTS.items():
            entries = data["hooks"].setdefault(event, [])
            mine = [h for e in entries for h in e.get("hooks", []) if aidd_hook(h.get("command")) == sub]
            if not mine:
                entries.append({"hooks": [_hook_entry(hook_command(sub, resolved), SESSION_HOOK_TIMEOUT)]})
                added.append(event)
            for h in mine:
                if not _resolves(_command_program(h["command"])):
                    _rewire(h, hook_command(sub, resolved))
                    added.append(event)
        if added:
            changed = True
            actions.append(f"updated  {_shown(settings)} ({', '.join(dict.fromkeys(added))}: the aidd session hooks)")
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    mcp_file = root / ".mcp.json"
    try:
        data = json.loads(mcp_file.read_text(encoding="utf-8")) if mcp_file.exists() else {}
    except ValueError:
        actions.append(f"kept     {_shown(mcp_file)} (not valid JSON; add the aidd server by hand)")
        return
    servers = data.setdefault("mcpServers", {})
    current = servers.get("aidd")
    if isinstance(current, dict) and _resolves(current.get("command")):
        actions.append(f"kept     {_shown(mcp_file)} (the aidd server is there)")
        return
    servers["aidd"] = mcp_server(resolved)
    mcp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    shown = " ".join([*resolved[0], "mcp"])
    actions.append(f"updated  {_shown(mcp_file)} (MCP server: {shown}" + (", its launcher did not resolve here)" if current else ")"))


# A harmless event for the edit-time hook: a Read, which the guard never decides on.
_PROBE_EVENT = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "README.md"}}
_MCP_PROBE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}


def _launch_shape(root: Path, words: list[str], env: dict[str, str], tail: list[str]) -> str | None:
    """Why doctor will not run this launcher, or None when it has the shape init writes: `aidd <tail>`, or a Python
    with `-m aidd <tail>` and at most PYTHONPATH, every path outside the repository. `aidd doctor` runs it, so a
    command the repository chose (a file inside it, another program) never runs."""
    if set(env) - {"PYTHONPATH"}:
        return f"it sets {', '.join(sorted(set(env) - {'PYTHONPATH'}))}"
    top = root.resolve()
    paths = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not words:
        return "it names no program"
    program, name = words[0], Path(words[0]).name
    python = re.fullmatch(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?", name) and words[1:] == ["-m", "aidd", *tail]
    if not python and not (name in ("aidd", "aidd.exe") and words[1:] == tail):
        return "it is not an aidd launcher that init writes"
    if os.path.isabs(program):
        paths.append(program)
    for p in paths:
        q = Path(p) if os.path.isabs(p) else root / p
        if q.resolve().is_relative_to(top):
            return f"{p} is inside the repository"
    return None


def _parse_hook(command: str, sub: str) -> tuple[list[str], dict[str, str]] | None:
    parsed = _hook_words(command)
    return parsed if parsed and parsed[0][-2:] == ["hook", sub] else None


def _run_probe(root: Path, words: list[str], env: dict[str, str], stdin: str, timeout: int) -> subprocess.CompletedProcess[str] | str:
    """Run a launcher once with `stdin`: the finished process, or why it could not run."""
    if not _resolves(words[0]):
        return f"{words[0]} is not found on PATH"
    try:
        return subprocess.run(
            words, input=stdin, env={**os.environ, **env}, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def run_hook_probe(root: Path, command: str, timeout: int = 20) -> str | None:
    """Run the configured edit-time hook command once with a harmless event; None when it runs, else why not."""
    parsed = _parse_hook(command, "pre-edit")
    if parsed is None:
        return "it does not parse as an aidd hook command"
    words, env = parsed
    why = _launch_shape(root, words, env, ["hook", "pre-edit"])
    if why:
        return f"not run: {why}"
    r = _run_probe(root, words, env, json.dumps({**_PROBE_EVENT, "cwd": str(root)}), timeout)
    if isinstance(r, str):
        return r
    if r.returncode != 0:
        last = (r.stderr or r.stdout).strip().splitlines()
        return f"exit {r.returncode}" + (f": {last[-1]}" if last else "")
    return None


def run_mcp_probe(root: Path, server: dict, timeout: int = 20) -> str | None:
    """Start the configured MCP server and send `initialize`; None when aidd answers, else why not."""
    command, args, env = server.get("command"), server.get("args") or [], server.get("env") or {}
    if not isinstance(command, str) or not isinstance(args, list) or not isinstance(env, dict):
        return "the entry is not a command with args"
    words, env = [command, *map(str, args)], {str(k): str(v) for k, v in env.items()}
    why = _launch_shape(root, words, env, ["mcp"])
    if why:
        return f"not run: {why}"
    r = _run_probe(root, words, env, json.dumps(_MCP_PROBE) + "\n", timeout)
    if isinstance(r, str):
        return r
    try:
        answer = json.loads(r.stdout.splitlines()[0])
        if answer["result"]["serverInfo"]["name"] == "aidd":
            return None
    except (IndexError, ValueError, KeyError, TypeError):
        pass
    last = (r.stderr or r.stdout).strip().splitlines()
    return f"exit {r.returncode}, no MCP answer" + (f": {last[-1]}" if last else "")


def claude_wiring_checks(root: Path, *, execute: bool) -> list[tuple[str, str]]:
    """Claude Code's repository wiring: the edit-time hook and the MCP server are configured, their launchers resolve on
    this machine, and, with `execute` (`aidd doctor`), each one actually starts. A wiring that cannot run is a failure:
    the guard would silently not guard."""
    label = HARNESSES["claude-code"].label
    fix = "`aidd init --agent-hooks` repairs a launcher that does not resolve (it runs `aidd` from PATH, or this Python with `-m aidd`)"
    out: list[tuple[str, str]] = []
    settings = root / ".claude" / "settings.json"
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {}) if settings.is_file() else {}
    except (ValueError, AttributeError):
        hooks = {}
    pre = [
        h["command"]
        for e in (hooks.get("PreToolUse") or [] if isinstance(hooks, dict) else [])
        if isinstance(e, dict)
        for h in e.get("hooks", []) or []
        if isinstance(h, dict) and aidd_hook(h.get("command")) == "pre-edit"
    ]
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {}) if (root / ".mcp.json").is_file() else {}
    except (ValueError, AttributeError):
        servers = {}
    server = servers.get("aidd") if isinstance(servers, dict) else None
    plugin = plugin_enabled(root)
    by_plugin = ("ok", f"{label}: the aidd plugin is enabled; it carries the edit-time hook, the session hooks, and the MCP server")
    if not pre and not isinstance(server, dict):
        unwired = f"{label} is in use, but the edit-time hook and the MCP server are not wired: `aidd init --agent-hooks`, or install the aidd plugin"
        return [by_plugin if plugin else ("warn", unwired)]
    broken, missing = [], []
    for command in pre:
        parsed = _parse_hook(command, "pre-edit")
        # A launcher doctor will not run (one inside the repository) is refused before PATH is asked: whether it
        # resolves differs by OS (Windows finds no file without an extension), and the answer is the same either way.
        refused = parsed and _launch_shape(root, *parsed, ["hook", "pre-edit"])
        if execute and refused:
            broken.append(f"the edit-time hook `{command}` does not run (not run: {refused})")
        elif not _resolves(_command_program(command)):
            broken.append(f"the edit-time hook `{command}` names a program not found here")
        elif execute and (why := run_hook_probe(root, command)):
            broken.append(f"the edit-time hook `{command}` does not run ({why})")
    if not isinstance(server, dict):
        missing.append("the MCP server is not in .mcp.json")
    elif not _resolves(server.get("command")):
        broken.append(f"the MCP server's command {server.get('command')!r} is not found here")
    elif execute and (why := run_mcp_probe(root, server)):
        broken.append(f"the MCP server does not start ({why})")
    if not pre:
        missing.insert(0, "the edit-time hook is not wired")
    if broken:
        out.append(("fail", f"{label}: " + "; ".join(broken) + f"; {fix}"))
    if missing and not plugin:
        out.append(("warn", f"{label}: " + "; ".join(missing) + ": `aidd init --agent-hooks`, or install the aidd plugin"))
    if not broken and not missing:
        out.append(("ok", f"{label}: the edit-time hook and the MCP server are wired" + (", and both start" if execute else "")))
    elif not broken and plugin:
        out.append(by_plugin)
    return out


def _tree_diff(a: Path, b: Path) -> list[str]:
    cmp = filecmp.dircmp(a, b, ignore=filecmp.DEFAULT_IGNORES + [".DS_Store", "Thumbs.db"])
    out = [f"only in bundled: {x}" for x in cmp.left_only] + [f"only in repo: {x}" for x in cmp.right_only]
    out += [f"differs: {x}" for x in cmp.diff_files]
    for sub in cmp.common_dirs:
        out += [f"{sub}/{x}" for x in _tree_diff(a / sub, b / sub)]
    return out


# Where Claude Code reads an organization's managed settings, from its "Deploy managed settings" page (checked
# 2026-09-28): the system directory holding managed-settings.json and managed-settings.d/, per OS. The macOS MDM
# profile lands in the managed preferences domain com.anthropic.claudecode, which macOS stores under
# /Library/Managed Preferences/ (an OS convention, not a path the page names). Windows also reads the HKLM
# registry value, and server-managed settings from the claude.ai console leave a cache in ~/.claude/.
MANAGED_SETTINGS_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": r"C:\Program Files\ClaudeCode",
}
MANAGED_PLIST = "/Library/Managed Preferences/com.anthropic.claudecode.plist"
SERVER_MANAGED_CACHE = ".claude/remote-settings.json"
MANAGED_SETTINGS_TEMPLATE = "templates/claude/managed-settings.json"


def managed_settings_sources(platform: str | None = None, home: Path | None = None) -> list[str]:
    """The Claude Code managed settings this machine carries: a file, a drop-in, an MDM profile, the HKLM
    registry value, or the server-managed cache. Presence only: `/status` in Claude Code says which one applies."""
    platform = platform or sys.platform
    home = home if home is not None else Path.home()
    found: list[str] = []
    key = "linux" if platform.startswith("linux") else platform
    if base := MANAGED_SETTINGS_DIRS.get(key):
        d = Path(base)
        if (d / "managed-settings.json").is_file():
            found.append(str(d / "managed-settings.json"))
        if (d / "managed-settings.d").is_dir() and any((d / "managed-settings.d").glob("*.json")):
            found.append(str(d / "managed-settings.d"))
    if key == "darwin" and Path(MANAGED_PLIST).is_file():
        found.append(MANAGED_PLIST)
    if key == "win32":
        try:
            import winreg  # type: ignore[import-not-found,unused-ignore]

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\ClaudeCode") as k:  # type: ignore[attr-defined,unused-ignore]
                if winreg.QueryValueEx(k, "Settings")[0]:  # type: ignore[attr-defined,unused-ignore]
                    found.append(r"HKLM\SOFTWARE\Policies\ClaudeCode\Settings")
        except (ImportError, OSError):
            pass
    if (home / SERVER_MANAGED_CACHE).is_file():
        found.append(str(home / SERVER_MANAGED_CACHE))
    return found


def house_standard_checks(root: Path, cfg: cfgmod.Config) -> list[tuple[str, str]]:
    """Each `[[standards]]` entry must name a document that exists, roles the team has, and tests the suite runs."""
    out: list[tuple[str, str]] = []
    roles = resources.roles()["roles"]
    suite = {t.get("name") for t in cfg.get("tests", default=[]) or []}
    for s in cfg.standards:
        name = s["name"]
        if not (root / s["path"]).is_file():
            out.append(("warn", f"standards {name!r}: {s['path']} does not exist, so no agent can read it"))
        unknown = [r for r in s["roles"] if r != "*" and r not in roles]
        if unknown:
            out.append(("warn", f"standards {name!r}: unknown role {', '.join(unknown)}; name aidd-team roles (`aidd owners` lists them) or *"))
        missing = [t for t in s.get("enforced_by", []) if t not in suite]
        if missing:
            out.append(("warn", f"standards {name!r}: enforced_by names no [[tests]] entry: {', '.join(missing)}; until one runs, the standard is guidance"))
    if cfg.standards and not out:
        enforced = sum(1 for s in cfg.standards if s.get("enforced_by"))
        out.append(("ok", f"house standards: {len(cfg.standards)}, {enforced} enforced by tests; `aidd owners` lists them by role"))
    return out


def runbook_checks(root: Path, cfg: cfgmod.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A runbook in use must have been run lately: warn when its last_tested is older than runbook_max_age_days."""
    today = today or dt.date.today()
    max_age = cfg.runbook_max_age_days if cfg else cfgmod.RUNBOOK_MAX_AGE_DAYS
    out: list[tuple[str, str]] = []
    for p in object_files(root, OPS_DIRS["runbook"]):
        rel = p.relative_to(root).as_posix()
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeDecodeError, model.ModelError) as exc:
            out.append(("warn", f"{rel}: {exc}"))
            continue
        if data.get("kind") != "runbook" or data.get("status") == "retired":
            continue
        last = data.get("last_tested")
        if not last:
            if data.get("status") == "active":
                out.append(("warn", f"{rel}: active runbook {data.get('id')} has never been tested; run it in a drill and record last_tested"))
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: last_tested {last!r} is not a date"))
            continue
        if age > max_age:
            when = f"last tested {last}, {age} days ago (limit {max_age})"
            out.append(("warn", f"{rel}: runbook {data.get('id')} was {when}; run it again and update last_tested"))
    return out


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed. `execute` (the `aidd doctor` command) also
    starts the configured agent hook and MCP server once, with a harmless input, and fails when either cannot run."""
    out: list[tuple[str, str]] = []
    ok = lambda m: out.append(("ok", m))  # noqa: E731
    warn = lambda m: out.append(("warn", m))  # noqa: E731
    fail = lambda m: out.append(("fail", m))  # noqa: E731

    def say(good: object, yes: str, no: str) -> None:
        out.append(("ok", yes) if good else ("warn", no))

    ok(f"aidd {__version__}, Python {sys.version.split()[0]}") if sys.version_info >= (3, 11) else fail("Python 3.11+ is required")
    if not (root / ".git").exists():
        warn("not a git repository root")
    cfg = None
    if (root / cfgmod.CONFIG_PATH).is_file():
        try:
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
            ok(f"config: profile {cfg.profile}")
            for w in cfg.warnings:
                warn(w)
        except (cfgmod.ConfigError, model.ModelError, RuntimeError) as exc:
            fail(f"config: {exc}")
    else:
        fail(f"no {cfgmod.CONFIG_PATH}; run `aidd init`")
    if cfg:
        if not cfg.get("tests"):
            warn("no [[tests]]: every Spec must bring its own commands (characterization)")
        if not cfg.approvers:
            fail(f"profile {cfg.profile} needs owners.approvers; {EMPTY_APPROVERS}")
        if cfg.gates["specialist_approvals"] and not cfg.reviewers:
            warn(f"profile {cfg.profile} needs owners.reviewers (a security pool at least) before any major change can ship")
        if cfg.gates["policy_required_routes"] and not cfg.policy_command:
            fail(
                f"profile {cfg.profile} requires policy.command for {', '.join(cfg.gates['policy_required_routes'])}; "
                "set it (aidd init --policy), or run `AIDD_ORG_PRESET=<preset.toml> aidd doctor` when the org preset binds it"
            )
        if not (root / cfg.specs_dir).is_dir():
            warn(f"no {cfg.specs_dir}/ directory yet")
        # A team of people and agents steers by one written goal and reviews by one rubric.
        if cfg.get("goal"):
            ok(f"goal: {cfg.get('goal')}")
        rubric = f"{REVIEW_POLICY}: the rubric every reviewer follows"
        say((root / REVIEW_POLICY).is_file(), rubric, f"no {REVIEW_POLICY}: the rubric every reviewer, human or agent, follows; `aidd init` writes one")
        out.extend(house_standard_checks(root, cfg))
        for w in agentmodels.independent_review_warnings(cfg.get("agents", "models", default={}) or {}, bool(cfg.get("agents", "independent_review"))):
            warn(w)
    out.extend(runbook_checks(root, cfg, today=today))
    skill = root / SKILL_REL
    if not (skill / "SKILL.md").is_file():
        warn(f"no vendored skill at {SKILL_REL}: fine if every agent loads the aidd plugin; otherwise run `aidd init`")
    else:
        bundled = resources.data_dir("skill")
        if skill.resolve() == bundled.resolve():
            ok("skill: this repository is the source")
        else:
            diff = _tree_diff(bundled, skill)
            say(not diff, f"skill matches aidd {__version__}", f"skill differs from aidd {__version__}: {', '.join(diff[:5])}; `aidd init --force` upgrades it")
    for d in DEFAULT_LINKS if "claude-code" in detect_harnesses(root) else ():
        link = root / d / "aidd"
        if link.is_symlink() and (link / "SKILL.md").is_file():
            ok(f"{link.relative_to(root)} resolves")
        elif link.is_dir() and (link / "SKILL.md").is_file() and (skill / "SKILL.md").is_file():
            rel = link.relative_to(root)
            say(not _tree_diff(skill, link), f"{rel} is a copy that matches", f"{rel} is a stale copy; `aidd init --force` refreshes it")
        else:
            warn(f"{Path(d) / 'aidd'} is missing; `aidd init` links it")
    agents = root / "AGENTS.md"
    say(agents.is_file() and "aidd" in agents.read_text(encoding="utf-8"), "AGENTS.md points at the skill", "AGENTS.md does not mention aidd")
    out.extend(instruction_file_size(root))
    detected = detect_harnesses(root)
    is_source = (skill / "SKILL.md").is_file() and skill.resolve() == resources.data_dir("skill").resolve()
    readers = []  # the agents that need nothing but AGENTS.md: one line for all of them
    for h in detected:
        label = HARNESSES[h].label
        if h == "claude-code" and is_source:
            ok(f"{label}: this repository is the plugin source; hooks.json and the plugin manifest carry the hook and the MCP server")
        elif h == "claude-code":
            settings = root / ".claude" / "settings.json"
            plugin = plugin_enabled(root)
            out.extend(claude_wiring_checks(root, execute=execute))
            hooked = settings.is_file() and HOOK_COMMAND in settings.read_text(encoding="utf-8")  # every launcher's command ends with it
            twice = session_hooks_wired(settings) if plugin else []
            if twice:
                warn(
                    f"{label}: the aidd plugin is enabled and {settings.relative_to(root)} also wires the session hooks "
                    f"{', '.join(twice)}, so each runs twice; remove those `aidd hook` entries from the settings file"
                )
            elif hooked and not plugin:
                missing = session_hooks_missing(settings)
                wired = f"{label}: the session hooks ({', '.join(SESSION_EVENTS)}) are wired"
                say(not missing, wired, f"{label}: the session hooks {', '.join(missing)} are not wired: `aidd init --agent-hooks` adds them")
        elif pointer := HARNESSES[h].pointer:
            p = root / pointer
            if p.is_file() and AGENTS_MARK in p.read_text(encoding="utf-8"):
                ok(f"{label}: {pointer} points at the skill")
            elif HARNESSES[h].only_if_present and not p.is_file():
                readers.append(label)
            else:
                warn(f"{label} is in use here, but {pointer} does not point at the skill; `aidd init` writes it")
        else:
            readers.append(label)
    if readers:
        ok(f"{len(readers)} agent{'s' if len(readers) > 1 else ''} read{'' if len(readers) > 1 else 's'} AGENTS.md: {', '.join(readers)}")
    if not detected:
        ok(
            "no coding agent's own files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them (`aidd init --harness <agent>` wires one)"
        )
    if cfg and cfg.profile == "regulated" and "claude-code" in detected:
        managed = managed_settings_sources()
        say(
            managed,
            f"Claude Code managed settings present ({', '.join(managed)}); `/status` in Claude Code names the one in force",
            "profile regulated, but this machine carries no Claude Code managed settings, so each developer's own settings "
            f"decide permissions, the sandbox, and hooks; deploy aidd's {MANAGED_SETTINGS_TEMPLATE} through MDM or the admin console "
            "(docs/ENTERPRISE.md). A claude.ai console policy not fetched yet is invisible here: check `/status`",
        )
    wf = root / ".github" / "workflows"
    if (wf / "aidd-gate.yml").is_file() and (wf / "aidd-tests.yml").is_file():
        ok("GitHub workflows present; require the `aidd/gate` status on the protected branch")
        from . import github  # best effort: says it skipped when offline or without a token

        out.extend(github.protection_checks(str(root)))
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok("GitLab CI include present; enforce it with a pipeline execution policy")
    else:
        warn("no aidd CI found; the gate is advisory until CI runs it")
    out.extend(pin_checks(root))
    return out


# The agent instruction files load into every session, so they stay about one page. 200 lines is the
# size Anthropic's Claude Code memory guidance targets for a CLAUDE.md (longer files cost context and
# adherence); 12 KiB bounds the same page written in long lines, well under Codex's 32 KiB cap.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
INSTRUCTION_MAX_LINES = 200
INSTRUCTION_MAX_BYTES = 12 * 1024


def instruction_file_size(root: Path) -> list[tuple[str, str]]:
    """A doctor warning for each agent instruction file past its size, which Learn's corrections grow."""
    out = []
    for name in INSTRUCTION_FILES:
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        if lines > INSTRUCTION_MAX_LINES or len(data) > INSTRUCTION_MAX_BYTES:
            limit = f"keep it under {INSTRUCTION_MAX_LINES} lines and {INSTRUCTION_MAX_BYTES // 1024} KiB (about one page)"
            out.append(("warn", f"{name} is {lines} lines, {len(data) // 1024} KiB: {limit}; move detail into skills or docs it links"))
    return out


OBSERVE_BLOCK = (
    "\n\n[observe]                         # required on major (and on normal under regulated)\n"
    'window = "24h"\n'
    'signals = "TODO: dashboard or SLO"\n'
    'rollback_trigger = "TODO: condition that starts the rollback"'
)

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
# Operational documents: where `aidd new` writes each kind, and where `aidd validate` and `aidd doctor` find them.
OPS_DIRS = {"runbook": "docs/runbooks", "postmortem": "docs/postmortems"}


def spec_template(route: str, full: bool = False) -> str:
    """The Spec template `aidd new spec` writes: the short one (Intent, Acceptance, Design, Rollback) for a normal Spec,
    the full one for `--full`, for major (whose Alternatives, Pre-mortem, and diagram `aidd validate` asks for), and for
    an emergency backfill."""
    return "spec" if full or route in ("major", "emergency") else "spec-short"


def new_object(
    root: Path,
    *,
    kind: str,
    id: str,
    title: str,
    route: str = "normal",
    ctype: str = "feat",
    owner_team: str = "",
    parent: str = "",
    specs_dir: str = "specs",
    today: dt.date | None = None,
    audience: str = "client",
    addressee: str = "",
    proposals_dir: str = "proposals",
    spec: str = "",
    scope: list[str] | None = None,
    dimensions: list[str] | None = None,
    irreversible: bool = False,
    full: bool = False,
) -> Path:
    if not ID_PATTERN.match(id):
        raise ValueError(f"id {id!r} must be letters, digits, and . _ : - (such as SPEC-42), at most 64 characters")
    if spec and not ID_PATTERN.match(spec):
        raise ValueError(f"spec {spec!r} must be a Spec id, such as INC-481")
    today = today or dt.date.today()
    tpl = (resources.data_dir("skill") / "assets" / f"{spec_template(route, full) if kind == 'spec' else kind}.md").read_text(encoding="utf-8")
    quoted = lambda s: json.dumps(s, ensure_ascii=False)[1:-1]  # noqa: E731  # the value sits inside "..." in the template
    values = dict(id=id, title=quoted(title), owner_team=quoted(owner_team or "TODO"), today=today.isoformat())
    if kind == "proposal":
        values |= dict(audience=audience, addressee=quoted(addressee or "TODO: who receives it and decides"))
    elif kind in OPS_DIRS:
        values |= dict(spec=spec or "TODO")
    else:
        values |= dict(route=route, type=ctype, trace_id=id.lower())
    text = fill(tpl, **values)
    if parent and kind not in OPS_DIRS:
        text = text.replace(f'kind = "{kind}"\n', f'kind = "{kind}"\nparent = "{parent}"\n', 1)
    if kind == "spec":
        # `aidd new spec --paths`: the planned paths are the first Task's scope, and the declared risk is the Spec's.
        if scope:
            text = re.sub(r"(?m)^scope = \[[^\]\n]*\]", lambda _: f"scope = {toml_list(scope)}", text, count=1)
        if dimensions:
            text = re.sub(r"(?m)^dimensions = \[\]", lambda _: f"dimensions = {toml_list(dimensions)}", text, count=1)
        if irreversible:
            text = re.sub(r"(?m)^reversible = true", "reversible = false", text, count=1)
    if kind == "spec" and route in ("major", "emergency"):
        # Observe is required on major (and on normal under regulated, where the gate asks for it).
        block = OBSERVE_BLOCK
        if route == "emergency":
            due = (today + dt.timedelta(days=2)).isoformat()
            block += f'\n[emergency]\nseverity = "sev2"\nkind = "outage"\ncommander = "@TODO"\nref = "INC-TODO"\nreview_due = "{due}"\n'
        head, sep, rest = text.partition("\n+++\n")
        text = head + block + sep + rest
    # A proposal gets its own folder: each role writes its part beside it, and one addressee's material stays apart.
    if kind == "proposal":
        path = root / proposals_dir / id / "proposal.md"
    elif kind in OPS_DIRS:
        path = root / OPS_DIRS[kind] / f"{id}.md"
    else:
        path = root / specs_dir / f"{id}.md"
    if path.exists():
        raise FileExistsError(f"{path} exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


MAX_VALIDATE_FILES = 1000
MAX_VALIDATE_DEPTH = 10


def _walk_bounded(root: Path, max_files: int = MAX_VALIDATE_FILES, max_depth: int = MAX_VALIDATE_DEPTH) -> tuple[list[Path], bool]:
    found: list[Path] = []
    stopped = False
    root_parts_len = len(root.resolve().parts)
    for dirpath, dirnames, filenames in os.walk(root):
        dpath = Path(dirpath).resolve()
        depth = len(dpath.parts) - root_parts_len
        if depth >= max_depth:
            dirnames.clear()
            stopped = True
            continue
        dirnames.sort()
        for fn in sorted(filenames):
            if len(found) >= max_files:
                return found, True
            found.append(Path(dirpath) / fn)
    return found, stopped


def validate_file(path: Path, label: str | None = None) -> list[str]:
    """Each finding names the file by `label`, else by the path in forward slashes, on every OS."""
    shown = label or path.as_posix()
    raw = str(path)
    return [e.replace(raw, shown) for e in _validate_file(path)] if raw != shown else _validate_file(path)


def _validate_file(path: Path) -> list[str]:
    if path.is_dir():
        files, stopped = _walk_bounded(path)
        errs = [
            e
            for f in files
            if ((f.name == "config.toml" and f.parent.name == ".aidd") or (f.suffix == ".md" and _is_object(f)))
            and f.name.lower() != "readme.md"
            and "assets" not in f.parts
            for e in validate_file(f)
        ]
        if stopped:
            errs.append(f"warning: {path}: directory walk reached bound and stopped early")
        return errs
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{path}: not UTF-8 text"]
    if path.suffix == ".toml":
        try:
            cfg = cfgmod.load_text(
                text, read=lambda p: (path.parent.parent / p).read_text(encoding="utf-8") if (path.parent.parent / p).is_file() else None, where=str(path)
            )
        except (cfgmod.ConfigError, model.ModelError, RuntimeError) as exc:
            return str(exc).splitlines()
        out = [f"warning: {w}" for w in cfg.warnings]
        if path.name == "config.toml" and not cfg.approvers:
            out.append(f"{path}: profile {cfg.profile} requires owners.approvers (solo too); {EMPTY_APPROVERS}")
        return out
    try:
        data, _, errs = model.load_object(text, str(path))
    except model.ModelError as exc:
        return [str(exc)]
    # A placeholder in what the gate executes or scopes is an error; elsewhere it is a reminder.
    tests = data.get("tests") or {}
    executable = [a for c in tests.get("commands", []) for a in c.get("command", [])]
    executable += [s for task in data.get("tasks", []) for s in task.get("scope", [])]
    executable += list(tests.get("files", []))
    if any("TODO" in str(x) for x in executable):
        if data.get("route") == "emergency":
            # A backfill stub committed with the repair; `aidd validate` holds its review_due.
            errs.append(f"warning: {path}: emergency backfill Spec still holds TODO placeholders; finish it by review_due")
        else:
            errs.append(f"{path}: test commands, tests.files, or a Task's scope still hold TODO placeholders")
    elif "TODO" in text:
        errs.append(f"warning: {path}: still contains TODO placeholders")
    if data.get("kind") == "spec" and data.get("route") in ("normal", "major"):
        if data.get("route") == "major":
            # Only a major Spec carries the full template's sections (a normal one may be the short Spec). A diagram is one
            # view chosen because it answers a question, so prose that answers it is enough; a Design with neither is not.
            design = section(text, "Design")
            if not has_diagram(design) and len(design.split()) < DESIGN_PROSE_WORDS:
                shape = "add one so a human reads the change's shape before the words at Spec approval"
                errs.append(f"warning: {path}: the Design section of a major Spec has no diagram (a ```mermaid block or an image) and little prose; {shape}")
            for heading, advice in (
                ("Alternatives considered", "say what else you weighed, including doing nothing"),
                ("Pre-mortem", "references/loop.md requires one"),
            ):
                if not section(text, heading):
                    errs.append(f"warning: {path}: a major Spec has no '## {heading}' section with content; {advice}")
        errs += _intent_and_conflict_warnings(path, text, data)
    if data.get("kind") in workitems.WORK_KINDS and data:
        errs += workitems.validate(path, text, data, _repo_root_of(path))
    if data.get("kind") == "spec" and not any(not e.startswith("warning: ") for e in errs):
        errs += _consistency_warnings(path, data)
        errs += _coverage_warnings(path, text, data)
    return errs


# An Acceptance item's id (A1, A2, ...), where the item starts: at the head of a line, a list item, or a table row,
# or right after a Gherkin keyword such as `Scenario:`.
_ACCEPTANCE_ID = re.compile(r"^[ \t]*(?:[-*|#]+[ \t]*)?\**(?:(?:Scenario Outline|Scenario|Example|Rule)[ \t]*:[ \t]*)?\**(A[1-9][0-9]{0,3})\b", re.M)


def acceptance_ids(text: str) -> list[str]:
    """The ids of the Acceptance items in a Spec's body, in order of first appearance."""
    return list(dict.fromkeys(_ACCEPTANCE_ID.findall(section(text, "Acceptance"))))


def _coverage_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Acceptance items no test command covers, and covered ids the Acceptance does not have, as warnings.
    Opt-in: only once a command declares `covers`, so a Spec written before the field existed stays quiet.
    The gate never reads `covers`: the runner's exit codes are the evidence, and this only shows the gaps."""
    commands = (data.get("tests") or {}).get("commands", []) or []
    declared = [c for c in commands if isinstance(c, dict) and c.get("covers")]
    if not declared:
        return []
    ids = acceptance_ids(text)
    covered = {i for c in declared for i in c["covers"]}
    if not ids:
        return [f"warning: {path}: tests.commands declare covers, but the '## Acceptance' section names no item ids; start each item with its id (A1, A2, ...)"]
    out = [
        f"warning: {path}: Acceptance item {i} is covered by no test command; add it to a command's covers, or say why it is not provable"
        for i in ids
        if i not in covered
    ]
    for c in declared:
        out += [
            f"warning: {path}: test command {c.get('name')!r} covers {i}, which the '## Acceptance' section does not have" for i in c["covers"] if i not in ids
        ]
    return out


# A Spec at or past Spec approval: its test files are frozen, so they must exist by now.
APPROVED_STATUSES = ("ready", "in_progress", "in_review", "released", "done")
# A Task's proof that names a test command: "test `rate-limit`", "command `unit`", or "`rate-limit` test".
_PROOF_COMMAND = re.compile(r"\b(?:tests?|commands?)\s+`([a-z0-9][a-z0-9_.-]{0,63})`|`([a-z0-9][a-z0-9_.-]{0,63})`\s+(?:tests?|commands?)\b", re.I)


def _repo_root_of(path: Path) -> Path | None:
    for d in path.resolve().parents:
        if (d / ".aidd").is_dir() or (d / ".git").exists():
            return d
    return None


def _suite_names(root: Path | None) -> set[str]:
    """The repository suite's `[[tests]]` names, read offline; an unreadable config yields what its own file names."""
    if root is None or not (root / cfgmod.CONFIG_PATH).is_file():
        return set()

    def offline(url: str) -> bytes:
        raise cfgmod.ConfigError(f"not fetched: {url}")

    try:
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root), fetch=offline)
        return {t.get("name") for t in cfg.get("tests", default=[]) or []}
    except Exception:  # noqa: BLE001  # a parent out of reach: fall back to the file's own entries
        try:
            raw = model.parse_toml((root / cfgmod.CONFIG_PATH).read_text(encoding="utf-8"), cfgmod.CONFIG_PATH)
        except (OSError, model.ModelError):
            return set()
        return {str(t.get("name")) for t in raw.get("tests", []) if isinstance(t, dict)}


def _consistency_warnings(path: Path, data: dict) -> list[str]:
    """Where a Spec's plan and its tests disagree, as warnings: a frozen test file that is not on disk, and a Task
    proof naming a test command nobody defined. (A command that runs a file outside tests.files is a lint error.)"""
    out = []
    tests = data.get("tests") or {}
    root = _repo_root_of(path)
    if root is not None and data.get("status") in APPROVED_STATUSES:
        for f in tests.get("files", []):
            if not any(c in f for c in "*?[") and not (root / f.rstrip("/")).exists():
                out.append(f"warning: {path}: tests.files {f!r} does not exist, but the Spec is {data['status']}; Spec approval froze a test nobody wrote")
    known = {c.get("name") for c in tests.get("commands", [])} | _suite_names(root)
    for task in data.get("tasks", []):
        for m in _PROOF_COMMAND.finditer(task.get("proof", "")):
            name = m.group(1) or m.group(2)
            if name not in known:
                out.append(
                    f"warning: {path}: task {task['id']}: proof names test command {name!r}, which is neither in tests.commands nor the repository's [[tests]]"
                )
    return out


def _intent_and_conflict_warnings(path: Path, text: str, data: dict) -> list[str]:
    """Reminders for a normal or major Spec: the originator's words, and the conflicts only a human may settle.
    Warnings, never errors, and only from `aidd validate`: the gate never reads the Spec body's sections."""
    out = []
    if not section(text, "Intent"):
        quote = "quote the originator's problem, outcome, who is affected, constraints, and open questions before the design"
        out.append(f"warning: {path}: no '## Intent' section with content; {quote}")
    dims = (data.get("risk") or {}).get("dimensions") or []
    pools = {rules.POOL_OF[d] for d in [*dims, data.get("type")] if d in rules.POOL_OF}
    if (data.get("route") == "major" or len(pools) > 1) and not section(text, "Policy conflicts"):
        who = "list where specialist input, domain packs, or org policy disagree and who decides, or write 'none'"
        out.append(f"warning: {path}: no '## Policy conflicts' section with content; {who}")
    return out


# Below this many words, a Design section has not said what it is there to say.
DESIGN_PROSE_WORDS = 40


def has_diagram(text: str) -> bool:
    """A Mermaid block or an image anywhere in the document."""
    return "```mermaid" in text or bool(re.search(r"!\[[^\]]*\]\(", text))


def object_files(root: Path, specs_dir: str) -> list[Path]:
    """aidd objects: Markdown files that open with `+++` front matter. Other tools' files (Spec Kit's specs/NNN-*/) are left alone."""
    d = root / specs_dir
    return sorted(p for p in d.rglob("*.md") if p.name.lower() != "readme.md" and _is_object(p)) if d.is_dir() else []


def _is_object(p: Path) -> bool:
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as fh:
            return fh.readline().strip() == "+++"
    except OSError:
        return False


def check_repo(root: Path, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    today = today or dt.date.today()
    errors: list[str] = []
    warnings: list[str] = []
    specs_dir, proposals_dir, bots = "specs", "proposals", set()
    cfg_path = root / cfgmod.CONFIG_PATH

    def rel(p: Path) -> str:
        """A repository path as a finding names it: from the root, in forward slashes."""
        return p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()

    if cfg_path.is_file():
        for e in validate_file(cfg_path, rel(cfg_path)):
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
            specs_dir, proposals_dir = cfg.specs_dir, cfg.proposals_dir
            bots = {b.lower().lstrip("@") for b in cfg.get("identities", "bots", default=[])}
        except (cfgmod.ConfigError, model.ModelError, RuntimeError):
            pass
    else:
        errors.append(f"no {cfgmod.CONFIG_PATH}")
    ids: dict[str, str] = {}
    objects: list[tuple[str, dict]] = []
    ops = [p for d in OPS_DIRS.values() for p in object_files(root, d)]
    for path in object_files(root, specs_dir) + object_files(root, proposals_dir) + ops:
        p = rel(path)
        errs = validate_file(path, p)
        for e in errs:
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            data, _ = model.split_front_matter(path.read_text(encoding="utf-8"), p)
        except model.ModelError:
            continue
        objects.append((p, data))
        oid = data.get("id")
        if oid in ids:
            errors.append(f"{p}: id {oid} is also used by {ids[oid]}")
        elif oid:
            ids[oid] = p
    errors += workitems.relation_errors(objects)
    for p, data in objects:
        if data.get("kind") == "proposal":
            for step in ("go_no_go", "sign_off"):
                who = str((data.get(step) or {}).get("by", ""))
                if who and (who.lower().lstrip("@") in bots or who.startswith("agent:")):
                    errors.append(f"{p}: {step}.by {who} is an agent account; a person decides a proposal")
        if data.get("kind") == "postmortem" and data.get("spec") and data["spec"] != "TODO":
            if data["spec"] not in ids:
                warnings.append(f"{p}: spec {data['spec']} is not in {specs_dir}/; name the emergency change's backfill Spec")
        parent = data.get("parent")
        if parent and parent not in ids:
            warnings.append(f"{p}: parent {parent} is not in {specs_dir}/ (fine if the parent lives outside the repository)")
        em = data.get("emergency")
        if data.get("route") == "emergency" and isinstance(em, dict) and em.get("review_due") is not None:
            try:
                due = dt.date.fromisoformat(str(em["review_due"]))
            except ValueError:
                errors.append(f"{p}: emergency.review_due {em['review_due']!r} is not a date")
                continue
            outcome = data.get("outcome")
            learn_ref = outcome.get("learn_ref") if isinstance(outcome, dict) else None
            if due < today and not learn_ref:
                errors.append(f"{p}: post-incident review was due {due}; record outcome.learn_ref")
        out = data.get("outcome") or {}
        if data.get("route") == "major" and out.get("released_at") and not out.get("observe_result"):
            warnings.append(f"{p}: released major change has no outcome.observe_result")
        # `hypothesis` is frozen by Spec approval and `outcome.result` records what the metric did. One without
        # the other means the claim in the changelog is not being kept: a result nobody predicted, or
        # a prediction nobody measured.
        if out.get("result") and not data.get("hypothesis"):
            warnings.append(f"{p}: outcome.result records a metric no hypothesis predicted; add the hypothesis before Spec approval next time")
        if data.get("hypothesis") and out.get("released_at") and not out.get("result"):
            warnings.append(f"{p}: a released change with a hypothesis has no outcome.result; Learn records what the metric did")
    return errors, warnings
