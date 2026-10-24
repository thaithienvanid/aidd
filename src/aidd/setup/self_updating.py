"""`aidd self-update` and the daily check: tell a person when a newer release of thaithienvanid/aidd is out, and
install it only once it is verified.

The CLI is itself a control, so it never changes by surprise and never runs what it did not check:
- The daily check only tells: "aidd vX.Y.Z is out". It installs the release itself only where the person opted in
  (AIDD_AUTO_UPDATE=1).
- It follows releases only. The tip of main, unreleased and unverified, is installed only on the person's explicit
  `aidd self-update --main`.
- A release is installed from its own wheel, downloaded from the GitHub Release and checked first: its sha256 against
  the release's SHA256SUMS, and, where `gh` is on PATH, its build provenance with `gh attestation verify`. A mismatch
  installs nothing.

aidd updates only an install it can redo the same way: uv's tool, pipx's, or the one-line installer's venv. A source
checkout follows its own checkout, and the zipapp, a pip install into a project, or a wheel of unknown origin are
left alone with the command to run.

The daily check runs after a command a person ran at a terminal (stdin and stderr both terminals), at most once a day,
and never in CI, in a shell an agent started, inside a hook, offline (AIDD_OFFLINE=1), or with AIDD_NO_UPDATE_CHECK=1.
A failed update leaves the old CLI in place and says so in one line.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from aidd import __version__, platforms
from aidd.kernel import git, http, resources
from aidd.setup import pins
from aidd.setup.pins import RELEASE_REPO_URL

# How long one check holds: a day, so a person sees at most one update line a day.
CHECK_EVERY_SECONDS = 24 * 60 * 60
# The opt-out; a shell an agent started (platforms.AGENT_ENV, the markers approvals check too) and CI never update.
OFF_ENV = "AIDD_NO_UPDATE_CHECK"
# The opt-in: the daily check installs a newer release itself, verified, instead of only telling.
AUTO_ENV = "AIDD_AUTO_UPDATE"
RELEASE_ASSETS = f"{RELEASE_REPO_URL}/releases/download"
RELEASE_REPO = RELEASE_REPO_URL.removeprefix("https://github.com/")
WHEEL_MAX_BYTES = 32 * 1024 * 1024
_TAG = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)(\^\{\})?")
_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Target:
    """What aidd updates to: the newest `vX.Y.Z` release tag, or main when there is none, and the commit it names."""

    label: str  # "v1.1.0" or "main"
    sha: str
    version: str | None  # "1.1.0" for a release; None for main

    def describe(self) -> str:
        return f"{self.label} ({self.sha[:12]})"


def _version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text)[:3]
    return tuple(int(p) for p in parts) if parts else (0,)


def latest(refs: dict[str, str], *, main: bool = False) -> Target | None:
    """The newest release tag in `refs` (an annotated tag read through to its commit); with `main`, the tip of main."""
    tags: dict[tuple[int, ...], str] = {}
    peeled: set[tuple[int, ...]] = set()
    for name, sha in refs.items():
        m = _TAG.fullmatch(name)
        if not m or not _SHA.fullmatch(sha):
            continue
        key = tuple(int(g) for g in m.groups()[:3])
        if m.group(4):  # the commit an annotated tag names wins over the tag object
            tags[key] = sha
            peeled.add(key)
        elif key not in peeled:
            tags[key] = sha
    if main:
        tip = refs.get("refs/heads/main", "")
        return Target("main", tip, None) if _SHA.fullmatch(tip) else None
    if tags:
        key = max(tags)
        return Target(f"v{'.'.join(map(str, key))}", tags[key], ".".join(map(str, key)))
    return None


def needs_update(target: Target, installed_version: str, installed_commit: str | None) -> bool:
    """True when `target` is not what runs. A release never moves aidd to a lower version; at the same version, a build
    from another commit moves onto the release's own commit. On main, any other commit updates."""
    if installed_commit == target.sha:
        return False
    if target.version is None:
        return True
    wanted, have = _version(target.version), _version(installed_version)
    if wanted != have:
        return wanted > have
    return installed_commit is not None


