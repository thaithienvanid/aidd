"""Rename every name of an Intent's agreement to the approval's, as one pass over the tracked files.

An Intent's yes is an approval: the action and step code `intent.agree` becomes `intent.approve`, the command `aidd agree` becomes
`aidd approve`, the gate "Intent agreement" becomes "Intent approval", the defer codes `intent_agreement_changed` and
`intent_not_agreed` become `intent_approval_changed` and `intent_not_approved`, and each function, constant, and module that said
"agreement" or "agreed" says "approval" or "approved". The pass renames whole words only (`\\b` bounds each), in the kinds of file
in KINDS, except the files in SKIP.

What it does not write, a person did: the shape of the yes (`agreed_by` and `agreed_at` became one `approval: {by, at}`, and the
`Agreed-by:` trailer became `Approved-by:` with `Approves:`), the status word `agreed`, the risk rules' patterns, the descriptions
and the prose around each renamed name, the CHANGELOG, the glossary, and the sort order of each list a rename moved. Run again
after those hunks, it would find nothing more to write, so it is a record of the first pass.

Run `python3 tools/rename_intent_approval.py` once, from anywhere, on the commit before the rename. It finds the repository from its
own path, changes only tracked files, and prints the count of each rule for each file. It makes no network call and uses the
standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# A name that is a word on its own, renamed in every tracked file of the kinds in KINDS except the ones in SKIP. The order matters
# only where one name holds another: the longer goes first.
IDENTIFIERS = {
    "intent.agree": "intent.approve",
    "aidd agree": "aidd approve",
    "Intent agreement": "Intent approval",
    "intent_agreement_changed": "intent_approval_changed",
    "intent_not_agreed": "intent_not_approved",
    "cmd_agree": "cmd_approve",
    "add_agree": "add_approve",
    "record_agreement": "record_approval",
    "agreed_document": "approved_document",
    "agreed_versions": "approved_versions",
    "agreed_version": "approved_version",
    "agreed_changes": "approved_changes",
    "_agreement_commit": "_approval_commit",
    "agreement_commit": "approval_commit",
    "agreement_view": "approval_view",
    "agreement_body": "approval_body",
    "agreement_warnings": "approval_warnings",
    "agreement_problems": "approval_problems",
    "_agreement_check": "_approval_check",
    "agreement_check": "approval_check",
    "_agreement_notes": "_approval_notes",
    "_agreements": "_approvals",
    "person_agreed": "person_approved",
    "not_agreed": "not_approved",
    "AgreementCase": "ApprovalCase",
    "AgreeCommandTests": "ApproveCommandTests",
    "aidd.workitems.agreement": "aidd.workitems.approval",
    "aidd.delegation.agreements": "aidd.delegation.intent_approvals",
    "workitems/agreement.py": "workitems/approval.py",
    "delegation/agreements.py": "delegation/intent_approvals.py",
    "test_delegation_agreements": "test_delegation_approvals",
    "test_intent_agreement": "test_intent_approval",
    "test_agreement": "test_approve_command",
}
# A module named by its package, as `agreements.changes`: renamed only where the module is meant, in these files.
MODULE_USES = {
    "src/aidd/delegation/action_checks.py": (r"\bagreements\b", "intent_approvals"),
    "src/aidd/delegation/__init__.py": (r"\bagreements \(", "intent_approvals ("),
    "src/aidd/workitems/current_work.py": (r"\bagreement\b(?=[,.])", "approval"),
    "src/aidd/workitems/__init__.py": (r'"agreement"', '"approval"'),
    "tests/test_approve_command.py": (r"\bagreement\b(?=\.\w|\n)", "approval"),
}
# The files git moves, before the names inside them change.
MOVES = {
    "src/aidd/workitems/agreement.py": "src/aidd/workitems/approval.py",
    "src/aidd/delegation/agreements.py": "src/aidd/delegation/intent_approvals.py",
    "tests/test_agreement.py": "tests/test_approve_command.py",
    "tests/test_intent_agreement.py": "tests/test_intent_approval.py",
    "tests/test_delegation_agreements.py": "tests/test_delegation_approvals.py",
}
KINDS = (".py", ".json", ".md", ".yaml", ".yml", ".sh", ".svg", ".txt", ".toml")
# The CHANGELOG is written by hand. This repository's own ask rules are the person's to regenerate (`aidd upgrade --only
# ask-rules`). The readers of an older shape and their tests and fixtures, and the one-time script of an earlier rename, are
# another change's. The design's case data names its own rows.
SKIP = (
    "CHANGELOG.md",
    ".claude/settings.json",
    "opencode.json",
    ".aidd/harness-rules.json",
    "schemas/retired-names.json",
    "src/aidd/workitems/old_shape.py",
    "src/aidd/workitems/migrating.py",
    "tests/test_old_shape_agrees.py",
    "tests/test_migration",
    "tests/fixtures/migration/",
    "tests/fixtures/ledgers/",
    "tests/fixtures/design/",
    "tools/",
)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def rename(text: str, rules: list[tuple[re.Pattern[str], str]]) -> tuple[str, list[tuple[str, int]]]:
    counts = []
    for pattern, new in rules:
        text, n = pattern.subn(new, text)
        if n:
            counts.append((pattern.pattern, n))
    return text, counts


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    for old, new in MOVES.items():
        if (root / old).exists():
            subprocess.run(["git", "mv", old, new], cwd=root, check=True)
    rules = [(re.compile(r"(?<![\w])" + re.escape(old) + r"(?![\w-])"), new) for old, new in IDENTIFIERS.items()]
    total = 0
    for rel in tracked(root):
        if not rel.endswith(KINDS) or rel.startswith(SKIP) or rel in SKIP:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new, counts = rename(text, rules)
        if rel in MODULE_USES:
            pattern, repl = MODULE_USES[rel]
            new, n = re.subn(pattern, repl, new)
            counts += [(pattern, n)] if n else []
        if new != text:
            path.write_text(new, encoding="utf-8")
            for pattern, n in counts:
                print(f"{rel}: {n} x {pattern}")
                total += n
    print(f"{total} renames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
