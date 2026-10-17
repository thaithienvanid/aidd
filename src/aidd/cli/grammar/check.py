"""The Check commands' arguments and flags: gate, validate, and record (verify, export)."""

from __future__ import annotations

from aidd import config
from aidd.cli import arguments


def register(cmd, flag) -> None:
    """Add the check commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd(
        "gate",
        "run every gate rule: locally as a preflight, in CI for a platform, or against any context; before any code, --paths "
        "forecasts the route of planned paths",
        "check:cmd_gate",
    )
    s.add_argument("platform", nargs="?", choices=["github", "gitlab"], help="CI entry point: gather a trusted context and report aidd/gate")
    s.add_argument("--context", help="context.json from any CI adapter (schemas/context.schema.json)")
    s.add_argument("--base", help=arguments.BASE_HELP)
    s.add_argument("--spec", help="local: the Spec this change implements (default: the one Spec in the diff)")
    s.add_argument("--body-file", help="local: PR/MR description holding the Change Request block")
    s.add_argument("--approvals", help='local: JSON for dry runs, {"reviews": [...], "comments": [...]}')
    s.add_argument("--evidence", default=".aidd/evidence/evidence.json", help="local and GitLab: evidence from `aidd test`")
    flag(s, "--no-policy", "local: do not run the Policy command")
    flag(s, "--markdown", "print the PR summary instead of text")
    flag(
        s,
        "--json",
        "print the decision record as JSON (schemas/record.schema.json, with schema_version), nothing else; with --paths, the forecast "
        "(schemas/forecast.schema.json)",
    )
    s.add_argument(
        "--mode",
        choices=["enforce", "advisory"],
        help="CI: advisory reports on 'aidd/gate (advisory)' and never blocks. The base branch's config `mode` wins; AIDD_MODE never relaxes the gate, and on GitLab neither does this flag (default: enforce)",
    )
    flag(s, "--dry-run", "CI: decide without posting a status")
    flag(s, "--pending-ok", "GitLab: exit 0 while approvals are pending")
    flag(s, "--post-status", "GitLab: also post an external status (needs an api-scope token)")
    flag(s, "--resolve", "GitHub: only print the pull request numbers this event concerns, and the head commit a run judges")
    s.add_argument("--record", metavar="PATH", help="write the derived change record here")
    s.add_argument("--events", metavar="PATH", help="append one gate event (a JSON line) here")
    s.add_argument("--explain", metavar="RULE", help="print what a rule checks and how to satisfy it, then exit")
    s.add_argument(
        "--paths",
        nargs="+",
        metavar="GLOB",
        help="before any code exists: forecast the route the paths or globs the change will touch need, its lane, and the lane's first "
        "step. It records nothing and posts no status; on the branch, the gate computes the route again from the real diff, which can "
        "only raise it",
    )
    s.add_argument("--type", choices=arguments.TYPES, help="--paths: the change type (default feat)")
    s.add_argument("--dimension", action="append", choices=arguments.DIMENSIONS, help="--paths: a declared risk dimension (repeatable)")
    flag(s, "--irreversible", "--paths: a revert would not restore the prior state (forces major)")
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write the Merge approval page: the decision and its findings with fixes, Acceptance against the evidence, what "
        "the verifier recorded, the review report's findings, the scope and budget, and the diff file by file, as one "
        "self-contained HTML page (default .aidd/views/merge-<head>.html). The gate never reads it",
    )

    s = cmd("validate", "validate files or directories; with none, the whole repository, including overdue emergency reviews", "check:cmd_validate")
    s.add_argument("paths", nargs="*", help="config .yaml files, object .md files, or directories")
    flag(s, "--json", "print the errors, the warnings, and the next step as JSON (schemas/validate.schema.json)")

    record = cmd(
        "record",
        "the records the gate writes: check an agent change record (verify), list the verifier's preview files (preview), or export gate records and events (export)",
        None,
    )
    records = record.add_subparsers(dest="record_command", required=True, metavar="ACTION")
    s = cmd(
        "verify",
        "check an agent change record (the in-toto statement `aidd gate --record` writes): its subject, tenant, decision, and human "
        "approvals, and, with --bundle or --online, its signature through `gh attestation verify`",
        "check:cmd_verify",
        into=records,
        short="check an agent change record: its subject, tenant, decision, approvals, and signature",
    )
    s.add_argument("target", metavar="SHA|PATH", help="a change record file, or a head commit SHA whose record is in --dir")
    s.add_argument("--dir", default=config.EVIDENCE_DIR, help="where to look for the record of a SHA")
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

    s = cmd(
        "preview",
        "list what the verifier saved under <evidence>/preview/<head-sha>/ in its artifacts.json, each file with its kind and "
        "SHA-256, so the Merge approval page shows it; aidd writes the list, so the verifier stays read-only",
        "check:cmd_record_preview",
        into=records,
        short="list the verifier's preview files in artifacts.json, for the Merge approval page",
    )
    s.add_argument("head", metavar="SHA", help="the head commit the preview ran on")
    s.add_argument("--dir", default=config.EVIDENCE_DIR, help="the evidence folder that holds preview/<SHA>/")

    s = cmd(
        "export",
        "export gate records or gate events as JSON or CSV, deterministically, for a log store or a spreadsheet",
        "check:cmd_export",
        into=records,
        short="export gate records or gate events as JSON or CSV",
    )
    s.add_argument("kind", choices=["records", "events"])
    s.add_argument("paths", nargs="+", metavar="PATH", help="record files (--record) or event files (--events), or directories holding them")
    s.add_argument("--since", metavar="DATE", help="events only: those at or after this ISO date or time")
    s.add_argument("--format", default="json", metavar="FORMAT", help="json, csv, or the name of an installed aidd.exporters extension")
    s.add_argument("--tenant", metavar="TENANT", help="only the records or events of this tenant (the `tenant` their config names)")
    s.add_argument("--out", metavar="DIR", help="write DIR/<kind>.<format> instead of printing")
    flag(
        s,
        "--by-control",
        "records only, as JSON: group the records and the Specs' linked docs by the control ids their compliance docs declare "
        "(schemas/control-evidence.schema.json; run it at the repository root)",
    )
