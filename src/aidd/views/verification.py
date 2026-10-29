"""The verification a page shows: each Acceptance criterion against the evidence's test results, and what the verifier recorded for the head (screenshots and their checksums)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

from aidd import gate
from aidd.kernel import documents, json_schema, repo_paths
from aidd.views import approval_summary, html_parts


def command_line(command) -> str:
    return shlex.join(str(c) for c in command) if isinstance(command, list) else str(command or "")


def _result_text(r: dict | None) -> html_parts.Html:
    if not r:
        return html_parts.Html("no result")
    exit_code = r.get("exit")
    if r.get("red_green") == "red":
        level = "pass" if gate.red_ok(r) else "fail"
        text = "fails on base, as it should" if gate.red_ok(r) else f"{r.get('status')} on base"
    else:
        level = "pass" if r.get("status") == "passed" else "fail"
        text = str(r.get("status"))
    flaky = " (flaky: passed on a retry)" if r.get("flaky") else ""
    return html_parts.join(html_parts.badge(level, text), f" exit {exit_code}{flaky}")


def _safe_artifact(evidence_dir: Path | None, rel: str) -> tuple[Path | None, str]:
    """The artifact's file when it is inside the evidence folder, or why not."""
    if evidence_dir is None:
        return None, "not embedded: the evidence folder is not here"
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts or re.match(r"^[A-Za-z]:", rel):
        return None, "not embedded: the path leaves the evidence folder"
    root = evidence_dir.resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        return None, "not embedded: the path leaves the evidence folder"
    if not p.is_file():
        return None, "not embedded: the file is not in the evidence folder here"
    return p, ""


