"""Sharing records through a git ref, `refs/aidd/records`, as git-bug shares its data: each record is one file in the
ref's tree, under the same `<yyyy>/<mm>/<id>.json` name, and ids never clash, so two machines merge by union.

`aidd records pull` fetches a remote's ref and adds the records this clone lacks, never changing one it has, and notes
each one it added as pulled: another's text, which `aidd risk --suggest` never counts. A pulled record must pass the
same checks as one written here.

`aidd records push` pulls first, then checks every file it would send and refuses the push when one fails: a link, a
file that is no record, or a value that looks like a secret. Its commit's only parent is the remote's, so nothing but
the remote's record files and the checked records leaves. A record the remote holds is never rewritten, and the local
ref moves only once the remote took it. A pushed record is permanent: union merge never removes one, and everyone who
can read the repository reads it.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from aidd.kernel import documents, git
from aidd.records import files

REF = "refs/aidd/records"
RECORDS_HOME = ".git/aidd/records"  # where a clone keeps its records, as people know it
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
    if not files.in_own_month(Path(name), _id_of(name)):
        return "its folder is not the year and month of its id"
    problems = files.record_problems(record, any_type=True)
    return problems[0] if problems else ""


def _case_clash(name: str, path: Path, folder: Path, remote: str) -> git.GitError:
    """The error for a record the remote has, when this clone holds a file of the same name apart from its case, which a
    case-insensitive file system cannot keep beside it: it names the file to rename or move."""
    mine = next((p for p in path.parent.iterdir() if p.name.lower() == path.name.lower()), path)
    return git.GitError(
        f"{remote} has the record {name}, and this clone holds {RECORDS_HOME}/{mine.relative_to(folder).as_posix()}, which differs only by case, "
        f"so nothing more was pulled. Rename that file, or move it out of {RECORDS_HOME}/, then run `aidd records pull` again"
    )


def pull_records(remote: str, cwd: str = ".") -> tuple[list[str], list[str]]:
    """(the records added from `remote`'s `refs/aidd/records`, by file name; the files there that are no record this
    aidd keeps, each with why). Both are empty when the remote has none, or this clone has them all."""
    _check_remote(remote, cwd)
    # `--no-filter`: a partial clone's filter would leave the records' blobs out, and no read fetches a missing one.
    code, err = git.attempt(
        ["fetch", "--no-tags", "--no-filter", "--no-write-fetch-head", remote, f"+{REF}:{_tracking(remote)}"], cwd, {**os.environ, **git.FETCH_ENV}, remote=True
    )
    if code != 0:
        if "couldn't find remote ref" in err:
            return [], []
        raise git.GitError(f"git fetch {remote} {REF}: {_said(err)}")
    have = _local_names(cwd)
    theirs = {name: sha for name, sha in git.ls_tree(_tracking(remote), cwd).items() if NAME.fullmatch(name) and name not in have}
    blobs = git.raw_objects(sorted(set(theirs.values())), cwd)
    absent = sorted(name for name, sha in theirs.items() if sha not in blobs)
    if absent:
        # The tracking ref may already sit at the remote's tip, as in a clone that pulled with its filter on, so a plain fetch
        # sends nothing: fetch everything once more, which asks for the objects the filter left out.
        again = ["fetch", "--no-tags", "--no-filter", "--refetch", "--no-write-fetch-head", remote, f"+{REF}:{_tracking(remote)}"]
        code, err = git.attempt(again, cwd, {**os.environ, **git.FETCH_ENV}, remote=True)
        if code != 0:
            raise git.GitError(
                f"{len(absent)} record(s) at {remote} have no content in this clone, and the full fetch that would bring them failed: {_said(err)}. "
                f"Nothing was pulled or pushed. `git fetch --refetch` needs git 2.36 or newer, so update git if it is older; otherwise run `aidd records pull` again"
            )
        blobs = git.raw_objects(sorted(set(theirs.values())), cwd)
        absent = sorted(name for name, sha in theirs.items() if sha not in blobs)
    if absent:  # never read as empty: a push after this would drop them from the remote
        shown = ", ".join(absent[:3]) + (f", and {len(absent) - 3} more" if len(absent) > 3 else "")
        raise git.GitError(
            f"{len(absent)} record(s) at {remote} have no content, even after a full fetch ({shown}), so {remote} lacks them and nothing was pulled or pushed. "
            f"Ask whoever pushed them to run `aidd records push` again"
        )
    folder, added, refused = files.records_dir(cwd), [], []
    for name, sha in sorted(theirs.items()):
        raw = blobs.get(sha, b"")
        why = _share_problem(name, raw)
        if why:
            refused.append(f"{name}: {why}")
            continue
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():  # only a file that differs by case, on a case-insensitive file system, reaches here
            raise _case_clash(name, path, folder, remote)
        # Marked as pulled before it is written, so a run that stops between the two never counts it as this clone's.
        with _pulled_file(cwd).open("a", encoding="utf-8") as mark:
            mark.write(f"{Path(name).stem}\n")
        try:
            with path.open("xb") as f:  # never over a record this clone has
                f.write(raw)
        except FileExistsError:
            raise _case_clash(name, path, folder, remote) from None
        added.append(name)
    return added, refused


def _id_of(name: str) -> str:
    """The id in a record's file name (`<yyyy>/<mm>/<id>.json`)."""
    return name.rpartition("/")[2].removesuffix(".json")


