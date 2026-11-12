"""The command that proves a change: `aidd test`, which runs the tests, green on the head and red on the base, and writes the evidence."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from aidd import testing
from aidd.cli import arguments
from aidd.kernel import documents, git


def cmd_test(args) -> int:
    arguments.enter_repo(args, "spec", file_attrs=("out",))
    changed = args.changed or args.watch
    if changed and args.require_green:
        raise ValueError(
            "--require-green needs the full run, because a quick --changed run skips the red runs and the frozen-file check and is never the change's "
            "evidence: drop --changed (--watch runs --changed too), or drop --require-green"
        )
    if args.no_red and args.require_green:
        raise ValueError(
            "--require-green needs the full run, because --no-red skips the red runs, so a test that never failed on the base would pass and a "
            "changed working tree would be excused: drop --no-red, or drop --require-green"
        )

    def once() -> int:
        ev, notes = testing.run_tests(
            base=args.base,
            spec=arguments.spec_by_id(args.spec) if args.spec else None,
            out_dir=args.out,
            red=not args.no_red,
            red_in_place=args.red_in_place,
            pass_env=args.pass_env or (),
            changed=changed,
            require_green=args.require_green,
            progress=lambda line: print(line, file=sys.stderr, flush=True),
        )
        return _print_test_results(ev, notes, args.out, no_red=args.no_red)

    if not args.watch:
        return once()
    out = Path(args.out).resolve()
    exclude = out.relative_to(Path.cwd().resolve()).as_posix() if out.is_relative_to(Path.cwd().resolve()) else None

    def announce() -> None:
        print(f"\n--- {dt.datetime.now():%H:%M:%S} aidd test --changed ---")
        try:
            once()
        except (ValueError, OSError, LookupError, git.GitError, RuntimeError) as exc:
            print(f"aidd: {exc}", file=sys.stderr)  # keep watching: the next save may fix it
        print("watching for changes every second; Ctrl-C to stop")

    return testing.watch_tests(announce, exclude=exclude)


def _print_test_results(ev: dict, notes: list[str], out: str, *, no_red: bool = False) -> int:
    """Each result, then the notes and where the evidence is. The exit code is `testing.exit_code`'s: 1 when a result is bad
    or a full run ran no command. A failing green run is marked `..` only when the result itself says the runner expected it
    before Implement."""
    before_implement = bool(ev.get("before_implement"))
    for r in ev["results"]:
        mark = testing.result_mark(r, before_implement=before_implement)
        flaky = f" after {len(r['attempts'])} attempts (flaky)" if r.get("flaky") else ""
        related = ", only its related tests" if r.get("related_tests") else ""
        print(
            f"[{mark}] {r['red_green']:5} {r['name']}: {r['status']} (exit {r['exit']}){flaky}{related} log {arguments.repo_relative(Path(out) / r.get('log', ''))}"
        )
    for n in notes:
        print(f"note: {n}")
    if ev["head_sha"] == ev["base_sha"]:
        print("note: this branch has no commit of its own yet, so nothing here proves a change; commit the work, then run `aidd test` again")
    partial = " (partial: a quick check, not the change's evidence)" if ev.get("partial") else ""
    revised = (
        f" (revises {', '.join(documents.one_line(r['id'], 64) for r in ev['revised_frozen'])} and rewrites files it froze: a person approves again)"
        if ev.get("revised_frozen")
        else ""
    ) + (" (the repository suite ran as its smoke set alone: the emergency route)" if ev.get("emergency_subset") else "")
    print(f"evidence: {arguments.repo_relative(Path(out) / 'evidence.json')}  head {ev['head_sha'][:12]}  base {ev['base_sha'][:12]}{partial}{revised}")
    return testing.exit_code(ev, no_red=no_red)
