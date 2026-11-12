"""Release files under `docs/releases/`: what is live in an environment, what was rolled back there, `aidd new release`,
and `aidd validate` checks on release files.

Rule 2 and Rule 3 of the design govern every read here:
- Live commit: the `commit` of the newest release file for an environment by `released_at`, or the default branch's tip for
  an environment that deploys on merge unless a release file is newer.
- Live Specs: the Specs that the live commit holds under the specs folder, minus any listed under `rolled_back` of some
  release of that environment with no later release listing them in `specs`. When a clone cannot read the live commit,
  `read_environment` falls back to the release files' `specs` lists and sets `note` to `"not checked: fetch the history"`.
- Rolled back: Specs not live there by Rule 2 that an earlier live commit of that environment held.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, git, globs, strict_yaml, timestamps
from aidd.kernel import text as kernel_text
from aidd.kernel.text import did_you_mean
from aidd.workitems import authoring, ids, objects, repo_reads

SHALLOW_NOTE = "not checked: fetch the history"
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$")
_HEX_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_SAFE_ENV = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Release:
    """One parsed release file from `docs/releases/`."""

    path: str
    environment: str
    released_at: str
    released_at_dt: dt.datetime
    commit: str
    specs: tuple[str, ...]
    rolled_back: tuple[str, ...]


@dataclass(frozen=True)
class EnvironmentState:
    """What is live and rolled back in one environment, derived from release files and git history."""

    environment: str
    live_commit: str | None
    live_specs: tuple[str, ...]
    rolled_back: tuple[str, ...]
    releases: tuple[Release, ...]
    note: str = ""


def _parse_rfc3339(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        return None
    return timestamps.parse_time(value)


def _environments(cfg: config.Config | None) -> list[dict]:
    raw = (cfg or config.EMPTY).get("environments", default=[])
    return [dict(e) for e in raw if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]]


def _environment_entry(cfg: config.Config | None, environment: str) -> dict | None:
    return next((e for e in _environments(cfg) if e.get("name") == environment), None)


def _branch_matches(pattern: str, branch: str) -> bool:
    return globs.match(pattern, branch) if globs.is_pattern(pattern) else pattern == branch


def _is_git_repo(root: Path | None) -> bool:
    if root is None:
        return False
    try:
        return git.repository_top(str(root)) is not None
    except git.GitError:
        return False


def _is_shallow(root: Path) -> bool:
    return git.run(["rev-parse", "--is-shallow-repository"], str(root), check=False).strip() == "true"


def _default_branch_tip(root: Path) -> tuple[str, dt.datetime] | None:
    """`(sha, committer_dt)` of the repository's default branch tip, reading remote first when tracked."""
    names, exact = git.default_branches(str(root))
    if not names:
        return None
    name = names[0]
    remote_first = exact and git.trunk_is_remote(str(root))
    candidates = [f"refs/remotes/origin/{name}", f"refs/heads/{name}"] if remote_first else [f"refs/heads/{name}", f"refs/remotes/origin/{name}"]
    tip = next((_try_rev_parse(root, ref) for ref in candidates if _try_rev_parse(root, ref)), "")
    if not tip:
        try:
            tip = git.rev_parse(git.default_base(str(root)), str(root))
        except git.GitError:
            return None
    rows = git.log_fields(["-1", tip], ["%H", "%ct"], str(root), check=False)
    return (rows[0][0], dt.datetime.fromtimestamp(int(rows[0][1]), tz=dt.UTC)) if rows else None


def _try_rev_parse(root: Path, ref: str) -> str:
    try:
        return git.rev_parse(ref, str(root))
    except git.GitError:
        return ""


def _deploys_on_merge(root: Path, env_cfg: dict | None) -> bool:
    if not env_cfg:
        return False
    patterns = [str(b) for b in env_cfg.get("branches") or [] if isinstance(b, str)]
    if not patterns:
        return False
    names, _ = git.default_branches(str(root))
    return any(_branch_matches(pat, b) for b in names[:1] for pat in patterns)


def _spec_id_from_text(rel: str, text: str) -> str | None:
    found = objects.front_line_in(iter(text.splitlines(keepends=True)))
    if not found or found[1] != "spec":
        return None
    try:
        data, _ = documents.split_front_matter(text, rel)
    except documents.DocumentError:
        return None
    sid = data.get("id")
    return sid if data.get("type") == "spec" and isinstance(sid, str) and ids.is_id(sid) else None


