"""Adopt, check, and extend a repository: init, doctor, new, validate."""

from __future__ import annotations

import datetime as dt
import filecmp
import functools
import itertools
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePath

from . import __version__, agentmodels, detect, docs, gitutil, globs, model, project, resources, rules, util, workitems
from . import config as cfgmod
from .harnesses import HARNESSES, pointer_files
from .model import section
from .util import toml_list

SKILL_REL = ".agents/skills/aidd"
DEFAULT_LINKS = (".claude/skills",)
AGENTS_MARK = "<!-- aidd -->"
GITIGNORE_LINE = "aidd-evidence/"
# Environment files hold secrets; the example beside them does not. Written under ENV_MARK, which uninstall looks for.
ENV_IGNORE = (".env*", "!.env.example")
ENV_MARK = "# aidd: environment files hold secrets; .env.example stays"
# The owner_team a solo repository's Specs get, so none starts with a TODO.
SOLO_TEAM = "maintainers"
# The smoke test `aidd init` binds when it finds no test command, so the first change has a suite to pass: every tracked
# Python file parses, and no tracked file holds a merge-conflict marker. Replace it with the real suite.
SMOKE_TEST = [
    "python3",
    "-c",
    "import ast, subprocess, sys\n"
    "bad = []\n"
    "for p in subprocess.run(['git', 'ls-files', '-z'], capture_output=True, text=True).stdout.split('\\0'):\n"
    "    try:\n"
    "        t = open(p, encoding='utf-8').read()\n"
    "        if p.endswith('.py'):\n"
    "            ast.parse(t, p)\n"
    "    except SyntaxError as e:\n"
    "        bad.append(f'{p}:{e.lineno}: {e.msg}')\n"
    "        continue\n"
    "    except (OSError, ValueError):\n"
    "        continue\n"
    "    if '\\n<<<<<<< ' in '\\n' + t:\n"
    "        bad.append(f'{p}: a merge-conflict marker')\n"
    "print('\\n'.join(bad) or 'smoke: the tracked Python files parse, and no file holds a conflict marker')\n"
    "sys.exit(1 if bad else 0)\n",
]
GITHUB_WORKFLOWS = ("aidd-tests.yml", "aidd-gate.yml", "aidd-relay.yml")
# The product's security scanning (dependency scan, SAST, SBOM, secret scan): written when compliance is on (a target, or the regulated
# profile), or with `--security-ci`; and Dependabot, written for the ecosystems init finds.
SECURITY_WORKFLOW = "aidd-security.yml"
# The GitLab side, under the same condition: the secret scan.
GITLAB_SECURITY = "aidd-security.gitlab-ci.yml"
DEPENDABOT = ".github/dependabot.yml"
# A manifest's file name and the Dependabot ecosystem that updates it; `*.csproj` and `*.tf` match by suffix.
DEPENDABOT_ECOSYSTEMS = {
    "package.json": "npm",
    "pyproject.toml": "pip",
    "requirements.txt": "pip",
    "Pipfile": "pip",
    "go.mod": "gomod",
    "Cargo.toml": "cargo",
    "Gemfile": "bundler",
    "composer.json": "composer",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    ".csproj": "nuget",
    "Dockerfile": "docker",
    "mix.exs": "mix",
    "pubspec.yaml": "pub",
    "Package.swift": "swift",
    ".tf": "terraform",
}
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
# A workflow that checks out aidd's source (aidd-observe.yml): `repository: thaithienvanid/aidd` and, on the next line, `ref:`.
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
    fetch breaks every CI run. Skipped with AIDD_OFFLINE=1, inside a hook (AIDD_HOOK_OFFLINE=1), without a GitHub
    remote, and when GitHub cannot be reached."""
    refs = pinned_refs(root)
    if not refs or "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
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
        if len(ref) == 40:
            out.append(("warn", why + "Pin a pushed commit or a release: `aidd upgrade --ref <sha> --yes`"))
        else:
            # Before the first release, the templates' tag pins name a tag that is not there yet.
            fix = "Pin a commit instead: `aidd upgrade --ref <sha> --yes` (or `aidd init --ref <sha>` on a first setup), "
            out.append(("warn", why + fix + f"with <sha> from `git ls-remote {RELEASE_REPO_URL} refs/heads/main`"))
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


def _origin_repo(root: Path) -> str | None:
    """The GitHub `owner/name` of `origin` when a person runs `aidd init`, if it is one; else None."""
    from . import github

    found = github.origin_repo(str(root))
    return found if found and github.REPO_NAME.match(found) else None


def config_text(
    profile: str,
    *,
    approvers: list[str] | None = None,
    specialists: dict[str, list[str]] | None = None,
    test: list[str] | None = None,
    policy: list[str] | None = None,
    mode: str | None = None,
    goal: str | None = None,
    test_name: str = "unit",
    default_team: str | None = None,
    risk_rules: list[dict] | None = None,
    stack: list[str] | None = None,
    preview: list[str] | None = None,
    ui: bool = True,
    compliance_targets: list[str] | None = None,
    held_commands: list[dict] | None = None,
    repo: str | None = None,
    existing_code: bool = False,
) -> str:
    """The starting .aidd/config.toml, filled from the skill's template. `mode` writes the gate's mode key when the schema has it;
    `risk_rules` are the ones `aidd init` detected, written under a comment that says how to drop one; `stack` is the
    technology radar it detected, written as a commented `[project.stack]` a person edits; `preview`, the local preview
    command when `preview_command` found an obvious one, else a commented example; `ui` False (a command-line tool or a
    library) writes the interface product defaults off, with the reason, and the rest commented. `held_commands` are the
    deploy and infrastructure commands `aidd init` detected, written active, each under a comment that a person may delete it.
    `repo` is the GitHub `owner/name` of `origin`, written as `[project] repo`, which autopilot (experimental) trusts.
    `existing_code` (a repository that already has a structure) writes the `modular_monolith` default off, with the reason."""
    tpl = (resources.data_dir("skill") / "assets" / "config.toml").read_text(encoding="utf-8")
    pools = "\n".join(f"{pool} = {toml_list(who)}" for pool, who in (specialists or {}).items())
    if mode and config_supports_mode():
        mode_line = f"mode = \"{mode}\"   # the gate's mode, read from the base branch; it wins over the CI file's input"
    else:
        mode_line = MODE_COMMENT
    text = fill(
        tpl,
        profile=profile,
        mode=mode_line,
        approvers=toml_list(approvers)
        if approvers
        else f'[]   # TODO: name who may approve, such as ["@org/leads"], or ["email:you@example.com"] to approve locally; {EMPTY_APPROVERS}',
        specialists=f"[owners.specialists]\n{pools}" if pools else '# [owners.specialists]\n# security = ["@org/security"]',
        tests=(
            (SMOKE_COMMENT if test == SMOKE_TEST else "") + f'[[tests]]\nname = "{test_name}"\ncommand = {toml_list(test)}'
            if test
            else '# [[tests]]\n# name = "unit"\n# command = ["npm", "test"]'
        ),
        policy=f"[policy]\ncommand = {toml_list(policy)}" if policy else '# [policy]\n# command = ["./scripts/aidd-policy"]',
        goal=f"goal = {json.dumps(goal, ensure_ascii=False)}   # {GOAL_COMMENT}"
        if goal
        else f'# goal = "make onboarding succeed on the first try"   # {GOAL_COMMENT}',
        preview=f'[preview]\ncommand = {toml_list(preview)}\n# url = "http://localhost:3000"'
        if preview
        else '# [preview]\n# command = ["docker", "compose", "up", "--build"]   # starts the app with its seed data\n# url = "http://localhost:3000"',
    )
    if default_team:
        text = text.replace('# default_team = "@org/team"', f"default_team = {json.dumps(default_team)}", 1)
    if risk_rules:
        text = text.rstrip("\n") + "\n\n" + RISK_COMMENT
        for r in risk_rules:
            text += f"\n[[risk_rules]]\nname = {json.dumps(r['name'])}\npaths = {toml_list(r['paths'])}\ndimensions = {toml_list(r['dimensions'])}\n"
    if held_commands:
        text = text.rstrip("\n") + "\n\n" + detect.held_toml(held_commands)
    if stack:
        text = text.rstrip("\n") + "\n\n" + project.stack_block(stack)
    if repo:
        text = text.rstrip("\n") + "\n\n" + project.repo_block(repo)
    return text.rstrip("\n") + "\n\n" + project.defaults_block(ui, existing_code) + "\n\n" + project.compliance_block(compliance_targets)


COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")


def preview_command(root: Path) -> list[str] | None:
    """The local preview command when it is obvious: a Docker Compose file at the root. None otherwise; guessing a
    command that does not start the app would send the verifier after the wrong thing."""
    return ["docker", "compose", "up", "--build"] if any((root / f).is_file() for f in COMPOSE_FILES) else None


SMOKE_COMMENT = (
    "# `aidd init` found no test command, so this smoke test holds the place of one: every tracked Python file parses, and no\n"
    "# tracked file holds a merge-conflict marker. Replace it with your suite, as its own change.\n"
)
RISK_COMMENT = (
    "# Sensitive areas `aidd init` found from folder and file names alone (a guess, not a finding): each raises the route of a\n"
    "# change that touches it. Remove a rule that is wrong, or narrow its paths, in the setup change.\n"
)


# Claude Code loads its agents, commands, skills, hooks, and MCP servers when a session starts.
RESTART_NOTICE = "Restart Claude Code in this folder to load the roles, commands, and hooks."
RESTART_BEFORE_INIT = "A session started before `aidd init` must restart to load them."


def wrote_claude_code_files(actions: list[str], root: Path) -> bool:
    """Whether `init` wrote something Claude Code loads only at start: a file under the repository's `.claude/` (agents,
    commands, skills, the hooks in its settings), its `.mcp.json`, or a plugin it installed. A file it kept does not
    count. Each path is read relative to `root`, so a repository that itself sits under a `.claude` folder never counts."""
    top = root.resolve()
    for a in actions:
        verb, _, rest = a.partition(" ")
        if verb == "ran" and "claude plugin install" in rest:
            return True
        if verb not in ("wrote", "updated", "linked", "copied"):
            continue
        shown = Path(rest.strip().split(" (", 1)[0].split(" -> ", 1)[0])
        try:
            parts = (shown if shown.is_absolute() else root / shown).resolve().relative_to(top).parts
        except ValueError:
            continue
        if parts and (parts[0] == ".claude" or parts == (".mcp.json",)):
            return True
    return False


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
        actions.append(f"kept     {_shown(dest)} (exists; `aidd upgrade --yes` upgrades it)")
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
    specialists: dict[str, list[str]] | None = None,
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
    risk_rules: list[dict] | None = None,
    stack: list[str] | None = None,
    ui: bool = True,
    compliance_targets: list[str] | None = None,
    security_ci: bool = False,
    held_commands: list[dict] | None = None,
    not_held: int = 0,
    existing_code: bool = False,
) -> list[str]:
    """Adopt. The gate starts in advisory mode (observe first) unless enforce is set; the CI files are pinned by `_resolve_pin`.

    Coding agents are detected (or given as `harnesses`) and each one is wired the way it reads instructions (`harnesses.py`):
    Claude Code gets the `.claude/skills` link, the guard hook, and the MCP server, unless `agent_hooks` is False or the
    plugins are installed instead (`claude_plugins`); an agent with its own instruction file gets a pointer file; the rest read AGENTS.md.
    `links` are extra skill directories to link whatever was detected. `devcontainer` also writes .devcontainer/ from
    templates/devcontainer/: a container that denies outbound traffic except to an allow-list, a starting point only.
    `compliance_targets` fill `[project.compliance]` (else it is written commented out); on GitHub, the security-scanning
    workflow is written when compliance is on (a target, or the regulated profile) or with `security_ci`, and Dependabot
    for the ecosystems found, always. `held_commands` (from `detect.held_commands`, with `not_held` names past its cap) are written into a new config only:
    a config that exists is kept, so re-running init never adds an entry twice or brings back one a person deleted.
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
            actions.append(f"hint     this machine has {labels}: wire {'it' if len(wired) == 1 else 'them'} with {flags}")
    claude = "claude-code" in detected
    fell_back, installed_now, why_not = False, list[str](), ""
    if claude_plugins:
        why_not, installed_now = install_claude_plugins(root, actions, team=team)
        claude_plugins, fell_back = not why_not, bool(why_not)
        if fell_back and not claude:
            # The person asked for Claude Code: wire its whole repository set, not only what detection would find.
            claude, detected = True, [*detected, "claude-code"]
    if not approvers and profile == "solo":
        # Solo still needs a listed approver: the operator, found without the network. The email the commits carry is what
        # a local approval (`aidd approve`) is counted as; a platform login is what a PR/MR's approval is counted as.
        login, email = operator_login(root), operator_email(root)
        approvers = [*([f"@{login}"] if login else []), *([f"email:{email}"] if email else [])] or None
        if approvers:
            actions.append(f"approver {', '.join(approvers)} (the operator, from the local git and gh config; a local approval counts as the email)")
        else:
            actions.append("hint     name the approver: `aidd init --approvers email:you@example.com --force` (the email your commits use)")
    mode = "enforce" if enforce else "advisory"
    cfg_text = config_text(
        profile,
        approvers=approvers,
        specialists=specialists,
        test=test,
        policy=policy,
        mode=mode,
        goal=goal,
        test_name="smoke" if test == SMOKE_TEST else "unit",
        default_team=SOLO_TEAM if profile == "solo" else None,
        risk_rules=risk_rules,
        stack=stack,
        preview=preview_command(root),
        ui=ui,
        compliance_targets=compliance_targets,
        held_commands=held_commands,
        repo=_origin_repo(root),
        existing_code=existing_code,
    )
    _write(root / cfgmod.CONFIG_PATH, cfg_text, force, actions)
    if existing_code and actions[-1].startswith("wrote"):
        actions.append(
            "hint     kept the existing structure: [project.defaults.off] names modular_monolith. To adopt the modular monolith, "
            "a person accepts an ADR and deletes that line (aidd-team:modular-monolith)"
        )
    if held_commands and actions[-1].startswith("wrote"):
        names = ", ".join(g["name"] for g in held_commands)
        actions.append(f"held     deploy and infrastructure commands for a person in [[guard.held_commands]]: {names}; a person may delete any")
        if not_held:
            actions.append(
                f"hint     {not_held} more deploy script names are not held (the first {detect.MAX_HELD_SCRIPTS} are); "
                "a person can add them to [[guard.held_commands]]"
            )
    if risk_rules:
        found = ", ".join(f"{r['name']} ({', '.join(r['paths'][:2])})" for r in risk_rules[:4])
        actions.append(f"risk     wrote the sensitive areas it found as [[risk_rules]]: {found}; remove any that is wrong")
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
            actions.append(
                f"hint     pin the aidd workflows to a commit SHA: `aidd upgrade --ref <sha> --yes` (they name v{__version__}; `init --force` would also replace the config)"
            )
    if devcontainer:
        for name in DEVCONTAINER_FILES:
            _write(root / ".devcontainer" / name, (tpl / "devcontainer" / name).read_text(encoding="utf-8"), force, actions)
    pr_tpl = (tpl / "github" / "pull_request_template.md").read_text(encoding="utf-8")
    on = bool(compliance_targets) or profile == "regulated"
    why = "--security-ci" if security_ci else "compliance targets" if compliance_targets else "the regulated profile"
    if ci == "github":
        for name in GITHUB_WORKFLOWS:
            text = pin_workflow((tpl / "github" / name).read_text(encoding="utf-8"), pin, release)
            if name == "aidd-gate.yml" and not enforce:
                text = re.sub(r"(mode:\s*)enforce", r"\1advisory", text, count=1)
            _write(root / ".github" / "workflows" / name, text, force, actions)
        _write(root / ".github" / "pull_request_template.md", pr_tpl, force, actions)
        if security_ci or on:
            before = len(actions)
            _write(root / ".github" / "workflows" / SECURITY_WORKFLOW, (tpl / "github" / SECURITY_WORKFLOW).read_text(encoding="utf-8"), force, actions)
            actions[before] += f" ({why}: dependency scan, SAST, an SBOM, and a secret scan)"
        _write(root / DEPENDABOT, dependabot_text(root), force, actions)
    elif ci == "gitlab":
        # The mode is the config's `mode` key, read from the base branch; a pipeline variable cannot change it.
        text = pin_workflow((tpl / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8"), pin, release)
        _write(root / ".gitlab" / "aidd.gitlab-ci.yml", text, force, actions)
        _write(root / ".gitlab" / "merge_request_templates" / "Default.md", pr_tpl, force, actions)
        actions.append("hint     add `include: { local: .gitlab/aidd.gitlab-ci.yml }` to .gitlab-ci.yml")
        if security_ci or on:
            before = len(actions)
            _write(root / ".gitlab" / GITLAB_SECURITY, (tpl / "gitlab" / GITLAB_SECURITY).read_text(encoding="utf-8"), force, actions)
            actions[before] += f" ({why}: a secret scan)"
            actions.append(f"hint     add `- local: .gitlab/{GITLAB_SECURITY}` to the include in .gitlab-ci.yml")
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
    have = text.splitlines()
    add = ([GITIGNORE_LINE] if GITIGNORE_LINE not in have else []) + ([ENV_MARK, *ENV_IGNORE] if ENV_IGNORE[0] not in have else [])
    if add:
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(("\n" if text and not text.endswith("\n") else "") + "".join(f"{line}\n" for line in add))
        actions.append(f"updated  {_shown(gi)}" + (" (environment files stay out of git, except .env.example)" if ENV_MARK in add else ""))
    if fell_back:
        actions.append(plugin_fallback_note(root, installed_now, why_not))
    return actions


def dependabot_text(root: Path) -> str:
    """templates/github/dependabot.yml with an entry per ecosystem whose manifest sits at the root or one or two
    folders down (skipping dependency and build folders): a cheap walk, never the whole tree."""
    from .detect import SKIP

    found: dict[str, set[str]] = {}

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for p in entries:
            if p.is_dir() and not p.is_symlink():
                if depth < 2 and p.name not in SKIP and not p.name.startswith("."):
                    walk(p, depth + 1)
                continue
            eco = DEPENDABOT_ECOSYSTEMS.get(p.name) or next((e for k, e in DEPENDABOT_ECOSYSTEMS.items() if k.startswith(".") and p.name.endswith(k)), None)
            if eco:
                rel = p.parent.relative_to(root).as_posix()
                found.setdefault(eco, set()).add("/" if rel == "." else f"/{rel}")

    walk(root, 0)
    text = (resources.data_dir("templates") / "github" / "dependabot.yml").read_text(encoding="utf-8")
    for eco, dirs in sorted(found.items()):
        listed = ", ".join(json.dumps(x) for x in sorted(dirs))
        text += (
            f"\n  - package-ecosystem: {eco}\n    directories: [{listed}]\n    schedule:\n      interval: monthly\n"
            f'    cooldown:\n      default-days: 7\n    groups:\n      {eco}:\n        patterns: ["*"]\n'
        )
    return text


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
        "`aidd test` and `aidd gate` find the Spec in the diff; name it with `--spec specs/<ID>.md`, or an inline Change Request block with `--body-file`. "
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


def install_claude_plugins(root: Path, actions: list[str], *, team: bool) -> tuple[str, list[str]]:
    """Install the aidd plugins for this user through the Claude Code CLI (user scope), instead of repository files:
    why not ("" when every install ran, else "missing" or "failed"), so init can fall back to repository wiring, and
    the plugins this run installed or found already installed (`claude` exits 0 for both), which the fallback note
    names to uninstall: with the repository files, they would load twice."""
    claude = shutil.which("claude")
    installed: list[str] = []
    if claude is None:
        actions.append("skipped  Claude Code plugins: no `claude` on PATH; wiring the repository instead")
        return "missing", installed
    commands = [[claude, "plugin", "marketplace", "add", MARKETPLACE_REPO], [claude, "plugin", "install", f"aidd@{MARKETPLACE}"]]
    if team:
        commands.append([claude, "plugin", "install", f"aidd-team@{MARKETPLACE}"])
    for cmd in commands:
        shown = " ".join(["claude", *cmd[1:]])
        try:
            r = PLUGIN_RUNNER(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(root))
        except (OSError, subprocess.TimeoutExpired) as exc:
            actions.append(f"failed   {shown}: {exc}; wiring the repository instead")
            return "failed", installed
        output = (r.stderr or r.stdout or "").strip()
        if r.returncode != 0 and not (cmd[2] == "marketplace" and "already" in output.lower()):
            actions.append(f"failed   {shown}: {output.splitlines()[-1] if output else 'exit ' + str(r.returncode)}; wiring the repository instead")
            return "failed", installed
        actions.append(f"ran      {shown}")
        if cmd[2] == "install":
            installed.append(cmd[-1])
    return "", installed


def claude_repo_files(root: Path) -> tuple[list[str], list[str]]:
    """The repository files that carry what the aidd plugins carry, for Claude Code: (the skill's part, the team's part).
    The skill's part is the `.claude/skills/aidd` link or copy, the aidd hook in `.claude/settings.json`, and the `aidd`
    server in `.mcp.json`; the team's part is the `aidd-*` agents, commands, and skills `aidd init --team` writes.
    A file that cannot be read counts as not carrying anything; `unreadable_claude_settings` names it. Only the names
    aidd ships count, so a team's own `.claude/skills/aidd-<name>` is never one of them."""
    skill: list[str] = []
    if (root / ".claude" / "skills" / "aidd").exists():
        skill.append(".claude/skills/aidd")
    try:
        if HOOK_COMMAND in (root / ".claude" / "settings.json").read_text(encoding="utf-8", errors="replace"):
            skill.append(".claude/settings.json")
    except OSError:
        pass
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError, AttributeError):
        servers = {}
    if isinstance(servers, dict) and "aidd" in servers:
        skill.append(".mcp.json")
    shipped = [rel for rel in team_files([], True) if rel.startswith(".claude/")]
    team = [f".claude/{d}" for d in ("agents", "commands", "skills") if any(rel.startswith(f".claude/{d}/") and (root / rel).is_file() for rel in shipped)]
    return skill, team


def plugin_fallback_note(root: Path, installed: list[str], why: str = "missing") -> str:
    """What `aidd init --claude-plugins` says when it wired the repository instead of the plugins: what Claude Code now
    loads from the repository, that those files replace the plugins, and how to switch to the plugins later. It never
    says to install the plugins as well: the skill and the roles would load twice (`aidd doctor` warns)."""
    skill, team = claude_repo_files(root)
    files = [*skill, *(f"{d}/{TEAM_PREFIX}*" for d in team)]
    undo = (
        (" Uninstall the plugins this run installed or found already installed: " + ", ".join(f"`claude plugin uninstall {p}`" for p in installed) + ".")
        if installed
        else ""
    )
    cause = (
        "the `claude` CLI is missing, so install the `claude` CLI"
        if why == "missing"
        else "the install failed, so see the `failed` line above and fix its cause"
    )
    return (
        f"fallback Claude Code loads aidd from the repository files instead: {', '.join(files) or 'none'}. These files replace the plugins, "
        f"so do not also install the plugins: the skill and the roles would load twice.{undo} To use the plugins instead: {cause}, "
        "run `aidd uninstall --yes`, then run the same `aidd init` again with `--claude-plugins`. "
        f"Init then adds the marketplace, as /plugin marketplace add {MARKETPLACE_REPO} does in Claude Code, and installs the plugins"
    )


TEAM_MARK = "<!-- aidd-team -->"
TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`
# The roles reference an installed agent file points to for its standards and practice skills: without the plugin,
# the team skill is not installed, so the reference is written into the repository, readable by every harness.
TEAM_ROLES_REF = ".aidd/team-roles.md"


def _team_text(text: str) -> str:
    """A plugin file as a project file: `aidd-team:<name>` becomes `aidd-<name>`, and the front matter's `name` gains the prefix.
    Project agents and skills are not namespaced by a plugin, so an unprefixed `code-review` or `developer` would
    collide with a built-in or a project's own agent, and the guard treats only `aidd-<role>` as a role.
    """
    text = text.replace(docs.ROLE_REFERENCE, f"the team roles reference (`{TEAM_ROLES_REF}`)")
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
    note = agentmodels.unsupported_note(model) if model and not value and model != agentmodels.INHERIT else None
    if harness == "codex":  # .codex/agents/<name>.toml: name, description, developer_instructions, and `model`
        lines = [f"name = {json.dumps(name)}", f"description = {json.dumps(desc)}"]
        if value:
            lines.append(f"model = {json.dumps(value)}")
        if note:
            lines.append(f"# {note}")
        if not writes:  # a read-only role may run commands (git diff, the tests); the sandbox still keeps its writes out
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
    if out:
        out[TEAM_ROLES_REF] = _team_text((team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8"))
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
    """Bring what aidd wrote into a repository up to this aidd: the vendored skill and its copies, the team files already installed, the
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
    for d in DEFAULT_LINKS:  # a copy `aidd init` made where symlinks are unavailable
        link = root / d / "aidd"
        if link.is_dir() and not link.is_symlink() and (link / "SKILL.md").is_file() and _tree_diff(resources.data_dir("skill"), link):
            actions.append(f"{verb} {_shown(link)} (a copy of the skill, to aidd {__version__})")
            if yes:
                shutil.rmtree(link)
                shutil.copytree(resources.data_dir("skill"), link)
    everything = team_files(list(NATIVE_AGENT_HARNESSES), True)
    installed = [rel for rel in everything if (root / rel).is_file()]
    if installed:
        claude = any(rel.startswith(".claude/") for rel in installed)
        harnesses = [h for h in NATIVE_AGENT_HARNESSES if any(rel in team_files([h], False) and rel != TEAM_ROLES_REF for rel in installed)]
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
        from . import standards

        text = cfg.read_text(encoding="utf-8")
        new = re.sub(r'^aidd_version = "[^"]*"', f'aidd_version = "{__version__}"', text, count=1, flags=re.M)
        docs_dir = globs.normal_dir(str((model.parse_toml(new, cfgmod.CONFIG_PATH).get("docs") or {}).get("dir") or "docs"))
        # The copies of library standards: an unedited one is refreshed from this aidd's library, an edited one is kept.
        refreshed, files, notes = standards.refresh(root, new, docs_dir)
        for rel, content, why in files:
            if content is None:
                if (root / rel).is_file():
                    actions.append(f"{'removed ' if yes else 'would remove'} {_shown(root / rel)} ({why})")
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
            appr, rev = owners.get("approvers", []), owners.get("specialists", owners.get("reviewers"))
            expected = config_text(
                raw.get("profile", "solo"),
                approvers=appr,
                specialists=rev,
                test=t_cmd,
                policy=pol,
                mode=raw.get("mode"),
                goal=raw.get("goal"),
                default_team=owners.get("default_team"),
                ui=(((raw.get("project") or {}).get("defaults") or {}).get("off") or {}).get("dark_mode") != project.NO_UI,
                existing_code=(((raw.get("project") or {}).get("defaults") or {}).get("off") or {}).get("modular_monolith") == project.EXISTING_STRUCTURE,
                repo=(raw.get("project") or {}).get("repo"),
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
        ours = {("PreToolUse", "pre-tool"), *SESSION_EVENTS.items()}
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

    for name in (*GITHUB_WORKFLOWS, SECURITY_WORKFLOW):
        remove_if(root / ".github" / "workflows" / name, ci_same(root / ".github" / "workflows" / name, "github", name))
    remove_if(root / DEPENDABOT, same(root / DEPENDABOT, dependabot_text(root)))
    pr_tpl = template("github", "pull_request_template.md")
    for path in (root / ".github" / "pull_request_template.md", root / ".gitlab" / "merge_request_templates" / "Default.md"):
        remove_if(path, same(path, pr_tpl))
    for name in ("aidd.gitlab-ci.yml", GITLAB_SECURITY):
        remove_if(root / ".gitlab" / name, ci_same(root / ".gitlab" / name, "gitlab", name))
    gi = root / ".gitignore"
    if gi.is_file():
        lines = gi.read_text(encoding="utf-8").splitlines()
        if GITIGNORE_LINE in lines or ENV_MARK in lines:
            actions.append(f"{verb} the aidd lines from {_shown(gi)}")
            if yes:
                aidd_lines = {GITIGNORE_LINE, ENV_MARK, *(ENV_IGNORE if ENV_MARK in lines else ())}
                rest = [x for x in lines if x not in aidd_lines]
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


HOOK_COMMAND = "aidd hook pre-tool"  # the bare form, written when `aidd` is on PATH; every form ends with it
# The same tools the aidd plugin's hooks/hooks.json matches: the edits, Bash and PowerShell for the shell check, and the
# MCP tools that could approve or merge: a name with a word the guard denies on (merge, approve, accept, complete, status,
# review) or a channel an `/aidd approve` line could travel through (a comment, note, discussion, thread, reply, issue,
# pull or merge request, PR or MR, commit, push, or file), in any case style. A browser or a docs search never starts
# the guard. Claude Code tests the name as a case-sensitive regular expression.
_MCP_WORDS = (
    "merge",
    "approv",
    "accept",
    "complete",
    "status",
    "review",
    "comment",
    "note",
    "discussion",
    "thread",
    "reply",
    "issue",
    "pull",
    "request",
    "commit",
    "push",
    "file",
)
_MCP_PR = r"(?:_|-)(?:[Pp][Rr]|[Mm][Rr])s?(?:_|-|$)|(?<=[a-z])(?:Pr|PR|Mr|MR)(?:[A-Z_-]|s?$)"  # no `](`: Markdown would read a link
HOOK_MATCHER = (
    "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*(?:"
    + "|".join(f"[{w[0].upper()}{w[0]}]{w[1:]}|{w.upper()}" for w in _MCP_WORDS)
    + f"|{_MCP_PR}).*"
)
# The session hooks: advisory helpers, so each fails open (`|| true`, `; exit 0` in PowerShell): an aidd too old to know the hook, or missing,
# never blocks a session or a stop. `aidd hook stop` at level strict blocks through its JSON decision, which Claude
# Code reads on exit 0. PreCompact saves the state of the work in the git directory; its output cannot add context, so
# session-start reads the state back (see aidd.hooks). UserPromptSubmit adds the next step to each prompt.
SESSION_EVENTS = {"SessionStart": "session-start", "Stop": "stop", "SubagentStop": "stop", "UserPromptSubmit": "prompt-submit", "PreCompact": "pre-compact"}
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
# `pre-edit` is the guard hook's earlier name. Adopters' settings still call it, so it is read as `pre-tool`.
HOOK_ALIASES = {"pre-edit": "pre-tool"}
_AIDD_HOOK = re.compile(r"(?<![\w-])aidd hook (pre-tool|pre-edit|session-start|prompt-submit|stop|pre-compact)(?![\w-])")


def aidd_hook(command) -> str | None:
    """Which aidd hook a settings command runs (`pre-tool`, `session-start`, `prompt-submit`, `stop`, `pre-compact`), whatever
    launcher it names, with an alias read as its hook; else None."""
    m = _AIDD_HOOK.search(command) if isinstance(command, str) else None
    return HOOK_ALIASES.get(m.group(1), m.group(1)) if m else None


def _on_default_path(directory: str) -> bool:
    """Whether an isolated interpreter (`-I`: no user site) imports from `directory` as is: a site-packages directory."""
    import site

    return any(Path(d).resolve() == Path(directory).resolve() for d in site.getsitepackages() if d)


# Starts aidd from an explicit source folder, as `python -I -c LOADER <src> aidd <args>`. `-I` keeps the working
# directory (the repository) and every PYTHON* variable off sys.path, so a repository cannot replace aidd or a module it
# imports. It holds no quote, so it passes unchanged through sh, PowerShell, and JSON. The plugin's hooks use it too:
# on a Python older than 3.11 it exits 3 before it reads stdin, and the plugin then runs it with a Python uv finds.
LOADER = "import sys; sys.version_info < (3, 11) and sys.exit(3); sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = sys.argv.pop(1); from aidd.cli import main; sys.exit(main())"


def launcher() -> tuple[list[str], dict[str, str]]:
    """How a hook or the MCP server starts this aidd, resolved when init runs: this interpreter by its absolute path,
    isolated (`-I`), with `-m aidd` when aidd is installed in its site-packages, else LOADER and the source it runs from
    (an install from a checkout or a pyz, which `-I` would not find through PYTHONPATH). Never the bare `aidd` on PATH:
    its console script runs without `-I`, so a PYTHONPATH from the project's settings could replace aidd's modules.
    (argv, extra environment): the environment is always empty."""
    src = str(Path(__file__).resolve().parent.parent)
    python = os.path.normpath(os.path.abspath(sys.executable))  # never resolved: a venv's python is a link into it
    return ([python, "-I", "-m", "aidd"] if _on_default_path(src) else [python, "-I", "-c", LOADER, src, "aidd"]), {}


def _absolute(path: str) -> bool:
    """An absolute path on this OS: init writes the interpreter's full path. A drive or UNC form (`C:\\...`,
    `\\\\server\\...`) counts only on Windows, where it is one."""
    return os.path.isabs(path) or (os.name == "nt" and re.match(r"[A-Za-z]:[\\/]|\\\\", path) is not None)


def isolated_launcher(words: list[str]) -> bool:
    """Whether a launcher's argv (before `hook ...` or `mcp`) is one a repository cannot hijack: an interpreter by its
    absolute path, run with `-I` and `-m aidd` or LOADER. A bare `aidd` or `python3` is found through PATH, and a Python
    run without `-I` reads PYTHONPATH and puts the working directory first on sys.path."""
    if not words or not _absolute(words[0]):
        return False
    return words[1:] == ["-I", "-m", "aidd"] or (len(words) == 6 and words[1:4] == ["-I", "-c", LOADER] and words[5] == "aidd")


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
    return f"{_shell_launcher(argv, env, shell)} hook {sub}" + ("" if HOOK_ALIASES.get(sub, sub) == "pre-tool" else _FAIL_OPEN[shell])


def _shell_field() -> str | None:
    """The `shell` field init writes on a hook entry: PowerShell on Windows, none elsewhere."""
    return WINDOWS_HOOK_SHELL if _hook_shell() == WINDOWS_HOOK_SHELL else None


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


def _hook_repair(root: Path, command: str, sub: str, shell: str | None = None) -> str | None:
    """Why init replaces a configured aidd hook: doctor would not run it (`_launch_shape`: inside the repository, extra
    words, not isolated) or it is not exactly what init writes. None when it may stay."""
    parsed = _parse_hook(command, sub)
    if parsed is None:
        return "it does not parse"
    return _launch_shape(root, *parsed, parsed[0][-2:]) or (None if _written_by_init(command, sub, parsed, shell) else NOT_INIT_WRITTEN)


NOT_INIT_WRITTEN = "it is not a command `aidd init` writes; `aidd init --agent-hooks` repairs it"


def _written_by_init(command: str, sub: str, parsed: tuple[list[str], dict[str, str]], shell: str | None = None) -> bool:
    """Whether `command` is exactly what `hook_command` renders for its parsed launcher in the shell that runs it: the
    entry's `shell` (`"powershell"`, which counts only on Windows), else sh. Doctor trusts the parse only then: a parser
    and a shell can read one string two ways (`...; other; exit 0`), and a PowerShell command under sh fails to parse,
    a non-blocking error that would leave the guard off."""
    words, env = parsed
    if words[-2] != "hook" or HOOK_ALIASES.get(words[-1], words[-1]) != sub:
        return False
    if shell == WINDOWS_HOOK_SHELL and os.name != "nt":
        return False
    return command.strip() == hook_command(words[-1], (words[:-2], env), WINDOWS_HOOK_SHELL if shell == WINDOWS_HOOK_SHELL else "sh")


def _mcp_written_by_init(server: dict) -> bool:
    """Whether an .mcp.json entry is one `mcp_server` writes: an isolated launcher (`isolated_launcher`) and `mcp`, and
    no environment, since init writes none. Other keys (such as `"type": "stdio"`) are the client's and do not count."""
    command, args, env = server.get("command"), server.get("args"), server.get("env")
    if not isinstance(command, str) or not isinstance(args, list) or not args or args[-1] != "mcp" or env:
        return False
    return isolated_launcher([command, *map(str, args[:-1])])


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


def claude_config_dir() -> Path:
    """Claude Code's user folder: CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def plugins_enabled(root: Path) -> set[str]:
    """The plugins Claude Code enables in this repository, from `enabledPlugins` in the user's settings, then the
    project's `.claude/settings.json`, then `.claude/settings.local.json`: a later file decides over an earlier one.
    Managed settings and a plugin installed but not named in any of them are not seen."""
    on: dict[str, bool] = {}
    for path in claude_settings_paths(root):
        try:
            enabled = json.loads(path.read_text(encoding="utf-8")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(enabled, dict):
            on.update({k: v is True for k, v in enabled.items()})
    return {k for k, v in on.items() if v}


def claude_settings_paths(root: Path) -> list[Path]:
    """The Claude Code settings files `plugins_enabled` reads, in the order a later one decides over an earlier one."""
    return [claude_config_dir() / "settings.json", root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]


def unreadable_claude_settings(root: Path) -> list[Path]:
    """The Claude Code settings files that exist but cannot be read, such as one without read permission."""
    out = []
    for path in claude_settings_paths(root):
        try:
            path.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            out.append(path)
    return out


def plugin_double_load(root: Path, label: str) -> list[tuple[str, str]]:
    """A warning for each aidd plugin enabled here whose part the repository files also carry: Claude Code loads both.
    A settings file it cannot read is a warning too, never a crash."""
    out: list[tuple[str, str]] = [
        ("warn", f"{label}: aidd cannot read {path}, so it cannot tell which plugins are enabled; check the file's permissions")
        for path in unreadable_claude_settings(root)
    ]
    on = plugins_enabled(root)
    skill, team = claude_repo_files(root)
    fix = "Keep one: remove the repository files (`aidd uninstall` lists them), or turn the plugin off"
    if f"aidd@{MARKETPLACE}" in on and ".claude/skills/aidd" in skill:
        out.append(
            (
                "warn",
                f"{label}: the aidd plugin (aidd@{MARKETPLACE}) is enabled and {', '.join(skill)} also carry what the plugin carries (the skill, the guard hook, the MCP server), so it would load twice. {fix}",
            )
        )
    if f"aidd-team@{MARKETPLACE}" in on and team:
        out.append(
            (
                "warn",
                f"{label}: the aidd-team plugin (aidd-team@{MARKETPLACE}) is enabled and {', '.join(team)} also hold the roles, so they would load twice. {fix}",
            )
        )
    return out


def _local_first(root: Path) -> bool:
    """The local gate is the gate here (no remote, or no CI gate): see localctx.platform_of."""
    from .localctx import platform_of

    return (root / ".git").exists() and platform_of(str(root)) == "local"


def team_installed(root: Path) -> bool:
    """The aidd-team roles are here: `aidd init --team` wrote their AGENTS.md section, or the aidd-team plugin is enabled."""
    agents = root / "AGENTS.md"
    if agents.is_file() and TEAM_MARK in agents.read_text(encoding="utf-8", errors="replace"):
        return True
    for name in ("settings.json", "settings.local.json"):
        try:
            enabled = json.loads((root / ".claude" / name).read_text(encoding="utf-8")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(enabled, dict) and enabled.get(f"aidd-team@{MARKETPLACE}") is True:
            return True
    return False


def session_hooks_wired(settings: Path) -> list[str]:
    """The SESSION_EVENTS a Claude Code settings file wires."""
    missing = session_hooks_missing(settings)
    return [event for event in SESSION_EVENTS if event not in missing]


def install_agent_hooks(root: Path, actions: list[str]) -> None:
    """Claude Code: the guard as a PreToolUse hook, and `aidd mcp` as a project MCP server. Both start aidd through `launcher()`, resolved now: this interpreter by its absolute path, isolated (`-I`). Both files
    are merged, never overwritten; an aidd entry whose program does not resolve on this machine is repaired. The
    plugin ships the same wiring for plugin users; when the project enables the aidd plugin, the session hooks are
    left to it, so they do not run twice.
    """
    resolved = launcher()
    pre_command = hook_command("pre-tool", resolved)
    if (why := _launch_shape(root, [*resolved[0], "hook", "pre-tool"], resolved[1], ["hook", "pre-tool"])) and "inside the repository" in why:
        # aidd installed into the project's own environment (its `.venv`): the repository can change that interpreter.
        actions.append(
            f"warn     aidd runs from {resolved[0][0]}, inside this repository, so `aidd doctor` will not trust the hook. "
            "Install aidd with `uv tool install` or `pipx`, then run `aidd init --agent-hooks`"
        )
    settings = root / ".claude" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except ValueError:
        actions.append(f"kept     {_shown(settings)} (not valid JSON; add the aidd hook by hand)")
        data = None
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", []) if data is not None else None
    ours = [entry for entry in pre or [] if any(aidd_hook(h.get("command")) == "pre-tool" for h in entry.get("hooks", []))]
    changed = False
    if pre is not None and ours:
        notes = []
        if not all(entry.get("matcher") == HOOK_MATCHER for entry in ours):
            # An older init matched fewer tools (edits only, or no PowerShell and MCP tools).
            for entry in ours:
                entry["matcher"] = HOOK_MATCHER
            notes.append("the aidd hook now matches every tool it checks")
        for h in (h for entry in ours for h in entry.get("hooks", []) if aidd_hook(h.get("command")) == "pre-tool"):
            if h["command"] == pre_command and h.get("shell") == _shell_field():
                continue
            if not _resolves(_command_program(h["command"])):
                _rewire(h, pre_command)
                notes.append(f"the aidd hook's launcher did not resolve here; it runs {pre_command}")
            elif why := _hook_repair(root, h["command"], "pre-tool", h.get("shell")):
                _rewire(h, pre_command)
                notes.append(f"the aidd hook's launcher was not one doctor runs ({why}); it runs {pre_command}")
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
                want = hook_command(sub, resolved)
                same = h["command"] == want and h.get("shell") == _shell_field()
                if not same and (not _resolves(_command_program(h["command"])) or _hook_repair(root, h["command"], sub, h.get("shell"))):
                    _rewire(h, want)
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
    args = current.get("args") if isinstance(current, dict) else None
    words = [str(current.get("command")), *map(str, args[:-1])] if isinstance(current, dict) and isinstance(args, list) else []
    shape = _launch_shape(root, [*words, "mcp"], {}, ["mcp"]) if words else "no entry"
    if isinstance(current, dict) and (current == mcp_server(resolved) or (_resolves(current.get("command")) and not shape and _mcp_written_by_init(current))):
        actions.append(f"kept     {_shown(mcp_file)} (the aidd server is there)")
        return
    servers["aidd"] = mcp_server(resolved)
    mcp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    shown = " ".join([*resolved[0], "mcp"])
    why = ", its launcher did not resolve here or ran Python without -I)" if current else ")"
    actions.append(f"updated  {_shown(mcp_file)} (MCP server: {shown}{why}")


# A harmless event for the guard hook: a Read, which the guard never decides on.
_PROBE_EVENT = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "README.md"}}
_MCP_PROBE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}


def _launch_shape(root: Path, words: list[str], env: dict[str, str], tail: list[str]) -> str | None:
    """Why doctor will not run this launcher, or None when it has the shape init writes: an isolated Python (`-I`) by
    its absolute path, with `-m aidd <tail>` or LOADER and its source folder, every path outside the repository. `aidd doctor` runs it, so a
    command the repository chose (a file inside it, another program) never runs."""
    if set(env) - {"PYTHONPATH"}:
        return f"it sets {', '.join(sorted(set(env) - {'PYTHONPATH'}))}"
    top = root.resolve()
    paths = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not words:
        return "it names no program"
    program, name = words[0], Path(words[0]).name
    here = Path(os.path.abspath(root))

    def inside(p: str) -> bool:
        q = Path(p) if _absolute(p) else root / p
        # Both as written and with links resolved: a repository's `.venv/bin/python` links to a Python outside it.
        # Each parent is compared as a file (samefile), not as text, so a case-changed path or a macOS firmlink counts.
        for path in (Path(os.path.normpath(os.path.abspath(q))), q.resolve()):
            if path.is_relative_to(here) or path.is_relative_to(top):
                return True
            for parent in (path, *path.parents):
                try:
                    if os.path.samefile(parent, top):
                        return True
                except OSError:
                    continue
        return False

    if _absolute(program) and inside(program):
        return f"{program} is inside the repository"
    repair = "`aidd init --agent-hooks` repairs it"
    if name in ("aidd", "aidd.exe") and words[1:] == tail:
        return f"it runs `aidd` without -I, so a PYTHONPATH from the project could replace aidd's modules; {repair}"
    is_python = re.fullmatch(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?", name)
    if is_python and words[1:] == ["-m", "aidd", *tail]:
        return f"it runs Python without -I, so the repository could replace aidd; {repair}"
    python = is_python and words[1:] == ["-I", "-m", "aidd", *tail]
    loader = is_python and len(words) == 6 + len(tail) and words[1:4] == ["-I", "-c", LOADER] and words[5:] == ["aidd", *tail]
    if not python and not loader:
        return "it is not an aidd launcher that init writes"
    if not _absolute(program):
        return f"it finds {program} through PATH, which the project's settings can change; {repair}"
    if loader:
        paths.append(words[4])
    for p in paths:
        if inside(p):
            return f"{p} is inside the repository"
    return None


def _parse_hook(command: str, sub: str) -> tuple[list[str], dict[str, str]] | None:
    parsed = _hook_words(command)
    return parsed if parsed and len(parsed[0]) >= 2 and parsed[0][-2] == "hook" and HOOK_ALIASES.get(parsed[0][-1], parsed[0][-1]) == sub else None


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


def run_hook_probe(root: Path, command: str, timeout: int = 20, shell: str | None = None) -> str | None:
    """Run the configured guard hook command once with a harmless event; None when it runs, else why not."""
    parsed = _parse_hook(command, "pre-tool")
    if parsed is None:
        return "it does not parse as an aidd hook command"
    words, env = parsed
    why = _launch_shape(root, words, env, words[-2:]) or (None if _written_by_init(command, "pre-tool", parsed, shell) else NOT_INIT_WRITTEN)
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
    why = _launch_shape(root, words, env, ["mcp"]) or (None if _mcp_written_by_init(server) else NOT_INIT_WRITTEN)
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
    """Claude Code's repository wiring: the guard hook and the MCP server are configured, their launchers resolve on
    this machine, and, with `execute` (`aidd doctor`), each one actually starts. A wiring that cannot run is a failure:
    the guard would silently not guard."""
    label = HARNESSES["claude-code"].label
    fix = "`aidd init --agent-hooks` repairs a launcher that does not resolve (it runs this Python by its absolute path, isolated)"
    out: list[tuple[str, str]] = []
    settings = root / ".claude" / "settings.json"
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {}) if settings.is_file() else {}
    except (OSError, ValueError, AttributeError):  # an unreadable file: `plugin_double_load` warns about it
        hooks = {}
    pre = [
        (h["command"], h.get("shell"))
        for e in (hooks.get("PreToolUse") or [] if isinstance(hooks, dict) else [])
        if isinstance(e, dict)
        for h in e.get("hooks", []) or []
        if isinstance(h, dict) and aidd_hook(h.get("command")) == "pre-tool"
    ]
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {}) if (root / ".mcp.json").is_file() else {}
    except (ValueError, AttributeError):
        servers = {}
    server = servers.get("aidd") if isinstance(servers, dict) else None
    plugin = plugin_enabled(root)
    by_plugin = ("ok", f"{label}: the aidd plugin is enabled; it carries the guard hook, the session hooks, and the MCP server")
    if not pre and not isinstance(server, dict):
        unwired = f"{label} is in use, but the guard hook and the MCP server are not wired: `aidd init --agent-hooks`, or install the aidd plugin"
        return [by_plugin if plugin else ("warn", unwired)]
    broken, missing = [], []
    for command, shell in pre:
        parsed = _parse_hook(command, "pre-tool")
        # A launcher doctor will not run (one inside the repository) is refused before PATH is asked: whether it
        # resolves differs by OS (Windows finds no file without an extension), and the answer is the same either way.
        refused = parsed and (
            _launch_shape(root, *parsed, parsed[0][-2:]) or (None if _written_by_init(command, "pre-tool", parsed, shell) else NOT_INIT_WRITTEN)
        )
        if execute and refused:
            broken.append(f"the guard hook `{command}` does not run (not run: {refused})")
        elif not _resolves(_command_program(command)):
            broken.append(f"the guard hook `{command}` names a program not found here")
        elif execute and (why := run_hook_probe(root, command, shell=shell)):
            broken.append(f"the guard hook `{command}` does not run ({why})")
    if not isinstance(server, dict):
        missing.append("the MCP server is not in .mcp.json")
    elif not _resolves(server.get("command")):
        broken.append(f"the MCP server's command {server.get('command')!r} is not found here")
    elif execute and (why := run_mcp_probe(root, server)):
        broken.append(f"the MCP server does not start ({why})")
    if not pre:
        missing.insert(0, "the guard hook is not wired")
    if broken:
        out.append(("fail", f"{label}: " + "; ".join(broken) + f"; {fix}"))
    if missing and not plugin:
        out.append(("warn", f"{label}: " + "; ".join(missing) + ": `aidd init --agent-hooks`, or install the aidd plugin"))
    if not broken and not missing:
        out.append(("ok", f"{label}: the guard hook and the MCP server are wired" + (", and both start" if execute else "") + f". {RESTART_BEFORE_INIT}"))
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


def standard_checks(root: Path, cfg: cfgmod.Config) -> list[tuple[str, str]]:
    """Each `[[standards]]` entry must name a document that exists, roles the team has, and tests the suite runs. Then
    the copies of library standards and the company's `[standards_policy]` (standards.doctor_checks)."""
    from . import standards

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
        types = {t: sum(1 for s in cfg.standards if s.get("type", "opinionated") == t) for t in ("opinionated", "industry")}
        kinds = ", ".join(f"{n} {t}" for t, n in types.items() if n)
        out.append(("ok", f"standards: {len(cfg.standards)} ({kinds}), {enforced} enforced by tests; `aidd owners` lists them by role"))
    return out + standards.doctor_checks(root, cfg)


def runbook_checks(root: Path, cfg: cfgmod.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A runbook in use must have been run lately: warn when its tested_on is older than runbook_max_age_days."""
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
        if data.get("restore"):
            out += _restore_drill(rel, data, today, max_age)
            continue
        last = data.get("tested_on")
        if not last:
            if data.get("status") == "active":
                out.append(("warn", f"{rel}: active runbook {data.get('id')} has never been tested; run it in a drill and record tested_on"))
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: tested_on {last!r} is not a date"))
            continue
        if age > max_age:
            when = f"last tested {last}, {age} days ago (limit {max_age})"
            out.append(("warn", f"{rel}: runbook {data.get('id')} was {when}; run it again and update tested_on"))
    return out


def review_checks(root: Path, cfg: cfgmod.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A living doc that records `reviewed_on` in its front matter must have been reviewed lately: warn when the date is
    older than `[docs] max_review_age_days`. The living docs are the repository's own (REPO_DOCS) and each doc a Spec
    links with `frozen = false`, except a runbook (runbook_checks reads its `tested_on`). The date is optional."""
    today = today or dt.date.today()
    max_age = cfg.max_review_age_days if cfg else cfgmod.MAX_REVIEW_AGE_DAYS
    docs_dir, specs_dir = (cfg.docs_dir, cfg.specs_dir) if cfg else ("docs", "specs")
    paths = [rel.replace("{docs}", docs_dir) for files in REPO_DOCS.values() for rel, tpl in files if tpl.endswith(".md")]
    for p in object_files(root, specs_dir):
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8"), p.name)
        except (OSError, UnicodeDecodeError, model.ModelError):
            continue
        if data.get("kind") == "spec":
            linked = [d for d in data.get("docs") or [] if isinstance(d, dict) and d.get("frozen") is False and d.get("kind") != "runbook"]
            paths += [str(d["path"]) for d in linked if d.get("path")]
    out: list[tuple[str, str]] = []
    for rel in dict.fromkeys(paths):
        p = root / rel
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or not _is_object(p):
            continue
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeDecodeError, model.ModelError) as exc:
            out.append(("warn", f"{rel}: {exc}"))
            continue
        last = data.get("reviewed_on")
        if not last:
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: reviewed_on {last!r} is not a date"))
            continue
        if age > max_age:
            out.append(
                (
                    "warn",
                    f"{rel}: last reviewed {last}, {age} days ago (limit {max_age}); a person reviews it, fixes or deletes what is stale, and updates reviewed_on",
                )
            )
    return out


def _restore_drill(rel: str, data: dict, today: dt.date, max_age: int) -> list[tuple[str, str]]:
    """A restore runbook (`restore = true`): it states its RTO and RPO, and a person drills the restore within
    runbook_max_age_days (`tested_on`), draft or active, since a backup nobody restored is not yet a backup."""
    rid = data.get("id")
    out: list[tuple[str, str]] = []
    if not (data.get("rto") and data.get("rpo")):
        out.append(("warn", f"{rel}: restore runbook {rid} states no rto and rpo; write the recovery time and recovery point objectives it must meet"))
    last = data.get("tested_on")
    if not last:
        out.append(
            ("warn", f"{rel}: restore runbook {rid} has never had a restore drill; restore from a backup into a scratch environment and record tested_on")
        )
        return out
    try:
        age = (today - dt.date.fromisoformat(str(last))).days
    except ValueError:
        return out + [("warn", f"{rel}: tested_on {last!r} is not a date")]
    if age > max_age:
        when = f"last ran {last}, {age} days ago (limit {max_age})"
        out.append(("warn", f"{rel}: the restore drill of runbook {rid} {when}; restore from a backup again, check the RTO and RPO held, and update tested_on"))
    return out


def _delegate_check(root: Path, cfg: cfgmod.Config) -> tuple[str, str] | None:
    """`[agents] delegate = "always"` with no aidd-team role installed: a fail when the config sets it (the guard denies
    every main-session edit, with no role to hand it to), information when it is the profile's default (no effect)."""
    from .guard import team_installed

    if cfgmod.delegate_mode(cfg.raw) != "always" or team_installed(str(root)):
        return None
    if cfgmod.delegate_set(cfg.raw):
        return "fail", (
            '[agents] delegate = "always", and no aidd-team role is installed: the guard denies every main-session '
            'edit of repository content, with no role to hand it to. Run `aidd init --team` (or install the aidd-team plugin), or set delegate = "auto"'
        )
    return "info", (
        f'[agents] delegate: the {cfg.profile} profile starts at "always", which applies only when the team is installed. '
        'Without it, the guard acts as "auto". Run `aidd init --team` to apply it'
    )


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed; only the aidd plugins' double-load check also
    reads the user's Claude Code settings (`plugins_enabled`). `execute` (the `aidd doctor` command) also
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
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root), skip_unread=True)  # an unread URL parent warns
            ok(f"config: profile {cfg.profile}")
            for w in cfg.warnings + cfgmod.advice(cfg):
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
        elif cfg.profile == "solo" and _local_first(root):
            # Solo: the person at this machine is the Approver, and a local approval counts as their git email.
            email = (operator_email(root) or "").lower()
            if email and f"email:{email}" not in {util.norm(a) for a in cfg.approvers}:
                warn(
                    f"local-first: an approval from this machine counts as email:{email}, which owners.approvers ({', '.join(cfg.approvers)}) "
                    f'does not list. So `aidd approve` would record approvals the gate never counts. Add "email:{email}" to owners.approvers'
                )
        if cfg.gates["specialist_approvals"] and not cfg.specialists:
            warn(f"profile {cfg.profile} needs owners.specialists (a security pool at least) before any major change can ship")
        if cfg.gates["separation_of_duties"]:
            # An author never approves their own change: a pool of one person cannot approve that person's major change.
            for pool, who in sorted(cfg.specialists.items()):
                if len(who) == 1 and "/" not in who[0]:
                    warn(
                        f"owners.specialists.{pool} has one member ({who[0]}), who can never approve a change they authored; "
                        "name at least two people in every specialist pool"
                    )
        if cfg.gates["policy_required_routes"] and not cfg.policy_command:
            fail(
                f"profile {cfg.profile} requires policy.command for {', '.join(cfg.gates['policy_required_routes'])}; "
                "set it (aidd init --policy), or run `AIDD_ORG_PRESET=<preset.toml> aidd doctor` when the org preset binds it"
            )
        delegate_line = _delegate_check(root, cfg)
        if delegate_line:
            out.append(delegate_line)
        for gate in cfg.get("guard", "held_commands", default=[]) or []:
            until = f", until a person sets {gate['requires']}" if gate.get("requires") else ""
            ok(f"held for a person: `{gate.get('name')}` ({' '.join(gate.get('match', []))}){until}")
        if not (root / cfg.specs_dir).is_dir():
            warn(f"no {cfg.specs_dir}/ directory yet")
        # A team of people and agents steers by one written goal and reviews by one rubric.
        if cfg.get("goal"):
            ok(f"goal: {cfg.get('goal')}")
        rubric = f"{REVIEW_POLICY}: the rubric every reviewer follows"
        say((root / REVIEW_POLICY).is_file(), rubric, f"no {REVIEW_POLICY}: the rubric every reviewer, human or agent, follows; `aidd init` writes one")
        out.extend(standard_checks(root, cfg))
        for w in agentmodels.independent_review_warnings(cfg.get("agents", "models", default={}) or {}, bool(cfg.get("agents", "independent_review"))):
            warn(w)
        for w in agentmodels.unknown_key_warnings(cfg.get("agents", "models", default={}) or {}):
            warn(w)
    out.extend(runbook_checks(root, cfg, today=today))
    out.extend(review_checks(root, cfg, today=today))
    skill = root / SKILL_REL
    if not (skill / "SKILL.md").is_file():
        warn(f"no vendored skill at {SKILL_REL}: fine if every agent loads the aidd plugin; otherwise run `aidd init`")
    else:
        bundled = resources.data_dir("skill")
        if skill.resolve() == bundled.resolve():
            ok("skill: this repository is the source")
        else:
            diff = _tree_diff(bundled, skill)
            say(
                not diff, f"skill matches aidd {__version__}", f"skill differs from aidd {__version__}: {', '.join(diff[:5])}; `aidd upgrade --yes` upgrades it"
            )
    for d in DEFAULT_LINKS if "claude-code" in detect_harnesses(root) else ():
        link = root / d / "aidd"
        if link.is_symlink() and (link / "SKILL.md").is_file():
            ok(f"{link.relative_to(root)} resolves")
        elif link.is_dir() and (link / "SKILL.md").is_file() and (skill / "SKILL.md").is_file():
            rel = link.relative_to(root)
            say(not _tree_diff(skill, link), f"{rel} is a copy that matches", f"{rel} is a stale copy; `aidd upgrade --yes` refreshes it")
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
            try:
                hooked = settings.is_file() and HOOK_COMMAND in settings.read_text(encoding="utf-8")  # every launcher's command ends with it
            except OSError:
                hooked = False
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
    if "claude-code" in detected:
        out.extend(plugin_double_load(root, HARNESSES["claude-code"].label))
    if not detected:
        ok(
            "no coding agent's own files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them (`aidd init --harness <agent>` wires one)"
        )
    if cfg and cfg.profile == "regulated" and "claude-code" in detected:
        managed = managed_settings_sources()
        say(
            managed,
            f"Claude Code managed settings present ({', '.join(managed)}); `/status` in Claude Code names the one in force",
            "profile regulated, but this machine carries no Claude Code managed settings. So each developer's own settings "
            f"decide permissions, the sandbox, and hooks. Deploy aidd's {MANAGED_SETTINGS_TEMPLATE} through MDM or the admin console "
            "(docs/ENTERPRISE.md). A claude.ai console policy not fetched yet is invisible here: check `/status`",
        )
    wf = root / ".github" / "workflows"
    if (wf / "aidd-gate.yml").is_file() and (wf / "aidd-tests.yml").is_file():
        ok("GitHub workflows present; require the `aidd/gate` status on the protected branch")
        from . import github  # best effort: says it skipped when offline or without a token

        out.extend(github.protection_checks(str(root)))
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok("GitLab CI include present; enforce it with a pipeline execution policy")
    elif _local_first(root) and not gitutil.run(["remote"], str(root), check=False).split():
        ok("local-first: no remote and no aidd CI, so `aidd gate` and `aidd ship` on this machine are the gate")
    else:
        warn("no aidd CI found; the gate is advisory until CI runs it (with no platform on purpose, `aidd gate` and `aidd ship` are the gate)")
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
    """The Spec template `aidd new spec` writes: the short one (Intent, Context, Acceptance, Design, Policy conflicts, Rollback) for a normal Spec,
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
    if parent and kind in PARENT_KIND:
        found = _kind_of(root, parent, (specs_dir, proposals_dir))
        if found and (why := parent_kind_error(kind, parent, found)):
            raise ValueError(f"{why}; name {KIND_NAMES[PARENT_KIND[kind]]} as --parent")
    today = today or dt.date.today()
    tpl = (resources.data_dir("skill") / "assets" / f"{spec_template(route, full) if kind == 'spec' else kind}.md").read_text(encoding="utf-8")
    quoted = lambda s: json.dumps(s, ensure_ascii=False)[1:-1]  # noqa: E731  # the value sits inside "..." in the template
    values = dict(id=id, title=quoted(title), owner_team=quoted(owner_team or "TODO"), today=today.isoformat())
    if kind == "proposal":
        values |= dict(audience=audience, addressee=quoted(addressee or "TODO: who receives it and decides"))
    elif kind in OPS_DIRS:
        values |= dict(spec=spec or ("none" if kind == "runbook" else "TODO"))
    else:
        values |= dict(route=route, type=ctype, trace_id=id.lower())
    text = fill(tpl, **values)
    if parent and kind not in OPS_DIRS:
        text = text.replace(f'kind = "{kind}"\n', f'kind = "{kind}"\nparent = "{parent}"\n', 1)
    if kind == "spec":
        # `aidd new spec --paths`: the planned paths are the first Task's scope, and the declared risk is the Spec's.
        from .guard import looks_like_test

        tests = [s for s in scope or [] if looks_like_test(s)]
        scope = [s for s in scope or [] if not looks_like_test(s)]
        if scope:
            text = re.sub(r"(?m)^scope = \[[^\]\n]*\]", lambda _: f"scope = {toml_list(scope)}", text, count=1)
        if tests:  # a Task's scope never holds a test file; the Spec freezes it in tests.files
            text = re.sub(r"(?m)^files = \[\"tests/TODO\"\]", lambda _: f"files = {toml_list(tests)}", text, count=1)
        if dimensions:
            text = re.sub(r"(?m)^dimensions = \[\]", lambda _: f"dimensions = {toml_list(dimensions)}", text, count=1)
        if irreversible:
            text = re.sub(r"(?m)^reversible = true", "reversible = false", text, count=1)
    if kind == "spec" and route in ("major", "emergency"):
        # Observe is required on major (and on normal under regulated, where the gate asks for it).
        block = OBSERVE_BLOCK
        if route == "emergency":
            due = (today + dt.timedelta(days=2)).isoformat()
            block += f'\n[emergency]\nseverity = "sev2"\nkind = "outage"\ncommander = "@TODO"\nincident = "INC-TODO"\nreview_due = "{due}"\n'
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


# The linked documents `aidd new <kind> <topic> --spec <ID>` writes, and the template each starts from. The design-spec doc
# is the design spec; `--prototype` writes its HTML prototype instead (PROTOTYPE), one file per Spec or flow in the design
# folder (`<docs_dir>/design/<area or Spec id>/prototype.html`), linked as the same kind.
DOC_TEMPLATES = {
    "tech-spec": "tech-spec.md",
    "test-plan": "test-plan.md",
    "adr": "adr.md",
    "threat-model": "threat-model.md",
    "authz": "authz-matrix.md",
    "design-spec": "design-spec.md",
    "api": "api.md",
    "slo": "slo.md",
    "compliance": "compliance.md",
    "analytics": "tracking-plan.md",
    "migration": "migration-plan.md",
    "acceptance": "acceptance.md",
    "feedback": "feedback.md",
}
PROTOTYPE = "prototype.html"
# Documents people keep filling after Spec approval: linked as living (`frozen = false`), only checked to exist.
LIVING_DOCS = frozenset({"slo", "acceptance", "data-map", "vendors"})
# Documents that belong to no one Spec, each in its own folder under `<docs_dir>`: the feedback log is a living record
# of what customers said after launch.
UNLINKED_DOCS = frozenset({"feedback"})
UNLINKED_FOLDERS = {"feedback": "feedback"}


# One per repository, never per Spec: `aidd new <kind>` writes each file (repository path, with {docs} for the configured
# docs folder, and its template). The glossary holds the project's terms, one meaning each, for every writer. Living documents: each later change to one is a change of its own. A Spec that
# touches personal data or a vendor links the data map or the vendor register as a living `[[docs]]` entry. The design
# system's build script (dependency-free Node) writes its CSS and DESIGN.md's token mirror, and checks them for drift.
REPO_DOCS = {
    "design-system": (("DESIGN.md", "DESIGN.md"), ("design/tokens.json", "tokens.json"), ("design/build.mjs", "design-build.mjs")),
    "architecture": (("{docs}/architecture/README.md", "architecture.md"),),
    "data-map": (("{docs}/data-map.md", "data-map.md"),),
    "vendors": (("{docs}/vendors.md", "vendors.md"),),
    "glossary": (("{docs}/GLOSSARY.md", "glossary.md"),),
}
# The engagement's documents, in the accepted proposal's folder: the contract (a statement of work), then each change
# order to it, `change-orders/CO-<n>.md`, from the same template family.
CONTRACT, CHANGE_ORDERS = "contract.md", "change-orders"
# Every kind `aidd new` writes besides the Spec and its containers, the proposal, and the postmortem.
DOC_KINDS_NEW = (*DOC_TEMPLATES, "runbook", *REPO_DOCS, "contract", "exploration")
# The design system's tokens: a Spec's design files that hold their own tokens beside it drift from it.
REPO_TOKENS = "design/tokens.json"


def new_repo_doc(root: Path, *, kind: str, title: str = "", docs_dir: str = "docs", today: dt.date | None = None) -> list[Path]:
    """Write a repository's design system or architecture overview from its templates; refuse when any file exists."""
    targets = [(root / rel.replace("{docs}", docs_dir), tpl) for rel, tpl in REPO_DOCS[kind]]
    taken = [p for p, _ in targets if p.exists()]
    if taken:
        raise FileExistsError(f"{taken[0].relative_to(root).as_posix()} exists: the repository has one {kind}; change it in its own change")
    values = dict(title=title or root.resolve().name, today=(today or dt.date.today()).isoformat())
    for path, tpl in targets:
        text = (resources.data_dir("skill") / "assets" / tpl).read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fill(text, **values) if tpl.endswith(".md") else text, encoding="utf-8")
    return [p for p, _ in targets]


def new_contract(root: Path, proposal_id: str, *, proposals_dir: str = "proposals", today: dt.date | None = None) -> Path:
    """The engagement's contract in the proposal's folder, from its template; once it exists, the next change order."""
    folder = root / proposals_dir / proposal_id
    if not ID_PATTERN.match(proposal_id) or not (folder / "proposal.md").is_file():
        raise ValueError(f"no proposal {proposal_id} in {proposals_dir}/: `aidd new contract <proposal id>` writes the contract of an accepted proposal")
    values = dict(proposal=proposal_id, today=(today or dt.date.today()).isoformat())
    if not (folder / CONTRACT).exists():
        path, tpl = folder / CONTRACT, "contract.md"
    else:
        taken = [int(m.group(1)) for p in (folder / CHANGE_ORDERS).glob("CO-*.md") for m in [re.fullmatch(r"CO-(\d+)\.md", p.name)] if m]
        number = max(taken, default=0) + 1
        path, tpl, values["number"] = folder / CHANGE_ORDERS / f"CO-{number}.md", "change-order.md", str(number)
    text = fill((resources.data_dir("skill") / "assets" / tpl).read_text(encoding="utf-8"), **values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _own_tokens(root: Path, data: dict) -> list[str]:
    """The tokens files a Spec's design files hold, other than the repository's own."""
    found = [f for pattern in (data.get("design") or {}).get("files") or [] for f in _matching(root, str(pattern))]
    return sorted({f for f in found if f != REPO_TOKENS and re.search(r"(?:^|[/.])tokens(?:\.json)?$", f.lower())})


def slug(text: str) -> str:
    """A file-name form of a topic: lowercase words joined by hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "doc"


def find_spec(root: Path, specs_dir: str, spec_id: str) -> Path:
    """The Spec file whose id is `spec_id`: `<specs_dir>/<ID>.md`, else any Spec in the folder that says so."""
    direct = root / specs_dir / f"{spec_id}.md"
    for p in [direct] + [p for p in object_files(root, specs_dir) if p != direct]:
        if not p.is_file():
            continue
        try:
            data, _ = model.split_front_matter(p.read_text(encoding="utf-8"), p.as_posix())
        except model.ModelError:
            continue
        if data.get("kind") == "spec" and data.get("id") == spec_id:
            return p
    raise ValueError(f"no Spec {spec_id} in {specs_dir}/: write it first (`aidd new spec {spec_id} --title ...`), or name an existing one")


def link_doc(spec_path: Path, kind: str, rel: str, *, frozen: bool = True) -> None:
    """Append a `[[docs]]` entry to the Spec's front matter; refuse when the result would not parse."""
    text = spec_path.read_text(encoding="utf-8").lstrip("﻿")
    m = model.FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{spec_path.as_posix()}: missing +++ TOML front matter")
    entry = f'[[docs]]\nkind = "{kind}"\npath = "{rel}"' + ("" if frozen else "\nfrozen = false")
    new = text[: m.start(1)] + m.group(1).rstrip("\n") + "\n\n" + entry + text[m.end(1) :]
    try:
        model.split_front_matter(new, spec_path.as_posix())
    except model.ModelError as exc:
        raise ValueError(f"{spec_path.as_posix()}: cannot add a [[docs]] entry ({exc}); write docs as [[docs]] tables") from exc
    spec_path.write_text(new, encoding="utf-8")


def new_doc(
    root: Path,
    *,
    kind: str,
    topic: str,
    spec_id: str = "",
    area: str = "",
    title: str = "",
    docs_dir: str = "docs",
    specs_dir: str = "specs",
    today: dt.date | None = None,
    link: bool = True,
    prototype: bool = False,
) -> tuple[Path, Path | None]:
    """Write a linked document from its template and link it from the Spec (unless `link` is false: a specialist
    writes its own doc and the Spec's writer adds the `[[docs]]` entry, one writer per file): an ADR as `<docs_dir>/adr/NNNN-<topic>.md`
    with the next number, the design spec's prototype (`prototype`) as `<docs_dir>/design/<area or Spec id>/prototype.html`, the
    design folder, anything else as `<docs_dir>/specs/<area or Spec id>/<kind>-<topic>.md`. The document's header names the Spec (its back-link). Returns the document and the Spec.
    A feedback log has no Spec: it is written as `<docs_dir>/feedback/<topic>.md`, and the Spec returned is None."""
    if kind not in DOC_TEMPLATES:
        raise ValueError(f"no template for {kind!r}; one of {', '.join(DOC_TEMPLATES)}")
    if area and not ID_PATTERN.match(area):
        raise ValueError(f"area {area!r} must be letters, digits, and . _ : - (such as checkout)")
    name = slug(topic)
    values = dict(title=title or topic, today=(today or dt.date.today()).isoformat())
    if prototype and kind != "design-spec":
        raise ValueError("--prototype writes the design spec's HTML prototype: `aidd new design-spec <topic> --spec <ID> --prototype`")
    tpl = (resources.data_dir("skill") / "assets" / (PROTOTYPE if prototype else DOC_TEMPLATES[kind])).read_text(encoding="utf-8")
    if kind in UNLINKED_DOCS:
        path = root / docs_dir / UNLINKED_FOLDERS[kind] / f"{name}.md"
        if path.exists():
            raise FileExistsError(f"{path} exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fill(tpl, **values), encoding="utf-8")
        return path, None
    spec_path = find_spec(root, specs_dir, spec_id)
    values |= dict(spec=spec_id, number="")
    if kind == "adr":
        folder = root / docs_dir / "adr"
        taken = [int(m.group(1)) for p in (folder.iterdir() if folder.is_dir() else []) for m in [re.match(r"(\d{4})-", p.name)] if m]
        number = max(taken, default=0) + 1
        path, values["number"] = folder / f"{number:04d}-{name}.md", f"{number:04d}"
    elif prototype:
        path = root / docs_dir / "design" / (area or spec_id) / PROTOTYPE
    else:
        path = root / docs_dir / "specs" / (area or spec_id) / f"{kind}-{name}.md"
    if path.exists():
        more = "; a second flow gets its own folder: `--area <flow>`" if prototype else ""
        raise FileExistsError(f"{path} exists{more}")
    values["spec_link"] = Path(os.path.relpath(spec_path, path.parent)).as_posix()
    text = fill(tpl, **values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if link:
        link_doc(spec_path, kind, path.relative_to(root).as_posix(), frozen=kind not in LIVING_DOCS)
    return path, spec_path


def required_docs(data: dict, acceptance: int, cfg: cfgmod.Config | None) -> list[tuple[str, str, str]]:
    """The documents the required-docs matrix asks this Spec for, as (kind, level, why): level `warn` on the routes a
    rule warns on, `suggest` on those it only suggests. Advice only: `aidd validate` warns, the gate never reads it."""
    route = data.get("route")
    matrix = cfg.docs_required if cfg is not None else cfgmod.DOCS_REQUIRED
    out = []
    for kind, rule in matrix.items():
        level = "warn" if route in rule.get("routes", []) else "suggest" if route in rule.get("suggest", []) else None
        if level is None:
            continue
        why = _doc_conditions(rule, data, acceptance, cfg)
        if why is None:
            continue
        if rule.get("any_of"):
            alt = next((w for w in (_doc_conditions(c, data, acceptance, cfg) for c in rule["any_of"]) if w is not None), None)
            if alt is None:
                continue
            why += alt
        out.append((kind, level, ", ".join([f"route {route}", *why])))
    return out


def _doc_conditions(rule: dict, data: dict, acceptance: int, cfg: cfgmod.Config | None) -> list[str] | None:
    """Why a doc rule's conditions hold for this Spec (every one must), or None when one does not."""
    risk = data.get("risk") or {}
    why = []
    if rule.get("dimensions"):
        hit = sorted(set(risk.get("dimensions") or []) & set(rule["dimensions"]))
        if not hit:
            return None
        why.append(f"risk {', '.join(hit)}")
    if rule.get("types"):
        if data.get("type") not in rule["types"]:
            return None
        why.append(f"type {data.get('type')}")
    if rule.get("paths"):
        scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
        if not any(globs.match_any(rule["paths"], s) or globs.match_any(rule["paths"], globs.sample_path(s)) for s in scopes):
            return None
        why.append("a matching path in scope")
    if rule.get("min_acceptance"):
        if acceptance < rule["min_acceptance"]:
            return None
        why.append(f"{acceptance} Acceptance items")
    if rule.get("profiles"):
        if cfg is None or cfg.profile not in rule["profiles"]:
            return None
        why.append(f"profile {cfg.profile}")
    if "compliance" in rule:
        on = project.compliance(cfg)["on"]
        if on is not rule["compliance"]:
            return None
        why.append("compliance on" if on else "compliance off")
    for key, said in (("uat", "uat"), ("hypothesis", "a hypothesis"), ("reversible", "reversible")):
        if key not in rule:
            continue
        value = risk.get("reversible", True) if key == "reversible" else bool(data.get(key))
        if value is not rule[key]:
            return None
        why.append(said if rule[key] else f"not {said}")
    return why


# What a Spec may carry in its own body instead of a linked document of that kind: the full Spec, before its detail moved to linked documents.
INLINE_DOC_SECTIONS = {"tech-spec": ("Alternatives considered", "Pre-mortem"), "runbook": ("Rollout",)}


def _matching(root: Path, pattern: str) -> list[str]:
    """The repository files a path or glob names, walking only below its literal prefix (never the whole tree)."""
    parts = pattern.rstrip("/").split("/")
    fixed = list(itertools.takewhile(lambda s: not any(c in s for c in "*?["), parts))
    if len(fixed) == len(parts) and not pattern.endswith("/"):
        return [pattern] if (root / pattern).is_file() else []
    base = root.joinpath(*fixed)
    if not base.is_dir():
        return []
    found = (p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    return sorted(f for f in found if globs.match_any([pattern], f))


def _new_hint(kind: str, sid: str) -> str:
    if kind in REPO_DOCS:
        return f"`aidd new {kind}` (the repository's one {kind}), then link it"
    if kind in DOC_TEMPLATES:
        return f"`aidd new {kind} <topic> --spec {sid}`"
    if kind == "runbook":
        return f"`aidd new runbook <ID> --title ... --spec {sid}`"
    return "write it and add a [[docs]] entry"


def _doc_findings(path: Path, text: str, data: dict) -> list[str]:
    """The linked documents, checked: every doc and local decision path exists (errors); a frozen doc names its Spec
    and holds no TODO, a test plan's Acceptance ids match the Spec's and its commands' `covers`, and the required-docs
    matrix (warnings). The paths are the repository's own only for a Spec in its Specs folder: a Spec elsewhere (an
    example, a fixture) gets the matrix alone."""
    root = _repo_root_of(path)
    if root is None:
        return []
    out: list[str] = []
    cfg = workitems.config_at(root)
    sid = str(data.get("id"))
    frozen = set(model.frozen_docs(data))
    ids = acceptance_ids(text)
    covered = {i for c in (data.get("tests") or {}).get("commands", []) for i in c.get("covers") or []}
    here = path.resolve().is_relative_to((root / (cfg.specs_dir if cfg else "specs")).resolve())
    for d in data.get("docs") or [] if here else []:
        files = _matching(root, d["path"])
        if not files:
            out.append(f"{path}: docs {d['path']!r} ({d['kind']}) does not exist; write it ({_new_hint(d['kind'], sid)}) or drop the entry")
            continue
        for f in files if d["path"] in frozen else []:
            body = (root / f).read_text(encoding="utf-8", errors="replace")
            if "TODO" in body:
                out.append(f"warning: {path}: frozen doc {f} still contains TODO placeholders; Spec approval would freeze them")
            if sid not in body:
                out.append(f"warning: {path}: frozen doc {f} does not name {sid}; start it with a back-link to the Spec")
        if d["kind"] == "test-plan":
            plan = list(dict.fromkeys(_ACCEPTANCE_ID.findall(section((root / files[0]).read_text(encoding="utf-8", errors="replace"), "Acceptance criteria"))))
            out += [f"warning: {path}: test plan {files[0]} lists {i}, which the Spec's '## Acceptance' does not have" for i in plan if i not in ids]
            out += [f"warning: {path}: Acceptance item {i} is missing from the test plan {files[0]}" for i in ids if i not in plan]
            out += [
                f"warning: {path}: test plan {files[0]} maps {i}, but no test command covers it; add it to a command's covers"
                for i in plan
                if i in ids and i not in covered
            ]
        if d["kind"] == "tech-spec":
            # The default home of testing: the tech spec's Test strategy maps the Spec's own ids, never new ones.
            mapped = list(dict.fromkeys(_ACCEPTANCE_ID.findall(section((root / files[0]).read_text(encoding="utf-8", errors="replace"), "Test strategy"))))
            out += [
                f"warning: {path}: the Test strategy in {files[0]} lists {i}, which the Spec's '## Acceptance' does not have" for i in mapped if i not in ids
            ]
            out += [
                f"warning: {path}: the Test strategy in {files[0]} maps {i}, but no test command covers it; add it to a command's covers"
                for i in mapped
                if i in ids and i not in covered
            ]
    for ref in data.get("decisions") or [] if here else []:
        if "://" not in ref and "/" in ref and not _matching(root, ref):
            out.append(f"{path}: decisions {ref!r} does not exist; link an ADR in the repository, or a URL")
    if (root / REPO_TOKENS).is_file():
        out += [
            f"warning: {path}: design.files hold their own tokens file {f}, but the repository's design system is {REPO_TOKENS}. "
            "Use its tokens, and propose a token change as a separate change, or the two drift apart"
            for f in _own_tokens(root, data)
        ]
    linked = {d["kind"] for d in data.get("docs") or []} | ({"design-spec"} if (data.get("design") or {}).get("files") else set())
    for kind, level, why in required_docs(data, len(ids), cfg):
        inline = INLINE_DOC_SECTIONS.get(kind)
        if level != "warn" or kind in linked or (inline and all(section(text, h) for h in inline)):
            continue
        own = f", or write {' and '.join(repr('## ' + h) for h in inline)} in the Spec" if inline else ""
        out.append(f"warning: {path}: the Spec ({why}) links no {kind} doc; {_new_hint(kind, sid)}{own} ([docs.required] tunes this)")
    return out


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
        out = [f"warning: {w}" for w in cfg.warnings + cfgmod.advice(cfg)]
        errors, warnings = project.findings(cfg)
        out += [f"{path}: {e}" for e in errors] + [f"warning: {path}: {w}" for w in warnings]
        if path.name == "config.toml" and not cfg.approvers:
            out.append(f"{path}: profile {cfg.profile} requires owners.approvers (solo too); {EMPTY_APPROVERS}")
        if path.parent.name == ".aidd":
            from .contextpack import inside

            out += [
                f"warning: {path}: [docs] exemplars names {rel}, which is not a file in the repository; name a Spec that exists, or remove it"
                for rel in cfg.get("docs", "exemplars", default=[]) or []
                if inside(path.parent.parent, rel) is None
            ]
        return out
    try:
        data, _, errs = model.load_object(text, str(path))
    except model.ModelError as exc:
        return [str(exc)]
    try:
        return _object_checks(path, text, data, errs)
    except (AttributeError, TypeError, KeyError):
        # The checks read the fields the schema describes. When the schema already rejected one (a string `risk`
        # where a table belongs), they stop there: the schema errors, and whatever they found first, are the report.
        if any(not e.startswith("warning: ") for e in errs):
            return errs
        raise


def _object_checks(path: Path, text: str, data: dict, errs: list[str]) -> list[str]:
    """The checks past the schema, appending to `errs` (the schema's findings) as they go."""
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
            # A linked tech spec carries the diagram, the alternatives, and the pre-mortem as well as the Spec can; with
            # neither, the required-docs matrix says so (`_doc_findings`).
            techs = _tech_specs(path, data)
            design = section(text, "Design")
            if not has_diagram(design) and len(design.split()) < DESIGN_PROSE_WORDS and not any(has_diagram(t) for _, t in techs):
                shape = "add one so a human reads the change's shape before the words at Spec approval"
                errs.append(f"warning: {path}: the Design section of a major Spec has no diagram (a ```mermaid block or an image) and little prose; {shape}")
            for heading, advice in (
                ("Alternatives considered", "say what else you weighed, including doing nothing"),
                ("Pre-mortem", "references/loop.md requires one"),
            ):
                for rel, body in techs if not section(text, heading) else []:
                    if not section(body, heading):
                        errs.append(f"warning: {path}: the tech spec {rel} has no '## {heading}' section with content; {advice}")
        errs += _intent_and_conflict_warnings(path, text, data)
    if data.get("kind") in workitems.WORK_KINDS and data:
        errs += workitems.validate(path, text, data, _repo_root_of(path))
    if data.get("kind") == "proposal" and not any(not e.startswith("warning: ") for e in errs):
        errs += _proposal_findings(path, text, data)
    if data.get("kind") == "initiative":
        errs += _evidence_warnings(path, text)
    if data.get("kind") == "spec" and not any(not e.startswith("warning: ") for e in errs):
        errs += _consistency_warnings(path, data)
        errs += _coverage_warnings(path, text, data)
        errs += _vague_warnings(path, text)
        errs += _doc_findings(path, text, data)
        errs += _after_ship_warnings(path, text, data)
        if hint := project.hold_hint(text, data, workitems.config_at(_repo_root_of(path))):
            errs.append(f"warning: {path}: {hint}")
        if hint := project.cost_hint(text, data, workitems.config_at(_repo_root_of(path)), _tech_specs(path, data), _listed_files(path, data)):
            errs.append(f"warning: {path}: {hint}")
        errs += [f"warning: {path}: {hint}" for hint in project.theme_hint(workitems.config_at(_repo_root_of(path)), _design_specs(path, data))]
    return errs


