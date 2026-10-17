"""The work items and the config as a git ref holds them, read offline, and who added each file."""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git

MAX_OBJECTS = 5000  # objects read at a ref; a Specs folder larger than this is read in part, and says so


def config_at(root: Path | None) -> config.Config | None:
    """The repository's config, read offline; None when it is missing or unreadable."""
    if root is None or not (root / config.CONFIG_PATH).is_file():
        return None

    def offline(url: str) -> bytes:
        raise config.ConfigError(f"not fetched: {url}")

    try:
        return config.load_file(config.CONFIG_PATH, str(root), fetch=offline)
    except Exception:  # noqa: BLE001  # an unreadable config is `aidd validate`'s own finding; agent: ids still count
        return None


def objects_at(root: Path, ref: str, specs_dir: str) -> tuple[list[tuple[str, dict, str, str]], bool]:
    """Every aidd object under `specs_dir` at `ref` (not only this branch's): (path, front matter, body, text), and
    whether the read stopped at MAX_OBJECTS. One `git cat-file --batch` reads them all."""
    listed = git.run(["ls-tree", "-r", "-z", "--name-only", ref, "--", specs_dir], str(root), check=False).split("\0")
    paths = [p for p in listed if p.endswith(".md") and Path(p).name.lower() != "readme.md"]
    capped = len(paths) > MAX_OBJECTS
    return read_at(root, ref, paths[:MAX_OBJECTS]), capped


def read_at(root: Path, ref: str, paths: list[str]) -> list[tuple[str, dict, str, str]]:
    """The aidd objects among `paths` as `ref` holds them: (path, front matter, body, text). One `git cat-file`."""
    if not paths:
        return []
    proc = git._git(["cat-file", "--batch"], str(root), input="".join(f"{ref}:{p}\n" for p in paths))
    raw, pos, out = proc.stdout, 0, []
    for p in paths:
        nl = raw.find(b"\n", pos)
        if nl < 0:
            break
        header = raw[pos:nl].split()
        pos = nl + 1
        if len(header) != 3 or header[1] != b"blob":
            continue
        size = int(header[2])
        text = raw[pos : pos + size].decode("utf-8", errors="replace")
        pos += size + 1
        if not text.lstrip("﻿").startswith("---"):
            continue
        try:
            data, body = documents.split_front_matter(text, p)
        except documents.DocumentError:
            continue
        if "kind" not in data:
            continue
        out.append((p, data, body, text))
    return out


def authors(root: Path, ref: str, specs_dir: str) -> dict[str, set[str]]:
    """Who added each file under `specs_dir`, as of `ref`: its first commit's author email and name, lowercased."""
    # Each commit is NUL, then its id, author email, and author name each ended by NUL, then the file names. Neither
    # field can hold a NUL, so an author name cannot add a commit or claim another's files.
    log = git.run(["log", "--diff-filter=A", "--format=%x00%H%x00%ae%x00%an%x00", "--name-only", ref, "--", specs_dir], str(root), check=False)
    out: dict[str, set[str]] = {}
    tokens = log.split("\0")[1:]
    for i in range(0, len(tokens) - 3, 4):
        sha, email, name, names = tokens[i : i + 4]
        if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha):
            break
        for p in names.split("\n"):
            if p.strip():
                out[p.strip()] = {x for x in (email.lower(), f"email:{email.lower()}", name.lower()) if x and x != "email:"}
    return out
