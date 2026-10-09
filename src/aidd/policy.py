"""Run the Policy interface: a command that prints allow, deny, or freeze.

It is also the extension point for org rules, in any language (a shell script,
OPA/Rego through `opa eval`, CEL): instead of a word, the command may print one
JSON object:

    {"verdict": "allow", "detail": "...",
     "findings": [{"rule": "jira-link", "level": "fail", "message": "...", "fix": "..."}]}

Findings join the decision as rules named `policy:<rule>`. The command reads the
change from AIDD_INPUT_FILE (JSON: change_id, base_sha, head_sha, route, type,
paths, body) as well as the AIDD_* variables.

No verdict, `allow` with a non-zero exit, a crash, or a timeout is `unreachable`, which the gate
treats as deny. An absent command is `unbound`, which only the profile decides.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile

from . import model, rules
from .util import run_bounded, scrub_credentials

VERDICTS = ("allow", "deny", "freeze")
MAX_POLICY_OUTPUT = 1024 * 1024
RULE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,59}$")


def run(
    command: list[str] | None, *, cwd: str = ".", env: dict[str, str] | None = None, timeout: float = 60, pass_env: list[str] | tuple[str, ...] = ()
) -> dict:
    """The command's answer. It sees no credential-like variable (a platform token, a *_KEY, a *SECRET*) unless the base
    branch's config names it in `policy.pass_env`."""
    if not command:
        return {"result": "unbound"}
    clean = scrub_credentials(dict(os.environ), keep=pass_env)
    try:
        code, stdout, _ = run_bounded(command, cwd=cwd, env={**clean, **(env or {})}, timeout=timeout)
    except OSError as exc:
        return {"result": "unreachable", "detail": str(exc)}
    if code is None:
        return {"result": "unreachable", "detail": f"timed out after {timeout}s"}
    out = (stdout[:MAX_POLICY_OUTPUT] if stdout else "").strip()
    if out.startswith("{"):
        return _json_answer(out, code)
    words = out.split(None, 1)
    verdict = words[0].lower() if words else ""
    if verdict in VERDICTS:
        detail = words[1].splitlines()[0][:200] if len(words) > 1 else ""
        if verdict == "allow" and code != 0:
            # A crash after printing allow is not an answer; deny and freeze stand whatever the exit.
            return {"result": "unreachable", "detail": f"printed allow but exited {code}"}
        return {"result": verdict, "detail": detail}
    return {"result": "unreachable", "detail": f"exit {code}, no verdict on stdout"}


def _json_answer(out: str, code: int) -> dict:
    try:
        data = json.loads(out)
    except ValueError:
        return {"result": "unreachable", "detail": "stdout is not valid JSON"}
    verdict = str(data.get("verdict", "")).lower()
    if verdict not in VERDICTS:
        return {"result": "unreachable", "detail": f"JSON verdict {verdict!r} is not allow, deny, or freeze"}
    if verdict == "allow" and code != 0:
        return {"result": "unreachable", "detail": f"printed allow but exited {code}"}
    findings = []
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or f.get("level") not in ("fail", "pending", "warn") or not f.get("rule"):
            return {"result": "unreachable", "detail": "each finding needs rule and level (fail, pending, warn)"}
        rname = str(f["rule"])
        if not RULE_NAME.match(rname):
            return {"result": "unreachable", "detail": f"invalid policy rule name {rname!r}"}
        findings.append({"rule": rname, "level": f["level"], "message": str(f.get("message", ""))[:300], "fix": str(f.get("fix", ""))[:300]})
    return {"result": verdict, "detail": str(data.get("detail", ""))[:200], "findings": findings[:50]}