def artifact_figure(a: dict, evidence_dir: Path | None) -> html_parts.Html:
    """One recorded artifact: a screenshot embedded as a data: image when it is here and its SHA-256 matches, else its
    path and hash."""
    rel, kind, sha = str(a.get("path", "")), str(a.get("kind", "")), str(a.get("sha256", ""))
    caption = html_parts.el("figcaption", html_parts.el("code", rel), f" ({kind}) sha256 {sha[:16]}…")
    p, why = _safe_artifact(evidence_dir, rel)
    img: html_parts.Html | str = ""
    if p is not None:
        mime = repo_paths.IMAGE_TYPES.get(p.suffix.lower())
        size = p.stat().st_size
        if kind != "screenshot" or mime is None:
            why = "not embedded: only screenshots (PNG, JPEG, GIF, WebP) are"
        elif size > html_parts.MAX_IMAGE_BYTES:
            why = f"not embedded: larger than {html_parts.MAX_IMAGE_BYTES // (1024 * 1024)} MB"
        else:
            data = p.read_bytes()
            if hashlib.sha256(data).hexdigest() != sha:
                why = "not embedded: its SHA-256 does not match what the verifier recorded"
            else:
                img = html_parts.el("img", src=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", alt=f"{kind} {rel}", loading="lazy")
    return html_parts.el("figure", img, caption, html_parts.el("p", why, class_="muted") if why else "")


def preview_artifacts(evidence_dir: Path | None, head_sha: object) -> list[dict]:
    """What the verifier recorded for this head: `<evidence>/preview/<head_sha>/artifacts.json` (schemas/artifacts.schema.json),
    or nothing when it is missing, unreadable, or not in that shape."""
    if evidence_dir is None or not re.fullmatch(r"[0-9a-f]{7,64}", str(head_sha or "")):
        return []
    try:
        items = json.loads((evidence_dir / "preview" / str(head_sha) / ARTIFACTS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(items) if not json_schema.validate(items, "artifacts.schema.json") else []


# The kind of each file the verifier records, by its extension (schemas/artifacts.schema.json).
PREVIEW_KINDS = {
    **dict.fromkeys(repo_paths.IMAGE_TYPES, "screenshot"),
    ".zip": "trace",
    **dict.fromkeys((".mp4", ".webm", ".mov"), "video"),
    **dict.fromkeys((".txt", ".log", ".json", ".har", ".md"), "transcript"),
}
ARTIFACTS_FILE = "artifacts.json"


def record_artifacts(evidence_dir: Path, head_sha: str) -> list[dict]:
    """List what the verifier saved under `<evidence>/preview/<head_sha>/` in its artifacts.json, each file with its kind
    and SHA-256, and return the list. aidd writes it, so the verifier stays read-only, as it does for `aidd test`.
    ValueError for a head that is not a commit SHA, a missing folder, a link, or a file of no kind it knows."""
    if not re.fullmatch(r"[0-9a-f]{7,64}", head_sha or ""):
        raise ValueError(f"{head_sha!r} is not a commit SHA: name the head the preview ran on, such as `git rev-parse HEAD`")
    folder = evidence_dir / "preview" / head_sha
    for part in (evidence_dir, evidence_dir / "preview", folder):
        # A link on the way would send the list's write elsewhere, such as onto a file the guard keeps an agent from.
        if part.is_symlink():
            raise ValueError(f"{part} is a symbolic link: aidd writes the list only into a real folder; remove the link")
    if not folder.is_dir():
        raise ValueError(f"{folder} is not a folder: save the screenshots, traces, and transcripts there first")
    items = []
    for p in sorted(folder.rglob("*")):
        if (p.name == ARTIFACTS_FILE or p.name.startswith(".artifacts-")) and p.parent == folder or p.is_dir() and not p.is_symlink():
            continue
        rel = p.relative_to(evidence_dir).as_posix()
        if p.is_symlink() or not p.is_file():
            raise ValueError(f"{rel} is a link or not a regular file: save the file itself there")
        kind = PREVIEW_KINDS.get(p.suffix.lower())
        if kind is None:
            raise ValueError(f"{rel}: aidd knows no kind for {p.suffix or 'a file with no extension'}; use one of {', '.join(sorted(PREVIEW_KINDS))}")
        items.append({"path": rel, "kind": kind, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    if not items:
        raise ValueError(f"{folder} holds no files: save the screenshots, traces, and transcripts there first")
    errors = json_schema.validate(items, "artifacts.schema.json")
    if errors:
        raise ValueError(f"the list does not match schemas/artifacts.schema.json: {errors[0]}")
    target = folder / ARTIFACTS_FILE
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"{target} is a link or not a regular file: remove it, and aidd writes the list again")
    # A new file renamed over the entry: never a write through whatever the entry points at.
    fd, tmp = tempfile.mkstemp(prefix=".artifacts-", dir=folder)
    try:
        os.fchmod(fd, 0o644)  # readable like any other file aidd writes, not mkstemp's 0600
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(items, indent=2) + "\n")
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return items


def _artifacts_for(artifacts: list[dict], ident: str) -> list[dict]:
    """The artifacts a verifier named for an Acceptance id: a file name that starts with it, such as a1-checkout.png."""
    pat = re.compile(rf"^{re.escape(ident.lower())}(?:[-_.]|$)")
    return [a for a in artifacts if pat.match(Path(str(a.get("path", ""))).name.lower())]


def spec_parts(text: str | None, path: str) -> tuple[dict, str]:
    if not text:
        return {}, ""
    try:
        return documents.split_front_matter(text, path)
    except documents.DocumentError:
        return {}, ""


def acceptance_rows(items: list[tuple[str, str]], cmds: list[dict], evidence: dict | None, evidence_dir: Path | None, *, artifacts: bool = True) -> list[list]:
    results = (evidence or {}).get("results") or []
    green = {r.get("name"): r for r in results if r.get("red_green") == "green"}
    red = {r.get("name"): r for r in results if r.get("red_green") == "red"}
    arts = preview_artifacts(evidence_dir, (evidence or {}).get("head_sha")) if artifacts else []
    rows = []
    for ident, text in items:
        by = [c for c in cmds if ident and ident in (c.get("covers") or [])]
        names = [str(c.get("name")) for c in by]
        row: list = [html_parts.el("strong", ident or "-"), text, html_parts.code_list(names) if names else html_parts.badge("fail", "nothing covers it")]
        if evidence is not None:
            row.append(
                html_parts.join(
                    [
                        html_parts.join(html_parts.el("div", html_parts.el("code", n), " ", _result_text(red.get(n))))
                        for n in names
                        if any(c.get("new_behavior") for c in by if c.get("name") == n)
                    ]
                )
                or "-"
            )
            row.append(html_parts.join([html_parts.el("div", html_parts.el("code", n), " ", _result_text(green.get(n))) for n in names]) or "-")
            if artifacts:
                row.append(html_parts.join([artifact_figure(a, evidence_dir) for a in _artifacts_for(arts, ident)]) or "-")
        rows.append(row)
    return rows


def results_table(evidence: dict) -> html_parts.Html:
    rows = []
    for r in evidence.get("results") or []:
        attempts = r.get("attempts") or []
        rows.append(
            [
                r.get("red_green"),
                html_parts.el("code", r.get("name")),
                r.get("source", ""),
                html_parts.el("code", command_line(r.get("command"))),
                _result_text(r),
                "" if r.get("duration_seconds") is None else f"{r['duration_seconds']}",
                f"{len(attempts)} attempt(s)" if attempts else "",
                html_parts.el("code", r.get("log")) if r.get("log") else "",
            ]
        )
    return html_parts.table(
        ["Phase", "Command", "Source", "Runs", "Result", "Seconds", "Retries", "Log"], rows, label="Every result, as the runner recorded it"
    )


def verification_section(evidence: dict | None, data: dict, body: str, evidence_dir: Path | None, *, stale: str = "") -> html_parts.Html:
    if evidence is None:
        return html_parts.el("p", stale or "No evidence for this head: run `aidd test`.", class_="muted")
    runner = evidence.get("runner") or {}
    flags = [
        ("Head", html_parts.el("code", evidence.get("head_sha", ""))),
        ("Base", html_parts.el("code", evidence.get("base_sha", ""))),
        ("Runner", " ".join(f"{k} {runner[k]}" for k in ("ci", "run_id", "url") if runner.get(k))),
        ("Partial", "yes: only the commands the working tree's changes select; the gate never accepts it" if evidence.get("partial") else ""),
        ("Spec phase", "yes: failing green results are expected before Implement" if evidence.get("spec_phase") else ""),
    ]
    parts: list = [html_parts.facts(flags)]
    items = approval_summary.acceptance(body) if body else []
    cmds = ((data.get("tests") or {}).get("commands")) or []
    if items and items[0][0]:
        parts.append(html_parts.el("h3", "Acceptance, command by command"))
        parts.append(
            html_parts.table(
                ["Id", "Acceptance", "Proven by", "Red on base", "Green on head", "Recorded"],
                acceptance_rows(items, cmds, evidence, evidence_dir),
                label="Each Acceptance item, the commands that cover it, their results, and what the verifier recorded",
            )
        )
    parts.append(html_parts.el("h3", "Results"))
    parts.append(results_table(evidence))
    arts = preview_artifacts(evidence_dir, evidence.get("head_sha"))
    if arts:
        parts.append(html_parts.el("h3", "Recorded while verifying"))
        parts.append(
            html_parts.el(
                "p", "Screenshots, traces, videos, and transcripts the verifier recorded on this head. For people: the gate never reads them.", class_="muted"
            )
        )
        parts.append(html_parts.join([artifact_figure(a, evidence_dir) for a in sorted(arts, key=lambda a: str(a.get("path")))]))
    return html_parts.join(parts)
