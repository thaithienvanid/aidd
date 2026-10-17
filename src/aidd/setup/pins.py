"""The aidd ref the CI files pin: the commit or release tag this aidd runs from, the refs a repository's CI files name,
whether they exist upstream, and repinning them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from aidd import __version__
from aidd.kernel import git, resources

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
REF = re.compile(r"[0-9a-f]{40}|v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")


def installed_ref() -> str | None:
    """The commit this aidd runs from, when it runs from a git checkout of aidd; None from an installed wheel."""
    src = resources.repo_root()
    if src is None or not (src / ".git").exists():
        return None
    try:
        sha = git.run(["rev-parse", "HEAD"], str(src), timeout_seconds=10).strip()
    except git.GitError:
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def release_tag_of(sha: str) -> str | None:
    """The release tag (`vX.Y.Z`) that names exactly this commit in the aidd checkout this aidd runs from, if any."""
    src = resources.repo_root()
    if src is None or not (src / ".git").exists() or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    try:
        tags = git.run(["tag", "--points-at", sha], str(src), timeout_seconds=10, check=False).split()
    except git.GitError:
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
    if not REF.fullmatch(ref):
        raise ValueError(f"--ref {ref!r} must be a 40-character commit SHA or a release tag such as v1.0.0")
    return repin(text, ref, release, pattern=_PIN)


def release_commit(version: str = __version__, timeout_seconds: int = 5) -> str | None:
    """The commit the release tag `v<version>` names on GitHub, so an installed aidd pins CI to a commit rather than a
    tag that can move. None when offline, when AIDD_OFFLINE=1, or when the tag is not there: the caller keeps the tag."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return None
    tag = f"refs/tags/v{version}"
    refs = remote_refs(RELEASE_REPO_URL, timeout_seconds, f"{tag}^{{}}", tag) or {}
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


def remote_refs(url: str = RELEASE_REPO_URL, timeout_seconds: int = 5, *patterns: str) -> dict[str, str] | None:
    """The ref names (all, or those matching `patterns`) at `url` and the object each names, or None when it cannot be reached."""
    try:
        out = git.run(["ls-remote", url, *patterns], ".", timeout_seconds=timeout_seconds, env={**os.environ, **git.FETCH_ENV})
    except git.GitError:
        return None
    return {name: sha for sha, _, name in (line.partition("\t") for line in out.splitlines()) if name}


def pin_checks(root: Path) -> list[tuple[str, str]]:
    """Best effort, online only: every aidd ref the CI files pin exists at thaithienvanid/aidd, since a pin nobody can
    fetch breaks every CI run. Skipped with AIDD_OFFLINE=1, inside a hook (AIDD_HOOK_OFFLINE=1), without a GitHub
    remote, and when GitHub cannot be reached."""
    refs = pinned_refs(root)
    if not refs or "1" in (os.environ.get("AIDD_OFFLINE"), os.environ.get("AIDD_HOOK_OFFLINE")):
        return []
    remotes = git.run(["remote", "-v"], str(root), check=False, timeout_seconds=10) if (root / ".git").exists() else ""
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


def resolve_pin(ref: str | None) -> tuple[str | None, str | None, str]:
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