# A change order the sign-off check reads: a regular file `CO-<n>.md` directly in the proposal's `change-orders/`.
_CHANGE_ORDER_NAME = re.compile(r"CO-\d+\.md")
# The one line of the change-order template that names the proposal hash after the change; the rest of the file is not read.
_CHANGE_ORDER_HASH = re.compile(r"(?m)^[ \t]*Proposal hash after this change:[ \t]*(`?)([0-9a-f]{32})\1[ \t]*$")
_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


def _proposal_findings(path: Path, text: str, data: dict) -> list[str]:
    """What a proposal owes. While it is drafted (go recorded, no sign-off yet), an open dependency names its owner, due
    date, and mitigation (a warning): a person sets them before the sign-off, so the change needs no new sign-off.
    Once signed off, its text still matches `sign_off.hash`, or a change order names the new hash (an error
    otherwise). A sign-off with no hash binds no text (a warning)."""
    out = []
    if model.proposal_status(data) == "drafting":
        for dep in data.get("dependencies") or []:
            if not isinstance(dep, dict) or dep.get("status") != "open":
                continue
            missing = [what for key, what in (("owner", "owner"), ("due", "due date"), ("mitigation", "mitigation")) if not str(dep.get(key) or "").strip()]
            if missing:
                them = "it" if len(missing) == 1 else "them"
                out.append(
                    f"warning: {path}: dependency {dep.get('id')} is open and has no {' and no '.join(missing)}; a person sets {them} before the sign-off"
                )
    sign_off = data.get("sign_off")
    if not isinstance(sign_off, dict):
        return out
    now = model.proposal_hash(text)
    signed = sign_off.get("hash")
    if not signed:
        out.append(f"warning: {path}: sign_off records no hash, so it binds no text; a person adds sign_off.hash from `aidd hash {path.as_posix()}`")
    elif signed != now:
        named, unread = _change_order_hashes(path)
        out += unread
        if now not in named:
            out.append(
                f"{path}: the proposal changed after sign-off: its hash is {now}, and sign_off.hash is {signed}. "
                f"A person signs it off again, or a change order in {CHANGE_ORDERS}/ records the change "
                "and names the new hash on its `Proposal hash after this change:` line"
            )
    return out


