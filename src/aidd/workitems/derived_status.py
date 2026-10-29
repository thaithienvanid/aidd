"""Effective status: derive every status git or the platform can prove, and store only what they cannot.

A status kept up to date by hand drifts: approved Specs that say draft, merged ones that say in_review, zombies in the
Approver's inbox. So aidd derives each status from what it can check, and the stored field is an optional cache that
`aidd validate` compares with the derived one:

| Spec status   | Derived from |
| ------------- | ------------ |
| `draft`       | no counted Spec approval of the Spec as it reads now, on a route that needs one |
| `ready`       | a counted Spec approval of the Spec as it reads now, and no commit in a Task's scope yet |
| `in_progress` | commits on the branch change a Task's scope |
| `in_review`   | the evidence is green on head (and a gate record, when there is one, waits on approvals at most) |
| `landed`     | the approved Spec is on the base branch: it merged |
| `done`        | landed, and no observe block or a healthy observe result |
| `rolled_back` | stored: outcome.rolled_back, or a failed observe window (nobody else can observe it) |
| `cancelled`   | stored: a person stopped it, or triage declined it |

Blocked is a flag, not a status: blockers names a wait, a blocked_by item is not finished, or a Task used its
retries. A counted Spec approval is one on the decision records (`aidd approve spec`), or one a gate record in the
evidence folder counted. Where neither exists, as on a platform whose approvals live on the PR/MR, the stored status
answers the question as a cache. The rest of each answer (commits, evidence, the merge) comes from git and the files
`aidd test` and `aidd gate --record` write.

`spec_status` and its companions are pure: they take the facts and decide. `Observer` gathers the facts from git for
one repository. Nothing here is evidence, and the gate never imports this module: the gate recomputes everything from
the platform itself.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, timestamps
from aidd.workitems import decision_records, spec_file

SPEC = ("draft", "ready", "in_progress", "in_review", "landed", "done", "rolled_back", "cancelled")
# At or past Spec approval: the stored status, read as a cache, says a person approved the hash.
PAST_APPROVAL = frozenset({"ready", "in_progress", "in_review", "landed", "done", "rolled_back"})
# Past implementation: every Task's work is built.
BUILT = frozenset({"in_review", "landed", "done", "rolled_back"})
TERMINAL = frozenset({"done", "rolled_back", "cancelled"})
# What another item's blocked_by waits for: the work landed (or ended).
UNBLOCKS = frozenset({"landed", "done", "rolled_back", "cancelled"})
# Statuses whose work can still be blocked; once in review, the work is built.
CAN_WAIT = frozenset({"draft", "ready", "in_progress"})
STARTED = frozenset({"in_progress", "in_review", "landed", "done", "rolled_back", "active"})
HEALTHY = ("pass",)
MAX_RETRIES = 3
PRIORITIES = ("urgent", "high", "medium", "low")
DEFAULT_ROUTES = ("normal", "major")
# Gate rules a person's approval clears: a gate record pending only on these waits for review, not for more work.
APPROVAL_RULES = frozenset({"spec_approval", "merge_approval", "specialist_approval"})
EVIDENCE_FILE, RECORD_FILE = "evidence.json", "record.json"
_APPROVE_SPEC = re.compile(r"^/aidd[ \t]+approve-spec[ \t]+(\S+)[ \t]+([0-9a-f]{40}|[0-9a-f]{64})\b")


def stored_status(data: dict) -> str | None:
    """The stored status as a cache (None when there is none)."""
    raw = data.get("status")
    return raw if isinstance(raw, str) else None


@dataclass(frozen=True)
class Facts:
    """What git and the platform prove about one copy of a Spec. None means unknown: the stored status answers."""

    approved: bool | None = None  # a counted Spec approval of the Spec as it reads now
    changed: tuple[str, ...] | None = None  # the paths the branch changed since it forked from the base
    green: bool | None = None  # the evidence is green on head, and a gate record waits on approvals at most
    landed: bool | None = None  # the approved Spec is on the base branch
    committed: bool | None = None  # the Spec is committed where it was read


def needs_spec_approval(data: dict, cfg: config.Config | None) -> bool:
    """Whether the Spec's route needs Spec approval under the profile (`gates.spec_approval_required_routes`)."""
    routes = (cfg.gates.get("spec_approval_required_routes") if cfg else None) or DEFAULT_ROUTES
    return str(data.get("route") or "normal") in routes


