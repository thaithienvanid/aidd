"""Locate bundled data: schemas, the skill, CI templates, the aidd-team plugin, and the standards library and stacks.

An installed wheel carries them under aidd/_data. A source checkout reads them
from the repository root, so the package and the repo never hold two copies.
The zipapp (`aidd.pyz`, built by `aidd.pyz`) carries them under aidd/_data inside
the archive; the first run extracts that folder, once per archive, into the user's
cache, since callers copy and walk the data as real files.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.resources
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from types import ModuleType

from aidd.kernel import git

# The aidd package folder (this module lives one level down, in aidd.kernel), and the checkout root above src/.
_PKG = Path(__file__).resolve().parents[1]
_REPO = _PKG.parent.parent
# aidd's own repository, where its releases and its source come from.
REPOSITORY_URL = "https://github.com/thaithienvanid/aidd"

LAYOUT = {
    "schemas": "schemas",
    "skill": ".agents/skills/aidd",
    "templates": "templates",
    "team": "plugins/aidd-team",
    "packs": "plugins/aidd-packs",
    "standards": "standards",
    "stacks": "stacks",
}
DATA_PREFIX = "aidd/_data/"
# The most the zipapp, and each file extracted from it, may hold. The largest data file is about 0.3 MB.
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024  # all the members together: many small files must not fill the cache either
# An extracted folder no zipapp has used for this long is removed when another zipapp extracts its own, so each new
# release's 6 MB do not pile up. A zipapp in use touches its folder's `.complete` once a run, so it is never removed.
STALE_EXTRACTED_SECONDS = 14 * 24 * 60 * 60


def archive() -> Path | None:
    """The zipapp this aidd runs from, or None when it runs from files on disk."""
    parent = _PKG.parent
    return parent if parent.is_file() and zipfile.is_zipfile(parent) else None


def cache_home() -> Path:
    """aidd's folder in the user's cache: the zipapp's extracted data and the daily update check."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "aidd"


_cache_home = cache_home


@functools.cache
def _extracted(pyz: Path) -> Path:
    """The archive's aidd/_data, extracted under the user's cache in a folder named by the archive's sha256, so a new
    or changed archive never reads another's data. Written to a temporary folder and renamed into place whole."""
    if pyz.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError(f"{pyz}: larger than {MAX_ARCHIVE_BYTES} bytes")
    with pyz.open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()[:24]
    dest = _cache_home() / f"pyz-{digest}"
    if (dest / ".complete").is_file():
        try:
            os.utime(dest / ".complete")  # in use: `_remove_stale_extracted` keeps it
        except OSError:
            pass
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_extracted(dest.parent)
    tmp = Path(tempfile.mkdtemp(prefix=".pyz-", dir=dest.parent))
    try:
        total = 0
        with zipfile.ZipFile(pyz) as zf:
            for info in zf.infolist():
                if not info.filename.startswith(DATA_PREFIX) or info.is_dir():
                    continue
                rel = PurePosixPath(info.filename[len(DATA_PREFIX) :])
                if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                    raise ValueError(f"{pyz}: unsafe member {info.filename!r}")
                target = tmp.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as member:
                    data = member.read(MAX_MEMBER_BYTES + 1)  # bounded, whatever size the header claims
                if len(data) > MAX_MEMBER_BYTES:
                    raise ValueError(f"{pyz}: {info.filename!r} is larger than {MAX_MEMBER_BYTES} bytes")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError(f"{pyz}: its data is larger than {MAX_TOTAL_BYTES} bytes in all")
                target.write_bytes(data)
        (tmp / ".complete").write_text(digest + "\n", encoding="utf-8")
        try:
            os.replace(tmp, dest)
        except OSError:  # another process finished first, or a stale partial folder is in the way
            if not (dest / ".complete").is_file():
                shutil.rmtree(dest, ignore_errors=True)
                os.replace(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


def _remove_stale_extracted(cache: Path) -> None:
    """Remove each `pyz-*` folder in aidd's cache that no zipapp has used for `STALE_EXTRACTED_SECONDS`, by the time of
    its `.complete`. A folder that is no link and has no `.complete` is a partial one, removed by the same age."""
    cutoff = time.time() - STALE_EXTRACTED_SECONDS
    for old in (p for p in cache.glob("pyz-*") if re.fullmatch(r"pyz-[0-9a-f]{24}", p.name)):  # `_extracted`'s names only
        try:
            if old.is_symlink() or not old.is_dir():
                continue
            mark = old / ".complete"
            if (mark.stat() if mark.is_file() else old.stat()).st_mtime < cutoff:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            continue


def data_dir(name: str) -> Path:
    pyz = archive()
    if pyz is not None:
        extracted = _extracted(pyz) / name
        if extracted.is_dir():
            return extracted
        raise FileNotFoundError(f"aidd data directory not found in {pyz}: {name}")
    bundled = _PKG / "_data" / name
    if bundled.is_dir():
        return bundled
    source = _REPO / LAYOUT[name]
    if source.is_dir():
        return source
    raise FileNotFoundError(f"aidd data directory not found: {name}")


def team_tool(name: str) -> ModuleType:
    """A tool the aidd-team plugin ships (`plugins/aidd-team/tools/<name>/<name>.py`), loaded as a module from aidd's
    data, so aidd runs the same code a person runs with aidd-team alone. Loaded once a process."""
    key = f"aidd_team_tools.{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = data_dir("team") / "tools" / name / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, path) if path.is_file() else None
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"aidd-team's {name} tool not found at {path}: reinstall aidd (`aidd self-update`)")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]  # a module that failed to load is never handed out half made
        raise
    return module


