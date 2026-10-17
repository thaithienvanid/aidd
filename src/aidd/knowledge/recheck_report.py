"""What the evidence recheck and the release check report: Markdown that reads as text too, and the exit code `--strict` turns red."""

from __future__ import annotations

from aidd.knowledge import release_feeds


def exit_code(result: dict, strict: bool) -> int:
    """1 only with `strict` and an entry moved or missing, or a library tool with a newer major release: an
    unreachable page or feed says nothing about the standard."""
    newer = any(r["status"] == "newer_major" for r in result.get("releases", []))
    return 1 if strict and (result["counts"]["moved"] or result["counts"]["missing"] or newer) else 0


def markdown(result: dict) -> str:
    """The report as Markdown (it reads as text too): what to fix, then the counts and what each status asks for."""
    c = result["counts"]
    lines = [f"# Standards evidence, re-read online on {result['checked_on']}", ""]
    rows = [r for r in result["results"] if r["status"] != "ok" or r["final_url"]]
    if rows:
        lines += ["| Status | Entry | Evidence | Why |", "| --- | --- | --- | --- |"]
        order = {s: i for i, s in enumerate(("moved", "missing", "ok", "unreachable"))}
        for r in sorted(rows, key=lambda r: order[r["status"]]):
            why = str(r["reason"]).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['status']} | `{r['id']}` ({r['where']}) | <{r['url']}> | {why} |")
        lines.append("")
    total = len(result["results"])
    lines.append(f"{total} entries with evidence: {c['ok']} ok, {c['moved']} moved, {c['missing']} missing, {c['unreachable']} unreachable.")
    releases = result.get("releases") or []
    if releases:
        flagged = [r for r in releases if r["status"] != "ok"]
        if flagged:
            lines += ["", "| Release | Library standard | Tool | Checked | Latest | Why |", "| --- | --- | --- | --- | --- | --- |"]
            for r in sorted(flagged, key=lambda r: release_feeds.RELEASE_STATUSES.index(r["status"])):
                why = str(r["reason"]).replace("|", "\\|").replace("\n", " ")
                status = r["status"].replace("_", " ")
                lines.append(f"| {status} | `{r['id']}` | {r['tool']} | {r['checked_version']} | {r['latest'] or '—'} | {why} |")
        n = {s: sum(1 for r in releases if r["status"] == s) for s in release_feeds.RELEASE_STATUSES}
        lines += ["", f"{len(releases)} library tools on their release feeds: {n['ok']} ok, {n['newer_major']} newer major, {n['unreachable']} unreachable."]
    lines += [
        "",
        "moved: find the page's new address and update `evidence.url`. missing: re-read the source, since its edition may have changed, "
        "and update the entry with a new quote and date. Either is a change to schemas/roles.json, which a person approves. "
        "unreachable: no answer to judge (a network error, a refusal, a type that is not text, or a limit of this run). It says nothing about the standard. "
        "newer major: read the tool's release notes, then update the library standard's `checked_version`, `pin`, and `checked` date. "
        "This check read the registry and the library and changed nothing.",
    ]
    return "\n".join(lines) + "\n"
