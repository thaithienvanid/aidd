"""Command-line interface and output formatting for the prototype tool."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for `prototype.py` (no abbreviated flags)."""
    parser = argparse.ArgumentParser(
        prog="prototype.py",
        description="aidd-team's prototype tool: show a design in the viewer, check it, and read its component contract.",
        allow_abbrev=False,
    )
    parser.add_argument("--docs", default="docs", help="the documentation folder that holds design/app/ (default: docs)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, what in (
        ("build", "write the design's page in the viewer to .aidd/views/, and print its problems"),
        ("check", "check the design and write nothing: report every problem with its line, and exit 1 on any"),
        ("components", "print the design's component contract as JSON"),
        ("screens", "print the design's screens as JSON: each one's id, title, parent, first state, and states in order"),
    ):
        command = commands.add_parser(name, help=what, allow_abbrev=False)
        command.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
        if name == "build":
            command.add_argument("--open", action="store_true", help="open the written page in your browser")
        elif name == "check":
            command.add_argument("--json", action="store_true", help="print the check result as JSON")
    shots = commands.add_parser("shots", help="print the fidelity pass's views as JSON, sized to the change", allow_abbrev=False)
    shots.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
    shots.add_argument("--changed-screen", action="append", default=[], metavar="ID", help="a new or reshaped screen: its full matrix; repeat for each")
    shots.add_argument("--changed-component", action="append", default=[], metavar="NAME", help="a component whose look or states changed; repeat for each")
    shots.add_argument("--frames", default="", metavar="IDS", help="the frames the product ships, by device id, comma-separated (default: 320,ios,1024)")
    shots.add_argument("--capture", action="store_true", help="render the selected views to PNGs using headless Chrome")
    shots.add_argument("--out", default="", metavar="DIR", help="folder for --capture PNGs (default: .aidd/shots)")
    stories = commands.add_parser("stories", help="check Storybook's index.json against the component contract: exit 1 on a missing story", allow_abbrev=False)
    stories.add_argument("index", help="Storybook's index.json, from `storybook build` (storybook-static/index.json)")
    stories.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
    new = commands.add_parser("new-product", help="start the product prototype in <docs>/design/app/", allow_abbrev=False)
    new.add_argument("--name", default="", help="the product's name")
    example = commands.add_parser("example", help="write the tool's showcase, a complete design to learn from, to .aidd/views/", allow_abbrev=False)
    example.add_argument("--open", action="store_true", help="open the written page in your browser")
    serve = commands.add_parser(
        "serve", help="serve the page on 127.0.0.1 until Ctrl-C, built again on each reload, with --lan for a phone", allow_abbrev=False
    )
    serve.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
    serve.add_argument("--lan", action="store_true", help="listen on the local network too, so a phone on it can open the page")
    serve.add_argument("--port", type=int, default=8765, help="the port (default: 8765)")
    design = commands.add_parser("new-design", help="start a design file, such as an exploration's sketch, from the starting design", allow_abbrev=False)
    design.add_argument("file", help="where to write it, such as directions/a.html")
    design.add_argument("--title", default="A direction", help="what it shows")
    save_c = commands.add_parser("save-comments", help="save exported viewer JSON into rounds/<N>/comments.json cleanly", allow_abbrev=False)
    save_c.add_argument("source", help='the JSON file the viewer\'s "Download comments.json" gives: its path, or - for stdin')
    save_c.add_argument(
        "file", nargs="?", help="a prototype or exploration direction file, whose folder gets the round; the product prototype's folder when absent"
    )
    save_c.add_argument("--round", type=int, default=None, metavar="N", help="the round to write, as in rounds/<N>/ (default: the round the JSON file names)")
    return parser