def repo_root() -> Path | None:
    """The source checkout root, or None when running from an installed wheel or the zipapp."""
    if archive() is not None:
        return None
    return _REPO if (_REPO / "schemas").is_dir() and (_REPO / "src" / "aidd").is_dir() else None


def source_commit() -> str | None:
    """The commit of the aidd source checkout this aidd runs from (its HEAD, such as the commit the reusable workflow
    pins), or None from a wheel, the zipapp, or a folder that is not a git checkout."""
    src = repo_root()
    if src is None or not (src / ".git").exists():
        return None
    try:
        sha = git.run(["rev-parse", "HEAD"], str(src), timeout_seconds=10).strip()
    except git.GitError:
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def installed_commit() -> str | None:
    """The commit of aidd's own repository that this aidd was installed from, as the installer recorded it (PEP 610's
    `direct_url.json`, written by `uv tool install git+https://github.com/thaithienvanid/aidd@<sha>` and by pip): only
    when that installed copy is the code running now."""
    from importlib import metadata

    try:
        dist = metadata.distribution("aidd")
        running = Path(__file__).resolve().parents[2]
        if not running.is_relative_to(Path(str(dist.locate_file(""))).resolve()):
            return None
        data = json.loads(dist.read_text("direct_url.json") or "{}")
    except (metadata.PackageNotFoundError, OSError, ValueError):
        return None
    vcs = data.get("vcs_info") if isinstance(data, dict) else None
    sha = vcs.get("commit_id") if isinstance(vcs, dict) and vcs.get("vcs") == "git" else None
    url = str(data.get("url", "")).removesuffix("/").removesuffix(".git")
    return sha if url == REPOSITORY_URL and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def running_commit() -> str | None:
    """The commit of aidd's own repository this aidd runs from: a source checkout's HEAD, else the commit a git install
    recorded (`installed_commit`). None from a release wheel or the zipapp, whose version names the release."""
    src = repo_root()
    if src is None or not (src / ".git").exists():
        return installed_commit()
    return source_commit()


def package_text(package: str, *parts: str) -> str:
    """A text file that ships inside an aidd package, such as `package_text("aidd.views", "design", "tokens.json")`. It
    reads through importlib.resources, so it works from the zipapp too, where a module's `__file__` is inside the
    archive and no folder on disk."""
    return importlib.resources.files(package).joinpath(*parts).read_text(encoding="utf-8")


@functools.cache
def load_json(name: str) -> dict:
    """A bundled JSON file under schemas/. A file too large to read as one names its parts (`"$parts": {key: file}`):
    each part file holds that key's value, and the result holds them all, as if one file did."""
    folder = data_dir("schemas")
    data = json.loads((folder / name).read_text(encoding="utf-8"))
    for key, part in (data.pop("$parts", None) or {}).items() if isinstance(data, dict) else ():
        data[key] = json.loads((folder / part).read_text(encoding="utf-8"))
    return data


SCHEMA_URN = "urn:aidd:1:"


def schema_file(ref_file: str) -> str:
    """The bundled file a $ref's document part names: `urn:aidd:1:<name>` (a schema's `$id`) is `<name>.schema.json`;
    a plain file name is itself."""
    if ref_file.startswith(SCHEMA_URN):
        return ref_file.removeprefix(SCHEMA_URN) + ".schema.json"
    return ref_file
