"""The commands on what the team already wrote: `aidd records`, the history of asks and reports, and `aidd recall`, the search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aidd import recall, records
from aidd.cli import arguments
from aidd.kernel import documents


def cmd_records(args) -> int:
    """`aidd records [add|push|pull]`: the records, newest first; one record written, after an answered ask or a reported
    action; or the records shared through a remote's `refs/aidd/records`."""
    if args.records_command == "add":
        if not (args.record_type and args.by and args.data):
            raise ValueError(
                "name the record: `aidd records add --type decision --by <harness>/<model> --data '<json>'`, such as "
                "`--by claude-code/claude-opus-5-5`; `--data -` reads the JSON from stdin"
            )
        if args.by.startswith("person:"):
            raise ValueError("an agent writes a record as itself: give `--by <harness>/<model>`, never a person's name")
        raw = sys.stdin.read() if args.data == "-" else args.data
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--data is not JSON: {exc}") from None
        if not isinstance(data, dict):
            raise ValueError("--data is the record's data: a JSON object, such as the decision's question, covers, and answer")
        record, path = records.add_record(args.record_type, data, by="agent:" + args.by.removeprefix("agent:"), subject=args.subject)
        if args.json:
            print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "record": record}, indent=2))
        else:
            print(f"Recorded {record['type']} {record['id']} in {path}")
        return 0
    if args.records_command in ("push", "pull"):
        # Push and pull run only from their exact words, `records push [remote]`, so the shapes a harness's ask rule
        # matches are the only ones that push. A rule is a net, never a control: SECURITY.md says so.
        words = getattr(args, "words", None)
        if words is not None and (words[:2] != ["records", args.records_command] or len(words) > 3 or any(w.startswith("-") for w in words)):
            raise ValueError(f"`aidd records {args.records_command}` takes only a remote, after it: `aidd records {args.records_command} origin`")
        args.remote = args.remote or "origin"
    elif args.remote:
        raise ValueError(f"unexpected {args.remote!r}: only `aidd records push` and `pull` take a remote")
    if args.records_command == "pull":
        added, refused = records.pull_records(args.remote)
        for line in refused:
            print(f"aidd: skipped {documents.one_line(line, 300)}", file=sys.stderr)
        print(f"Pulled {len(added)} record(s) from {args.remote}." if added else f"{args.remote} has no record this clone lacks.")
        return 0
    if args.records_command == "push":
        print(f"Pushing to {records.push_url(args.remote)}", file=sys.stderr)
        pulled, held = records.push_records(args.remote)
        print(
            f"Pushed {held} record(s) to {args.remote}'s refs/aidd/records" + (f", after pulling {pulled}." if pulled else ".")
            if held
            else "No records to push yet."
        )
        return 0
    found, unreadable = records.read_records(record_type=args.record_type, subject=args.subject)
    pulled_here = records.pulled_ids()
    partly = records.partly_read(found)
    if args.json:
        shown = sorted(pulled_here & {r["id"] for r in found})
        print(
            json.dumps(
                {"schema_version": arguments.JSON_SCHEMA_VERSION, "records": found, "pulled": shown, "partly_read": partly, "unreadable": unreadable}, indent=2
            )
        )
        return 0
    for r in found:
        data = r["data"]  # a record of a newer type, or another's, may hold any shape: read only what is there
        question = data.get("question") if isinstance(data.get("question"), dict) else {}
        answer = data.get("answer") if isinstance(data.get("answer"), dict) else {}
        what = question.get("text") or data.get("said") or ""
        parts = [
            r.get("recorded_at", ""),
            r["type"],
            r.get("subject"),
            data.get("action"),
            answer.get("outcome"),
            f"by {r.get('by')}",
            r.get("written_with") == "mcp" and "through the MCP tool",
            answer.get("by") and f"answered by {answer['by']}",
            r["id"] in pulled_here and "pulled from a remote",
            r["id"] in partly and "read in part",
        ]
        line = "  ".join(documents.one_line(x, 80) for x in parts if x)  # a pulled record's fields are another's text
        print(f"{line}: {documents.one_line(what, 100)}" if what else line)
    if not found:
        print("No records yet. The agent writes one after each ask you answer and each action it reports (`aidd records add`).")
    if partly:
        print(
            f"aidd: {len(partly)} record(s) are read in part, as a newer aidd's records are, or with a field missing: they are listed, and nothing counts them as an answer",
            file=sys.stderr,
        )
    if unreadable:
        print(
            f"aidd: {len(unreadable)} file(s) in {records.records_dir()} do not read as a record, so they were skipped: {documents.one_line(_under(unreadable[0], records.records_dir()))}",
            file=sys.stderr,
        )
    return 0


def cmd_recall(args) -> int:
    """`aidd recall`: the lines of the team's writing that hold every word; a cache of the files, never evidence or a yes."""
    arguments.enter_repo(args)
    answer = recall.search(Path("."), arguments.config_or_none_quiet(args), args.recall_words, limit=args.limit)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | answer, indent=2))
    else:
        print(recall.search_text(answer), end="")
    return 0


def _under(path, folder) -> str:
    """`path` as it reads from `folder`, which the message names already, so a long folder never hides the file's name."""
    try:
        return Path(path).relative_to(folder).as_posix()
    except ValueError:
        return str(path)