def _tasks(data: dict) -> list[dict]:
    return [t for t in data.get("tasks") or [] if isinstance(t, dict)]


def touches(task: dict, changed: tuple[str, ...] | list[str]) -> bool:
    scope = [str(s) for s in task.get("scope") or []]
    return bool(scope) and any(globs.match_any(scope, p) for p in changed)


def declined(data: dict) -> bool:
    return (data.get("triage") or {}).get("decision") == "declined"


def spec_status(data: dict, facts: Facts | None = None, *, approval: bool = True) -> str:
    """The Spec's effective status from the facts; each unknown fact is read from the stored status. `approval`:
    whether its route needs Spec approval (`needs_approval`)."""
    f = facts or Facts()
    s = stored_status(data) or "draft"
    out = data.get("outcome") or {}
    if s == "cancelled" or declined(data):
        return "cancelled"
    if out.get("rolled_back") or out.get("observe_result") == "fail" or s == "rolled_back":
        return "rolled_back"
    landed = f.landed if f.landed is not None else s in ("landed", "done")
    if landed:
        if not spec_file.observes(data) or out.get("observe_result") in HEALTHY:
            return "done"
        return "done" if f.landed is None and s == "done" else "landed"
    approved = f.approved if f.approved is not None else s in PAST_APPROVAL
    if approval and not approved:
        return "draft"
    if f.changed is not None:
        started = any(touches(t, f.changed) for t in _tasks(data))
    else:
        started = s in ("in_progress", "in_review")
    if not started:
        # A Spec approval recorded where the route makes it optional still makes the Spec ready: its tests are frozen.
        return "ready" if approved else "draft"
    green = f.green if f.green is not None else s == "in_review"
    return "in_review" if green else "in_progress"


_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_WINDOW = re.compile(r"^([0-9]+)([mhd])$")
# Once the change reached production: what the hypothesis is measured after.
LANDED_STATUSES = frozenset({"landed", "done"})