def _is_candidate_spec(rel: str, specs_dir: str) -> bool:
    return bool(rel) and rel.endswith(".md") and Path(rel).name.lower() != "readme.md" and not objects.is_saved_request(rel, specs_dir)


def _specs_at_commit(
    root: Path,
    ref: str,
    specs_dir: str,
    cache: dict[tuple[str, str], str | None] | None = None,
) -> list[str]:
    """Sorted unique Spec IDs held under `specs_dir` at commit `ref`. Raises `git.GitError` when `ref` cannot be read."""
    sha = git.rev_parse(f"{ref}^{{commit}}", str(root))
    tree = git.ls_tree(sha, str(root), paths=[specs_dir])
    found: set[str] = set()
    for rel, oid in tree.items():
        if not _is_candidate_spec(rel, specs_dir):
            continue
        key = (rel, oid)
        if cache is not None and key in cache:
            sid = cache[key]
        else:
            text = git.show(sha, rel, str(root))
            sid = _spec_id_from_text(rel, text) if text is not None else None
            if cache is not None:
                cache[key] = sid
        if sid:
            found.add(sid)
    return sorted(found)


def _first_parent_commits(root: Path, tip: str) -> list[tuple[str, str]]:
    """First-parent commits reachable from `tip`, as `(sha, first_parent_sha)` pairs."""
    by_sha = {row[0]: row[1].split()[0] if row[1].strip() else "" for row in git.log_fields([tip], ["%H", "%P"], str(root), check=False)}
    chain: list[tuple[str, str]] = []
    cur = tip
    while cur in by_sha:
        parent = by_sha[cur]
        if parent:
            chain.append((cur, parent))
        cur = parent
    return chain


def _deleted_specs_on_first_parent(root: Path, tip: str, specs_dir: str) -> list[str]:
    """Spec IDs whose files under `specs_dir` were deleted along the `--first-parent` chain ending at `tip`."""
    touching = {row[0] for row in git.log_fields([tip, "--", specs_dir], ["%H"], str(root), check=False)}
    found: set[str] = set()
    for commit_sha, parent_sha in _first_parent_commits(root, tip):
        if commit_sha not in touching:
            continue
        raw = git.run(["diff", "--name-only", "-z", parent_sha, commit_sha, "--", specs_dir], str(root), check=False, raw=True)
        for rel in raw.split("\0"):
            if not _is_candidate_spec(rel, specs_dir) or git.show(commit_sha, rel, str(root)) is not None:
                continue
            text = git.show(parent_sha, rel, str(root))
            if text is not None and (sid := _spec_id_from_text(rel, text)):
                found.add(sid)
    return sorted(found)


def _parse_release(path_str: str, data: dict) -> Release | None:
    if data.get("type") != "release":
        return None
    env, raw_at, commit = data.get("environment"), data.get("released_at"), data.get("commit")
    raw_specs, raw_rb = data.get("specs"), data.get("rolled_back") or []
    at_dt = _parse_rfc3339(raw_at)
    if not (
        isinstance(env, str)
        and bool(env)
        and at_dt is not None
        and isinstance(commit, str)
        and bool(_HEX_SHA.fullmatch(commit))
        and isinstance(raw_specs, list)
        and isinstance(raw_rb, list)
    ):
        return None
    return Release(
        path=path_str,
        environment=env,
        released_at=str(raw_at),
        released_at_dt=at_dt,
        commit=commit,
        specs=tuple(s for s in raw_specs if isinstance(s, str)),
        rolled_back=tuple(s for s in raw_rb if isinstance(s, str)),
    )


def _load_releases(root: Path, environment: str | None = None) -> list[Release]:
    files, _ = objects.work_files(root, objects.OPS_DIRS["release"])
    out: list[Release] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        text, _ = objects.read_document(root, rel)
        if text is None:
            continue
        try:
            data, _ = documents.split_front_matter(text, rel)
        except documents.DocumentError:
            continue
        parsed = _parse_release(rel, data)
        if parsed is not None and (environment is None or parsed.environment == environment):
            out.append(parsed)
    return sorted(out, key=lambda r: (r.released_at_dt, r.path))