def declared(body: str, head_files: dict[str, str]) -> dict:
    """Best-effort declared fields for the Policy environment. The gate re-derives them strictly."""
    cr, _ = model.parse_change_block(body)
    if not cr:
        return {}
    src = cr
    if "spec" in cr and cr["spec"] in head_files:
        try:
            src, _ = model.split_front_matter(head_files[cr["spec"]])
        except model.ModelError:
            return {}
    return {
        "route": src.get("route", ""),
        "type": src.get("type", ""),
        "risk": src.get("risk") if isinstance(src.get("risk"), dict) else {},
        "confidence": src.get("confidence", ""),
        "tasks": len(src.get("tasks") or []) or 1,
    }


def route_for_policy(d: dict, *, cfg, paths: list[str], changed_lines: int, dependencies: list[dict] | None = None) -> tuple[str, str]:
    """(route, required route): the route the gate will enforce, never below what the diff requires.

    The gate raises a Spec-backed normal change to major only after Policy has run, so Policy must
    see the raised route itself: a rule such as "major needs a change ticket" would otherwise
    judge the declared route and allow the change.
    """
    route = str(d.get("route", ""))
    if cfg is None or not d:
        return route, ""
    try:
        required = rules.assess(
            paths=paths,
            cfg=cfg,
            ctype=str(d.get("type", "")),
            risk=d.get("risk") or {},
            confidence=str(d.get("confidence", "")),
            task_count=int(d.get("tasks", 1)),
            changed_lines=changed_lines,
            dependencies=dependencies,
        ).required_route
    except (KeyError, TypeError, ValueError):
        return route, ""
    if route in rules.ROUTE_RANK and rules.ROUTE_RANK[required] > rules.ROUTE_RANK[route]:
        route = required
    return route, required


def evaluate_in_base(command: list[str] | None, *, repo: str, base_ref: str, **kw) -> dict:
    """Run Policy from a clean worktree of the base ref, never from a checkout the change controls."""
    if not command:
        return {"result": "unbound"}
    from . import gitutil

    tmp = tempfile.mkdtemp(prefix="aidd-base-")
    try:
        gitutil.run(["worktree", "add", "--detach", "--force", tmp, base_ref], repo)
        return evaluate(command, cwd=tmp, **kw)
    except gitutil.GitError as exc:
        return {"result": "unreachable", "detail": f"base worktree: {exc}"}
    finally:
        gitutil.run(["worktree", "remove", "--force", tmp], repo, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def evaluate(
    command: list[str] | None,
    *,
    cwd: str,
    change_id: str,
    base_sha: str,
    head_sha: str,
    paths: list[str],
    body: str,
    head_files: dict[str, str],
    cfg=None,
    changed_lines: int = 0,
    dependencies: list[dict] | None = None,
) -> dict:
    """Run the Policy command. `paths` must include rename sources (rules.changed_paths): a rule
    that denies a folder would otherwise miss a file moved out of it."""
    if not command:
        return {"result": "unbound"}
    d = declared(body, head_files)
    route, required = route_for_policy(d, cfg=cfg, paths=paths, changed_lines=changed_lines, dependencies=dependencies)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(paths))
        paths_file = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(
            {
                "change_id": change_id,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "route": route,
                "declared_route": d.get("route", ""),
                "required_route": required,
                "type": d.get("type", ""),
                "paths": paths,
                "body": body,
            },
            fh,
        )
        input_file = fh.name
    try:
        return run(
            command,
            cwd=cwd,
            env={
                "AIDD_INPUT_FILE": input_file,
                "AIDD_CHANGE_ID": change_id,
                "AIDD_BASE_SHA": base_sha,
                "AIDD_HEAD_SHA": head_sha,
                "AIDD_ROUTE": route,
                "AIDD_REQUIRED_ROUTE": required,
                "AIDD_TYPE": d.get("type", ""),
                "AIDD_CHANGED_PATHS_FILE": paths_file,
            },
            pass_env=list((cfg.get("policy", "pass_env", default=[]) if cfg is not None else []) or []),
        )
    finally:
        os.unlink(paths_file)
        os.unlink(input_file)
