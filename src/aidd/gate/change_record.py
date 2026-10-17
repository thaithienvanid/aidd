"""The agent change record: what one gate decision proves about a change, as an in-toto Statement v1.

`aidd gate --record PATH` writes it next to the gate record (`change-record.intoto.json`; `.aidd/evidence/` for the local
default). The subject is the head commit (`git+<repo>@<sha>`, digest `gitCommit`); the predicate
(schemas/change-record.schema.json, a draft at version 0.1) holds the tenant, the route and lane, the Spec and its
approvals, the Merge approvals, the red-then-green evidence, the scope result, provenance, the decision, and its codes.

The file itself is unsigned: anyone who can write it can change it. The gate workflow may sign it (actions/attest, an
input that is off by default); `aidd record verify` then checks the signature with `gh attestation verify`. The attest action
takes only SHA-2 subjects, so the signed attestation's subject is the sha256 of this statement file and its predicate
is this predicate; the file in turn names the commit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from aidd import __version__, config
from aidd.gate import decision_report, routing
from aidd.gate.engine import Decision
from aidd.kernel import json_schema

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
# A stable URI under the repository that defines the predicate: the schema file. The version is in the predicate.
PREDICATE_TYPE = "https://github.com/thaithienvanid/aidd/blob/main/schemas/change-record.schema.json"
PREDICATE_VERSION = "0.1"
FILENAME = "change-record.intoto.json"
SCHEMA = "change-record.schema.json"
_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
GH_TIMEOUT_SECONDS = 120


def repo_uri(platform: str | None, repo: str | None) -> str:
    """The repository as a URI for the subject name: the platform's web address, or the adapter's name for it."""
    repo = repo or "local"
    if platform == "github":
        return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com').rstrip('/')}/{repo}"
    if platform == "gitlab":
        return f"{os.environ.get('CI_SERVER_URL', 'https://gitlab.com').rstrip('/')}/{repo}"
    return repo


def _scope_result(d: Decision) -> str:
    if "scope" not in d.record:
        return "not_checked"  # the gate stopped before it knew the scope
    codes = {f.code for f in d.findings if f.level == "fail"}
    return "outside" if codes & {"scope.outside", "scope.catch_all", "scope.overlaps_test", "scope.test_catch_all"} else "within"


def predicate(d: Decision, ctx: dict, *, run_url: str | None = None) -> dict:
    """The change-record predicate for one decision (schemas/change-record.schema.json)."""
    r = d.record
    cfg = d.config
    route = r.get("route")
    spec = None
    if r.get("spec_id"):
        required = bool(cfg and route in cfg.gates.get("spec_approval_routes", []))
        spec = {
            "id": r["spec_id"],
            "path": r.get("spec"),
            "hash": r.get("spec_hash"),
            "approval_required": required,
            "approvals": list(r.get("spec_approvals") or []),
            "approved_before_implementation": r.get("spec_approval_before_implementation"),
        }
    raw_change = ctx.get("change")
    change: dict = raw_change if isinstance(raw_change, dict) else {}
    out = {
        "predicate_version": PREDICATE_VERSION,
        "aidd_version": __version__,
        "loop_version": decision_report.loop_version(),
        "tenant": r.get("tenant"),
        "repo": ctx.get("repo") if isinstance(ctx.get("repo"), str) else "",
        "platform": r.get("platform"),
        "trusted": bool(r.get("trusted", d.trusted)),
        "change": {"id": str(r.get("change") or ""), "url": change.get("url") or None},
        "profile": r.get("profile"),
        "route": route,
        "lane": routing.LANES.get(route) if route else None,
        "required_route": r.get("required_route"),
        "base_sha": r.get("base_sha"),
        "head_sha": r.get("head_sha"),
        "config_sha256": r.get("config_sha256"),
        "spec": spec,
        "merge_approval": {
            "approvals": list(r.get("merge_approvals") or []),
            "specialists": dict(r.get("specialist_approved_by") or {}),
            "separation_of_duties": r.get("separation_of_duties"),
        },
        "evidence": {
            "runner": r.get("evidence_runner"),
            "tests": [
                {
                    "name": t["name"],
                    "source": t["source"],
                    "command": list(t["command"]),
                    "green_exit": t.get("exit"),
                    "green_status": t["status"],
                    "red_exit": t.get("red_exit"),
                    "red_status": t.get("red_status"),
                }
                for t in r.get("tests") or []
            ],
            "status_checks": dict(r.get("status_checks") or {}),
        },
        "scope": {
            "result": _scope_result(d),
            "declared": list(r.get("scope") or []),
            "changed_files": int(r.get("changed_files", 0)),
            "changed_lines": int(r.get("changed_lines", 0)),
        },
        "provenance": {
            "assisted_by": list(r.get("assisted_by") or []),
            "authors": list(r.get("authors") or []),
            "agent_accounts": sorted(cfg.get("identities", "bots", default=[]) or []) if cfg else [],
        },
        "decision": d.decision,
        "findings": d.codes(),
        "run_url": run_url,
    }
    if r.get("merge_group_sha"):
        out["merge_group_sha"] = r["merge_group_sha"]
    return out


def statement(d: Decision, ctx: dict, *, run_url: str | None = None) -> dict | None:
    """The in-toto Statement v1 for a decision, or None when the gate could not name the head commit."""
    head = d.record.get("head_sha")
    if not isinstance(head, str) or not _SHA.match(head):
        return None
    pred = predicate(d, ctx, run_url=run_url)
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": f"git+{repo_uri(pred['platform'], pred['repo'] or None)}@{head}", "digest": {"gitCommit": head}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": pred,
    }


def path_for(record_path: str, number: int | None = None) -> Path:
    """Where the statement goes: next to the gate record, numbered when one run gates several pull requests."""
    name = FILENAME if number is None else f"change-record-{number}.intoto.json"
    return Path(record_path).parent / name


def write_change_record(d: Decision, ctx: dict, record_path: str, *, number: int | None = None, run_url: str | None = None) -> Path | None:
    """Write the statement next to the gate record; None when there is no head commit to name."""
    stmt = statement(d, ctx, run_url=run_url)
    if stmt is None:
        return None
    errs = json_schema.validate(stmt["predicate"], SCHEMA)
    if errs:
        raise RuntimeError(f"invalid change record: {'; '.join(errs)}")
    path = path_for(record_path, number)
    path.write_text(json.dumps(stmt, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def write_records(d: Decision, ctx: dict, record_out: str, *, number: int | None = None, run_url: str | None = None) -> None:
    """A CI adapter's gate record at `record_out` (as `<stem>-<number>.<ext>` when one run gates several pull requests),
    checked against its schema, and the change record next to it: an in-toto statement the workflow may sign."""
    errs = json_schema.validate(d.record, "record.schema.json")
    if errs:
        raise RuntimeError(f"invalid gate record: {'; '.join(errs)}")
    stem, dot, ext = record_out.rpartition(".")
    path = record_out if number is None else (f"{stem}-{number}.{ext}" if dot else f"{record_out}-{number}")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d.record, fh, indent=2)
    write_change_record(d, ctx, record_out, number=number, run_url=run_url)


# ---- aidd record verify


def _agent(identity: str, agent_accounts: list[str]) -> bool:

    user = config.normalize_identity(identity)
    return config.is_bot(user) or config.agent_account(user, {config.normalize_identity(a) for a in agent_accounts})


def check(stmt: object, *, sha: str | None = None, tenant: str | None = None) -> list[str]:
    """Why a change record does not prove a change may merge; empty when it does. Signatures are checked apart."""
    if not isinstance(stmt, dict):
        return ["not a JSON object"]
    problems: list[str] = []
    if stmt.get("_type") != STATEMENT_TYPE:
        problems.append(f"_type is {stmt.get('_type')!r}, not {STATEMENT_TYPE}")
    if stmt.get("predicateType") != PREDICATE_TYPE:
        problems.append(f"predicateType is {stmt.get('predicateType')!r}, not {PREDICATE_TYPE}")
    pred = stmt.get("predicate")
    errs = json_schema.validate(pred, SCHEMA)
    if errs:
        return problems + [f"predicate: {e}" for e in errs[:10]]
    assert isinstance(pred, dict)
    head = pred["head_sha"]
    subjects = stmt.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(subjects[0], dict):
        problems.append("the statement must have exactly one subject, the head commit")
    else:
        subj = subjects[0]
        digest = (subj.get("digest") or {}).get("gitCommit") if isinstance(subj.get("digest"), dict) else None
        if digest != head:
            problems.append(f"the subject's gitCommit {digest!r} is not the predicate's head {head}")
        name = subj.get("name")
        if not isinstance(name, str) or not name.startswith("git+") or not name.endswith(f"@{head}"):
            problems.append(f"the subject name {name!r} does not name git+<repo>@{head}")
    if sha and sha.lower() != head:
        problems.append(f"the record is for {head}, not {sha}")
    if tenant and pred.get("tenant") != tenant:
        problems.append(f"the record belongs to tenant {pred.get('tenant')!r}, not {tenant!r}")
    if pred.get("trusted") is not True:
        problems.append("the record was not made from a trusted context (a CI adapter's), so it proves nothing about the merge")
    if pred["decision"] != "pass":
        problems.append(f"the gate decided {pred['decision']}, not pass")
    agents = list(pred["provenance"].get("agent_accounts") or [])
    spec = pred.get("spec")
    if spec and spec.get("approval_required"):
        approvals = spec.get("approvals") or []
        if not approvals:
            problems.append(f"Spec {spec['id']} needed Spec approval, and the record holds none")
        bad = sorted(a["identity"] for a in approvals if _agent(a["identity"], agents))
        if bad:
            problems.append(f"Spec approval by an agent or bot account: {', '.join(bad)}")
    merge = pred["merge_approval"]["approvals"]
    if pred.get("route") != "standard" and not merge:
        problems.append("no Merge approval in the record")
    bad = sorted(a["identity"] for a in merge if _agent(a["identity"], agents))
    if bad:
        problems.append(f"Merge approval by an agent or bot account: {', '.join(bad)}")
    stale = sorted(a["identity"] for a in merge if a.get("commit") not in (None, head))
    if stale:
        problems.append(f"Merge approval bound to another commit than the head: {', '.join(stale)}")
    return problems


def find_change_record(target: str, directory: str) -> Path:
    """The statement a target names: a file path, or a commit SHA whose statement is in `directory`."""
    p = Path(target)
    if p.is_file():
        return p
    if _SHA.match(target.lower()):
        d = Path(directory)
        for f in sorted(d.glob("*.intoto.json")) if d.is_dir() else []:
            try:
                stmt = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            subj = (stmt.get("subject") or [{}])[0] if isinstance(stmt, dict) and isinstance(stmt.get("subject"), list) else {}
            if isinstance(subj, dict) and (subj.get("digest") or {}).get("gitCommit") == target.lower():
                return f
        raise FileNotFoundError(f"no change record for {target} in {directory}/; pass the record's path")
    raise FileNotFoundError(f"{target}: no such file, and not a commit SHA")


GATE_WORKFLOW = ".github/workflows/aidd-gate.yml"


def gh_argv(gh: str, path: str, *, repo: str, bundle: str | None = None, signer_workflow: str | None = None, default_branch: str = "main") -> list[str]:
    """`gh attestation verify` for the statement file, as an argument list: nothing goes through a shell.

    The signature must come from the repository's gate workflow (`signer_workflow`, by default `<repo>/.github/workflows/
    aidd-gate.yml`), run from its default branch (the gate's events, `pull_request_target`, `issue_comment`, and
    `workflow_run`, all run the default branch's workflow), on a GitHub-hosted runner."""
    argv = [gh, "attestation", "verify", str(path), "--repo", repo, "--predicate-type", PREDICATE_TYPE, "--format", "json"]
    if bundle:
        argv += ["--bundle", str(bundle)]
    argv += ["--signer-workflow", signer_workflow or f"{repo}/{GATE_WORKFLOW}"]
    argv += ["--source-ref", f"refs/heads/{default_branch}", "--deny-self-hosted-runners"]
    return argv


def verify_signature(
    path: Path, stmt: dict, *, repo: str, bundle: str | None = None, signer_workflow: str | None = None, default_branch: str = "main"
) -> str | None:
    """None when `gh attestation verify` accepts a signed attestation of this statement file whose predicate is this
    predicate; otherwise why not."""
    gh = shutil.which("gh")
    if not gh:
        return "the gh CLI is not on PATH, so the signature cannot be checked"
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
        return f"{repo!r} is not an owner/name repository"
    try:
        argv = gh_argv(gh, str(path), repo=repo, bundle=bundle, signer_workflow=signer_workflow, default_branch=default_branch)
        p = subprocess.run(argv, capture_output=True, text=True, timeout=GH_TIMEOUT_SECONDS, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"gh attestation verify did not finish: {type(exc).__name__}"
    if p.returncode != 0:
        return f"gh attestation verify rejected it: {(p.stderr or p.stdout).strip()[:300]}"
    try:
        results = json.loads(p.stdout or "[]")
    except ValueError:
        return "gh attestation verify printed no JSON, so the signed predicate cannot be compared"
    signed = [((x.get("verificationResult") or {}).get("statement") or {}).get("predicate") for x in results if isinstance(x, dict)]
    if not any(s == stmt.get("predicate") for s in signed):
        return "the signed attestation's predicate differs from this record's"
    return None