def _installer_venv() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "aidd" / "venv"


def install_kind() -> str:
    """How this aidd was installed: `checkout`, `pyz`, `uv`, `pipx`, `venv` (the one-line installer's), or `other`."""
    if resources.archive() is not None:
        return "pyz"
    if resources.repo_root() is not None:
        return "checkout"
    prefix = Path(sys.prefix)
    if (prefix / "uv-receipt.toml").is_file():
        return "uv"
    if (prefix / "pipx_metadata.json").is_file():
        return "pipx"
    try:
        if prefix.resolve() == _installer_venv().resolve():
            return "venv"
    except OSError:
        pass
    return "other"


def spec(target: Target) -> str:
    return f"git+{RELEASE_REPO_URL}@{target.sha}"


def wheel_name(version: str) -> str:
    return f"aidd-{version}-py3-none-any.whl"


def _digest_for(sums: str, name: str) -> str | None:
    """The sha256 SHA256SUMS lists for `name` (`<hex>  <name>`, or `<hex> *<name>`), or None."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    return None


def verified_wheel(target: Target, where: Path | None = None) -> tuple[Path | None, str]:
    """The release's wheel, downloaded and checked: (its path, how it was checked), or (None, why nothing installs).
    Its sha256 must match the release's SHA256SUMS; where `gh` is on PATH, `gh attestation verify` must also accept
    its build provenance. Both come from the GitHub Release of the tag `target` names."""
    if target.version is None:
        return None, "the tip of main has no release to verify"
    name = wheel_name(target.version)
    base = f"{RELEASE_ASSETS}/{target.label}"
    try:
        sums = http.get_bytes(f"{base}/SHA256SUMS", max_bytes=256 * 1024).decode("utf-8", "replace")
        wheel = http.get_bytes(f"{base}/{name}", max_bytes=WHEEL_MAX_BYTES)
    except (http.HttpError, OSError, ValueError) as exc:
        return None, f"could not download {name} and SHA256SUMS from the {target.label} release ({exc})"
    want = _digest_for(sums, name)
    if want is None:
        return None, f"the {target.label} release's SHA256SUMS does not list {name}"
    if hashlib.sha256(wheel).hexdigest() != want:
        return None, f"{name} does not match the {target.label} release's SHA256SUMS: nothing was installed"
    folder = (where or neutral_dir()) / target.label
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(wheel)
    gh = shutil.which("gh")
    if gh is None:
        return path, "its sha256 matches the release's SHA256SUMS (with `gh` on PATH, aidd also verifies its build provenance)"
    try:
        done = subprocess.run(
            [gh, "attestation", "verify", str(path), "--repo", RELEASE_REPO],
            cwd=folder,
            env=_neutral_env(folder),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"`gh attestation verify` could not run ({exc}): nothing was installed"
    if done.returncode != 0:
        said = ((done.stderr or "") + (done.stdout or "")).strip().splitlines()
        return None, f"`gh attestation verify` refused {name}{f' ({said[-1]})' if said else ''}: nothing was installed"
    return path, "its sha256 matches the release's SHA256SUMS, and `gh` verified its build provenance"


def update_command(kind: str, source: str) -> list[str] | None:
    """The command that reinstalls aidd from `source` (a verified wheel's path, or a `git+` spec of main) the way it was
    installed, or None when aidd cannot redo that install."""
    if kind == "uv" and (uv := shutil.which("uv")):
        return [uv, "tool", "install", "--force", "--python", ">=3.11", source]
    if kind == "pipx" and (pipx := shutil.which("pipx")):
        base = getattr(sys, "_base_executable", "") or sys.executable
        return [pipx, "install", "--force", "--python", base, source]
    if kind == "venv":
        return [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--upgrade", source]
    return None


def manual_hint(kind: str) -> str:
    """What a person runs when aidd cannot update itself."""
    if kind == "checkout":
        root = resources.repo_root()
        return f"aidd runs from the checkout at {root}, so it follows that checkout: `git pull` there updates it."
    if kind == "pyz":
        return 'aidd runs from aidd.pyz: download the new aidd.pyz from the release, with SHA256SUMS (docs/INSTALL.md, "One file: aidd.pyz").'
    if kind in ("uv", "pipx"):
        return f"{kind} is not on PATH, so aidd cannot reinstall itself: put it on PATH, or reinstall aidd (docs/INSTALL.md)."
    return (
        f'aidd was not installed by uv, pipx, or the one-line installer: reinstall it with `uv tool install "git+{RELEASE_REPO_URL}@<sha>"` (docs/INSTALL.md).'
    )


def neutral_dir() -> Path:
    """Where the check and the reinstall run: an empty folder of aidd's own, never the person's current directory. A
    repository's `.git/config` (a credential helper, an `insteadOf`) or a project's `uv.toml` (an index) would
    otherwise steer what aidd fetches and installs, and run code of their own."""
    where = resources.cache_home() / "self-update"
    where.mkdir(parents=True, exist_ok=True)
    return where


def _neutral_env(where: Path) -> dict[str, str]:
    # git stops looking for a repository at `where`, so a repository around aidd's cache (a versioned home) is never read.
    return {**os.environ, **git.FETCH_ENV, "GIT_CEILING_DIRECTORIES": str(where.parent)}


def check(timeout_seconds: int = 5, *, main: bool = False) -> Target | None:
    """The newest release on GitHub now (with `main`, the tip of main), or None when there is none or it cannot be reached."""
    try:
        where = neutral_dir()
        out = git.run(["ls-remote", RELEASE_REPO_URL, "refs/tags/v*", "refs/heads/main"], str(where), env=_neutral_env(where), timeout_seconds=timeout_seconds)
    except (git.GitError, OSError):
        return None
    refs = {name: sha for sha, _, name in (line.partition("\t") for line in out.splitlines()) if name}
    return latest(refs, main=main) if refs else None


def current() -> str:
    commit = pins.installed_commit()
    return f"aidd {__version__}" + (f" ({commit[:12]})" if commit else "")


def run_update(command: list[str], quiet: bool) -> tuple[int, str]:
    """Run the reinstall; its exit code and, when `quiet`, the last line it printed (for a failure line)."""
    try:
        where = neutral_dir()
        done = subprocess.run(command, cwd=where, env=_neutral_env(where), capture_output=quiet, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    said = ((done.stderr or "") + (done.stdout or "")).strip().splitlines() if quiet else []
    return done.returncode, said[-1] if said else ""


def _on(value: str | None) -> bool:
    return (value or "").strip().lower() not in ("", "0", "false", "no")


def auto_allowed(command: str | None, environ=None, isatty=None) -> bool:
    """Whether the daily check may run after `command`: a person at a terminal, outside CI, agents, hooks, and offline."""
    env = os.environ if environ is None else environ
    tty = isatty or (lambda: sys.stdin.isatty() and sys.stderr.isatty())
    if command in (None, "self-update", "hook", "mcp"):
        return False
    if any(env.get(v) for v in platforms.AGENT_ENV) or _on(env.get("CI")) or _on(env.get(OFF_ENV)):
        return False
    if "1" in (env.get("AIDD_OFFLINE"), env.get("AIDD_HOOK_OFFLINE")):
        return False
    return bool(tty())


def _stamp() -> Path:
    return resources.cache_home() / "self-update-checked"


def _due(now: float) -> bool:
    try:
        return now - _stamp().stat().st_mtime >= CHECK_EVERY_SECONDS
    except OSError:
        return True


def _install(kind: str, target: Target, quiet: bool) -> tuple[bool, str]:
    """Install `target` the way aidd was installed: a release from its verified wheel, main from its commit. (whether it
    installed, what to say)."""
    if target.version is None:
        source, how = spec(target), "the tip of main, unreleased and unverified"
    else:
        wheel, how = verified_wheel(target)
        if wheel is None:
            return False, how
        source = str(wheel)
    cmd = update_command(kind, source)
    if cmd is None:
        return False, manual_hint(kind)
    if not quiet:
        print(f"Update from {current()} to {target.describe()} with {kind}: {how}", flush=True)
    code, last = run_update(cmd, quiet=quiet)
    if code != 0:
        return False, f"the update failed{f': {last}' if last else f' (exit {code})'}; {current()} still runs"
    return True, f"updated to {target.describe()} ({how}). In each repository, `aidd upgrade` lists the files to bring up to it."


def auto_update(command: str | None, now: float | None = None) -> None:
    """The daily check, after a command: tell the person a newer release is out, in one line. With AIDD_AUTO_UPDATE=1,
    install it instead, verified (_install). Silent when up to date, unreachable, or when it cannot redo the install;
    a failure leaves the old CLI. Never raises."""
    try:
        if not auto_allowed(command):
            return
        now = time.time() if now is None else now
        if not _due(now):
            return
        kind = install_kind()
        if kind == "checkout":
            return
        stamp = _stamp()
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        os.utime(stamp, (now, now))
        target = check()
        if target is None or not needs_update(target, __version__, pins.installed_commit()):
            return
        sys.stdout.flush()
        if not _on(os.environ.get(AUTO_ENV)) or kind not in ("uv", "pipx", "venv"):
            print(
                f"aidd: {target.label} is out; this is {current()}. `aidd self-update` installs it, checked against the "
                f"release first ({OFF_ENV}=1 turns this note off)",
                file=sys.stderr,
            )
            return
        print(f"aidd: updating from {current()} to {target.describe()} with {kind} ({AUTO_ENV}=1 asked for it)", file=sys.stderr)
        done, said = _install(kind, target, quiet=True)
        print(f"aidd: {said}" if done else f"aidd: not updated: {said}. `aidd self-update` tries again.", file=sys.stderr)
    except Exception:  # the check must never turn a finished command into a failure
        return


def self_update(check_only: bool = False, main: bool = False) -> tuple[int, list[str]]:
    """`aidd self-update`: the exit code and the lines to print; the reinstall itself prints as it runs. A release is
    installed from its verified wheel; `main` installs the tip of main, unreleased, only when the person asks."""
    kind = install_kind()
    if kind == "checkout":
        return 0, [manual_hint(kind)]
    if os.environ.get("AIDD_OFFLINE") == "1":
        return 2, ["offline (AIDD_OFFLINE=1): aidd cannot ask GitHub for the latest release."]
    target = check(timeout_seconds=20, main=main)
    if target is None:
        if not main:
            return 2, [
                f"no release of {RELEASE_REPO} is out yet, or {RELEASE_REPO_URL} cannot be read (git ls-remote). "
                "`aidd self-update --main` installs the tip of main: unreleased code, with no release to verify it against."
            ]
        return 2, [f"could not read {RELEASE_REPO_URL} (git ls-remote): check the network and your access."]
    if not needs_update(target, __version__, pins.installed_commit()):
        return 0, [f"{current()} is up to date: the latest is {target.describe()}."]
    if update_command(kind, "-") is None:
        return 2, [f"the latest is {target.describe()}; this is {current()}.", manual_hint(kind)]
    how = "from its wheel, after checking it against the release's SHA256SUMS (and its provenance, with gh)" if target.version else "unreleased and unverified"
    if check_only:
        return 0, [f"would update from {current()} to {target.describe()} with {kind}, {how}"]
    done, said = _install(kind, target, quiet=False)
    if not done:
        return 2, [said]
    try:
        _stamp().parent.mkdir(parents=True, exist_ok=True)
        _stamp().touch()
    except OSError:
        pass
    return 0, [said]