def hypothesis_due(data: dict) -> dt.date | None:
    """When the Spec's hypothesis is due to be measured: the latest date its own text names ("... by 2026-12-31"),
    else the release (`outcome.released_on`) plus the observe window. None when neither says."""
    named = [d for d in (timestamps.parse_date(m) for m in _ISO_DATE.findall(str(data.get("hypothesis") or ""))) if d]
    if named:
        return max(named)
    released = timestamps.parse_date((data.get("outcome") or {}).get("released_on") or "")
    if released is None:
        return None
    m = _WINDOW.match(str((data.get("observe") or {}).get("window") or ""))
    if not m:
        return released
    n, unit = int(m.group(1)), m.group(2)
    days = n if unit == "d" else -(-n // 24) if unit == "h" else -(-n // 1440)
    return released + dt.timedelta(days=days)


def outcome_due(data: dict, status: str, today: dt.date) -> dt.date | None:
    """The date a landed Spec's hypothesis was due, when it has passed and nobody recorded `outcome.result`; else None.
    Learn records the result (met, missed, or inconclusive, with the number); this only reminds."""
    out = data.get("outcome") or {}
    if not data.get("hypothesis") or out.get("result"):
        return None
    if status not in LANDED_STATUSES and not (out.get("released_on") and status not in ("rolled_back", "cancelled")):
        return None
    due = hypothesis_due(data)
    return due if due is not None and due < today else None


def retries_used(data: dict) -> list[str]:
    return [str(t.get("id")) for t in _tasks(data) if int(t.get("retry_count") or 0) >= MAX_RETRIES]


def blocked_reasons(data: dict, status: str, waits: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Why the item is blocked, or [] when it is not: blockers names a wait, blocked_by work is unfinished, or a Task
    used its retries. Only open work (draft, ready, in progress, and a container) can be blocked."""
    if status not in CAN_WAIT and status not in ("active",):
        return []
    out = []
    if str(data.get("blockers") or "").strip():
        out.append(str(data["blockers"]))
    out += [f"{t} used its {MAX_RETRIES} retries; a person re-plans it" for t in retries_used(data)]
    if waits:
        out.append(f"blocked by {', '.join(waits)}")
    return out


def stopped_at(note: dict | None) -> str | None:
    """The stop rule the latest handoff note says fired, or None."""
    raw = str((note or {}).get("stopped_at") or "").strip()
    return raw if raw and raw.lower() not in ("none", "n/a", "-") else None


def task_states(
    data: dict,
    status: str,
    facts: Facts | None = None,
    *,
    note: dict | None = None,
    approval: bool = True,
    blockers: list[str] | tuple[str, ...] = (),
) -> list[dict]:
    """Each Task with its derived state, for a coordinator that starts one agent per `todo` Task:

    - `done`: the Spec is past implementation, or the Task's scope changed and the evidence is green on head, or a
      person recorded `done: true`.
    - `stopped`: it used its retries, or the latest handoff note stopped while the Task was in progress.
    - `in_progress`: commits change its scope.
    - `blocked`: a Task it depends_on is not done (`waiting_on`), or the Spec itself is not approved or is blocked.
    - `todo`: an agent may start it now.
    """
    f = facts or Facts()
    tasks = _tasks(data)
    changed = f.changed
    done = {str(t.get("id")) for t in tasks if status in BUILT or t.get("done") is True or (changed is not None and f.green and touches(t, changed))}
    stop = stopped_at(note)
    out = []
    for t in tasks:
        tid = str(t.get("id"))
        task: dict = {"id": t.get("id"), "title": t.get("title"), "scope": list(t.get("scope", []) or []), "depends_on": list(t.get("depends_on", []) or [])}
        if t.get("skills"):
            task["skills"] = list(t["skills"])
        assignee = str(t.get("assignee") or "")
        if assignee:
            task["assignee"] = assignee
            if assignee.startswith("agent:"):
                task["role"] = assignee.split(":", 1)[1]
        why = ""
        started = changed is not None and touches(t, changed)
        pending = [d for d in task["depends_on"] if d not in done]
        if tid in done:
            state = "done"
        elif status == "cancelled":
            state, why = "blocked", "the Spec is cancelled"
        elif approval and status == "draft":
            state, why = "blocked", "the Spec waits for Spec approval; no Task starts before it"
        elif int(t.get("retry_count") or 0) >= MAX_RETRIES:
            state, why = "stopped", f"used its {MAX_RETRIES} retries: a person re-plans it"
        elif started and stop:
            state, why = "stopped", f"the latest handoff note stopped at {stop}"
        elif started:
            state = "in_progress"
        elif pending:
            state, why = "blocked", f"waits for {', '.join(pending)} to be done"
            task["waiting_on"] = pending
        elif blockers:
            state, why = (
                "blocked",
                f"the Spec is {'; '.join(blockers)}" if blockers[0].startswith("blocked by") else f"the Spec is blocked: {'; '.join(blockers)}",
            )
        else:
            state = "todo"
        task["status"] = state
        if why:
            task["why"] = why
        out.append(task)
    return out


def container_status(data: dict, children: list[str]) -> str:
    """An Epic's or Initiative's status: done or cancelled when a person recorded it (an Initiative's `go_no_go` of
    `no_go` is cancelled), active once any child started, else draft. With no child in the repository (they may live
    elsewhere), the stored status answers."""
    s = stored_status(data)
    if s in ("done", "cancelled"):
        return s
    if (data.get("go_no_go") or {}).get("decision") == "no_go":
        return "cancelled"
    if not children:
        return s or "draft"
    return "active" if any(c in STARTED for c in children) else "draft"


def container_statuses(items: list[dict], specs: dict[str, str]) -> tuple[dict[str, str], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Every Epic's and Initiative's derived status from its children's (Specs first, then Epics, then Initiatives),
    added to `specs` (the Specs' derived statuses by id); with each container's progress (children finished, of all)
    and its children's ids."""
    status = dict(specs)
    children: dict[str, list[str]] = {}
    for d in items:
        if d.get("parent") and d.get("id"):
            children.setdefault(str(d["parent"]), []).append(str(d["id"]))
    progress: dict[str, tuple[int, int]] = {}
    for kind in ("epic", "initiative"):
        for d in items:
            if d.get("kind") != kind or not d.get("id"):
                continue
            cid = str(d["id"])
            kids = [status.get(c, "draft") for c in children.get(cid, [])]
            status[cid] = container_status(d, kids)
            if kids:
                progress[cid] = (sum(1 for k in kids if finished(k)), len(kids))
    return status, progress, children


def finished(status: str) -> bool:
    """Whether a child counts toward its container's progress: it ended (done, rolled back, or cancelled)."""
    return status in TERMINAL


def status_unblocks(status: str) -> bool:
    """Whether an item another one is blocked_by lets it go: the work landed on the base branch, or ended."""
    return status in UNBLOCKS


def item_priority(data: dict, idx: dict[str, dict] | None = None) -> str:
    """The item's priority: an emergency is urgent; else its own, else its nearest parent's, else medium."""
    if data.get("route") == "emergency":
        return "urgent"
    seen: set[str] = set()
    item: dict | None = data
    while item is not None:
        if item.get("priority") in PRIORITIES:
            return str(item["priority"])
        parent = str(item.get("parent") or "")
        if not parent or parent in seen or idx is None:
            break
        seen.add(parent)
        item = idx.get(parent)
    return "medium"


def approval_holds(obs: Observer, rel: str, data: dict) -> bool:
    """Whether Spec approval holds for the working tree's Spec at `rel` (see `Observer.holds`). Declared here for the
    callers outside this module: the guard freezes tests and design by it."""
    return obs.holds(rel, data)


# ---- What git proves ------------------------------------------------------------------------------------------


class Observer:
    """The facts for Specs in one repository, read from git, the decision records, and the evidence folder.

    One per command: it caches each ref's tree, the approvals, and the evidence it reads. Every read that fails leaves
    its fact unknown (None), and the stored status answers instead."""

    def __init__(self, root: Path, cfg: config.Config | None):
        self.root, self.cwd, self.cfg = root, str(root), cfg
        self.head = self.sha("HEAD")
        self._base: tuple[str | None, str | None] | None = None
        self._trees: dict[str, dict[str, str]] = {}
        self._approvals: list[tuple[str, str]] | None | bool = False
        self._hashes_at: dict[tuple[str, str], str | None] = {}
        self._spec_paths: dict[str, dict[str, list[str]]] | None = None
        self._records: list[dict] | None = None
        self._evidence: list[dict] | None = None
        self._files: list[str] | None = None
        self._forks: dict[str, str | None] = {}
        self._shallow: bool | None = None

    def _find_base(self) -> tuple[str | None, str | None]:
        if self._base is None:
            name = None
            if self.head:
                try:
                    name = git.default_base(self.cwd)
                except git.GitError:
                    name = None
            self._base = (name, self.sha(name))
        return self._base

    @property
    def base(self) -> str | None:
        """The base branch's name (`git.default_base`), or None."""
        return self._find_base()[0]

    @property
    def base_sha(self) -> str | None:
        return self._find_base()[1]

    def sha(self, ref: str | None) -> str | None:
        if not ref:
            return None
        return git.run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], self.cwd, check=False).strip() or None

    def needs_spec_approval(self, data: dict) -> bool:
        return needs_spec_approval(data, self.cfg)

    def tree(self, sha: str) -> dict[str, str]:
        if sha not in self._trees:
            try:
                self._trees[sha] = git.ls_tree(sha, self.cwd)
            except git.GitError:
                self._trees[sha] = {}
        return self._trees[sha]

    @property
    def is_shallow_clone(self) -> bool:
        """Whether this is a shallow clone, read once: its oldest commit is a graft that seems to add every file."""
        if self._shallow is None:
            self._shallow = git.run(["rev-parse", "--is-shallow-repository"], self.cwd, check=False).strip() == "true"
        return self._shallow

    def fork(self, sha: str) -> str | None:
        """Where the commit left the base branch; None without a base."""
        if not self.base_sha:
            return None
        if sha not in self._forks:
            self._forks[sha] = git.run(["merge-base", self.base_sha, sha], self.cwd, check=False).strip() or None
        return self._forks[sha]

    # -- approvals

    def _approval_lines(self) -> list[tuple[str, str]] | None:
        """(Spec id, the commit it was approved at) of each counted local Spec approval; None when this repository has no
        decision records."""
        if self._approvals is False:
            self._approvals = None
            if self.head and git.ok(["rev-parse", "--verify", "--quiet", decision_records.DECISIONS_REF], self.cwd):
                signed = bool(self.cfg) and self.cfg.gates.get("local_approvals") == "signed"  # type: ignore[union-attr]
                try:
                    _, comments, _ = decision_records.load_local_approvals(
                        self.cwd,
                        require_signed=signed,
                        signers=decision_records.base_signers(self.cfg, self.base_sha, self.cwd),
                        signers_file=decision_records.signers_path(self.cfg),
                    )
                except git.GitError:
                    comments = []
                found = []
                # Only an Approver's approval counts, as the gate counts it: an approval recorded under an identity the
                # pool does not hold (an email where the pool lists a login) never froze or cleared anything there.
                pool = {config.normalize_identity(str(a)) for a in (self.cfg.approvers if self.cfg else [])}
                for c in comments:
                    if signed and not c.get("verified"):
                        continue
                    if pool and config.normalize_identity(str(c.get("user") or "")) not in pool:
                        continue
                    m = _APPROVE_SPEC.match(str(c.get("body", "")))
                    if m:
                        found.append((m.group(1), m.group(2)))
                self._approvals = found
        return self._approvals  # type: ignore[return-value]

    def _dirs(self) -> list[str]:
        artifact = str((self.cfg.get("evidence", "artifact") if self.cfg else None) or "")
        return list(dict.fromkeys([config.EVIDENCE_DIR, *([artifact.rstrip("/")] if artifact else [])]))

    def _json(self, name: str) -> list[dict]:
        """The JSON objects a local run wrote into the evidence folder. A file git tracks (committed at HEAD or staged)
        is never one: the folder is ignored, so such a file is something the branch itself asserts."""
        out = []
        for d in self._dirs():
            rel = f"{d}/{name}"
            try:
                data = json.loads((self.root / rel).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or self._tracked(rel):
                continue
            out.append(data)
        return out

    def _tracked(self, rel: str) -> bool:
        if git.ok(["ls-files", "--error-unmatch", "--", rel], self.cwd):
            return True
        return bool(self.head) and git.ok(["cat-file", "-e", f"{self.head}:{rel}"], self.cwd)

    def _known_commit(self, sha: object) -> bool:
        """Whether `sha` is a full commit id this repository holds: the head a gate run judged here."""
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            return False
        return git.ok(["cat-file", "-e", f"{sha}^{{commit}}"], self.cwd)

    def records(self) -> list[dict]:
        """Gate records `aidd gate --record` wrote into the evidence folder, each for a commit this repository holds. A
        record the branch commits, or one naming no head here, is not evidence: it could assert any approval."""
        if self._records is None:
            self._records = [r for r in self._json(RECORD_FILE) if self._known_commit(r.get("head_sha"))]
        return self._records

    def evidence(self) -> list[dict]:
        if self._evidence is None:
            self._evidence = [e for e in self._json(EVIDENCE_FILE) if not e.get("partial")]
        return self._evidence

    def approved(self, sid: str, h: str | None) -> bool | None:
        """Whether a counted Spec approval names this Spec at a commit where it hashes to `h`; None when nothing local
        records approvals."""
        lines = self._approval_lines()
        recs = [r for r in self.records() if str(r.get("spec_id")) == sid]
        if lines is None and not recs:
            return None
        if h is None:
            return False
        # An approval naming the base commit proves no Spec commit, so the gate never counts it (spec_approval.names_base).
        return any(i == sid and sha != self.base_sha and self.spec_hash_at(sid, sha) == h for i, sha in lines or []) or any(
            r.get("spec_hash") == h and r.get("spec_approved_by") for r in recs
        )

    def spec_hash_at(self, sid: str, sha: str) -> str | None:
        """The Spec hash of Spec `sid` at commit `sha`, what an approval of that commit approved: the file that holds the
        Spec at HEAD (or at `sha`, for a Spec HEAD does not hold, such as another branch's), read at `sha`, as the gate
        reads it. None when git does not have the commit, when no file or more than one claims the id, or when that file
        at `sha` is not this Spec."""
        key = (sid, sha)
        if key not in self._hashes_at:
            self._hashes_at[key] = None
            known = git.ok(["cat-file", "-e", f"{sha}^{{commit}}"], self.cwd)
            path = self._spec_path(sid) or (self._spec_path(sid, sha) if known and not self._spec_path_claimed(sid) else None)
            text = git.show(sha, path, self.cwd) if path and known else None
            try:
                if text is not None and path and documents.split_front_matter(text, path)[0].get("id") == sid:
                    self._hashes_at[key] = self.hash_at(sha, text)
            except documents.DocumentError:
                pass
        return self._hashes_at[key]

    def _spec_path(self, sid: str, at: str | None = None) -> str | None:
        """The one file under the specs folder at HEAD (or at commit `at`) whose front matter claims Spec `sid`; None
        for none, or for two."""
        claims = self._claims(at or self.head)
        return claims[sid][0] if len(claims.get(sid, [])) == 1 else None

    def _spec_path_claimed(self, sid: str) -> bool:
        """Whether any file at HEAD claims Spec `sid`: two that do leave it unresolved, never looked up elsewhere."""
        return sid in self._claims(self.head)

    def _claims(self, sha: str | None) -> dict[str, list[str]]:
        """The files under the specs folder at `sha` that claim each Spec id."""
        if self._spec_paths is None:
            self._spec_paths = {}
        key = sha or ""
        if key not in self._spec_paths:
            from aidd.workitems import repo_reads

            specs = str(self.cfg.specs_dir if self.cfg else "specs").strip("/")
            claims: dict[str, list[str]] = {}
            if sha:
                for rel, data, _, _ in repo_reads.objects_at(self.root, sha, specs)[0]:
                    if data.get("kind", "spec") == "spec" and isinstance(data.get("id"), str):
                        claims.setdefault(data["id"], []).append(rel)
            self._spec_paths[key] = claims
        return self._spec_paths[key]

    def knows_approvals(self) -> bool:
        return self._approval_lines() is not None or bool(self.records())

    def approvals(self) -> list[tuple[str, str]]:
        """(Spec id, commit) of each counted local Spec approval, newest first; empty when nothing local records them."""
        return self._approval_lines() or []

    def spec_path_at(self, sid: str, sha: str) -> str | None:
        """The one file at commit `sha` that claims Spec `sid` (a rename moves it), or None."""
        return self._spec_path(sid, sha)

    # -- hashes

    def hash_at(self, sha: str, text: str) -> str | None:
        try:
            return spec_file.spec_hash(text, self.tree(sha), lambda p: git.show(sha, p, self.cwd))
        except documents.DocumentError:
            return None

    def hash_worktree(self, text: str, data: dict) -> str | None:
        """The hash of the Spec as the working tree holds it, with its frozen files as they are on disk."""
        if self._files is None:
            listed = git.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], self.cwd, check=False)
            self._files = [p for p in listed.split("\0") if p]
        frozen = spec_file.frozen_files(data)
        files = [p for p in self._files if globs.match_any(frozen, p) and (self.root / p).is_file()]
        try:
            return spec_file.spec_hash(text, git.hash_files(files, self.cwd), lambda p: (self.root / p).read_text(encoding="utf-8", errors="replace"))
        except (documents.DocumentError, git.GitError):
            return None

    # -- evidence

    def green(self, sha: str | None, data: dict) -> bool | None:
        """Whether the evidence shows the Spec's commands green on `sha`, and a gate record for it passes or waits on
        approvals at most. None when neither the evidence nor a gate record speaks about `sha`."""
        if not sha:
            return None
        sid = str(data.get("id"))
        names = {str(c.get("name")) for c in (data.get("tests") or {}).get("commands", []) or [] if isinstance(c, dict)}
        verdicts = []
        for ev in self.evidence():
            if ev.get("head_sha") != sha:
                continue
            results = [r for r in ev.get("results", []) if isinstance(r, dict) and r.get("red_green", "green") == "green"]
            passed = {str(r.get("name")) for r in results if r.get("status") == "passed"}
            verdicts.append(bool(results) and names <= passed and all(r.get("status") == "passed" for r in results))
        for rec in self.records():
            if rec.get("head_sha") != sha or str(rec.get("spec_id")) != sid:
                continue
            pending = set(rec.get("pending_rules") or [])
            verdicts.append(rec.get("decision") == "pass" or (rec.get("decision") == "pending" and not rec.get("failed_rules") and pending <= APPROVAL_RULES))
        return all(verdicts) if verdicts else None

    # -- the facts for one copy

    def landed(self, rel: str, sid: str, h: str | None, approval: bool) -> bool | None:
        """Whether this Spec, as approved, is on the base branch: the base holds it with the same hash (only its
        bookkeeping may differ, such as the outcome a person records after the merge), approved there."""
        if not self.base_sha:
            return None
        text = git.show(self.base_sha, rel, self.cwd)
        if text is None:
            return False
        try:
            data, _ = documents.split_front_matter(text, rel)
        except documents.DocumentError:
            return False
        if str(data.get("id")) != sid:
            return False
        hb = self.hash_at(self.base_sha, text)
        if h is not None and hb != h:
            return False  # a new change to the Spec, not yet merged
        return self._on_base(rel, sid, data, hb, approval)

    def _on_base(self, rel: str, sid: str, data: dict, h: str | None, approval: bool) -> bool:
        """Whether the base branch's copy of a Spec is landed work, not a stub someone committed there: approved (on a
        route that needs it; the stored status answers when nothing local records approvals), or, on a route that
        needs no approval, with a commit changing a Task's scope since the Spec landed."""
        if approval:
            ok = self.approved(sid, h)
            return (stored_status(data) in PAST_APPROVAL) if ok is None else ok
        scopes = [s for t in _tasks(data) for s in t.get("scope") or [] if "TODO" not in str(s)]
        if not scopes or not self.base_sha:
            return False
        added = git.run(["log", "--diff-filter=A", "--format=%H", "-1", self.base_sha, "--", rel], self.cwd, check=False).strip()
        if not added:
            return False
        since = [self.base_sha, f"^{added}^"] if git.ok(["rev-parse", "-q", "--verify", f"{added}^"], self.cwd) else [self.base_sha]
        specs = [f":(glob){g}**" if g.endswith("/") else f":(glob){g}" for g in scopes]
        return bool(git.run(["rev-list", "-1", *since, "--", *specs], self.cwd, check=False).strip())

    def worktree(self, rel: str, text: str, data: dict) -> Facts:
        """The facts for the Spec this branch's working tree holds: approvals of its current hash, the paths changed
        since the branch forked (committed, staged, unstaged, and untracked), the evidence for HEAD, and the merge."""
        if not self.head:
            return Facts()
        sid, approval = str(data.get("id")), self.needs_spec_approval(data)
        committed = git.show(self.head, rel, self.cwd) is not None
        h = self.hash_worktree(text, data) if (self.knows_approvals() or self.base_sha) else None
        fork = self.fork(self.head)
        changed = None
        if fork:
            changed = tuple(git.changed_since(self.cwd, fork))
        green = self.green(self.head, data)
        if green:
            scopes = [s for t in _tasks(data) for s in t.get("scope") or []]
            dirty = git.dirty(self.cwd, untracked=True, check=False)
            if any(globs.match_any(scopes, p) for p in dirty):
                green = False  # the evidence is for HEAD, and the Task's files changed since
        landed = self.landed(rel, sid, h, approval)
        return Facts(approved=self.approved(sid, h), changed=changed, green=green, landed=landed, committed=committed)

    def at(self, sha: str, rel: str, text: str, data: dict) -> Facts:
        """The facts for the Spec as the commit `sha` holds it: the tip of a branch, or the base branch itself."""
        sid, approval = str(data.get("id")), self.needs_spec_approval(data)
        h = self.hash_at(sha, text) if self.knows_approvals() or (self.base_sha and sha != self.base_sha) else None
        if sha == self.base_sha:
            return Facts(approved=self.approved(sid, h), landed=self._on_base(rel, sid, data, h, approval), committed=True)
        fork = self.fork(sha)
        changed = None
        if fork:
            changed = tuple(p for p in git.run(["diff", "--name-only", "-z", fork, sha], self.cwd, check=False).split("\0") if p)
        return Facts(
            approved=self.approved(sid, h),
            changed=changed,
            green=self.green(sha, data),
            landed=self.landed(rel, sid, h, approval),
            committed=True,
        )

    def status(self, facts: Facts, data: dict) -> str:
        return spec_status(data, facts, approval=self.needs_spec_approval(data))

    def working_tree(self, specs_dir: str, objects: list[tuple[str, dict, str]]) -> dict[str, str]:
        """The derived status of every work item in the working tree, by id: a Spec this branch changes from the
        working tree's facts, any other Spec as the base branch holds it, and each Epic and Initiative from its
        children."""
        fork = self.fork(self.head) if self.head else None
        ours = set(git.changed_since(self.cwd, fork, specs_dir)) if fork else None
        out: dict[str, str] = {}
        for rel, data, text in objects:
            if data.get("kind") != "spec" or not data.get("id"):
                continue
            if ours is None or rel in ours or not self.base_sha:
                facts = self.worktree(rel, text, data)
            else:
                facts = self.at(self.base_sha, rel, text, data)
            out[str(data["id"])] = self.status(facts, data)
        return container_statuses([d for _, d, _ in objects], out)[0]

    def holds(self, rel: str, data: dict) -> bool:
        """Whether Spec approval holds for the Spec in the working tree: the one check the guard, `aidd
        next`, and `aidd validate` share. A counted approval of its hash as HEAD or the working tree holds it; where
        nothing local records approvals, a stored status at or past ready answers."""
        known = self.frozen(rel, data)
        return (stored_status(data) in PAST_APPROVAL) if known is None else known

    def frozen(self, rel: str, data: dict) -> bool | None:
        """Whether Spec approval froze the Spec's tests and design: a counted approval of its hash as HEAD holds it,
        or as the working tree holds it. None when nothing local records approvals (the stored status answers)."""
        if not self.knows_approvals():
            return None
        sid = str(data.get("id"))
        hashes = []
        committed = git.show(self.head, rel, self.cwd) if self.head else None
        if committed is not None:
            hashes.append(self.hash_at(self.head, committed))  # type: ignore[arg-type]
        path = self.root / rel
        if path.is_file():
            hashes.append(self.hash_worktree(path.read_text(encoding="utf-8", errors="replace"), data))
        return any(self.approved(sid, h) for h in hashes if h)
