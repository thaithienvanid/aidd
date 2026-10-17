"""The Decide commands' arguments and flags: hash, approve, and explore."""

from __future__ import annotations

from aidd.cli import arguments


def register(cmd, flag) -> None:
    """Add the decide commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd(
        "explore",
        "render an exploration's one comparison page: two or three divergent directions side by side (stacked on a phone), "
        "the trade-offs under each, each round's screenshots beside the round before with the feedback each change answers, "
        "and a choice to copy. The page records nothing and approves nothing: the owning role writes the pick and its reason "
        "in the Spec's Design section, DESIGN.md, or an ADR",
        "decide:cmd_explore",
    )
    s.add_argument("folder", help="the exploration's folder, such as specs/SPEC-12/explore/split-bill or specs/explore/queues")
    s.add_argument("--out", metavar="PATH", help="where to write the page (default: .aidd/views/explore-<folder>.html)")

    s = cmd(
        "hash",
        "print the Spec hash of a Spec and its frozen test and design files, or the approval line an Approver posts; for a proposal, the hash its sign-off records",
        "decide:cmd_hash",
    )
    s.add_argument("spec", help="path to the Spec file or the proposal, or its id (SPEC-1, PROP-3)")
    s.add_argument("--ref", default="HEAD", help="commit to hash; the gate hashes the PR head")
    flag(s, "--worktree", "hash the working tree instead of a commit")
    flag(s, "--line", "print the whole approval line (/aidd approve-spec ID HASH COMMIT), or a proposal's sign_off line, instead of the bare hash")
    flag(
        s,
        "--summary",
        "print a phone-sized summary of what the hash approves first (intent, Acceptance ids and text, scope, risk, rollback, "
        "frozen test files), at most 25 lines, ending with the hash or, with --line, the approval line",
    )
    flag(
        s,
        "--html",
        "also write the Spec approval page: one self-contained HTML page with the intent, Acceptance against the tests, the route "
        "and why, the risk and rollback, each frozen file and doc, the diagrams, what changed since the last approval, and the "
        "approval line to copy (default .aidd/views/spec-<ID>.html). It never approves",
    )
    s.add_argument("--out", metavar="PATH", help="--html: write the page here instead")

    _approve(cmd("approve", "local-first: record a person's Spec approval or Merge approval on this machine, with no platform", "decide:cmd_approve"), flag)


def _approve(s, flag) -> None:
    """`aidd approve`'s arguments: the terminal form, and the preview and the confirmed form a dialog uses."""
    s.add_argument(
        "what",
        nargs="?",
        choices=["spec", "merge", "all", "stop"],
        help="spec or merge; all, a standing approval: the agent records each approval for you until you stop it; stop, its end; "
        "none, at your terminal, lists what waits on you to pick from",
    )
    s.add_argument("spec", nargs="?", help="for spec: the Spec, such as specs/SPEC-1.md or SPEC-1")
    s.add_argument("more", nargs="*", metavar="SPEC", help="for spec, at your terminal: more Specs, all approved after one question")
    s.add_argument("--base", help=arguments.BASE_HELP)
    s.add_argument(
        "--ref", default="HEAD", metavar="BRANCH_OR_COMMIT", help="spec: approve the Spec as this branch or commit holds it, from any worktree (default HEAD)"
    )
    flag(
        s,
        "--show",
        "print what you would approve as JSON (a Spec: its title, Acceptance, hash, and commit; a merge: the branch, its head, what "
        "changed, and the gate's state), with warnings and problems; record nothing",
    )
    s.add_argument(
        "--confirmed",
        metavar="HASH_OR_HEAD",
        help="record the approval a person confirmed in a dialog (aidd-mods in Claude Code, or an MCP client) for exactly this Spec hash, "
        "or for a merge this head commit, without the terminal question; the record says where. The guard denies it to agents",
    )
    s.add_argument(
        "--confirmed-in",
        default="claude-code",
        metavar="WHERE",
        help="with --confirmed: where the person confirmed, for the record: claude-code (default), or mcp:<client> for an MCP client's dialog",
    )
    s.add_argument(
        "--evidence",
        help="merge: the evidence `aidd test` wrote, whose results the digest and the gate state show (default .aidd/evidence/evidence.json)",
    )
    flag(s, "--skip-cooloff", "merge, local-first: skip the route's cool-off, on record (the gate warns and the record names you)")
    flag(
        s,
        "--auto-merge",
        "merge, on a platform: also turn on the pull request's auto-merge, so it merges by itself once `aidd/gate` passes (only where the base branch requires `aidd/gate`)",
    )
    flag(s, "--but-major", "all: leave major and emergency changes to you")
    s.add_argument("--until", metavar="YYYY-MM-DD", help="all: the last day the standing approval holds (default: until you stop it)")