def _contract_command(tool: Any, root: Path, args: argparse.Namespace) -> int:
    contract, problems = tool.contract_of(root, args.file, args.docs)
    if contract is None:
        for problem in problems:
            print(f"problem: {problem}")
        return 1
    if args.command == "components":
        print(json.dumps(contract, indent=2))
        return 0
    try:
        stories = tool.stories_of(json.loads(Path(args.index).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"problem: {args.index} cannot be read ({exc}): run `storybook build`, then name its index.json")
        return 1
    missing = tool.missing_stories(contract, stories)
    print("\n".join(f"problem: {m}" for m in missing) or f"every component variant has a story ({len(stories)} stories read)")
    return 1 if missing else 0


def _capture_shots_dir(root: Path, raw_out: str) -> tuple[Path | None, str]:
    base = root.resolve()
    rel = raw_out or ".aidd/shots"
    if Path(rel).is_absolute():
        return None, f"{rel} escapes the project folder: pass a path inside it, such as .aidd/shots"
    dest = (base / rel).resolve()
    if not dest.is_relative_to(base) or dest == base:
        return None, f"{rel} escapes the project folder: pass a path inside it"
    return dest, ""


def _screens_command(tool: Any, root: Path, args: argparse.Namespace) -> int:
    out_dir: Path | None = None
    if args.command == "shots" and args.capture:
        out_dir, err = _capture_shots_dir(root, args.out)
        if err or out_dir is None:
            print(f"problem: {err}", file=sys.stderr)
            return 2
    if args.command == "shots":
        frames = [f.strip() for f in args.frames.split(",") if f.strip()]
        found, problems = tool.shots_of(root, args.file, args.docs, components=args.changed_component, screens=args.changed_screen, frames=frames)
    else:
        found, problems = tool.screens_of(root, args.file, args.docs)
    for problem in problems:
        print(f"problem: {problem}")
    if problems:
        return 1
    if found is not None:
        print(json.dumps(found, indent=2))
    if args.command == "shots" and args.capture and found is not None and out_dir is not None:
        page, b_problems = tool.build_design_file(root, args.file) if args.file else tool.build_product_prototype(root, args.docs, write=True)
        if not page:
            for p in b_problems:
                print(f"problem: {p}", file=sys.stderr)
            return 1
        written, c_problems = tool._sibling("prototype_capture").capture_shots(page, found["shots"], out_dir)
        if c_problems:
            for p in c_problems:
                print(f"problem: {p}", file=sys.stderr)
            return 2
        print(f"captured {len(written)} shots in {out_dir.relative_to(root.resolve()).as_posix()}", file=sys.stderr)
    return 0


def _check_command(tool: Any, root: Path, args: argparse.Namespace) -> int:
    where = args.file or f"{args.docs}/{tool.APP}/"
    if not args.file and not tool.product_prototype_dir(root, args.docs).is_dir():
        msg = f"no file named, and no product prototype in {args.docs}/{tool.APP}/: name a design file, such as specs/<ID>/design/prototype.html, or start a product prototype with `aidd new product-prototype` (this tool's `new-product`)"
        if args.json:
            print(json.dumps({"schema_version": str(tool.FORMAT), "ok": False, "target": where, "summary": "", "problems": [msg]}, indent=2))
        else:
            print(f"problem: {msg}")
        return 1
    problems, ok = tool.check_design_file(root, args.file) if args.file else tool.check_product_prototype(root, args.docs)
    if args.json:
        print(json.dumps({"schema_version": str(tool.FORMAT), "ok": not problems, "target": where, "summary": ok, "problems": problems}, indent=2))
        return 1 if problems else 0
    print("\n".join(f"problem: {problem}" for problem in problems) or ok or "the prototype is consistent")
    if problems:
        print(tool.problems_line(len(problems), where))
    return 1 if problems else 0


def _scaffold_command(tool: Any, root: Path, args: argparse.Namespace) -> int:
    if args.command == "example":
        page = tool.view_example(root)
        print(f"wrote {page.relative_to(root).as_posix()}: open it in a browser\n{tool.file_url(page)}")
        if args.open:
            print(tool.open_page(page))
        print(
            "next: start your own design with `aidd new design-spec <topic> --spec <ID> --prototype`, or this tool's `new-design <file>`; never copy the showcase"
        )
        return 0
    if args.command == "new-design":
        try:
            shown = tool.new_design(root, args.file, args.title).relative_to(root).as_posix()
        except (ValueError, FileExistsError) as exc:
            print(f"problem: {exc}", file=sys.stderr)
            return 2
        print(f"{shown}\nnext: sketch the direction in it, then `{tool.BUILD} {shown}` to see it")
        return 0
    try:
        paths = tool.new_product_prototype(root, docs_dir=args.docs, product=args.name)
    except (ValueError, FileExistsError) as exc:
        print(f"problem: {exc}", file=sys.stderr)
        return 2
    for path in paths:
        print(path.relative_to(root).as_posix())
    return 0


def _save_comments_command(tool: Any, root: Path, args: argparse.Namespace) -> int:
    base = root.resolve()
    if args.file:
        design = (base / args.file).resolve()
        if not design.is_relative_to(base) or not design.is_file():
            print(f"problem: {args.file} is not a design file inside this repository", file=sys.stderr)
            return 2
        direction, folder, err = tool.direction_of(base, design)
        if err:
            print(f"problem: {err}", file=sys.stderr)
            return 2
    else:
        if Path(args.docs).is_absolute():
            print(f"problem: {args.docs} must stay inside this repository", file=sys.stderr)
            return 2
        docs_root = base / args.docs
        folder, direction = tool.product_prototype_dir(base, args.docs), ""
        if docs_root.is_symlink() or folder.parent.is_symlink() or folder.is_symlink() or not folder.resolve().is_relative_to(base):
            print(f"problem: {args.docs}/{tool.APP}/ must be a plain folder inside this repository", file=sys.stderr)
            return 2
        if not folder.is_dir():
            print(f"problem: no product prototype in {args.docs}/{tool.APP}/", file=sys.stderr)
            return 2
    dest, problems = tool._rounds().save_round_comments(folder, args.source, direction=direction, round_num=args.round)
    if problems or dest is None:
        for p in problems:
            print(f"problem: {p}", file=sys.stderr)
        return 2
    shown = dest.resolve().relative_to(base).as_posix()
    next_cmd = f"{tool.BUILD} {args.file}" if args.file else tool.BUILD
    print(f"saved {shown}\nnext: rebuild to review earlier rounds with `{next_cmd}`")
    return 0


def run(tool: Any, argv: list[str] | None = None) -> int:
    """Execute one subcommand against `tool` (`prototype` module)."""
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    if args.command in ("example", "new-design", "new-product"):
        return _scaffold_command(tool, root, args)
    if args.command == "save-comments":
        return _save_comments_command(tool, root, args)
    if args.command == "serve":
        return int(tool.serve_design(root, args.file, args.docs, lan=args.lan, port=args.port))
    if args.command in ("components", "stories"):
        return _contract_command(tool, root, args)
    if args.command in ("screens", "shots"):
        return _screens_command(tool, root, args)
    if args.command == "check":
        return _check_command(tool, root, args)
    if not args.file and not tool.product_prototype_dir(root, args.docs).is_dir():
        print(
            f"problem: no file named, and no product prototype in {args.docs}/{tool.APP}/: name a design file, such as specs/<ID>/design/prototype.html, or start a product prototype with `aidd new product-prototype` (this tool's `new-product`)"
        )
        return 1
    out, problems = tool.build_design_file(root, args.file) if args.file else tool.build_product_prototype(root, args.docs, write=True)
    for problem in problems:
        print(f"problem: {problem}")
    if out:
        print(f"wrote {out.relative_to(root).as_posix()}: open it in a browser\n{tool.file_url(out)}")
        if getattr(args, "open", False):
            print(tool.open_page(out))
    if out and problems:
        print(tool.problems_line(len(problems), args.file or f"{args.docs}/{tool.APP}/"))
    return 1 if problems else 0


def serve_design(tool: Any, root: Path, rel: str | None, docs_dir: str = "docs", *, lan: bool = False, port: int = 8765) -> int:
    """Serve one design file or the product prototype locally, rebuilding on each request."""
    if rel:
        shown, _, problems = tool._design_source(root, rel)
        if problems:
            print("\n".join(problems))
            return 2
        folder = (root / shown).parent
        if folder.resolve() == root.resolve():
            print(
                f"{shown} sits at the repository's top, so serving its folder would share every file there: move it into a folder of its own, such as design/{Path(shown).name}"
            )
            return 2
    else:
        folder = tool.product_prototype_dir(root, docs_dir)
        if not folder.is_dir():
            print(f"no product prototype in {docs_dir}/{tool.APP}/: name a design file, or start one with `{tool.BUILD} new-product`")
            return 2
    building = threading.Lock()

    def page() -> str:
        with building:
            out, found = tool.build_design_file(root, rel) if rel else tool.build_product_prototype(root, docs_dir)
            if out is None:
                raise ValueError("; ".join(found) or "the design cannot be read")
            return out.read_text(encoding="utf-8")

    return int(tool._sibling("server").serve(folder, page, lan=lan, port=port))
