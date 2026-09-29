"""aidd: the command line."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__, docs, evals, ext, gitutil, globs, http, inputs, localctx, metrics, model, repo, report, resources, rules, runner
from . import config as cfgmod
from .util import TRAILER, agent_coauthors, red_ok, split_command
from .verify import verify

# Where `aidd hook pre-edit` logs its denials (guard.GUARD_LOG), relative to the repository's top level.
GUARD_LOG_DEFAULT = ".aidd/work/guard.jsonl"
# The version of `aidd owners --json` (schemas/owners.schema.json): a new key keeps it, a renamed or removed one bumps it.
OWNERS_SCHEMA_VERSION = "1"

EXIT = {"pass": 0, "fail": 1, "pending": 3}
VOCAB = resources.load_json("common.schema.json")["$defs"]
TYPES = VOCAB["type"]["enum"]
DIMENSIONS = VOCAB["dimension"]["enum"]
EPILOG = """The loop: next (the route and lane) -> (spec lane: new spec, draft PR/MR, approve-spec) -> implement + test -> review -> approve -> ship.
Exit codes: 0 pass or ok, 1 fail, 3 pending (a local gate; `gate github` exits 0 and `gate gitlab` exits 1 on pending unless --pending-ok), 2 error.
Docs: https://github.com/thaithienvanid/aidd"""
PASS_ENV_HELP = (
    "pass this credential-like variable to the command (repeatable); by default every *TOKEN*, *SECRET*, *PASSWORD*, *_KEY, "
    "and *CREDENTIAL* variable is dropped"
)


