"""The Author commands' arguments and flags: new, import, describe, revise, test, and proposal."""

from __future__ import annotations

from aidd import config, workitems
from aidd.cli import arguments


def register(cmd, flag) -> None:
    """Add the author commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd(
        "prototype",
        "assemble the whole-product prototype from docs/design/app/ (sitemap.json, shell.html, and flows/) into aidd's prototype viewer, "
        ".aidd/views/prototype.html, and check it: every link and navigation item opens a screen, no flow draws its own navigation, "
        "and every flow is reachable",
        "author:cmd_prototype",
    )
    s.add_argument(
        "file",
        nargs="?",
        help="a Spec's or a flow's prototype file, such as specs/SPEC-12/design/prototype.html, to open in the current viewer; "
        "the file is never changed, so a frozen prototype gets every fix to the viewer",
    )
    flag(s, "--check", "only check the sources: report every problem, with its line in a prototype file, exit 1 on any, and write nothing")
    flag(s, "--example", "write the prototype tool's showcase, a complete design to learn the format from, to .aidd/views/")
    flag(s, "--open", "open the written page in your browser, after printing its address")
    flag(s, "--components", "print the design's component contract as JSON: each data-component, its variants, screens, and test ids")
    flag(s, "--screens", "print the design's screens as JSON: each one's id, title, parent, first state, and states in order")
    s.add_argument("--new-design", metavar="FILE", help="write a design file from the starting design, such as an exploration's sketch (directions/a.html)")
    s.add_argument("--title", default="A direction", help="with --new-design: what the design shows")
    s.add_argument(
        "--stories", metavar="INDEX", help="check Storybook's index.json (from `storybook build`) against the component contract: exit 1 on a missing story"
    )
    s = cmd(
        "new",
        "create a Spec, Epic, Initiative (a solo founder's brief too), Proposal, runbook, postmortem, or feedback log from the template; or a document a Spec links "
        "(tech-spec, test-plan, adr, threat-model, authz, design-spec (--prototype for its HTML prototype), api, slo, compliance, analytics, migration, acceptance), "
        "written from its template and added to the Spec's `docs`; or the repository's one design-system (DESIGN.md, design/tokens.json, and design/build.mjs), product-prototype (docs/design/app/, which `aidd prototype` opens), architecture overview "
        "(docs/architecture/README.md), data-map, vendors register, glossary (docs/GLOSSARY.md), or vulnerability-policy (docs/security/); or a proposal's contract, then each change order (`aidd new contract <proposal id>`); "
        "or an exploration (`aidd new exploration <folder> --title <question>`), rendered by `aidd explore`",
        "author:cmd_new",
    )
    # The kinds besides the Spec, its containers, the proposal, and the postmortem come from repo.DOC_KINDS_NEW; runbook
    # stays beside postmortem in the help.
    s.add_argument(
        "kind",
        choices=[
            "spec",
            "epic",
            "initiative",
            "proposal",
            "runbook",
            "postmortem",
            *(k for k in workitems.DOC_KINDS_NEW if k != "runbook"),
            "product-prototype",
        ],
    )
    s.add_argument(
        "id",
        nargs="?",
        help='such as SPEC-42, or for a Spec, Epic, Initiative, or Proposal its title (`aidd new spec "Add a discount"`), which takes the next '
        "free id; for a linked document, its topic, such as rate-limits; a contract's proposal id; an exploration's folder; none for a repository document",
    )
    s.add_argument(
        "--title",
        help="a Spec's, Epic's, Initiative's, Proposal's, runbook's, or postmortem's title (or give it in place of the id); an exploration's question; a document's default is its topic",
    )
    s.add_argument(
        "--route",
        choices=["normal", "major", "emergency"],
        help="a Spec is normal (the default; the gate raises it when needed), major, or an emergency backfill; with --paths, the "
        "computed route wins when it is higher",
    )
    s.add_argument("--type", default="feat", choices=arguments.TYPES, help="the change type")
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="spec: the paths or globs the change will touch; computes the route (and says when no Spec is needed) and writes them as the Task's scope",
    )
    s.add_argument("--dimension", action="append", choices=arguments.DIMENSIONS, help="spec: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "spec: a revert would not restore the prior state (forces major)")
    flag(s, "--force", "spec: write a Spec even when the paths are on the fast lane")
    flag(
        s,
        "--full",
        "spec: every section (adds Problem, Goals, Non-goals, and Learn); by default a normal Spec is the short one (Intent, "
        "Context, Acceptance, Design, Policy conflicts, Rollback), and a major Spec is full; alternatives and the pre-mortem "
        "live in the tech spec it links",
    )
    s.add_argument(
        "--base",
        default="",
        metavar="BRANCH",
        help="spec: the branch it lands in, such as goal/booking, the goal branch of a small goal that is batched (default: the default branch)",
    )
    s.add_argument("--owner-team", default="", help="default: owners.default_owner_team from the config")
    s.add_argument("--parent", default="", help="the parent's id: an Epic for a Spec, an Initiative for an Epic")
    s.add_argument("--audience", default="client", choices=["client", "internal"], help="a proposal's audience: a client, or the company's own decision makers")
    s.add_argument("--addressee", default="", help='who receives a proposal and decides, such as "Acme Corp" or "the executive committee"')
    s.add_argument(
        "--spec",
        default="",
        help="the Spec id: a linked document's Spec (required), a runbook's (linked as a living doc), or a postmortem's (the Spec that carries the fix)",
    )
    s.add_argument(
        "--area",
        default="",
        help="a linked document's folder under the specs folder, such as checkout, shared by several Specs (default: the Spec id); for --prototype, a second flow's folder in the Spec's design/",
    )
    flag(s, "--no-link", "a linked document: write it and print its `docs` entry, leaving the Spec to its writer to link it")
    flag(
        s,
        "--prototype",
        "ui: write the HTML prototype instead of the design spec, as prototype.html in the design folder: every screen of the flow, "
        "its states, themes, and frames, deep links, and feedback mode, shown by `aidd prototype`",
    )
    s.add_argument("--owner", default="", help="exploration: the role that owns it (default product-designer; architect for an architecture question)")
    s.add_argument(
        "--timebox",
        default="45 minutes",
        help="exploration: minutes or a cost, or a spike's end date (YYYY-MM-DD); when it runs out, the owner stops and presents",
    )

    s = cmd(
        "import",
        "write a short Spec from another planning tool's files (Spec Kit, OpenSpec, Kiro, BMAD): Intent, Acceptance ids, "
        "Tasks with the paths it names, and the computed route; it links the plan instead of copying it. `issues`: one suggested Spec per new issue of a "
        "tracker (--github or --file), its text quoted as data, waiting for a person's triage; an issue already imported is skipped",
        "author:cmd_import",
    )
    s.add_argument("tool", choices=["speckit", "openspec", "kiro", "bmad", "issues"])
    s.add_argument(
        "path",
        nargs="?",
        help="Spec Kit: specs/NNN-feature/; OpenSpec: openspec/changes/<change>/; Kiro: .kiro/specs/<feature>/; BMAD: one story file; none for issues",
    )
    s.add_argument(
        "--github", metavar="OWNER/REPO", help="issues: the repository's open issues (GITHUB_TOKEN or GH_TOKEN when set; public repositories without one)"
    )
    s.add_argument("--file", metavar="PATH", help="issues: a JSON array exported from any tracker, each {title, body, url, labels}, or GitHub's shape")
    s.add_argument("--label", metavar="LABEL", help="issues: only GitHub issues with this label")
    s.add_argument("--limit", type=int, metavar="N", help="issues: at most this many new Specs (default 30, at most 500)")
    s.add_argument("--id", metavar="ID", help="the Spec id (default: SPEC-<n>, one past the highest in the Specs folder)")
    s.add_argument("--out", metavar="DIR", help="where to write it (default: the config's Specs folder)")
    s.add_argument("--title", help="the Spec's title (default: the source's)")
    s.add_argument("--type", choices=arguments.TYPES, help="the change type (default: feat; fix for a Kiro bugfix spec)")

    s = cmd("describe", "print the Change Request block that describes the current branch's change, with the reasons for its route", "author:cmd_describe")
    s.add_argument("--base", help=arguments.BASE_HELP)
    s.add_argument(
        "--type",
        choices=arguments.TYPES,
        help="the change type (default: the newest Conventional Commit subject's type, else docs for doc-only diffs, else feat)",
    )
    flag(
        s,
        "--commit",
        "local-first, with no PR/MR description: record the block in an empty commit on the branch, where `aidd test`, `aidd gate`, "
        "and `aidd land` read it (the newest such commit wins)",
    )

    s = cmd(
        "revise",
        "reopen an approved Spec: record what was wrong (`revisions` in its front matter), which voids its approval, so its owners "
        "change the Spec, its tests, its design files, and its frozen docs, and the next Spec approval freezes them again",
        "author:cmd_revise",
    )
    s.add_argument("spec", help="the Spec, such as SPEC-42 or specs/SPEC-42.md")
    s.add_argument("why", help="what was wrong, in one sentence; the approval card shows it to the Approver")

    s = cmd("test", "run the tests (green on head, red on base) and write evidence", "author:cmd_test")
    s.add_argument("--base", help=arguments.BASE_HELP)
    s.add_argument("--spec", help="the Spec whose tests to run (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="PR/MR description holding the Change Request block")
    s.add_argument("--out", default=config.EVIDENCE_DIR, help="where evidence.json and logs go")
    flag(s, "--no-red", "skip red runs (the gate will still require them)")
    flag(s, "--red-in-place", "CI only: run red in this checkout, keeping installed dependencies")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)
    flag(
        s,
        "--changed",
        "local: run only the commands the working tree's changes against the base select (a matching when_changed, a Spec command when "
        "a path is in a Task's scope or its test files, a config command without when_changed), green only; the evidence is marked partial "
        "and the gate never accepts it",
    )
    flag(s, "--watch", "local: run --changed now and again whenever a file changes, until Ctrl-C (exit 0)")
    flag(
        s,
        "--merge-queue",
        "CI, for a merge queue entry (a GitHub merge_group run or a GitLab merge train pipeline): test the entry's commit against "
        "the commit it was built on (as the gate computes it)",
    )

    s = cmd(
        "proposal",
        "a proposal's tables for the document you send (matrix), an accepted proposal as an Initiative and Epics (convert), "
        "or a person's go/no-go (decide) and sign-off (sign-off), asked at their terminal",
        "author:cmd_proposal",
    )
    s.add_argument("action", choices=["matrix", "convert", "decide", "sign-off"])
    s.add_argument("file", help="the proposal, such as proposals/PROP-1/proposal.md, or its id (PROP-1)")
    s.add_argument("decision", nargs="?", choices=["go", "no-go"], help="decide: go, to draft it, or no-go")
    s.add_argument("--reason", help="decide: why, in a sentence, for whoever reads the decision later")
    s.add_argument("--by", metavar="IDENTITY", help="decide, sign-off: who decides (default: @<your GitHub login>, else email:<git user.email>)")
    flag(s, "--show", "decide, sign-off: print what the person decides as JSON, with any reason it cannot be recorded; record nothing")
    s.add_argument(
        "--confirmed",
        metavar="DECISION|HASH",
        help="decide, sign-off: record what a person confirmed in a dialog (aidd-mods in Claude Code, or an MCP client): the decision, "
        "or for a sign-off the proposal's hash `--show` gave. The guard denies it to agents",
    )
    s.add_argument(
        "--decided-via",
        default="claude-code",
        metavar="WHERE",
        help="with --confirmed: where the person confirmed: claude-code (default), opencode, or mcp:<client>",
    )
