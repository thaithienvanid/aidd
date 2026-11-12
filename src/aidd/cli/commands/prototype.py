"""Implementation of the `aidd prototype` command, split from `work.py` to keep command modules concise."""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.cli import arguments
from aidd.kernel import command_names, resources


def _no_page_message(args, where: str) -> str:
    if args.file and Path(args.file).is_dir():
        return f"wrote no page: {args.file} is a directory, not a prototype file; name a file, such as specs/<ID>/design/prototype.html"
    if args.file and not Path(args.file).is_file():
        return (
            f"wrote no page: {args.file} does not exist; run `aidd new design-spec <topic> --spec <ID> --prototype` to start one, "
            "or `aidd prototype --example` to see an example"
        )
    target = f" {command_names.quoted(args.file) or '<file>'}" if args.file else ""
    return f"wrote no page: fix the problems above in {where}, then run `aidd prototype{target}` again"


def _prepare_prototype_args(args) -> Path:
    """Validate conflicting `aidd prototype` flags, capture original cwd, and rebase relative `--save-comments`."""
    modes = (
        args.check,
        args.example,
        args.new_design is not None,
        args.components,
        args.screens,
        args.shots,
        args.stories is not None,
        args.save_comments is not None,
    )
    if sum(map(bool, modes)) > 1:
        raise ValueError(
            "--check checks the design; --example, --new-design, --components, --screens, --shots, --stories, and --save-comments each run one action: give one of them"
        )
    cwd = Path.cwd()
    if args.save_comments and args.save_comments != "-" and not Path(args.save_comments).is_absolute():
        args.save_comments = str(cwd / args.save_comments)
    reading = arguments.prototype_reading(args)
    if args.serve and args.check:
        raise ValueError("--serve serves the page and --check only checks it: run `aidd prototype --check` first, then --serve")
    if args.serve and (reading or args.example or args.new_design is not None):
        raise ValueError("--serve serves the page interactively: drop read-only or scaffolding flags")
    if (args.lan or args.port != 8765) and not args.serve:
        raise ValueError("--lan and --port go with --serve: add --serve to serve the page")
    if args.open and (args.check or reading or args.new_design is not None or args.serve):
        raise ValueError("--open opens the written page in your browser: drop --check, --serve, --new-design, and read-only flags")
    return cwd


def _rebase_shots_out(args, cwd: Path) -> None:
    """Keep relative `--out` anchored to the caller's cwd before `enter_repo` changes to repo root."""
    if not args.out or Path(args.out).is_absolute():
        return
    top = Path.cwd().resolve()
    dest = (cwd / args.out).resolve()
    if not dest.is_relative_to(top) or dest == top:
        raise ValueError(f"{args.out} escapes the project folder: pass a path inside it, such as .aidd/shots")
    args.out = dest.relative_to(top).as_posix()


def run(args) -> int:
    """Execute `aidd prototype` from validated CLI arguments."""
    cwd = _prepare_prototype_args(args)
    arguments.enter_repo(args, "file", "new_design", file_attrs=("stories",), outside_ok=True)
    _rebase_shots_out(args, cwd)
    reading = arguments.prototype_reading(args)
    tool = resources.team_tool("prototype")
    if args.example:
        page = tool.view_example(Path("."))
        print(f"wrote {page.as_posix()}: open it in a browser; it is a way to learn, never a start\n{tool.file_url(page)}")
        print("next: `aidd new design-spec <topic> --spec <ID> --prototype` starts a design of your own")
        if args.open:
            print(tool.open_page(page))
        return 0
    if args.new_design is not None:
        print(tool.new_design(Path("."), args.new_design, args.title).as_posix())
        print(f"next: sketch the direction in it, then `aidd prototype {command_names.quoted(args.new_design) or '<file>'}` to see it")
        return 0
    cfg = arguments.config_or_none()
    docs = (cfg or config.EMPTY).docs_dir
    if not args.file and not tool.product_prototype_dir(Path("."), docs).is_dir():
        raise ValueError(
            f"no product prototype in {docs}/design/app/: name a design file, such as `aidd prototype --check <file>`, or start one with `aidd new product-prototype`"
        )
    if args.serve:
        return int(tool.serve_design(Path("."), args.file, docs, lan=args.lan, port=args.port))
    if reading:
        return tool.main(["--docs", docs, *reading, *(["--", args.file] if args.file else [])])
    if args.file and args.check:
        problems, ok = tool.check_design_file(Path("."), args.file)
        print("\n".join(f"problem: {problem}" for problem in problems) or ok)
        if problems:
            print(tool.problems_line(len(problems), args.file))
        return 1 if problems else 0
    if args.file:
        out, problems = tool.build_design_file(Path("."), args.file)
    else:
        out, problems = tool.build_product_prototype(Path("."), docs, write=not args.check)
    where = args.file or f"{docs}/design/app/"
    for problem in problems:
        print(f"problem: {problem}")
    if out:
        print(f"wrote {out.as_posix()}: open it in a browser" + (f"; {args.file} is unchanged" if args.file else "") + f"\n{tool.file_url(out)}")
        if args.open:
            print(tool.open_page(out))
    elif not args.check:
        print(_no_page_message(args, where))
    if out and problems:
        print(tool.problems_line(len(problems), where))
    if args.check:
        print("the prototype is consistent" if not problems else tool.problems_line(len(problems), where))
    return 1 if problems else 0