class _Help(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show a default only when it says something and the help text does not already explain it."""

    def _get_help_string(self, action):
        text = action.help or ""
        if "default" in text or action.default in (None, "", False, [], argparse.SUPPRESS):
            return text
        return super()._get_help_string(action)


def _enter_repo(args, *path_attrs: str, file_attrs: tuple[str, ...] = ()) -> None:
    """Run from the repository root. Repo-relative arguments are rebased; file arguments become absolute."""
    top = Path(gitutil.toplevel(check=True))
    cwd = Path.cwd()
    for attr in file_attrs:
        value = getattr(args, attr, None)
        if value:
            setattr(args, attr, str((cwd / value).resolve()))
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if value:
            abs_path = (cwd / inputs.repo_path(value)).resolve()
            setattr(args, attr, abs_path.relative_to(top.resolve()).as_posix() if abs_path.is_relative_to(top.resolve()) else inputs.repo_path(value))
    os.chdir(top)


def _repo_relative(path: Path) -> str:
    """A path as printed after `_enter_repo`: relative to the repository root when it is inside it, else as given."""
    p = path.resolve()
    here = Path.cwd().resolve()
    return p.relative_to(here).as_posix() if p.is_relative_to(here) else str(path)


def _body(args) -> str | None:
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    if getattr(args, "spec", None):
        return localctx.spec_block(args.spec)
    return None


def _reviewers(entries: list[str] | None) -> dict[str, list[str]]:
    """--reviewer security=@org/security,@alice -> {"security": ["@org/security", "@alice"]}."""
    out: dict[str, list[str]] = {}
    for entry in entries or []:
        pool, sep, who = entry.partition("=")
        if not sep or not pool.strip() or not who.strip():
            raise ValueError(f"--reviewer takes POOL=WHO[,WHO], got {entry!r}")
        out.setdefault(pool.strip(), []).extend(w.strip() for w in who.split(",") if w.strip())
    return out


def cmd_init(args) -> int:
    from . import detect

    root = Path(args.path)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    found = detect.detect(root)
    if args.dry_run:
        print(detect.markdown(found), end="")
        return 0
    if not args.approvers and args.profile != "solo":
        # An empty owners.approvers fails every change closed; under solo init names the operator, elsewhere nobody can guess.
        print(
            f"error: profile {args.profile} needs the people who may approve: pass --approvers, such as\n"
            f"  aidd init --profile {args.profile} --approvers @your-org/leads\n"
            "(a user @alice, a team @org/team, or email:you@example.com for local-first approvals; `aidd init --dry-run` writes nothing)",
            file=sys.stderr,
        )
        return 2
    links = list(dict.fromkeys(args.link or []))
    repo.pin_workflow("", args.ref)  # a bad --ref stops here, before init writes anything
    # Without --test, the suite detected at the repository root; a monorepo's per-package suites stay a suggestion.
    detected_test = next((t["test"] for t in found["tests"] if t["path"] == "."), None) if not args.test else None
    if detected_test:
        print(f"detected the test command: {' '.join(detected_test)} (pass --test to choose another)")
    for line in repo.init(
        root,
        profile=args.profile,
        ci=args.ci,
        links=links,
        skill=not args.no_skill,
        force=args.force,
        approvers=args.approvers,
        reviewers=_reviewers(args.reviewer),
        test=split_command(args.test) if args.test else detected_test,
        policy=split_command(args.policy) if args.policy else None,
        goal=args.goal,
        enforce=args.enforce,
        agent_hooks=True if args.agent_hooks else (False if args.no_agent_hooks else None),
        team=args.team,
        harnesses=None if not args.harness else [h for h in args.harness if h != "none"],
        claude_plugins=args.claude_plugins,
        ref=args.ref,
        devcontainer=args.devcontainer,
    ):
        print(line)
    if not gitutil.run(["rev-parse", "--verify", "--quiet", "HEAD"], str(root), check=False).strip():
        # Greenfield: nothing is on the default branch yet, so nothing can be gated.
        print(
            "\nNew repository: commit this setup, with your project scaffold, directly to the default branch as Day 0.\n"
            "Then run `aidd doctor`, and ship every later change through a pull request.\n"
            "The first Spec usually brings the test runner and the first test."
        )
    else:
        print("\nNext: check owners and [[tests]] in .aidd/config.toml, run `aidd doctor`, and merge this setup.")
    if fit := detect.found_to_fit(found):
        print(f"It also found {'; '.join(fit)}: `aidd init --dry-run` shows the config it proposes for them.")
    if not args.enforce and args.ci != "none":
        print(
            "The gate starts in advisory mode: it reports on 'aidd/gate (advisory)' and blocks nothing. Read `aidd metrics`\n"
            "for a week or two, then set mode to enforce (the aidd-gate.yml input on GitHub, `mode = 'enforce'` in .aidd/config.toml\n"
            "on GitLab) and require aidd/gate."
        )
    return 0


def cmd_upgrade(args) -> int:
    """Bring a repository's aidd files up to this aidd, in one change; a dry run unless --yes."""
    try:
        actions = repo.upgrade(Path(args.path), ref=args.ref, yes=args.yes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in actions:
        print(line)
    if not args.yes and not actions[0].startswith("nothing to update"):
        print("\ndry run: nothing changed. Run again with --yes, then `aidd doctor`, and merge it as one change; it touches")
        print("protected paths, so the gate treats it as major.")
    print("\nThe CLI itself: `uv tool upgrade aidd` or `pipx upgrade aidd` (or the one-line installer with AIDD_REF=<release>).")
    print("The Claude Code plugins: `claude plugin update aidd@aidd` and `claude plugin update aidd-team@aidd`.")
    return 0


def cmd_uninstall(args) -> int:
    for line in repo.uninstall(Path(args.path), links=args.link or [], yes=args.yes):
        print(line)
    return 0


def cmd_doctor(args) -> int:
    results = repo.doctor(Path(args.path), execute=True)
    for level, msg in results:
        print(f"[{level:4}] {msg}")
    return 1 if any(level == "fail" for level, _ in results) else 0


def _config_or_none() -> cfgmod.Config | None:
    if not Path(cfgmod.CONFIG_PATH).is_file():
        return None
    return cfgmod.load_file(cfgmod.CONFIG_PATH)


def _spec_route(args, cfg: cfgmod.Config | None) -> tuple[str, bool]:
    """(route, write) for `aidd new spec`: with --paths, the route computed from the paths (the entry rule), raised to
    --route when that is higher; without, --route (default normal). `write` is False when the paths need no Spec."""
    chosen = args.route or "normal"
    if args.kind != "spec" or not args.paths:
        return chosen, True
    if cfg is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    a = rules.assess_paths(cfg, args.paths, ctype=args.type, dimensions=args.dimension or [], irreversible=args.irreversible)
    print(f"route: the minimum for these paths is {a.required_route} ({a.lane} lane)")
    for line in rules.reason_lines(a):
        print(f"  - {line}")
    if a.lane == "fast":
        if not args.force:
            print(
                "no Spec needed: the fast lane implements and verifies directly, and `aidd change` prints the toml aidd block for "
                "the PR/MR. A Spec is still yours to choose: `--force` writes one (route normal), and the gate never lets a change "
                "below its minimum, only above it."
            )
            return a.required_route, False
        return max(chosen, "normal", key=rules.ROUTE_RANK.__getitem__), True
    route = max(chosen, a.required_route, key=rules.ROUTE_RANK.__getitem__)
    if args.route and rules.ROUTE_RANK[args.route] < rules.ROUTE_RANK[a.required_route]:
        print(f"route {a.required_route}, not --route {args.route}: a Spec's route is never below the computed minimum")
    return route, True


def cmd_new(args) -> int:
    _enter_repo(args)
    cfg = _config_or_none()
    if args.kind != "spec" and (args.paths or args.dimension or args.irreversible):
        raise ValueError("--paths, --dimension, and --irreversible compute a Spec's route: use them with `aidd new spec`")
    if args.route == "emergency" and args.paths:
        raise ValueError("an emergency backfill Spec takes its route from the declared emergency, not from --paths")
    route, write = _spec_route(args, cfg)
    if not write:
        return 0
    path = repo.new_object(
        Path("."),
        kind=args.kind,
        id=args.id,
        title=args.title,
        route=route,
        scope=args.paths or None,
        dimensions=args.dimension or None,
        irreversible=args.irreversible,
        full=args.full,
        ctype=args.type,
        owner_team=args.owner_team or (cfg.get("owners", "default_team", default="") if cfg else ""),
        parent=args.parent,
        specs_dir=cfg.specs_dir if cfg else "specs",
        audience=args.audience,
        addressee=args.addressee,
        proposals_dir=cfg.proposals_dir if cfg else "proposals",
        spec=args.spec,
    )
    print(path)
    todo = {
        "runbook": "name the service, write steps a person can copy, run it once, record last_tested",
        "postmortem": "fill the timeline, causes, and action items with owners and dates",
        "proposal": "fill the needs and the goal, have a person record go_no_go",
    }.get(args.kind, "fill Context, Acceptance, tasks, and tests, write the test files")
    if args.kind == "spec" and repo.spec_template(route, args.full) == "spec-short":
        scope = "" if args.paths else "the Task's scope, "  # --paths already wrote it
        todo = f"replace the TODOs (Intent, Acceptance, Design, Rollback, {scope}the tests), write the test files"
    print(f"next: {todo}, then `aidd validate {path}`")
    return 0


def cmd_import(args) -> int:
    """A short Spec from Spec Kit, OpenSpec, Kiro, or BMAD planning files, pointing at them."""
    from . import importers

    _enter_repo(args, "out", file_attrs=("path",))
    cfg = _config_or_none()
    if cfg is None:
        raise ValueError(f"no {cfgmod.CONFIG_PATH}: `aidd init` first, so the route can be computed from the paths")
    path, lines = importers.build(args.tool, Path(args.path), Path("."), cfg, spec_id=args.id, out=args.out, title=args.title, ctype=args.type)
    print(path.as_posix())
    for line in lines:
        print(line)
    return 0


def cmd_validate(args) -> int:
    if not args.paths:
        _enter_repo(args)
        errors, warnings = repo.check_repo(Path("."))
    else:
        found = [e for p in args.paths for e in repo.validate_file(Path(p))]
        errors = [e for e in found if not e.startswith("warning: ")]
        warnings = [e for e in found if e.startswith("warning: ")]
    for w in warnings:
        print(w if w.startswith("warning: ") else f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_hash(args) -> int:
    _enter_repo(args, "spec")
    if args.worktree:
        text = Path(args.spec).read_text(encoding="utf-8")
        data, _ = model.split_front_matter(text, args.spec)
        # Untracked files count too: the hash must match what the gate computes once they are committed.
        files = [
            p
            for p in gitutil.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"]).split("\0")
            if p and globs.match_any(model.frozen_paths(data), p) and Path(p).is_file()
        ]
        tree = gitutil.hash_files(files)
    else:
        shown = gitutil.show(args.ref, args.spec)
        if shown is None:
            raise ValueError(f"{args.spec} is not in {args.ref}; commit it first, or pass --worktree")
        text = shown
        data, _ = model.split_front_matter(text, args.spec)
        tree = gitutil.ls_tree(args.ref)
        dirty = gitutil.run(["status", "--porcelain", "--", args.spec, *model.frozen_paths(data)], check=False).strip()
        if dirty:
            print(f"warning: uncommitted changes to the Spec or its tests; this hash is for {args.ref}", file=sys.stderr)
    h = model.spec_hash(text, tree)
    # The commit makes the approval prove Spec approval came before implementation (gates.spec_approval_proof).
    sha = "" if args.worktree else " " + gitutil.rev_parse(args.ref)
    if args.worktree and args.comment:
        print(
            "warning: a --worktree line names no commit, so it cannot prove Spec approval came before implementation; under spec_approval_proof = require it never counts",
            file=sys.stderr,
        )
    line = f"/aidd approve-spec {data.get('id')} {h}{sha}" if args.comment else h
    if args.digest:
        from . import digest

        # What the Approver reads before posting the line, in at most 25 lines; the line itself is the last.
        print(digest.spec_digest(text, args.spec, line))
    else:
        print(line)
    return 0


def cmd_approve(args) -> int:
    """Record a person's approval on this machine, with no platform: a Spec approval or a Merge approval (local.py)."""
    from . import local

    _enter_repo(args, "spec")
    try:
        if args.what == "spec":
            if not args.spec:
                print("error: name the Spec: aidd approve spec specs/<ID>.md", file=sys.stderr)
                return 2
            text = gitutil.show("HEAD", args.spec)
            if text is None and not Path(args.spec).is_file():
                print(f"error: no such Spec: {args.spec}", file=sys.stderr)
                return 2  # a usage error, like a missing argument
            if text is None:
                print(f"error: {args.spec} is not committed; commit the Spec and its tests first", file=sys.stderr)
                return 1  # a failed check: the Spec exists, but not in HEAD
            data, _ = model.split_front_matter(text, args.spec)
            if gitutil.run(["status", "--porcelain", "--", args.spec, *model.frozen_paths(data)], check=False).strip():
                print("error: the Spec or its tests have uncommitted changes; approve what is committed", file=sys.stderr)
                return 1
            head = gitutil.rev_parse("HEAD")
            line = local.approve_spec_line(str(data.get("id")), model.spec_hash(text, gitutil.ls_tree("HEAD")), head)
            local.require_person(f"Spec approval for {data.get('id')}: its Spec and tests at {head[:12]}")
        else:
            head = gitutil.rev_parse("HEAD")
            line = local.approve_merge_line(head)
            local.require_person(f"Merge approval for the head commit {head[:12]}")
        sha, signed = local.record(line)
    except local.NotAPerson as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {'a signed' if signed else 'an unsigned'} approval ({sha[:12]} on {local.APPROVALS_REF})")
    if not signed:
        print("set up git commit signing with a key that asks for your presence, so an approval cannot be written without you")
    return 0


def cmd_ship(args) -> int:
    """Merge a branch that passes the gate into the base branch, on this machine: the local-first Ship."""
    from . import local

    _enter_repo(args, file_attrs=("out",))
    branch = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    base = args.base or inputs.default_base(".").removeprefix("origin/")
    if branch in (base, "HEAD"):
        print(f"error: switch to the branch to ship; this is {branch}", file=sys.stderr)
        return 2
    if gitutil.run(["status", "--porcelain", "--untracked-files=no"]).strip():
        print("error: the working tree has uncommitted changes; commit or stash them first", file=sys.stderr)
        return 1
    head = gitutil.rev_parse("HEAD")
    # The tests run here, on this exact head: evidence on disk is a file an agent could have written.
    ev, notes = runner.run_tests(base=base, out_dir=args.out, pass_env=args.pass_env or ())
    for n in notes:
        print(f"note: {n}")
    ctx = localctx.build(base=base, head=head, run_policy=True)
    if ev["head_sha"] != ctx["head_sha"] or gitutil.rev_parse("HEAD") != head:
        print(f"not shipped: {branch} moved while its tests ran; run `aidd ship` again", file=sys.stderr)
        return 1
    ctx["evidence"] = ev
    d = verify(ctx)
    print(report.text(d))
    if d.decision != "pass":
        print(f"not shipped: the gate says {d.decision}", file=sys.stderr)
        return 1
    try:
        local.require_person(f"Ship {branch} at {head[:12]} into {base}" + (" as one squashed commit" if args.squash else ""))
        new = local.ship(branch, base, squash=args.squash, message=args.message or _ship_message(ctx, branch), head=ctx["head_sha"])
    except (local.NotAPerson, RuntimeError, gitutil.GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"shipped {branch} at {head[:12]} into {base} at {new[:12]}")
    return 0


def _ship_message(ctx: dict, branch: str) -> str:
    """The Spec's title and id when the branch carries one Spec; else the newest commit's subject (commits are newest first)."""
    cr, _ = model.parse_change_block(ctx["change"].get("body") or "")
    spec = (cr or {}).get("spec")
    text = gitutil.show(ctx["head_sha"], spec) if spec else None
    if text:
        try:
            data, _ = model.split_front_matter(text, str(spec))
        except model.ModelError:
            data = {}
        if data.get("title"):
            return f"{data['title']} ({data.get('id', branch)})"
    subject = next((c["message"].splitlines()[0] for c in ctx["commits"][:1] if c.get("message", "").strip()), "")
    return subject or f"Ship {branch}"


def cmd_change(args) -> int:
    """Print a starting toml aidd block for the current branch."""
    _enter_repo(args)
    cfg = cfgmod.load_file(cfgmod.CONFIG_PATH)
    base = args.base or inputs.default_base()
    base_sha = gitutil.merge_base(gitutil.rev_parse(base), gitutil.rev_parse("HEAD"))
    files = gitutil.numstat(base_sha, "HEAD")
    if not files:
        raise ValueError(f"no changes between {base} and HEAD")
    paths = rules.changed_paths(files)
    ctype = args.type or ("docs" if all(p.endswith((".md", ".rst", ".txt")) for p in paths) else "feat")
    a = rules.assess(
        paths=paths,
        cfg=cfg,
        ctype=ctype,
        risk={"dimensions": [], "reversible": True},
        confidence="high",
        task_count=1,
        changed_lines=sum(f["additions"] + f["deletions"] for f in files),
        binary_files=sum(1 for f in files if f.get("binary")),
    )
    commits = gitutil.commits(base_sha, "HEAD")
    bots = {b.lower() for b in cfg.get("identities", "bots", default=[])}
    assisted = sorted(
        {m.strip() for c in commits for m in TRAILER.findall(c["message"]) if m.strip().lower() != "none"}
        | {x for c in commits for x in agent_coauthors(c["message"], bots)}
    )
    print(f"# The diff's minimum route is {a.required_route} ({a.lane} lane), because:")
    for line in rules.reason_lines(a):
        print(f"#   - {line}")
    if a.required_route in ("normal", "major"):
        print("# That needs a Spec:")
        print(f'#   aidd new spec <ID> --title "..." --type {ctype} --paths {" ".join(paths[:5])}{" ..." if len(paths) > 5 else ""}')
        print("# then put this block in the PR/MR description:")
        print('```toml aidd\nspec = "specs/<ID>.md"\n```')
        return 0
    print("```toml aidd")
    print(f'route = "{a.required_route}"')
    print(f'type = "{ctype}"')
    print(f"scope = {json.dumps(paths)}")
    print(f"assisted_by = {json.dumps(assisted)}")
    print("```")
    return 0


def cmd_test(args) -> int:
    _enter_repo(args, "spec", file_attrs=("body_file", "out"))
    if args.merge_group:
        args.base = _merge_group_base(args.base)
    changed = args.changed or args.watch

    def once() -> int:
        ev, notes = runner.run_tests(
            base=args.base,
            spec=args.spec,
            body=_body(args) if args.body_file else None,
            out_dir=args.out,
            red=not args.no_red,
            red_in_place=args.red_in_place,
            pass_env=args.pass_env or (),
            changed=changed,
        )
        return _print_test_results(ev, notes, args.out)

    if not args.watch:
        return once()
    out = Path(args.out).resolve()
    exclude = out.relative_to(Path.cwd().resolve()).as_posix() if out.is_relative_to(Path.cwd().resolve()) else None

    def announce() -> None:
        print(f"\n--- {dt.datetime.now():%H:%M:%S} aidd test --changed ---")
        try:
            once()
        except (ValueError, OSError, LookupError, gitutil.GitError, RuntimeError) as exc:
            print(f"aidd: {exc}", file=sys.stderr)  # keep watching: the next save may fix it
        print(f"watching for changes every {args.interval:g}s; Ctrl-C to stop")

    return runner.watch(announce, interval=args.interval, exclude=exclude)


def _merge_group_base(base: str | None) -> str:
    """In a merge_group run: the commit the queue entry was built on, computed as the gate computes it."""
    from . import github

    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise ValueError("--merge-group reads the merge_group event from GITHUB_EVENT_PATH; run it in a merge_group workflow")
    group = github.merge_group_of(json.loads(Path(path).read_text(encoding="utf-8")))
    if group is None:
        raise ValueError("--merge-group: this event is not a merge_group event")
    head = gitutil.rev_parse("HEAD")
    if head != group.sha:
        raise ValueError(f"--merge-group: the checkout is {head[:12]}, not the merge-group commit {group.sha[:12]}")
    parent, stacked = github.queue_parent(".", head, group.named_parent, gitutil.rev_parse(base or f"origin/{group.base_ref}"))
    print(f"merge queue: pull request #{group.number}, built on {parent[:12]}" + (" (a previous queue entry)" if stacked else ""))
    return parent


def _print_test_results(ev: dict, notes: list[str], out: str) -> int:
    bad = False
    for r in ev["results"]:
        good = (r["phase"] == "green" and r["status"] == "passed") or (r["phase"] == "red" and red_ok(r))
        bad |= not good
        print(f"[{'ok' if good else '!!'}] {r['phase']:5} {r['name']}: {r['status']} (exit {r['exit']}) log {_repo_relative(Path(out) / r.get('log', ''))}")
    for n in notes:
        print(f"note: {n}")
    partial = " (partial: the gate does not accept it)" if ev.get("partial") else ""
    print(f"evidence: {_repo_relative(Path(out) / 'evidence.json')}  head {ev['head_sha'][:12]}  base {ev['base_sha'][:12]}{partial}")
    return 1 if bad else 0


def cmd_gate(args) -> int:
    if args.explain:
        from . import rulebook

        print(rulebook.explain(args.explain))
        return 0
    if args.platform == "github":
        from . import github

        return github.gate(dry_run=args.dry_run, events_out=args.events, record_out=args.record, resolve_only=args.resolve, mode=args.mode)
    if args.platform == "gitlab":
        from . import gitlab

        return gitlab.gate(
            dry_run=args.dry_run,
            evidence_path=args.evidence,
            events_out=args.events,
            record_out=args.record,
            pending_fails=not args.pending_ok,
            post=args.post_status,
            mode=args.mode,
        )
    if args.context:
        ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    else:
        _enter_repo(args, "spec", file_attrs=("body_file", "approvals", "evidence", "record", "events"))
        ctx = localctx.build(base=args.base, body=_body(args), approvals=args.approvals, evidence=args.evidence, run_policy=not args.no_policy)
    d = verify(ctx)
    if args.record:
        from . import changerecord

        Path(args.record).write_text(json.dumps(d.record, indent=2) + "\n", encoding="utf-8")
        # The agent change record: an in-toto statement of this decision, next to the gate record.
        changerecord.write(d, ctx if isinstance(ctx, dict) else {}, args.record)
    if args.events:
        with open(args.events, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.event(d, ctx.get("repo") if isinstance(ctx, dict) else None)) + "\n")
    print(report.markdown(d) if args.markdown else report.text(d))
    if not args.markdown and not args.context and d.record.get("required_route"):
        # Locally, the route the gate computed from the real diff, and why: the entry rule, checked.
        print(f"  computed route {d.record['required_route']} ({rules.LANES.get(d.record['required_route'], '?')} lane) from the diff, because:")
        for line in rules.reason_lines({"reasons": d.record.get("route_reasons") or []}):
            print(f"    - {line}")
    return EXIT[d.decision]


def cmd_observe(args) -> int:
    """Run a Spec's observe command once, or poll it for the window (--window); --write records outcome.observe_result. Never rolls back."""
    _enter_repo(args, "spec")
    path = Path(args.spec)
    text = path.read_text(encoding="utf-8")
    data, _ = model.split_front_matter(text, args.spec)
    obs = data.get("observe")
    if not obs:
        raise ValueError(f"{args.spec} has no observe block")
    cfg = _config_or_none()
    command = obs.get("command") or (cfg.observe_command if cfg else None)
    print(f"window: {obs['window']}  rollback trigger: {obs['rollback_trigger']}")
    if obs.get("signals"):
        print(f"signals: {obs['signals']}")
    if not command:
        print("no observe command: a human watches the signals for the window")
        if args.window:
            print("error: --window polls the observe command; set observe.command in the Spec or the config", file=sys.stderr)
            return 2
        return 0
    from .util import run_bounded, scrub_credentials

    # The command may come from the Spec, which the change wrote, and runs where release credentials
    # live: it sees none of them unless the operator passes one by name.
    env = {
        **scrub_credentials(dict(os.environ), keep=args.pass_env or ()),
        "AIDD_SPEC_ID": str(data.get("id")),
        "AIDD_WINDOW": obs["window"],
        "AIDD_ROLLBACK_TRIGGER": obs["rollback_trigger"],
    }

    def check() -> int | None:
        # A timeout kills the command's whole process group, so a watcher it started cannot linger.
        code, _, _ = run_bounded(command, env=env, timeout=args.timeout, capture=False)
        return code

    if args.window:
        from . import observe

        length = obs["window"] if args.window == "spec" else args.window
        window_s, every_s = observe.seconds(length), observe.seconds(args.every)
        print(f"watching for {length}: the observe command every {args.every}; the trigger fires after {args.consecutive} failed check(s) in a row")
        # A check that timed out counts as unhealthy (124, as timeout(1) reports it).
        w = observe.watch_window(lambda: 124 if (c := check()) is None else c, window_s=window_s, every_s=every_s, consecutive=args.consecutive)
        result = w.result
        if result == "pass":
            print(f"observe: pass: the {length} window ended after {w.checks} check(s), {w.failures} unhealthy; the rollback trigger never fired")
        else:
            print(f"observe: ROLLBACK TRIGGER FIRED after {w.checks} check(s): {obs['rollback_trigger']}")
            print("aidd never rolls back: run your rollback now, then record it (outcome.rolled_back) and go to Learn")
    else:
        code = check()
        result = "pass" if code == 0 else "fail"
        print(f"observe: {result} (exit {code})" + ("" if result == "pass" else f"; if this persists, roll back: {obs['rollback_trigger']}"))
    if args.write:
        path.write_text(model.set_outcome(text, "observe_result", result), encoding="utf-8")
        print(f"wrote outcome.observe_result = {result!r} to {path}")
    return 0 if result == "pass" else 1


def cmd_watch(args) -> int:
    """Judge a metric series against its control band; with --write, turn a breach into a draft Spec to triage."""
    from . import bands

    series = Path(args.series).resolve()
    _enter_repo(args)
    band = bands.band_from_config(_config_or_none(), args.metric)
    band = bands.Band(
        band.metric,
        args.window or band.window,
        args.diagnose_sigma or band.diagnose_sigma,
        args.propose_sigma or band.propose_sigma,
    )
    reading = bands.assess(bands.load_series(series), band)
    breach = reading.tier in ("diagnose", "propose")
    written = None
    if breach and args.write:
        cfg = _config_or_none()
        spec_id = args.write if args.write != "auto" else f"OBS-{args.metric}-{dt.date.today():%Y%m%d}".replace("_", "-")
        written = repo.new_object(
            Path("."),
            kind="spec",
            id=spec_id,
            title=f"{args.metric} breached its control band ({reading.tier})",
            route="normal",
            ctype="fix",
            owner_team=(cfg.get("owners", "default_team", default="") if cfg else ""),
            specs_dir=cfg.specs_dir if cfg else "specs",
        )
        text = written.read_text(encoding="utf-8")
        head, sep, body = text.partition("\n+++\n")
        written.write_text(head + sep + "\n" + bands.intent_text(reading, series.name, cfg.get("goal") if cfg else None) + body, encoding="utf-8")
    if args.json:
        print(json.dumps(reading.as_dict() | {"spec": str(written) if written else None}, indent=2))
    else:
        print(f"{reading.metric}: {reading.tier}" + (f" ({reading.note})" if reading.note else f", {reading.sigma} sigma"))
        for rule in reading.rules:
            print(f"  rule {rule}")
        if written:
            print(f"wrote {written}: a draft Spec for the service owner to triage")
    return 1 if breach else 0


def cmd_proposal(args) -> int:
    """Render a proposal's tables, or turn an accepted proposal into an Initiative and Epics."""
    from . import proposal

    _enter_repo(args, file_attrs=("file",))
    try:
        data = proposal.load(Path(args.file))
    except (model.ModelError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2  # bad input: a missing file, or one that is not a valid proposal
    if args.action == "matrix":
        print(proposal.matrix(data), end="")
        return 0
    cfg = _config_or_none()
    try:
        written = proposal.convert(data, Path(cfg.specs_dir if cfg else "specs"), cfg.get("owners", "default_team", default="") if cfg else "")
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote    {path.as_posix()}")
    print("next: the product manager ranks the Epics and writes Spec stubs under them (`/aidd-team:plan`)")
    return 0


def cmd_log(args) -> int:
    """One Spec's history: status transitions, approvals, and Assisted-by trailers."""
    from . import speclog

    records = [str(Path(r).resolve()) for r in args.record or []]  # before entering the root: relative to where it ran
    _enter_repo(args, *(("spec",) if args.spec.endswith(".md") else ()))
    log = speclog.build(Path("."), args.spec, records)
    print(json.dumps(log, indent=2) if args.json else speclog.markdown(log), end="\n" if args.json else "")
    return 0


def _next_filters(args):
    from . import nextstep

    return nextstep.Filters(all=args.all, mine=args.mine, agent=args.agent, blocked=args.blocked, waiting_on_me=args.waiting_on_me, label=args.label)


def cmd_next(args) -> int:
    """What to do now in this repository, and who does it."""
    from . import nextstep

    if not args.repos:
        _enter_repo(args)
        steps = nextstep.plan(Path("."), filters=_next_filters(args))
        print(json.dumps(steps, indent=2) if args.json else nextstep.markdown(steps), end="" if not args.json else "\n")
        return 0
    # A project in several repositories: each one answers for itself, from its own root.
    everything: dict[str, list[dict]] = {}
    here = os.getcwd()
    for path in args.repos:
        top = gitutil.toplevel(path) if Path(path).is_dir() else ""
        if not top:
            everything[path] = [nextstep._step(f"{path} is not a git repository", nextstep.YOU, "check the path")]
            continue
        os.chdir(top)
        try:
            everything[path] = nextstep.plan(Path(top), filters=_next_filters(args))
        finally:
            os.chdir(here)
    if args.json:
        print(json.dumps(everything, indent=2))
    else:
        print("\n".join(f"## {path}\n\n{nextstep.markdown(steps)}" for path, steps in everything.items()), end="")
    return 0


def cmd_owners(args) -> int:
    """Who decides and who does the work: the humans who approve and every agent role, with the team's goal."""
    from . import owners

    _enter_repo(args)
    r = owners.build(_config_or_none(), changed=args.changed)
    # The JSON carries the version of its shape (schemas/owners.schema.json), like `aidd metrics --json`.
    print(json.dumps({"schema_version": OWNERS_SCHEMA_VERSION} | r, indent=2) if args.json else owners.markdown(r))
    return 0


def cmd_mcp(args) -> int:
    from . import mcp

    top = gitutil.toplevel()
    return mcp.serve(root=top or os.getcwd())


def cmd_hook(args) -> int:
    if args.event == "pre-edit":
        from . import guard

        return guard.pre_edit_hook()
    from . import hooks

    return hooks.run(args.event)


def cmd_gen_docs(args) -> int:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("gen-docs maintains the aidd source repository; run it from a source checkout")
    stale = docs.gen_docs(root, check=args.check)
    for p in stale:
        print(("stale: " if args.check else "updated: ") + str(p.relative_to(root)))
    if args.check and stale:
        print("run `aidd gen-docs` and commit the result")
        return 1
    return 0


def cmd_eval(args) -> int:
    root = Path(args.root) if args.root else (resources.repo_root() or Path("."))
    if args.suite == "report":
        if not args.paths:
            raise ValueError("report reads the JSON-lines files written with --record: aidd eval report evals-results.jsonl")
        print(evals.report_markdown(evals.load_records([Path(x) for x in args.paths])))
        return 0
    if args.paths:
        raise ValueError(f"unexpected arguments {' '.join(args.paths)!r}: only `aidd eval report` takes files")
    if args.suite in ("examples", "standards") and (args.repeat != 1 or args.control or args.record or args.model_label):
        raise ValueError("--repeat, --control, --record, and --model-label measure an agent: use them with routing, roles, or tasks")
    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1")
    if args.suite == "examples":
        if not (root / "examples").is_dir():
            raise RuntimeError(f"no examples/ under {root}; pass --root <aidd source checkout>")
        if args.materialize:
            n = evals.materialize(root, Path(args.materialize))
            print(f"wrote {n} resolved cases to {args.materialize}")
            return 0
        results = evals.run_examples(root)
        for r in results:
            print(f"[{'ok' if r['ok'] else '!!'}] {r['case']}: got {r['got']}" + ("" if r["ok"] else f" want {r['want']}"))
        return 0 if all(r["ok"] for r in results) else 1
    if args.suite == "standards":
        today = dt.date.today()
        stale = evals.stale_standards(today, args.max_days)
        for s in stale:
            print(f"[!!] {s['where']}: {docs.standard_text(s)} {'checked' if s.get('checked') else 'reviewed'} {evals.dated(s)}, {s['age_days']} days ago")
        entries = evals.standards()
        emerging = sum(1 for s in entries if s.get("maturity") == "emerging")
        print(f"{len(entries)} standards ({emerging} marked emerging); {len(stale)} not checked within {args.max_days} days")
        for day, count in evals.bulk_checked_dates():
            print(f"warning: {count} entries share the checked date {day}; one bulk edit is not {count} confirmations, so re-check them per source")
        unsourced = evals.unsourced_standards()
        for s in unsourced:
            print(f"[!!] {s['id']}: names edition {s['edition']!r} but no source to check it against")
        unevidenced = evals.unevidenced_standards()
        for s in unevidenced:
            print(f"[!!] {s['id']}: checked {s['checked']} with no source and evidence; add what was read, or mark a practice `reviewed`")
        unpinned = evals.unpinned_extensions()
        for x in unpinned:
            print(f"[!!] {x['where']}: {x['name']} ({x['kind']}) has no {' and no '.join(x['missing'])}")
        return 0 if not stale and not unsourced and not unevidenced and not unpinned else 1
    if not args.cmd:
        raise ValueError(f'--cmd is required for the {args.suite} suite, for example --cmd "claude -p"')
    words = split_command(args.cmd)
    if not words:
        raise ValueError("--cmd is empty")
    if shutil.which(words[0]) is None:
        raise RuntimeError(f"cannot run {words[0]!r}: not found on PATH")
    if args.suite == "tasks":
        return _eval_tasks(args)
    scenarios = Path(args.scenarios) if args.scenarios else root / "evals" / args.suite
    if not evals.load_scenarios(scenarios):
        raise RuntimeError(f"no scenarios in {scenarios}; pass --scenarios <dir> (they ship in the source repository)")
    if args.suite == "roles":
        return _measure(
            args,
            lambda material: evals.run_roles(scenarios, args.cmd, material=material),
            lambda r: f"{r['id']} ({r['role']})" + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
            noun="scenario(s)",
            metric="passed",
        )
    return _measure(
        args,
        lambda material: evals.run_routing(scenarios, args.cmd, embed=not args.no_embed, material=material),
        lambda r: f"{r['id']}: want {r['want']}, got {r['got']}  {r['reason']}",
        noun="scenario(s)",
        metric="accuracy",
        options={"embed": not args.no_embed},
    )


def _eval_tasks(args) -> int:
    """Your own agent configuration on your own tasks: the repository is --root or the current directory, never aidd's source."""
    repo = Path(args.root or ".").resolve()
    scenarios = Path(args.scenarios) if args.scenarios else repo / "evals" / "tasks"
    tasks = evals.load_scenarios(scenarios) if scenarios.is_dir() else []
    if not tasks:
        template = resources.data_dir("templates") / "evals"
        raise RuntimeError(
            f"no tasks in {scenarios}; start from the template: mkdir -p {scenarios.parent} && cp -R {template}/tasks {scenarios} ({template}/README.md says how)"
        )
    return _measure(
        args,
        lambda material: evals.run_tasks(scenarios, args.cmd, repo=repo),
        lambda r: r["id"] + ("" if r["ok"] else ": " + "; ".join(r["misses"])),
        noun="task(s)",
        metric="passed",
        control=False,
    )


def _measure(args, run, detail, *, noun: str, metric: str, control: bool = True, options: dict | None = None) -> int:
    """Run an agent suite --repeat times (and again without the aidd material for --control), print it, record it, and gate on mean pass@1.

    `run(material)` is one trial of every scenario. The control only reports: it never decides the exit code.
    """
    k = args.repeat
    results = evals.measure(lambda: run(True), k)
    for r in results:
        mark = "ok" if r["pass_all"] else ("~~" if r["passed"] else "!!")
        print(f"[{mark}] {detail(r)}" + (f"  (passed {r['passed']}/{k})" if k > 1 else ""))
    stats = evals.summary(results)
    mean = stats["mean_pass_at_1"]
    if k == 1:
        print(f"{metric} {mean:.1%} over {len(results)} {noun}; threshold {args.min_accuracy:.0%}")
    else:
        print(
            f"mean pass@1 {mean:.1%} over {len(results)} {noun}, {k} trials each; pass^{k} {stats['pass_k_share']:.1%}; "
            f"threshold {args.min_accuracy:.0%} on mean pass@1"
        )
    judged = [r for r in results if r.get("judgment")]
    if judged:
        label = metric if k == 1 else "mean pass@1"
        print(f"judgment-only {label} {sum(r['pass_at_1'] for r in judged) / len(judged):.1%} over {len(judged)} scenario(s)")
    baseline = None
    if args.control and not control:
        print("control: not applicable to tasks; a task carries no instructions of its own, the repository's configuration is the agent's material")
    elif args.control:
        baseline = evals.measure(lambda: run(False), k)
        base = evals.summary(baseline)["mean_pass_at_1"]
        print(f"control without the aidd material: mean pass@1 {base:.1%}; lift {(mean - base) * 100:+.1f} points (reported, never gating)")
    if args.record:
        line = evals.record_line(
            suite=args.suite,
            cmd=args.cmd,
            model=args.model_label,
            repeat=k,
            results=results,
            threshold=args.min_accuracy,
            control=baseline,
            options=options,
        )
        evals.append_record(Path(args.record), line)
        print(f"recorded to {args.record}")
    return 0 if mean >= args.min_accuracy else 1


def cmd_metrics(args) -> int:
    if args.guard:
        if args.guard == GUARD_LOG_DEFAULT:
            # The hook keeps its log at the repository's top level, wherever this runs from.
            try:
                args.guard = str(Path(gitutil.toplevel(check=True)) / GUARD_LOG_DEFAULT)
            except (gitutil.GitError, OSError):
                pass
        counts = metrics.guard_denials(metrics.load([args.guard], since=args.since) if Path(args.guard).is_file() else [])
        print(json.dumps(counts, indent=2) if args.json else metrics.guard_markdown(counts, args.guard), end="\n" if args.json else "")
        return 0
    if not args.events:
        raise ValueError("metrics needs one or more event files, or --guard [PATH]")
    if args.propose and not args.autonomy:
        raise ValueError("--propose goes with --autonomy")
    if args.cost and (args.by or args.dora or args.autonomy):
        raise ValueError("--cost goes with the summary, not with --by, --dora, or --autonomy")
    events = metrics.load(args.events, since=args.since)
    if args.tenant:
        events = [e for e in events if e.get("tenant") == args.tenant]
    cfg = _config_or_none()
    targets = cfg.get("targets", default={}) if cfg else {}
    if args.by:
        groups = metrics.grouped(events, args.by, args.target_wait, targets)
        print(json.dumps(groups, indent=2) if args.json else metrics.markdown_grouped(groups, args.by))
        return 0
    if args.dora:
        rows = metrics.dora(events, Path(args.specs) if args.specs else None, targets)
        print(json.dumps(rows, indent=2) if args.json else metrics.dora_markdown(rows), end="" if not args.json else "\n")
        return 1 if any(r["met"] is False for r in rows) else 0
    if args.autonomy:
        rows = metrics.autonomy(events, **(cfg.get("agents", "autonomy", default={}) if cfg else {}))
        if args.propose:
            proposals = metrics.propose_standard_changes(events, rows, TYPES)
            out = {"schema_version": metrics.SCHEMA_VERSION, "proposals": proposals}
            print(json.dumps(out, indent=2) if args.json else metrics.proposals_text(proposals), end="\n" if args.json else "")
            return 0
        print(json.dumps(rows, indent=2) if args.json else metrics.autonomy_markdown(rows))
        return 0
    s = metrics.summarize(events, args.target_wait, targets)
    if args.specs:
        s |= metrics.delivery_outcomes(Path(args.specs))
    if args.cost:
        s["cost"] = metrics.cost(events, metrics.load_ledger(args.cost, since=args.since), targets, s["first_pass_share"])
    if args.render:
        renderers = ext.installed("aidd.renderers")
        if args.render not in renderers:
            raise ValueError(f"no renderer {args.render!r}; installed: {', '.join(sorted(renderers)) or 'none'}")
        print(renderers[args.render](s), end="")
    else:
        print(json.dumps(s, indent=2) if args.json else metrics.markdown(s))
    # A missed loop-speed target fails the run, like a DORA target; cost is display only and never sets the exit code.
    return 1 if any(r["met"] is False for r in s["loop_speed"]) else 0


def cmd_export(args) -> int:
    """Gate records or events as JSON or CSV (or an installed exporter's format), the same bytes for the same inputs."""
    from . import export

    items = export.collect(args.kind, args.paths, since=args.since, tenant=args.tenant)
    out = export.render(args.kind, items, args.format)
    if not args.out:
        if isinstance(out, bytes):
            sys.stdout.buffer.write(out)
        else:
            sys.stdout.write(out)
        return 0
    path = Path(args.out) / f"{args.kind}.{args.format}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(out, bytes):
        path.write_bytes(out)
    else:
        path.write_text(out, encoding="utf-8", newline="\n")
    print(f"wrote {path} ({len(items)} {args.kind})")
    return 0


def _default_branch(root: str) -> str:
    """The origin's default branch (`refs/remotes/origin/HEAD`), or main."""
    try:
        head = gitutil.run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], root, check=False).strip()
    except (gitutil.GitError, OSError):
        head = ""
    return head.removeprefix("origin/") or "main"


def cmd_verify(args) -> int:
    """Check an agent change record: its shape, subject, tenant, decision, and approvals, then its signature."""
    from . import changerecord

    path = changerecord.find(args.target, args.dir)
    try:
        stmt = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"aidd verify: {path}: not JSON ({exc})")
        return 1
    sha = args.target.lower() if not Path(args.target).is_file() else args.sha
    problems = changerecord.check(stmt, sha=sha, tenant=args.tenant)
    signature = "unsigned"
    if not problems and (args.bundle or args.online):
        from . import github

        pred = stmt["predicate"]
        # The repository comes from the verifier, never from the record: a record names whatever repository its writer chose.
        repo = args.repo or github.origin_repo(".") or ""
        if not repo:
            problems.append("the signature needs the GitHub repository: pass --repo owner/name (there is no github.com origin remote here)")
        elif pred.get("platform") != "github" or pred.get("repo") != repo:
            problems.append(f"the record names the {pred.get('platform')} repository {pred.get('repo')!r}, not {repo}")
        else:
            branch = args.default_branch or _default_branch(".")
            why = changerecord.verify_signature(path, stmt, repo=repo, bundle=args.bundle, signer_workflow=args.signer_workflow, default_branch=branch)
            if why:
                problems.append(f"signature: {why}")
            else:
                signature = "signed"
    head = (stmt.get("predicate") or {}).get("head_sha") if isinstance(stmt, dict) and isinstance(stmt.get("predicate"), dict) else None
    print(f"aidd verify: {path}  head {str(head)[:12]}  signature {signature}")
    for p in problems:
        print(f"  [FAIL] {p}")
    if problems:
        return 1
    if signature == "unsigned":
        print(
            "  unsigned: nothing proves who wrote this file; pass --bundle or --online to check its attestation"
            + ("" if args.allow_unsigned else ", or --allow-unsigned")
        )
        return 0 if args.allow_unsigned else 1
    print("  verified: the record is signed, names the head, passed, and humans approved")
    return 0