def _change_order_hashes(path: Path) -> tuple[set[str], list[str]]:
    """The hashes the change orders beside the proposal at `path` name, and a warning for each one not read.

    It reads only regular files named `CO-<n>.md` directly in `change-orders/`: never a symlink, a symlinked folder, a
    subfolder, or a file over model.MAX_DOCUMENT_BYTES. In each, only the template's `Proposal hash after this change:`
    line counts, outside HTML comments."""
    folder = path.parent / CHANGE_ORDERS
    if folder.is_symlink():
        return set(), [f"warning: {path}: {CHANGE_ORDERS}/ is not read: it is a symlink"]
    try:
        entries = sorted((e for e in os.scandir(folder) if _CHANGE_ORDER_NAME.fullmatch(e.name)), key=lambda e: e.name)
    except FileNotFoundError:
        return set(), []
    except OSError as exc:
        return set(), [f"warning: {path}: {CHANGE_ORDERS}/ is not read: {exc.strerror or exc}"]
    named: set[str] = set()
    unread = []
    for entry in entries:
        why = ""
        try:
            if entry.is_symlink():
                why = "it is a symlink"
            elif not entry.is_file(follow_symlinks=False):
                why = "it is not a regular file"
            else:
                body = _read_change_order(entry.path)
                if body is None:
                    why = f"it is over {model.MAX_DOCUMENT_BYTES} bytes"
                else:
                    named.update(m.group(2) for m in _CHANGE_ORDER_HASH.finditer(_HTML_COMMENT.sub("", body)))
        except OSError as exc:
            why = exc.strerror or str(exc)
        if why:
            unread.append(f"warning: {path}: change order {CHANGE_ORDERS}/{entry.name} is not read: {why}")
    return named, unread