def _resolve_or_keep(root: Path, commit: str) -> str:
    return _try_rev_parse(root, f"{commit}^{{commit}}") or commit


def _pick_live_commit(
    root: Path,
    releases: list[Release],
    default_tip: tuple[str, dt.datetime] | None,
    has_git: bool,
) -> str | None:
    if default_tip is not None:
        tip_sha, tip_dt = default_tip
        if releases and releases[-1].released_at_dt > tip_dt:
            return _resolve_or_keep(root, releases[-1].commit) if has_git else releases[-1].commit
        return tip_sha
    if releases:
        return _resolve_or_keep(root, releases[-1].commit) if has_git else releases[-1].commit
    return None


def _active_rollbacks(releases: list[Release]) -> set[str]:
    active: set[str] = set()
    for r in releases:
        active.difference_update(r.specs)
        active.update(r.rolled_back)
    return active


@dataclass(frozen=True)
class _Scan:
    root: Path
    specs_dir: str
    has_git: bool
    blob_cache: dict[tuple[str, str], str | None]


def _earlier_held_specs(
    scan: _Scan,
    releases: list[Release],
    default_tip: tuple[str, dt.datetime] | None,
    live_commit: str | None,
) -> tuple[set[str], str]:
    held: set[str] = set()
    note = ""
    for r in releases:
        if scan.has_git:
            try:
                held.update(_specs_at_commit(scan.root, r.commit, scan.specs_dir, scan.blob_cache))
                continue
            except git.GitError:
                note = SHALLOW_NOTE
        held.update(r.specs)
    if default_tip is not None:
        tip_sha, _ = default_tip
        if live_commit != tip_sha:
            try:
                held.update(_specs_at_commit(scan.root, tip_sha, scan.specs_dir, scan.blob_cache))
            except git.GitError:
                note = SHALLOW_NOTE
        held.update(_deleted_specs_on_first_parent(scan.root, tip_sha, scan.specs_dir))
    return held, note


def read_environment(root: Path, environment: str, cfg: config.Config | None = None) -> EnvironmentState:
    """What is live and rolled back in `environment` according to Rules 2 and 3."""
    cfg = cfg if cfg is not None else repo_reads.config_at(root)
    specs_dir = (cfg or config.EMPTY).specs_dir
    releases = _load_releases(root, environment)
    has_git = _is_git_repo(root)
    default_tip = _default_branch_tip(root) if has_git and _deploys_on_merge(root, _environment_entry(cfg, environment)) else None
    live_commit = _pick_live_commit(root, releases, default_tip, has_git)
    rollbacks = _active_rollbacks(releases)

    scan = _Scan(root=root, specs_dir=specs_dir, has_git=has_git, blob_cache={})
    note = ""
    live_set: set[str] = set()
    if live_commit is not None:
        try:
            held = _specs_at_commit(root, live_commit, specs_dir, scan.blob_cache) if has_git else []
            if not has_git:
                note = SHALLOW_NOTE
            else:
                live_set = {s for s in held if s not in rollbacks}
        except git.GitError:
            note = SHALLOW_NOTE
        if note:
            fallback: set[str] = set()
            for r in releases:
                fallback.update(r.specs)
                fallback.difference_update(r.rolled_back)
            live_set = fallback - rollbacks

    earlier_held, earlier_note = _earlier_held_specs(scan, releases, default_tip, live_commit)
    return EnvironmentState(
        environment=environment,
        live_commit=live_commit,
        live_specs=tuple(sorted(live_set)),
        rolled_back=tuple(sorted(earlier_held - live_set)),
        releases=tuple(releases),
        note=note or earlier_note,
    )