def _remote_entries(commit: str, cwd: str) -> dict[str, str]:
    """The files of a remote commit's tree that are named like a record and are regular files, by name and blob id. Any
    other path there (a `.git/config` that git refuses in an index, a link, a folder) is left out, and so drops from the
    next push, because only a record may live in this ref."""
    if not commit:
        return {}
    held = {}
    for entry in git.run(["ls-tree", "-r", "-z", "--full-tree", commit], cwd).split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[:2] == ["100644", "blob"] and NAME.fullmatch(path):
            held[path] = parts[2]
    return held


def _records_commit(remote: str, records: dict[str, bytes], cwd: str) -> str:
    """The commit to push: the remote's record files (a file this aidd refused stays as it is), plus `records`, the exact
    bytes that passed the checks, parented on the remote's commit so the push is a fast-forward and no other history
    leaves. A record is a fact someone wrote, so one the remote holds under the same name with other content is never
    replaced: that refuses the push (ValueError)."""
    theirs = _commit_of(_tracking(remote), cwd)
    held = _remote_entries(theirs, cwd)
    order = sorted(records)
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        copies = Path(tmp) / "checked"
        copies.mkdir()
        for i, n in enumerate(order):
            (copies / str(i)).write_bytes(records[n])
        shas = git.run(["hash-object", "-w", "--no-filters", "--stdin-paths"], cwd, input="".join(f"{copies / str(i)}\n" for i in range(len(order)))).split()
        mine = dict(zip(order, shas, strict=True))
        # By id, and only the file in its id's own year and month: a copy in another folder is a refused file, and never the
        # record a clone is compared with.
        held_by_id = {_id_of(n): sha for n, sha in held.items() if files.in_own_month(Path(n), _id_of(n))}
        changed = sorted(n for n, sha in mine.items() if held_by_id.get(_id_of(n), sha) != sha)
        if changed:
            raise ValueError(
                f"nothing was pushed, because these records differ from the ones {remote} holds with the same id, and a record is never rewritten:\n  "
                + "\n  ".join(f"{RECORDS_HOME}/{n}" for n in changed)
                + f"\nMove each file out of {RECORDS_HOME}/, run `aidd records pull`, and write what changed as a new record with `aidd records add`"
            )
        entries = {**held, **mine}
        git.run(["update-index", "--add", "--index-info"], cwd, env=env, input="".join(f"100644 {sha}\t{n}\n" for n, sha in sorted(entries.items())))
        tree = git.run(["write-tree"], cwd, env=env).strip()
    if theirs and git.run(["rev-parse", f"{theirs}^{{tree}}"], cwd).strip() == tree:
        return theirs
    return git.run(["commit-tree", tree, *(["-p", theirs] if theirs else []), "-m", "aidd records"], cwd).strip()


def push_records(remote: str, cwd: str = ".") -> tuple[int, int]:
    """Pull from `remote`, check every record this clone holds, then push them all to its `refs/aidd/records`, never
    forced: (the records pulled, the records the ref holds now). Refuses, naming each file, when one of this clone's fails a
    check, or when the pull found a record without its content. A file there that the pull refused stays as it is: the
    pushed tree starts from the remote's own, so nothing is dropped and nobody is blocked."""
    added, _refused = pull_records(remote, cwd)
    pulled = len(added)
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
    try:
        head = _records_commit(remote, {n: checked[n] for n in order}, cwd)
    except git.GitError as exc:
        raise git.GitError(
            f"aidd could not build the records to push from {remote}'s ({_said(str(exc))}), so nothing was pushed. "
            f"Run `aidd records pull` and `aidd records push` again; if this repeats, {remote}'s {REF} holds something git cannot read, so ask whoever runs {remote} to check it"
        ) from exc
    code, err = git.attempt(["push", remote, f"{head}:{REF}"], cwd, {**os.environ, **git.FETCH_ENV}, remote=True)
    if code != 0:
        if "fetch first" in err or "non-fast-forward" in err:
            raise git.GitError(f"{remote} got new records while this ran, so nothing was replaced: run `aidd records push` again")
        raise git.GitError(f"{remote} refused the records: {_said(err)}")
    git.run(["update-ref", REF, head], cwd)  # only once the remote took it
    return pulled, len(names)
