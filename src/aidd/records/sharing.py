"""Sharing records through a git ref, `refs/aidd/records`, as git-bug shares its data: each record is one file in the
ref's tree, under the same `<yyyy>/<mm>/<id>.json` name, and ids never clash, so two machines merge by union.

`aidd records pull` fetches a remote's ref and adds the records this clone lacks, never changing one it has, and notes
each one it added as pulled: another's text, which `aidd risk --suggest` never counts. A pulled record must pass the
same checks as one written here.

`aidd records push` pulls first, then checks every file it would send and refuses the push when one fails: a link, a
file that is no record, or a value that looks like a secret. Its commit's only parent is the remote's, so nothing but
the checked records leaves, and the local ref moves only once the remote took it. A pushed record is permanent: union
merge never removes one, and everyone who can read the repository reads it.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from aidd.kernel import documents, git
from aidd.records import files

REF = "refs/aidd/records"
NAME = re.compile(r"[0-9]{4}/[0-9]{2}/([0-9]{8}T[0-9]{9}Z-[0-9a-f]{8})\.json")


def _said(err: str) -> str:
    """git's error text as aidd says it: a URL's user and password taken out, since a remote's URL may hold a token, and
    each line made safe for a terminal."""
    return "; ".join(documents.one_line(line, 300) for line in re.sub(r"://[^/@\s]+@", "://<redacted>@", err).splitlines() if line.strip())


def _tracking(remote: str) -> str:
    return f"refs/aidd/remotes/{remote}/records"


def _pulled_file(cwd: str) -> Path:
    return files.records_dir(cwd).parent / "records-pulled"


def pulled_ids(cwd: str = ".") -> set[str]:
    """The ids of the records `aidd records pull` added: another's text, never this clone's own account."""
    path = _pulled_file(cwd)
    return set(path.read_text(encoding="utf-8").split()) if path.is_file() else set()


def push_url(remote: str, cwd: str = ".") -> str:
    """Where a push to `remote` goes, as git resolves it, with any user and password taken out."""
    _check_remote(remote, cwd)
    return _said(git.run(["remote", "get-url", "--push", remote], cwd).strip())


def _check_remote(remote: str, cwd: str) -> None:
    names = git.run(["remote"], cwd).splitlines()
    if remote not in names:
        known = ", ".join(names) or "none"
        raise ValueError(f"{remote!r} is not a remote of this clone (its remotes: {known}); records go only to a remote the clone names")


def _local_names(cwd: str) -> dict[str, Path]:
    folder = files.records_dir(cwd)
    found = (p.relative_to(folder).as_posix() for p in folder.glob("*/*/*.json")) if folder.is_dir() else ()
    return {name: folder / name for name in found if NAME.fullmatch(name)}


def _commit_of(ref: str, cwd: str) -> str:
    return git.run(["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], cwd, check=False).strip()


def _share_problem(name: str, raw: bytes) -> str:
    """Why a file named `name` may not be shared, or "" when it may: it must be a record, of the id its name says, that
    passes the checks a record passes when it is written."""
    record = files.parse_record(raw)
    match = NAME.fullmatch(name)
    if record is None or not match or record["id"] != match.group(1):
        return "it is not a record whose id is its file name"
    problems = files.record_problems(record, any_type=True)
    return problems[0] if problems else ""


def pull_records(remote: str, cwd: str = ".") -> tuple[list[str], list[str]]:
    """(the records added from `remote`'s `refs/aidd/records`, by file name; the files there that are no record this
    aidd keeps, each with why). Both are empty when the remote has none, or this clone has them all."""
    _check_remote(remote, cwd)
    code, err = git.attempt(["fetch", "--no-tags", "--no-write-fetch-head", remote, f"+{REF}:{_tracking(remote)}"], cwd, {**os.environ, **git.FETCH_ENV})
    if code != 0:
        if "couldn't find remote ref" in err:
            return [], []
        raise git.GitError(f"git fetch {remote} {REF}: {_said(err)}")
    have = _local_names(cwd)
    theirs = {name: sha for name, sha in git.ls_tree(_tracking(remote), cwd).items() if NAME.fullmatch(name) and name not in have}
    blobs = git.raw_objects(sorted(set(theirs.values())), cwd)
    folder, added, refused = files.records_dir(cwd), [], []
    for name, sha in sorted(theirs.items()):
        raw = blobs.get(sha, b"")
        why = _share_problem(name, raw)
        if why:
            refused.append(f"{name}: {why}")
            continue
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Marked as pulled before it is written, so a run that stops between the two never counts it as this clone's.
        with _pulled_file(cwd).open("a", encoding="utf-8") as mark:
            mark.write(f"{Path(name).stem}\n")
        with path.open("xb") as f:  # never over a record this clone has
            f.write(raw)
        added.append(name)
    return added, refused


def push_records(remote: str, cwd: str = ".") -> tuple[int, int]:
    """Pull from `remote`, check every record this clone holds, then push them all to its `refs/aidd/records`, never
    forced: (the records pulled, the records the ref holds now). Refuses, naming each file, when one fails a check."""
    pulled = len(pull_records(remote, cwd)[0])
    names = _local_names(cwd)
    if not names:
        return pulled, 0
    order = sorted(names)
    root = files.records_dir(cwd).resolve()
    checked: dict[str, bytes] = {}
    bad = []
    for n in order:
        path = names[n]
        linked = path.is_symlink() or not path.is_file() or path.resolve().parent.parent.parent != root  # a link, or a linked folder
        why = "it, or its folder, is a link" if linked else _share_problem(n, raw := path.read_bytes())
        if why:
            bad.append(f"{path}: {why}")
        else:
            checked[n] = raw
    if bad:
        raise ValueError("nothing was pushed, because these files may not be shared; move each out of the records folder:\n  " + "\n  ".join(bad))
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        copies = Path(tmp) / "checked"
        copies.mkdir()
        for i, n in enumerate(order):  # the exact bytes that passed the check, never the file as it stands later
            (copies / str(i)).write_bytes(checked[n])
        shas = git.run(["hash-object", "-w", "--no-filters", "--stdin-paths"], cwd, input="".join(f"{copies / str(i)}\n" for i in range(len(order)))).split()
        git.run(["update-index", "--add", "--index-info"], cwd, env=env, input="".join(f"100644 {s}\t{n}\n" for n, s in zip(order, shas, strict=True)))
        tree = git.run(["write-tree"], cwd, env=env).strip()
    # The remote's commit is the only parent: the tree already holds every record pulled from it, so the push is a
    # fast-forward, and no other history this clone's ref points at can leave with it.
    theirs = _commit_of(_tracking(remote), cwd)
    if theirs and git.run(["rev-parse", f"{theirs}^{{tree}}"], cwd).strip() == tree:
        head = theirs
    else:
        head = git.run(["commit-tree", tree, *(["-p", theirs] if theirs else []), "-m", "aidd records"], cwd).strip()
    code, err = git.attempt(["push", remote, f"{head}:{REF}"], cwd, {**os.environ, **git.FETCH_ENV})
    if code != 0:
        if "fetch first" in err or "non-fast-forward" in err:
            raise git.GitError(f"{remote} got new records while this ran, so nothing was replaced: run `aidd records push` again")
        raise git.GitError(f"{remote} refused the records: {_said(err)}")
    git.run(["update-ref", REF, head], cwd)  # only once the remote took it
    return pulled, len(names)
