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
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

# The aidd package folder (this module lives one level down, in aidd.kernel), and the checkout root above src/.
_PKG = Path(__file__).resolve().parents[1]
_REPO = _PKG.parent.parent

_LAYOUT = {
    "schemas": "schemas",
    "skill": ".agents/skills/aidd",
    "templates": "templates",
    "team": "plugins/aidd-team",
    "standards": "standards",
    "stacks": "stacks",
}
DATA_PREFIX = "aidd/_data/"


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
    digest = hashlib.sha256(pyz.read_bytes()).hexdigest()[:24]
    dest = _cache_home() / f"pyz-{digest}"
    if (dest / ".complete").is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".pyz-", dir=dest.parent))
    try:
        with zipfile.ZipFile(pyz) as zf:
            for info in zf.infolist():
                if not info.filename.startswith(DATA_PREFIX) or info.is_dir():
                    continue
                rel = PurePosixPath(info.filename[len(DATA_PREFIX) :])
                if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                    raise ValueError(f"{pyz}: unsafe member {info.filename!r}")
                target = tmp.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
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
    source = _REPO / _LAYOUT[name]
    if source.is_dir():
        return source
    raise FileNotFoundError(f"aidd data directory not found: {name}")


def repo_root() -> Path | None:
    """The source checkout root, or None when running from an installed wheel or the zipapp."""
    if archive() is not None:
        return None
    return _REPO if (_REPO / "schemas").is_dir() and (_REPO / "src" / "aidd").is_dir() else None


@functools.cache
def load_json(name: str) -> dict:
    return json.loads((data_dir("schemas") / name).read_text(encoding="utf-8"))


SCHEMA_URN = "urn:aidd:1:"


def schema_file(ref_file: str) -> str:
    """The bundled file a $ref's document part names: `urn:aidd:1:<name>` (a schema's `$id`) is `<name>.schema.json`;
    a plain file name is itself."""
    if ref_file.startswith(SCHEMA_URN):
        return ref_file.removeprefix(SCHEMA_URN) + ".schema.json"
    return ref_file