def _read_change_order(where: str) -> str | None:
    """A change order's text, or None when it is over model.MAX_DOCUMENT_BYTES. It never follows a symlink or blocks on
    a special file that took the file's place after the folder was listed: either is an OSError."""
    fd = os.open(where, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise OSError(0, "it is not a regular file")
        blob = fh.read(model.MAX_DOCUMENT_BYTES + 1)
    return None if len(blob) > model.MAX_DOCUMENT_BYTES else blob.decode("utf-8", errors="replace")


# From review on: a client who accepts by hand (`uat = true`) has an acceptance record that lists the Spec's ids.
_ACCEPTANCE_DUE = frozenset({"in_review", "shipped", "done"})


def _after_ship_warnings(path: Path, text: str, data: dict, today: dt.date | None = None) -> list[str]:
    """What a Spec owes once it is in review or shipped, as warnings: the outcome of a hypothesis past its due date,
    and, with `uat = true`, an acceptance record that lists every Acceptance id. The status is the stored one, as a
    cache (a recorded `outcome.released_on` also says it shipped); the gate never reads either."""
    from . import state

    status = state.spec_status(data)
    out = []
    due = state.outcome_due(data, status, today or dt.date.today())
    if due is not None:
        how = "met, missed, or inconclusive, with the number, in the Spec's [outcome] result"
        out.append(f"warning: {path}: the hypothesis was due {due} and no outcome.result is recorded; record the outcome ({how})")
    released = bool((data.get("outcome") or {}).get("released_on"))
    ids = acceptance_ids(text)
    root = _repo_root_of(path)
    if data.get("uat") and ids and root is not None and (status in _ACCEPTANCE_DUE or released):
        sid = data.get("id")
        files = [f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("kind") == "acceptance" for f in _matching(root, str(d.get("path")))]
        why = f"uat = true and the Spec is {status if status in _ACCEPTANCE_DUE else 'released'}"
        if not files:
            out.append(
                f"warning: {path}: {why}, but it links no acceptance record; `aidd new acceptance <topic> --spec {sid}`, "
                "and a person records the client's acceptance of each Acceptance id before ship"
            )
        else:
            listed = {i for f in files for i in _ACCEPTANCE_ID.findall((root / f).read_text(encoding="utf-8", errors="replace"))}
            missing = [i for i in ids if i not in listed]
            if missing:
                out.append(f"warning: {path}: {why}, but the acceptance record {', '.join(files)} does not list {', '.join(missing)}; add a row for each")
    return out


def _design_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The design specs a Spec links (its Markdown `design-spec` docs), as (path, text), those that exist."""
    root = _repo_root_of(path)
    if root is None:
        return []
    rels = [f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("kind") == "design-spec" for f in _matching(root, str(d.get("path")))]
    return [(rel, (root / rel).read_text(encoding="utf-8", errors="replace")) for rel in rels if rel.endswith(".md")]


def _tech_specs(path: Path, data: dict) -> list[tuple[str, str]]:
    """The tech-spec docs a Spec links, as (path, text), those that exist."""
    root = _repo_root_of(path)
    if root is None:
        return []
    found = [f for d in data.get("docs") or [] if isinstance(d, dict) and d.get("kind") == "tech-spec" for f in _matching(root, str(d.get("path")))]
    return [(f, (root / f).read_text(encoding="utf-8", errors="replace")) for f in found]


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


# A Task's proof that names a test command: "test `rate-limit`", "command `unit`", or "`rate-limit` test".
_PROOF_COMMAND = re.compile(r"\b(?:tests?|commands?)\s+`([a-z0-9][a-z0-9_.-]{0,63})`|`([a-z0-9][a-z0-9_.-]{0,63})`\s+(?:tests?|commands?)\b", re.I)


def _approval_holds(root: Path, path: Path, data: dict) -> bool:
    from . import state

    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return state.stored(data) in state.PAST_APPROVAL
    return state.Observer(root, workitems.config_at(root)).holds(rel, data)


def _listed_files(path: Path, data: dict) -> list[str]:
    """The repository's files (tracked, and untracked but not ignored), read only when a Task's scope is a glob or a
    folder: what such a scope stands for. Empty outside a git checkout."""
    scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]
    root = _repo_root_of(path)
    if root is None or not (root / ".git").exists() or not any(any(c in s for c in "*?") or s.endswith("/") for s in scopes):
        return []
    try:
        out = gitutil.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], str(root), check=False)
    except gitutil.GitError:
        return []
    return [p for p in out.split("\0") if p]


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
    """Where a Spec's plan and its tests disagree, as warnings: a frozen test file that is not on disk, a Task
    proof naming a test command nobody defined, and an experiment with no guardrail or no hypothesis to decide.
    (A command that runs a file outside tests.files is a lint error.)"""
    out = []
    exp = data.get("experiment")
    if isinstance(exp, dict):
        if not exp.get("guardrails"):
            out.append(f"warning: {path}: the experiment names no guardrail; add `guardrails`, the metrics that must not get worse while it runs")
        if not data.get("hypothesis"):
            out.append(f"warning: {path}: the experiment has no hypothesis to decide; add the `hypothesis` its primary metric measures")
    tests = data.get("tests") or {}
    root = _repo_root_of(path)
    # Once Spec approval holds (the check the guard, `aidd assess`, and `aidd list` share), the test files are frozen: they must exist.
    if root is not None and _approval_holds(root, path, data):
        for f in tests.get("files", []):
            if not any(c in f for c in "*?[") and not (root / f.rstrip("/")).exists():
                out.append(f"warning: {path}: tests.files {f!r} does not exist, but Spec approval holds; Spec approval froze a test nobody wrote")
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


# A line that states a target, or names what proves it: a number, inline code, a link, or a file path.
_MEASURABLE = re.compile(r"\d|`|\]\(|https?://|[\w.-]+/[\w./-]*\.\w+")
# Numbers that state no target: list numbering, an Acceptance id (A1, AC-1), and a work-item id (SPEC-4, EPIC-2).
_NOT_A_TARGET = re.compile(r"^[ \t]*(?:[-*|][ \t]*)?\d+[.)][ \t]|\bA[1-9][0-9]{0,3}\b|\b[A-Z][A-Z0-9]*-\d+\b")
# A Gherkin name line: it names the behaviour, and its steps carry the target.
_GHERKIN_NAME = re.compile(r"^[ \t]*(?:Feature|Rule|Background|Scenario Outline|Scenario|Examples?)[ \t]*:", re.I)


@functools.cache
def _vague_words() -> re.Pattern[str]:
    """The words in schemas/vague-words.json, as whole words in any case; a hyphen joins a word."""
    words = sorted(resources.load_json("vague-words.json")["words"], key=len, reverse=True)
    alternatives = "|".join(r"\s+".join(map(re.escape, w.split())) for w in words)
    return re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.I)


def vague_lines(text: str) -> list[tuple[str, str, list[str], str]]:
    """(section, Acceptance id or "", the vague words, the line) for each line of a Spec's Acceptance and
    Non-functional requirements sections that uses a vague word and states no target."""
    out = []
    for name in ("Acceptance", "Non-functional requirements"):
        item = ""
        for line in section(text, name, fences=False).splitlines():
            if m := _ACCEPTANCE_ID.match(line):
                item = m.group(1)
            if _GHERKIN_NAME.match(line):
                continue
            words = list(dict.fromkeys(" ".join(w.group(1).lower().split()) for w in _vague_words().finditer(line)))
            if words and not _MEASURABLE.search(_NOT_A_TARGET.sub("", line)):
                out.append((name, item if name == "Acceptance" else "", words, line.strip()))
    return out


def _vague_warnings(path: Path, text: str) -> list[str]:
    """A warning per vague line (`vague_lines`): never an error, and the gate never reads it."""
    out = []
    for name, item, words, line in vague_lines(text):
        where = f"Acceptance {item}" if item else f"a line of '## {name}'"
        shown = line if len(line) <= 60 else line[:59] + "…"
        out.append(
            f"warning: {path}: {where} says {', '.join(repr(w) for w in words)} with no number, unit, or test reference ({shown!r}); "
            'state a measurable target, such as "p95 under 300 ms" or "returns 429"'
        )
    return out


# A source behind a claim: a link, a file path, a quote, or a dated note (an ISO date, or a year and a month).
_SOURCE = re.compile(r"\]\(|https?://|`[^`]+`|[\w.-]+/[\w./-]*\.\w+|\"[^\"]{3,}\"|“[^”]{3,}”|\b\d{4}-\d{2}\b")
_PROBLEM_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\**Problem\**[ \t]*:\**(.*)$", re.I)
_EVIDENCE = re.compile(r"\bEvidence[ \t]*:\**(.*)$", re.I)


def _sourced(claim: str) -> bool:
    """Whether a claim names its source, says it is assumed, or is still a template placeholder."""
    return not claim.strip() or "TODO" in claim or "(assumed)" in claim.lower() or bool(_SOURCE.search(claim))


def _evidence_warnings(path: Path, text: str) -> list[str]:
    """An Initiative's Brief: its Problem line and its journey's Evidence each cite a source, or are marked "(assumed)".
    Warnings, never errors: an invented claim reads like a found one, and only its source tells them apart."""
    fix = 'add a link, a file path, a quote with its source, or a dated note, or mark it "(assumed)"'
    lines = section(text, "Brief").splitlines()
    claims = []
    for i, line in enumerate(lines):
        if m := _PROBLEM_LINE.match(line):
            wrapped = itertools.takewhile(lambda ln: ln[:1] in " \t" and not _PROBLEM_LINE.match(ln) and not ln.lstrip().startswith(("-", "*")), lines[i + 1 :])
            claims.append(("the Brief's Problem line", " ".join([m.group(1), *wrapped])))
        elif line.lstrip().startswith("|") and line.strip("| \t").lower().startswith("evidence"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
            claims += [("a journey Evidence cell", c) for c in cells]
        elif m := _EVIDENCE.search(line):
            claims.append(("the journey's Evidence", m.group(1)))
    return [f"warning: {path}: {where} cites no source; {fix}" for where, claim in claims if not _sourced(claim)]


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


def _status_warnings(root: Path, specs_dir: str, objects: list[tuple[str, dict]], texts: dict[str, str]) -> list[str]:
    """Where a stored status, a cache, disagrees with the status aidd derives, and a done Epic or Initiative that
    still has an open child. Warnings: the derived status is what `aidd assess` and `aidd list` show, and the gate reads neither."""
    from . import state

    work = [(p, d, texts.get(p, "")) for p, d in objects if d.get("kind") in workitems.WORK_KINDS]
    if not work:
        return []
    try:
        derived = state.Observer(root, workitems.config_at(root)).working_tree(specs_dir, work)
    except gitutil.GitError:
        return []
    _, _, children = state.containers([d for _, d, _ in work], derived)
    out = []
    for p, d, _ in work:
        oid, stored = str(d.get("id")), state.stored(d)
        now = derived.get(oid)
        if stored is None or now is None:
            continue
        if d.get("kind") == "spec" and stored != now:
            out.append(
                f"{p}: the stored status {stored} disagrees with the derived status {now}; aidd assess and aidd list show {now}. Update the status or remove it"
            )
        elif d.get("kind") != "spec" and stored in ("draft", "active") and stored != now:
            out.append(f"{p}: the stored status {stored} disagrees with the derived status {now} (from its children); update the status or remove it")
        if stored == "done" and d.get("kind") != "spec":
            open_ = [c for c in children.get(oid, []) if not state.finished(derived.get(c, "draft"))]
            if open_:
                out.append(f"{p}: status done, but {', '.join(open_)} {'is' if len(open_) == 1 else 'are'} not finished; reopen it or finish them")
    return out


def overdue_flags(objects: list[tuple[str, dict]], today: dt.date) -> list[tuple[str, dict, dict]]:
    """(path, Spec, flag) for each `[[flags]]` entry whose `cleanup_due` has passed while no Spec lists it in
    `removes_flags`; a cancelled or rolled-back Spec's flags never reached users, and a later Spec that declares the same
    flag again with a later `cleanup_due` extends it. Cheap: the front matter only, no git."""
    specs = [(p, d) for p, d in objects if d.get("kind") == "spec" and d.get("status") not in ("cancelled", "rolled_back")]
    removed = {str(n) for _, d in specs for n in d.get("removes_flags") or []}
    latest: dict[str, tuple[str, dict, dict]] = {}
    for p, d in specs:
        for flag in d.get("flags") or []:
            if not isinstance(flag, dict) or not flag.get("name") or str(flag["name"]) in removed:
                continue
            due, name = str(flag.get("cleanup_due", "9999")), str(flag["name"])
            if name not in latest or due >= str(latest[name][2].get("cleanup_due", "9999")):
                latest[name] = (p, d, flag)
    return [found for found in latest.values() if str(found[2].get("cleanup_due", "9999")) < today.isoformat()]


def overdue_actions(rel: str, data: dict, today: dt.date) -> list[str]:
    """Problem management: each action item of a postmortem in review or published whose `due` date has passed and
    that is not `done`. Like the flag cleanup date, a date passing is a warning, never a gate rule."""
    if data.get("status") not in ("in_review", "published"):
        return []
    out = []
    for a in data.get("actions") or []:
        if not isinstance(a, dict) or a.get("done") or str(a.get("due", "9999")) >= today.isoformat():
            continue
        where = f" (tracked in {a['tracked_in']})" if a.get("tracked_in") else ""
        out.append(
            f"{rel}: postmortem {data.get('id')} action {a.get('what')!r} (owner {a.get('owner')}) was due on {a.get('due')} and is not done{where}. "
            "Finish it and record done = true, or have its owner set a new due date"
        )
    return out


def target_errors(rel: str, data: dict) -> list[str]:
    """Each postmortem action whose `target` names no pack or practice skill of aidd-team: the lesson would go nowhere."""
    from . import knowledge

    out = []
    for a in data.get("actions") or []:
        if isinstance(a, dict) and a.get("target") and (why := knowledge.target_problem(str(a["target"]))):
            out.append(f"{rel}: postmortem {data.get('id')} action {a.get('what')!r}: {why}")
    return out


def knowledge_action_how(action: dict) -> str:
    """What an open knowledge action asks for, said the same way by `aidd list` and the Learn commands."""
    return (
        f"raise a suggested Spec that updates {action.get('target')}. That change goes to schemas/roles.json or the skill's SKILL.md in "
        "the aidd repository, reviewed by its steward. Record tracked_in, and done = true once it lands"
    )


def flag_cleanup(flag: dict) -> str:
    """What an overdue flag asks for, said the same way by `aidd validate` and `aidd list`."""
    return f'write the cleanup Spec that deletes it and lists it in removes_flags = ["{flag.get("name")}"]'


# A vendor's renewal comes up in `aidd validate` this many days ahead, so a person decides before it renews by default.
RENEWAL_NOTICE_DAYS = 30


def vendor_renewals(text: str, today: dt.date, notice_days: int = RENEWAL_NOTICE_DAYS) -> list[tuple[str, dt.date, str]]:
    """(vendor, renewal date, owner) for each row of a vendor register's table whose `Renewal date` falls within
    `notice_days` of `today` or has passed. A row without a real date (a placeholder) is skipped."""
    out: list[tuple[str, dt.date, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if "renewal date" not in header or set("".join(cells)) <= set("-: "):
            continue
        at = header.index("renewal date")
        try:
            due = dt.date.fromisoformat(cells[at])
        except (IndexError, ValueError):
            continue
        if (due - today).days <= notice_days:
            owner = cells[header.index("owner")] if "owner" in header and header.index("owner") < len(cells) else ""
            out.append((cells[0], due, owner))
    return out


def _renewal_warnings(root: Path, objects: list[tuple[str, dict]], today: dt.date, docs_dir: str = "docs") -> list[str]:
    """A warning per vendor whose renewal is near or past, from the repository's vendor register and any other one a
    Spec links."""
    paths = dict.fromkeys(
        [globs.under(docs_dir, "vendors.md")]
        + [
            str(d.get("path"))
            for _, s in objects
            if s.get("kind") == "spec"
            for d in s.get("docs") or []
            if isinstance(d, dict) and d.get("kind") == "vendors" and d.get("path")
        ]
    )
    out = []
    for rel in paths:
        path = root / rel
        if not path.is_file():
            continue
        for vendor, due, owner in vendor_renewals(path.read_text(encoding="utf-8", errors="replace"), today):
            when = f"passed on {due}" if due < today else f"is due on {due}, in {(due - today).days} days"
            out.append(f"{rel}: vendor {vendor}'s renewal {when} (owner {owner or 'not named'}); a person decides to renew, renegotiate, or exit")
    return out


# The one kind each work item's `parent` names: a Spec sits under an Epic, an Epic under an Initiative.
PARENT_KIND = {"spec": "epic", "epic": "initiative"}
KIND_NAMES = {
    "spec": "a Spec",
    "epic": "an Epic",
    "initiative": "an Initiative",
    "proposal": "a proposal",
    "runbook": "a runbook",
    "postmortem": "a postmortem",
}


def parent_kind_error(kind: str, parent: str, parent_kind: str) -> str:
    """Why `parent`, an object of `parent_kind`, cannot be the parent of a `kind`, or "" when it can."""
    if kind not in PARENT_KIND or parent_kind == PARENT_KIND[kind]:
        return ""
    return f"parent {parent} is {KIND_NAMES.get(parent_kind, parent_kind)}; {KIND_NAMES[kind]}'s parent is {KIND_NAMES[PARENT_KIND[kind]]}"


def _kind_of(root: Path, oid: str, folders: tuple[str, ...]) -> str:
    """The kind of the object whose id is `oid` in `folders`, or "" when none has it (or it cannot be read)."""
    for path in (p for d in folders for p in object_files(root, d)):
        try:
            data, _ = model.split_front_matter(path.read_text(encoding="utf-8", errors="replace"), str(path))
        except (model.ModelError, OSError):
            continue
        if str(data.get("id")) == oid:
            return str(data.get("kind"))
    return ""


def check_repo(root: Path, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    today = today or dt.date.today()
    errors: list[str] = []
    warnings: list[str] = []
    specs_dir, proposals_dir, docs_dir, bots = "specs", "proposals", "docs", set()
    cfg_path = root / cfgmod.CONFIG_PATH

    def rel(p: Path) -> str:
        """A repository path as a finding names it: from the root, in forward slashes."""
        return p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()

    if cfg_path.is_file():
        for e in validate_file(cfg_path, rel(cfg_path)):
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
            specs_dir, proposals_dir, docs_dir = cfg.specs_dir, cfg.proposals_dir, cfg.docs_dir
            bots = {b.lower().lstrip("@") for b in cfg.get("identities", "bots", default=[])}
        except (cfgmod.ConfigError, model.ModelError, RuntimeError):
            pass
    else:
        errors.append(f"no {cfgmod.CONFIG_PATH}")
    ids: dict[str, str] = {}
    kinds: dict[str, str] = {}
    objects: list[tuple[str, dict]] = []
    texts: dict[str, str] = {}
    ops = [p for d in OPS_DIRS.values() for p in object_files(root, d)]
    for path in object_files(root, specs_dir) + object_files(root, proposals_dir) + ops:
        p = rel(path)
        errs = validate_file(path, p)
        for e in errs:
            (warnings if e.startswith("warning: ") else errors).append(e)
        try:
            texts[p] = path.read_text(encoding="utf-8")
            data, _ = model.split_front_matter(texts[p], p)
        except model.ModelError:
            continue
        objects.append((p, data))
        oid = data.get("id")
        if oid in ids:
            errors.append(f"{p}: id {oid} is also used by {ids[oid]}")
        elif oid:
            ids[oid] = p
            kinds[oid] = str(data.get("kind"))
    errors += workitems.relation_errors(objects)
    warnings += _status_warnings(root, specs_dir, objects, texts)
    for p, _, flag in overdue_flags(objects, today):
        warnings.append(f"{p}: flag {flag.get('name')} was due for removal on {flag.get('cleanup_due')} (owner {flag.get('owner')}); {flag_cleanup(flag)}")
    warnings += _renewal_warnings(root, objects, today, docs_dir)
    for p, data in objects:
        if data.get("kind") == "proposal":
            for step in ("go_no_go", "sign_off", "outcome"):
                who = str((data.get(step) or {}).get("by", ""))
                if who and project.is_agent(who, bots):
                    errors.append(f"{p}: {step}.by {who} is an agent account; a person decides a proposal")
        if data.get("kind") == "initiative":
            who = str((data.get("go_no_go") or {}).get("by", ""))
            if who and project.is_agent(who, bots):
                errors.append(f"{p}: go_no_go.by {who} is an agent account; a person decides whether an Initiative goes ahead")
        if data.get("kind") in ("proposal", "initiative"):
            for entry in data.get("decisions") or []:
                who = str(entry.get("by", "")) if isinstance(entry, dict) else ""
                if who and project.is_agent(who, bots):
                    errors.append(f"{p}: decisions {entry.get('id')}.by {who} is an agent account; a person decides scope")
        if data.get("kind") == "postmortem" and data.get("spec") and data["spec"] != "TODO":
            if data["spec"] not in ids:
                warnings.append(f"{p}: spec {data['spec']} is not in {specs_dir}/; name the emergency change's backfill Spec")
        if data.get("kind") == "postmortem":
            warnings += overdue_actions(p, data, today)
            errors += target_errors(p, data)
        parent = data.get("parent")
        if parent and parent not in ids:
            warnings.append(f"{p}: parent {parent} is not in {specs_dir}/ (fine if the parent lives outside the repository)")
        elif parent and (why := parent_kind_error(str(data.get("kind")), parent, kinds[parent])):
            # Unlike a missing parent, which may live outside the repository, a parent of another kind is wrong for certain.
            errors.append(f"{p}: {why}")
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
        if data.get("route") == "major" and out.get("released_on") and not out.get("observe_result"):
            warnings.append(f"{p}: released major change has no outcome.observe_result")
        # `hypothesis` is frozen by Spec approval and `outcome.result` records what the metric did. One without
        # the other means the claim in the changelog is not being kept: a result nobody predicted, or
        # a prediction nobody measured.
        if out.get("result") and not data.get("hypothesis"):
            warnings.append(f"{p}: outcome.result records a metric no hypothesis predicted; add the hypothesis before Spec approval next time")
        if data.get("hypothesis") and out.get("released_on") and not out.get("result"):
            warnings.append(f"{p}: a released change with a hypothesis has no outcome.result; Learn records what the metric did")
    from . import explore

    warnings += explore.hints(root, workitems.config_at(root), today)
    return errors, warnings