def _allowed_branch_refs(root: Path, env_cfg: dict) -> tuple[list[str], list[str]]:
    """`(ref_names, display_patterns)` for branches where a release commit may live (default branch + `env.branches`)."""
    default_names, _ = git.default_branches(str(root))
    env_patterns = [str(b) for b in env_cfg.get("branches") or [] if isinstance(b, str)]
    refs = git.run(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"], str(root), check=False).split()
    matched: list[str] = []
    for ref in refs:
        if ref.endswith("/HEAD"):
            continue
        if ref.startswith("refs/heads/"):
            bname = ref.removeprefix("refs/heads/")
        elif ref.startswith("refs/remotes/") and "/" in ref.removeprefix("refs/remotes/"):
            bname = ref.removeprefix("refs/remotes/").split("/", 1)[1]
        else:
            continue
        if bname in default_names or any(_branch_matches(pat, bname) for pat in env_patterns):
            matched.append(ref)
    return matched, list(dict.fromkeys([*default_names[:1], *env_patterns]))


def _commit_on_allowed_branch(root: Path, sha: str, env_cfg: dict) -> tuple[bool, list[str]]:
    refs, display = _allowed_branch_refs(root, env_cfg)
    return any(git.ok(["merge-base", "--is-ancestor", sha, ref], str(root)) for ref in refs), display


def _render_release(root: Path, draft: Release, day: str) -> str:
    tpl = authoring.template_text(root, "release", "release.md")
    text = kernel_text.fill_template(tpl, environment=draft.environment, released_at=draft.released_at, commit=draft.commit, released_day=day)
    m = re.match(r"\A(---\r?\n.*?\r?\n)(---[ \t]*(?:\r?\n|\Z).*)", text, re.S)
    if not m:
        return text
    front, rest = m.group(1), m.group(2)
    front = re.sub(r"(?m)^specs: .*$", lambda _: f"specs: {strict_yaml.flow(list(draft.specs))}", front, count=1)
    front = re.sub(r"(?m)^rolled_back: .*$", lambda _: f"rolled_back: {strict_yaml.flow(list(draft.rolled_back))}", front, count=1)
    return front + rest


def _next_sequence_path(root: Path, environment: str, day: str) -> Path:
    folder = root / objects.OPS_DIRS["release"]
    pattern = re.compile(rf"^{re.escape(environment)}-{re.escape(day)}-(\d+)\.md$")
    taken = [int(m.group(1)) for p in (folder.iterdir() if folder.is_dir() else []) for m in [pattern.match(p.name)] if m]
    return folder / f"{environment}-{day}-{max(taken, default=0) + 1}.md"


def _checked_released_at(root: Path, environment: str, released_at: str | None) -> tuple[str, str]:
    if released_at is None:
        at_dt = dt.datetime.now(dt.UTC)
        released_at_str = timestamps.utc_stamp(at_dt)
    else:
        parsed_at = _parse_rfc3339(released_at)
        if parsed_at is None:
            raise ValueError(
                f"`--released-at` {released_at!r} must be an ISO 8601 timestamp with timezone, such as `2026-11-20T15:10:00Z`; pass a valid timestamp or omit the flag"
            )
        at_dt = parsed_at
        released_at_str = released_at
    existing = _load_releases(root, environment)
    if existing and at_dt <= existing[-1].released_at_dt:
        latest = existing[-1]
        raise ValueError(
            f"`--released-at` ({released_at_str}) must be later than the newest release for {environment} ({latest.path} at {latest.released_at}); "
            f"pass a timestamp after {latest.released_at} or omit `--released-at`"
        )
    return released_at_str, at_dt.astimezone(dt.UTC).date().isoformat()


def _checked_new_release_inputs(
    root: Path,
    environment: str,
    commit: str,
    cfg: config.Config | None,
    released_at: str | None,
) -> tuple[config.Config, str, str, str]:
    if not _is_git_repo(root):
        raise ValueError(git.no_repository_problem("new release"))
    if _is_shallow(root):
        raise ValueError("this clone is shallow, so `aidd new release` cannot read the commit history it needs; run `git fetch --unshallow` first")
    cfg = repo_reads.config_at(root) if cfg is None else cfg
    q_env = command_names.quoted(environment) or "<environment>"
    q_sha = command_names.quoted(commit) or "<sha>"
    if cfg is None:
        raise ValueError(
            f"cannot read {config.CONFIG_PATH}; run `aidd init` or write `environments` there, then run `aidd new release {q_env} --commit {q_sha}`"
        )
    if not environment or not _SAFE_ENV.fullmatch(environment):
        raise ValueError(
            f"environment {environment!r} must start with a lowercase letter and use only lowercase letters, digits, `-`, and `_`; name one from `environments` in {config.CONFIG_PATH}"
        )
    envs = _environments(cfg)
    env_cfg = _environment_entry(cfg, environment)
    if env_cfg is None:
        known = [str(e["name"]) for e in envs]
        hint = did_you_mean(environment, known, form=f"aidd new release {{}} --commit {q_sha}") if known else ""
        raise ValueError(
            f"environment {environment!r} is not in {config.CONFIG_PATH}'s `environments` ({', '.join(known) or 'none'})"
            + (f"; {hint}" if hint else f"; add `- {{name: {environment}}}` under `environments` in {config.CONFIG_PATH}")
        )
    if not commit or commit.startswith("-"):
        raise ValueError("`aidd new release` needs `--commit <sha>`; run `git log -n 5 --oneline` and pass `--commit <sha>`")
    try:
        full_sha = git.rev_parse(f"{commit}^{{commit}}", str(root))
    except git.GitError:
        raise ValueError(f"commit {commit!r} is not in this repository; pick one from `git log -n 10 --oneline`, or run `git fetch --unshallow`") from None
    on_branch, display = _commit_on_allowed_branch(root, full_sha, env_cfg)
    if not on_branch:
        raise ValueError(
            f"commit {commit} ({full_sha[:12]}) is not on {', '.join(display) or 'default branch'}; merge it first, pass a commit on one of those branches, "
            f"or list its branch under `environments` for {environment} in {config.CONFIG_PATH}"
        )
    released_at_str, day = _checked_released_at(root, environment, released_at)
    return cfg, full_sha, released_at_str, day


def new_release(root: Path, environment: str, commit: str, *, cfg: config.Config | None = None, released_at: str | None = None) -> Path:
    """Write `<docs/releases>/<environment>-<yyyy-mm-dd>-<n>.md` per Rules 6 and 7, refusing unknown environments or off-branch commits."""
    cfg, full_sha, released_at_str, day = _checked_new_release_inputs(root, environment, commit, cfg, released_at)
    specs_dir = cfg.specs_dir
    prior = read_environment(root, environment, cfg)
    held_now = _specs_at_commit(root, full_sha, specs_dir)
    if prior.live_commit is not None:
        try:
            prior_held = set(_specs_at_commit(root, prior.live_commit, specs_dir))
        except git.GitError:
            prior_held = set(prior.live_specs)
    else:
        prior_held = set()
    specs_added = tuple(s for s in held_now if s not in prior_held)
    held_set = set(held_now)
    rolled_back_removed = tuple(s for s in prior.live_specs if s not in held_set)
    path = _next_sequence_path(root, environment, day)
    draft = Release(
        path=path.name,
        environment=environment,
        released_at=released_at_str,
        released_at_dt=dt.datetime.now(dt.UTC),
        commit=full_sha,
        specs=specs_added,
        rolled_back=rolled_back_removed,
    )
    authoring.write_new(
        path,
        _render_release(root, draft, day),
        "run `aidd new release` again to pick the next sequence number",
        root,
    )
    return path


def _file_commit_findings(root: Path, where: str, data: dict, env_cfg: dict | None, specs_dir: str) -> list[str]:
    commit = str(data.get("commit") or "")
    env = str(data.get("environment") or "")
    try:
        full_sha = git.rev_parse(f"{commit}^{{commit}}", str(root))
        held = set(_specs_at_commit(root, full_sha, specs_dir))
    except git.GitError:
        if _is_shallow(root):
            return [f"warning: {where}: commit {commit} is {SHALLOW_NOTE} (`git fetch --unshallow`)"]
        return [f"{where}: commit {commit} is not in this repository; set `commit` to a commit from `git log --oneline`, or run `git fetch`"]

    out = [
        f"{where}: `specs` lists {sid}, which commit {commit} does not hold under {specs_dir}/; remove {sid} from `specs`, or point `commit` at the commit that holds {sid}"
        for sid in data.get("specs") or []
        if sid not in held
    ]
    if env_cfg is not None and not _is_shallow(root):
        on_branch, display = _commit_on_allowed_branch(root, full_sha, env_cfg)
        if not on_branch:
            out.append(
                f"{where}: commit {commit} is not on {', '.join(display) or 'default branch'}; merge it first, or add its branch under `environments` for {env} in {config.CONFIG_PATH}"
            )
    return out


def file_findings(root: Path | None, path: Path, data: dict) -> list[str]:
    """Per-file validation findings (`aidd validate`) on one release file whose front matter already fits `release.schema.json`."""
    where = str(path)
    out: list[str] = []
    env = str(data.get("environment") or "")
    if _parse_rfc3339(data.get("released_at")) is None:
        out.append(f"{where}: `released_at` must be an RFC 3339 timestamp with timezone (such as `2026-11-20T15:10:00Z`); fix `released_at`")
    if root is None:
        return out
    cfg = repo_reads.config_at(root)
    env_cfg = _environment_entry(cfg, env) if cfg is not None else None
    if cfg is not None and env_cfg is None:
        known = [str(e["name"]) for e in _environments(cfg)]
        hint = did_you_mean(env, known) if known else ""
        out.append(
            f"{where}: environment {env!r} is not listed in {config.CONFIG_PATH}'s `environments`; "
            + (f"{hint} Or add " if hint else "add ")
            + f"`- {{name: {env}}}` under `environments` in {config.CONFIG_PATH}"
        )
    elif cfg is None and not (root / config.CONFIG_PATH).is_file():
        out.append(f"{where}: environment {env!r} cannot be checked without {config.CONFIG_PATH}; run `aidd init` and list `{env}` in `environments`")
    if _is_git_repo(root):
        out += _file_commit_findings(root, where, data, env_cfg, (cfg or config.EMPTY).specs_dir)
    return out


def _env_repo_findings(scan: _Scan, env: str, ordered: list[Release]) -> tuple[list[str], list[str]]:
    errors = [
        f"{curr.path}: `released_at` ({curr.released_at}) matches {prev.path} for environment {env}; set distinct timestamps in `released_at` so their order is clear"
        for prev, curr in zip(ordered, ordered[1:], strict=False)
        if prev.released_at_dt == curr.released_at_dt
    ]
    warnings: list[str] = []
    prev_live: set[str] | None = None
    prev_path: str | None = None
    ever_held: set[str] = set()
    active_rollbacks: set[str] = set()
    for r in ordered:
        active_rollbacks.difference_update(r.specs)
        active_rollbacks.update(r.rolled_back)
        try:
            held: set[str] | None = set(_specs_at_commit(scan.root, r.commit, scan.specs_dir, scan.blob_cache)) if scan.has_git else None
        except git.GitError:
            held = None
        if held is None:
            ever_held.update(r.specs)
            prev_live = (prev_live | set(r.specs)) - active_rollbacks if prev_live is not None else None
            prev_path = None
            continue
        if prev_live is not None and prev_path is not None and (missing := sorted((prev_live - held) - set(r.rolled_back))):
            joined = ", ".join(missing)
            warnings.append(
                f"{r.path}: commit {r.commit} no longer holds {joined} from {prev_path}, and `rolled_back` leaves it out; add {joined} to `rolled_back` in {r.path}"
            )
        if unheld := [s for s in r.rolled_back if s not in (ever_held | held)]:
            joined = ", ".join(unheld)
            warnings.append(
                f"{r.path}: `rolled_back` names {joined}, which neither an earlier release of {env} nor commit {r.commit} held; remove {joined} from `rolled_back`, or record the prior release first"
            )
        ever_held.update(held)
        prev_live = held - active_rollbacks
        prev_path = r.path
    return errors, warnings


def repo_findings(root: Path, parsed_objects: list[tuple[str, dict]], cfg: config.Config | None = None) -> tuple[list[str], list[str]]:
    """Repository-wide validation `(errors, warnings)` across release files (Rule 6 and Walk 5)."""
    scan = _Scan(root=root, specs_dir=(cfg or config.EMPTY).specs_dir, has_git=_is_git_repo(root), blob_cache={})
    by_env: dict[str, list[Release]] = {}
    for rel_path, data in parsed_objects:
        if (r := _parse_release(rel_path, data)) is not None:
            by_env.setdefault(r.environment, []).append(r)

    errors: list[str] = []
    warnings: list[str] = []
    for env, group in sorted(by_env.items()):
        ordered = sorted(group, key=lambda r: (r.released_at_dt, r.path))
        env_errors, env_warnings = _env_repo_findings(scan, env, ordered)
        errors += env_errors
        warnings += env_warnings
    return errors, warnings