def build_parser(*, plugins: bool = False) -> argparse.ArgumentParser:
    """The CLI. With `plugins`, installed `aidd.commands` extensions add their subcommands, unless discovery is sealed;
    `main` asks for them only when the command it runs is not one of ext.PROTECTED."""
    p = argparse.ArgumentParser(prog="aidd", description="aidd: route, prove, and gate AI-driven change.", epilog=EPILOG, formatter_class=_Help)
    p.add_argument("--version", action="version", version=f"aidd {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def cmd(name: str, help_text: str, func) -> argparse.ArgumentParser:
        s = sub.add_parser(name, help=help_text, description=help_text, formatter_class=_Help)
        s.set_defaults(func=func)
        return s

    def flag(parser, name: str, help_text: str) -> None:
        parser.add_argument(name, action="store_true", help=help_text)

    base_help = "base branch to compare against (default: origin/HEAD, then origin/main, origin/master, main, master)"

    s = cmd("init", "adopt aidd in a repository", cmd_init)
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--dry-run", "print what init finds (stacks, tests, sensitive areas, owners, CI) and the config it proposes; write nothing")
    s.add_argument("--profile", choices=resources.profiles()["order"], default="team", help="gate strictness")
    s.add_argument("--ci", choices=["github", "gitlab", "none"], default="github", help="CI templates to install")
    s.add_argument(
        "--ref",
        metavar="SHA_OR_TAG",
        help="pin the CI files' aidd action and workflow to this commit SHA or release tag (default: the commit this aidd runs "
        "from, when it is a git checkout)",
    )
    s.add_argument("--approvers", nargs="+", metavar="WHO", help="owners.approvers, such as @org/team")
    s.add_argument("--reviewer", action="append", metavar="POOL=WHO", help="a specialist pool, such as security=@org/security (repeatable)")
    s.add_argument("--test", metavar="COMMAND", help='the repository suite, such as "npm test"')
    s.add_argument("--goal", metavar="SENTENCE", help='the goal every agent steers by, such as "make onboarding succeed on the first try"')
    flag(s, "--team", "also install the aidd-team roles: Claude Code agents, commands, and domain-pack skills, and an AGENTS.md section for other harnesses")
    hooks = s.add_mutually_exclusive_group()
    flag(
        hooks,
        "--agent-hooks",
        "wire Claude Code's edit-time guard hook (.claude/settings.json) and the aidd MCP server (.mcp.json) even when Claude Code is not detected",
    )
    flag(hooks, "--no-agent-hooks", "do not wire the hook and the MCP server even when Claude Code is detected")
    s.add_argument(
        "--harness",
        action="append",
        choices=[*repo.HARNESSES, "none"],
        metavar="AGENT",
        help="the coding agents to wire instead of detecting them: " + ", ".join(repo.HARNESSES) + ", or none (repeatable)",
    )
    flag(s, "--claude-plugins", "install the aidd plugins for this user through the `claude` CLI instead of repository files for Claude Code")
    flag(s, "--enforce", "install the gate in enforce mode; by default it starts advisory, reporting on 'aidd/gate (advisory)' without blocking")
    s.add_argument("--policy", metavar="COMMAND", help='policy.command, such as "./scripts/aidd-policy" (org and regulated need one)')
    flag(
        s,
        "--devcontainer",
        "also write .devcontainer/: a dev container for agents that denies outbound traffic except to an allow-list (a starting point; aidd sandboxes nothing)",
    )
    s.add_argument("--link", action="append", metavar="DIR", help="extra agent skill directory to link, besides .claude/skills (repeatable)")
    flag(s, "--no-skill", "do not vendor the skill (agents load the plugin instead)")
    flag(s, "--force", "overwrite existing files and upgrade the vendored skill")

    s = cmd(
        "upgrade",
        "bring a repository's aidd files up to this aidd: the skill, the team files, the CI pins, and aidd_version; a dry run unless --yes",
        cmd_upgrade,
    )
    s.add_argument("path", nargs="?", default=".", help="repository root")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files to this aidd commit or release; default: this aidd's")
    flag(s, "--yes", "make the changes")

    s = cmd("uninstall", "reverse `aidd init`: list what it would remove, or remove it with --yes", cmd_uninstall)
    s.add_argument("path", nargs="?", default=".", help="the repository (default: the current directory)")
    flag(s, "--yes", "remove the files; without it, only list them")
    s.add_argument("--link", action="append", metavar="DIR", help="extra skill link directories given to `aidd init --link` (repeatable)")

    s = cmd("doctor", "check that a repository is wired correctly", cmd_doctor)
    s.add_argument("path", nargs="?", default=".", help="repository root")

    s = cmd("new", "create a Spec, Epic, Initiative, Proposal, runbook, or postmortem from the template", cmd_new)
    s.add_argument("kind", choices=["spec", "epic", "initiative", "proposal", "runbook", "postmortem"])
    s.add_argument("id", help="such as SPEC-42")
    s.add_argument("--title", required=True)
    s.add_argument(
        "--route",
        choices=["normal", "major", "emergency"],
        help="a Spec is normal (the default; the gate raises it when needed), major, or an emergency backfill; with --paths, the "
        "computed route wins when it is higher",
    )
    s.add_argument("--type", default="feat", choices=TYPES, help="the change type")
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="spec: the paths or globs the change will touch; computes the route (and says when no Spec is needed) and writes them as the Task's scope",
    )
    s.add_argument("--dimension", action="append", choices=DIMENSIONS, help="spec: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "spec: a revert would not restore the prior state (forces major)")
    flag(s, "--force", "spec: write a Spec even when the paths are on the fast lane")
    flag(
        s,
        "--full",
        "spec: every section (Problem, Goals, Alternatives, cross-cutting concerns, Pre-mortem); by default a normal Spec is "
        "the short one (Intent, Acceptance, Design, Rollback), and a major Spec is full",
    )
    s.add_argument("--owner-team", default="", help="default: owners.default_team from the config")
    s.add_argument("--parent", default="", help="parent Epic or Initiative id")
    s.add_argument("--audience", default="client", choices=["client", "internal"], help="a proposal's audience: a client, or the company's own decision makers")
    s.add_argument("--addressee", default="", help='who receives a proposal and decides, such as "Acme Corp" or "the executive committee"')
    s.add_argument("--spec", default="", help="a postmortem's Spec id: the Spec that carries the fix")

    s = cmd(
        "import",
        "write a short Spec from another planning tool's files (Spec Kit, OpenSpec, Kiro, BMAD): Intent, Acceptance ids, "
        "Tasks with the paths it names, and the computed route; it links the plan instead of copying it",
        cmd_import,
    )
    s.add_argument("tool", choices=["speckit", "openspec", "kiro", "bmad"])
    s.add_argument(
        "path",
        help="Spec Kit: specs/NNN-feature/; OpenSpec: openspec/changes/<change>/; Kiro: .kiro/specs/<feature>/; BMAD: one story file",
    )
    s.add_argument("--id", metavar="ID", help="the Spec id (default: SPEC-<n>, one past the highest in the Specs folder)")
    s.add_argument("--out", metavar="DIR", help="where to write it (default: the config's Specs folder)")
    s.add_argument("--title", help="the Spec's title (default: the source's)")
    s.add_argument("--type", choices=TYPES, help="the change type (default: feat; fix for a Kiro bugfix spec)")

    s = cmd("validate", "validate files or directories; with none, the whole repository, including overdue emergency reviews", cmd_validate)
    s.add_argument("paths", nargs="*", help="config .toml files, object .md files, or directories")

    s = cmd("hash", "print the approval hash of a Spec and its frozen test and design files", cmd_hash)
    s.add_argument("spec", help="path to the Spec file")
    s.add_argument("--ref", default="HEAD", help="commit to hash; the gate hashes the PR head")
    flag(s, "--worktree", "hash the working tree instead of a commit")
    flag(s, "--comment", "print the full approval comment line")
    flag(
        s,
        "--digest",
        "print a phone-sized digest of what the hash approves first (intent, Acceptance ids and text, scope, risk, rollback, "
        "frozen test files), at most 25 lines, ending with the hash or, with --comment, the approval line",
    )

    s = cmd("change", "print a starting toml aidd block for the current branch", cmd_change)
    s.add_argument("--base", help=base_help)
    s.add_argument("--type", choices=TYPES, help="the change type (default: docs for doc-only diffs, else feat)")

    s = cmd("test", "run the tests (green on head, red on base) and write evidence", cmd_test)
    s.add_argument("--base", help=base_help)
    s.add_argument("--spec", help="the Spec whose tests to run (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="PR/MR description holding the toml aidd block")
    s.add_argument("--out", default="aidd-evidence", help="where evidence.json and logs go")
    flag(s, "--no-red", "skip red runs (the gate will still require them)")
    flag(s, "--red-in-place", "CI only: run red in this checkout, keeping installed dependencies")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)
    flag(
        s,
        "--changed",
        "local: run only the commands the working tree's changes against the base select (a matching when_changed, a Spec command when "
        "a path is in a Task's scope or its test files, a config command without when_changed), green only; the evidence is marked partial "
        "and the gate never accepts it",
    )
    flag(s, "--watch", "local: run --changed now and again whenever a file changes, until Ctrl-C (exit 0)")
    s.add_argument("--interval", type=float, default=1.0, metavar="SECONDS", help="--watch: how often to look for changes")
    flag(s, "--merge-group", "CI, in a merge_group run: test the merge-group commit against the commit the queue entry was built on (as the gate computes it)")

    s = cmd("gate", "run every gate rule: locally as a preflight, in CI for a platform, or against any context", cmd_gate)
    s.add_argument("platform", nargs="?", choices=["github", "gitlab"], help="CI entry point: gather a trusted context and report aidd/gate")
    s.add_argument("--context", help="context.json from any CI adapter (schemas/context.schema.json)")
    s.add_argument("--base", help=base_help)
    s.add_argument("--spec", help="local: the Spec this change implements (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="local: PR/MR description holding the toml aidd block")
    s.add_argument("--approvals", help='local: JSON for dry runs, {"reviews": [...], "comments": [...]}')
    s.add_argument("--evidence", default="aidd-evidence/evidence.json", help="local and GitLab: evidence from `aidd test`")
    flag(s, "--no-policy", "local: do not run the Policy command")
    flag(s, "--markdown", "print the PR summary instead of text")
    s.add_argument(
        "--mode",
        choices=["enforce", "advisory"],
        help="CI: advisory reports on 'aidd/gate (advisory)' and never blocks. The base branch's config `mode` wins; on GitLab this flag and AIDD_MODE cannot relax the gate (default: enforce)",
    )
    flag(s, "--dry-run", "CI: verify without posting a status")
    flag(s, "--pending-ok", "GitLab: exit 0 while approvals are pending")
    flag(s, "--post-status", "GitLab: also post an external status (needs an api-scope token)")
    flag(s, "--resolve", "GitHub: only print the pull request numbers this event concerns")
    s.add_argument("--record", metavar="PATH", help="write the derived change record here")
    s.add_argument("--events", metavar="PATH", help="append one gate event (a JSON line) here")
    s.add_argument("--explain", metavar="RULE", help="print what a rule checks and how to satisfy it, then exit")

    s = cmd("metrics", "summarize gate events", cmd_metrics)
    s.add_argument("--tenant", metavar="TENANT", help="only the events of this tenant (the `tenant` their config names)")
    s.add_argument("events", nargs="*", help="JSON-lines files written with --events, from any number of repositories")
    s.add_argument(
        "--guard",
        nargs="?",
        const=GUARD_LOG_DEFAULT,
        metavar="PATH",
        help="count the edit-time guard's denials by reason and by role, from the log `aidd hook pre-edit` keeps (default .aidd/work/guard.jsonl at the repository's top level)",
    )
    s.add_argument("--since", metavar="DATE", help="only events at or after this ISO date or time, such as the last retrospective")
    s.add_argument(
        "--by",
        choices=list(metrics.GROUPS),
        help="one summary per repo, owner (organization or company), team (the Spec's owner_team), profile, route, or author",
    )
    s.add_argument(
        "--target-wait", type=float, metavar="MINUTES", help="name the approvals and checks whose median wait is above this many minutes (a day is 1440)"
    )
    flag(s, "--autonomy", "gradual release: per agent and change type, how its changes fared and the stage of autonomy the evidence supports")
    flag(s, "--dora", "the five DORA software delivery metrics against the [targets] in the config; exit 1 when one misses")
    s.add_argument("--specs", metavar="DIR", help="add the change failure rate and days to restore from the Specs' outcome (DORA stability)")
    s.add_argument(
        "--cost",
        metavar="LEDGER",
        help="join a host-exported cost ledger (JSON lines: ts, amount, currency, agent, spec, branch, sha) to the changes; display only, never a gate",
    )
    flag(s, "--propose", "with --autonomy: print a [[standard_changes]] entry for each class that meets the thresholds, for a person to merge")
    s.add_argument("--render", metavar="NAME", help="print the summary with an installed aidd.renderers extension instead")
    flag(s, "--json", "print JSON")

    s = cmd(
        "eval",
        "run the example suite, an agent routing eval, the role evals, the standards currency check, or your own agent tasks; report recorded runs",
        cmd_eval,
    )
    s.add_argument("suite", choices=["examples", "routing", "roles", "standards", "tasks", "report"])
    s.add_argument("paths", nargs="*", metavar="PATH", help="report: JSON-lines files written with --record, printed as one markdown table")
    s.add_argument(
        "--root", help="examples, routing, roles: the aidd source checkout (default: this installation's source, if any); tasks: your repository (default: .)"
    )
    s.add_argument("--scenarios", help="directory of scenario .toml files")
    s.add_argument("--cmd", help='agent command that reads a prompt on stdin, such as "claude -p"')
    flag(s, "--no-embed", "routing: rely on the harness loading the skill instead of embedding routes.md")
    s.add_argument(
        "--min-accuracy", type=float, default=0.9, help="fail below this mean pass@1: the share of correct routes, passed role scenarios, or passed tasks"
    )
    s.add_argument("--repeat", type=int, default=1, metavar="K", help="routing, roles, tasks: run each scenario K times; report pass@1 and pass^K")
    flag(
        s,
        "--control",
        "routing, roles: also run every scenario without the aidd material (the skill reference, the role playbook) and report the lift; never gates",
    )
    s.add_argument("--record", metavar="PATH", help="routing, roles, tasks: append this run to a JSON-lines file (read it with `aidd eval report`)")
    s.add_argument("--model-label", metavar="TEXT", help="the model name to record with the run, as you name it (aidd never infers it)")
    s.add_argument("--max-days", type=int, default=365, help="standards: fail when an entry was last checked more than this many days ago")
    s.add_argument(
        "--materialize",
        metavar="DIR",
        help="examples: write every case and mutation as a resolved context plus its expectation, for another verifier to run",
    )

    s = cmd(
        "observe",
        "run a Spec's observe command once after release, or poll it for the observe window (--window); exit 0 healthy (the window "
        "ended with the rollback trigger never firing), 1 unhealthy (the trigger fired), 2 error. It never rolls back",
        cmd_observe,
    )
    s.add_argument("spec", help="the Spec file, such as specs/SPEC-42.md")
    s.add_argument(
        "--window",
        nargs="?",
        const="spec",
        metavar="DURATION",
        help="poll until the Spec's observe.window ends, or this long (such as 90s, 30m, 24h); stop as soon as the rollback trigger fires",
    )
    s.add_argument("--every", default="5m", metavar="DURATION", help="--window: how often to run the observe command, such as 30s or 5m")
    s.add_argument("--consecutive", type=int, default=1, metavar="N", help="--window: the rollback trigger fires after this many unhealthy checks in a row")
    flag(s, "--write", "record outcome.observe_result in the Spec (a bookkeeping field Spec approval ignores)")
    s.add_argument("--timeout", type=int, default=600, help="seconds before the command counts as failed")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)

    s = cmd("proposal", "a proposal's tables for the document you send (matrix), or an accepted proposal as an Initiative and Epics (convert)", cmd_proposal)
    s.add_argument("action", choices=["matrix", "convert"])
    s.add_argument("file", help="the proposal, such as proposals/PROP-1/proposal.md")

    s = cmd("approve", "local-first: record a person's Spec approval or Merge approval on this machine, with no platform", cmd_approve)
    s.add_argument("what", choices=["spec", "merge"])
    s.add_argument("spec", nargs="?", help="for spec: the Spec, such as specs/SPEC-1.md")

    s = cmd("ship", "local-first: merge the current branch into the base branch once the gate passes, keeping its history or squashing it", cmd_ship)
    s.add_argument("--base", help="the base branch; default: the repository's default branch")
    flag(s, "--squash", "one commit on the base branch, keeping every Assisted-by trailer")
    s.add_argument("--message", help="the merge or squash commit message; default: the Spec's title, or the newest commit's subject")
    s.add_argument("--out", default="aidd-evidence", help="where the tests ship runs on the head write their evidence and logs")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=PASS_ENV_HELP)

    s = cmd(
        "next",
        "what to do now in this repository, and who does it: you, your agent, or an Approver; it starts every change with the "
        "route and lane computed for the branch's diff",
        cmd_next,
    )
    s.add_argument("repos", nargs="*", metavar="REPO", help="the repositories of a project, such as api web infra; default: this one")
    flag(s, "--json", "print the steps as JSON")
    flag(s, "--all", "the backlog: every Spec under the Specs folder at HEAD, not only this branch's")
    flag(s, "--mine", "only Specs you added or with a Task assigned to you (git user.email/name, GitHub login)")
    s.add_argument("--agent", nargs="?", const="", metavar="ROLE", help="only Specs with a ready Task assigned to an agent (to agent:ROLE when given)")
    flag(s, "--blocked", "only blocked work: status blocked, or blocked_by unfinished work")
    flag(s, "--waiting-on-me", "the Approver inbox: approvals waiting on you, and a warning past max_open_per_approver")
    s.add_argument("--label", metavar="LABEL", help="only Specs with this label")

    s = cmd("log", "one Spec's history from git: status transitions with time in state, approvals, and Assisted-by trailers", cmd_log)
    s.add_argument("spec", help="the Spec, such as specs/SPEC-1.md or SPEC-1")
    s.add_argument(
        "--record",
        action="append",
        metavar="PATH",
        help="a gate record from `aidd gate --record` (repeatable; default aidd-evidence/record.json when it exists)",
    )
    flag(s, "--json", "print the log as JSON")

    s = cmd("owners", "who decides and who does the work: the approvers, the specialist pools, and every agent role", cmd_owners)
    flag(s, "--json", "print the owners as JSON")
    s.add_argument(
        "--changed",
        nargs="+",
        metavar="PATH",
        help="the paths the change touches: each role lists only the house standards whose when_changed matches them",
    )

    s = cmd(
        "watch",
        "judge a metric series against its control band (no model); exit 1 when an agent may diagnose or propose",
        cmd_watch,
    )
    s.add_argument("series", help="values, oldest first: JSON lines with a value field, CSV ending in the value, or one number per line")
    s.add_argument("--metric", required=True, help="the metric's name; a matching [[observe.bands]] entry sets the thresholds")
    s.add_argument("--window", type=int, help="how many recent values make the baseline (default 30)")
    s.add_argument("--diagnose-sigma", type=float, help="standard deviations at which an agent may diagnose read-only (default 2)")
    s.add_argument("--propose-sigma", type=float, help="standard deviations at which an agent may propose a change (default 3)")
    s.add_argument(
        "--write", nargs="?", const="auto", metavar="SPEC_ID", help="on a breach, write a draft Spec with the evidence (default id OBS-<metric>-<date>)"
    )
    flag(s, "--json", "print the reading as JSON")

    cmd("mcp", "serve aidd to agents as MCP tools over stdio (next, check_edit, validate, hash, change, gate)", cmd_mcp)
    s = cmd(
        "hook",
        "agent harness hooks; pre-edit reads a Claude Code PreToolUse event and denies edits outside the active Spec; session-start adds "
        "`aidd next` to a new session; stop reminds the agent to run `aidd test` (Stop and SubagentStop); pre-compact is a no-op",
        cmd_hook,
    )
    s.add_argument("event", choices=["pre-edit", "session-start", "stop", "pre-compact"])

    s = cmd("gen-docs", "maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills", cmd_gen_docs)
    flag(s, "--check", "fail when any generated block is stale")

    s = cmd("export", "export gate records or gate events as JSON or CSV, deterministically, for a log store or a spreadsheet", cmd_export)
    s.add_argument("kind", choices=["records", "events"])
    s.add_argument("paths", nargs="+", metavar="PATH", help="record files (--record) or event files (--events), or directories holding them")
    s.add_argument("--since", metavar="DATE", help="events only: those at or after this ISO date or time")
    s.add_argument("--format", default="json", metavar="FORMAT", help="json, csv, or the name of an installed aidd.exporters extension")
    s.add_argument("--tenant", metavar="TENANT", help="only the records or events of this tenant (the `tenant` their config names)")
    s.add_argument("--out", metavar="DIR", help="write DIR/<kind>.<format> instead of printing")

    s = cmd(
        "verify",
        "check an agent change record (the in-toto statement `aidd gate --record` writes): its subject, tenant, decision, and human "
        "approvals, and, with --bundle or --online, its signature through `gh attestation verify`",
        cmd_verify,
    )
    s.add_argument("target", metavar="SHA|PATH", help="a change record file, or a head commit SHA whose record is in --dir")
    s.add_argument("--dir", default="aidd-evidence", help="where to look for the record of a SHA")
    s.add_argument("--sha", metavar="SHA", help="with a PATH: the head commit the record must name")
    s.add_argument("--tenant", metavar="TENANT", help="the tenant the record must belong to")
    s.add_argument("--bundle", metavar="PATH", help="a Sigstore bundle (from `gh attestation download`) to verify the signature against")
    flag(s, "--online", "fetch and verify the attestation from GitHub with `gh attestation verify`")
    s.add_argument(
        "--repo", metavar="OWNER/NAME", help="the GitHub repository that signed it (default: this checkout's github.com origin); the record must name it"
    )
    s.add_argument(
        "--signer-workflow", metavar="WORKFLOW", help="the workflow the signature must come from (default: OWNER/NAME/.github/workflows/aidd-gate.yml)"
    )
    s.add_argument("--default-branch", metavar="BRANCH", help="the branch the signing workflow ran from (default: origin/HEAD, else main)")
    flag(s, "--allow-unsigned", "exit 0 for a record that holds but is not signed (it still prints unsigned)")

    if plugins and not ext.sealed():
        ext.register_commands(sub, set(sub.choices))
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    # A protected command (the gate, the test runner, approvals, ship, the hooks, the MCP server) never discovers
    # extensions: seal discovery before its parser is built, so no plugin module is imported in this process.
    command = ext.command_of(argv)
    if command in ext.PROTECTED:
        ext.seal()
    args = build_parser(plugins=command not in ext.PROTECTED).parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, LookupError, gitutil.GitError, http.HttpError, RuntimeError) as exc:
        print(f"aidd: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # a bug must never look like a gate decision (exit 1)
        print(f"aidd: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
