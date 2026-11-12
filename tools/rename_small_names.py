"""Rename six names, each in every file that states it: a Task's `depends_on` is `blocked_by`, the order file's `product_owner` is
`owner`, `aidd doctor`'s result words are `error`, `warning`, and `note` (a check that passed has none), a need's `answer`
values are `full`, `partial`, `alternative`, and `none`, an exploration's `taste_pick` is `visual_pick`, and the status
JSON's `intent_branch_state` and `spec_branch_state` are `branch_state`.

Each row holds its replacements, and the line a few of them leave alone, in the tables below. A name that another tool owns
stays: `depends_on` in a `tach.toml`, a doc check's `warn` level, an icon named `warn`. What the replacements cannot decide
(a value's new place in a sentence, a table's order, a code path) is edited by hand in the same change. Run it twice and
the second run changes nothing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "tools/rename_small_names.py"
# The one test that holds each old name beside its new one, to show the old name is refused.
NAMES_TEST = "tests/test_field_names.py"

# Row 1. The files that state a Task's `depends_on`; `tach.toml`'s own key is no Task's, and the vocabulary test's data is edited by hand.
TASK_LINK = re.compile(r"\bdepends_on\b")
TASK_LINK_KEPT = frozenset({SELF, "standards/python/tach.md", "tests/fixtures/design/data_rules/judged.json", NAMES_TEST})

# Row 2. The order file's person.
ORDER_FILES = (
    ".agents/skills/aidd/assets/intent-order.md",
    "schemas/product-scope.schema.json",
    "src/aidd/workitems/product_checks.py",
    "tests/product_scope_fixtures.py",
    "tests/test_product_scope_checks.py",
    "tests/test_product_scope_schemas.py",
)
ORDER_PERSON = re.compile(r"\bproduct_owner\b")

# Row 3. The files that return a doctor check as (result, message), and the tests that read one. A quoted result word becomes
# the new one, and `"ok"` becomes the empty result, because a check that passed has no word. A line that holds a word of
# another thing stays: a string prefix, a doc check's level, an icon.
DOCTOR_SOURCES = (
    "src/aidd/knowledge/standard_copy_checks.py",
    "src/aidd/setup/ask_rules.py",
    "src/aidd/setup/claude_plugins.py",
    "src/aidd/setup/delegation_wiring.py",
    "src/aidd/setup/doctor_checks.py",
    "src/aidd/setup/doctor_environments.py",
    "src/aidd/setup/doctor_harnesses.py",
    "src/aidd/setup/doctor_leftovers.py",
    "src/aidd/setup/doctor_listing.py",
    "src/aidd/setup/doctor_probes.py",
    "src/aidd/setup/doctor_team.py",
    "src/aidd/setup/doctor_tests.py",
    "src/aidd/setup/domain_packs.py",
    "src/aidd/setup/pins.py",
    "src/aidd/setup/worktree_base.py",
)
DOCTOR_TESTS = (
    "tests/test_claude_user_folder.py",
    "tests/test_cra_target.py",
    "tests/test_delegation_owner_warnings.py",
    "tests/test_delegation_setup.py",
    "tests/test_delegation_standing.py",
    "tests/test_delivery_defaults.py",
    "tests/test_doctor_environments.py",
    "tests/test_doctor_leftovers.py",
    "tests/test_doctor_related_tests.py",
    "tests/test_doctor_versions.py",
    "tests/test_engagement.py",
    "tests/test_fail_closed.py",
    "tests/test_frozen_test_rules.py",
    "tests/test_gh_api_risk.py",
    "tests/test_harness_sizes.py",
    "tests/test_harness_trust.py",
    "tests/test_init_defaults.py",
    "tests/test_launcher.py",
    "tests/test_launcher_guard.py",
    "tests/test_onboarding.py",
    "tests/test_ops_docs.py",
    "tests/test_plugin_channel.py",
    "tests/test_practice_warnings.py",
    "tests/test_release_surface.py",
    "tests/test_risk.py",
    "tests/test_ruleset_check.py",
    "tests/test_specialist_pools.py",
    "tests/test_standards.py",
    "tests/test_standards_owners.py",
    "tests/test_team_models_honest.py",
    "tests/test_team_packs.py",
    "tests/test_upgrade.py",
    "tests/test_upgrade_engine.py",
    "tests/test_verification_block.py",
    "tests/test_wired_harnesses.py",
    "tests/test_worktree_base.py",
)
DOCTOR_WORDS = (
    (re.compile(r'(?<!startswith\()(?<!removeprefix\()"warn"'), '"warning"'),
    (re.compile(r'"fail"'), '"error"'),
    (re.compile(r'"info"'), '"note"'),
    (re.compile(r'\("ok", '), '("", '),
)
# In the code, `"ok",` alone on a line is a check that passed, written over several lines; the tests name `"ok"` in other ways, by hand.
DOCTOR_LINE_WORDS = ((re.compile(r'^(\s*)"ok",$'), r'\1"",'),)
DOCTOR_LINE_KEPT = re.compile(r'\.level\b|\bask\.level|authz-matrix|compliance-record|\bdoc_type\b|"suggest"|"info": \{|stdout="|\("ok", "3\.5\.0"\)')
# `info` as a word of another thing, in the files above: JSON that a feed returns, and a folder of git.
DOCTOR_NOTE_KEPT = re.compile(r'"info"\s*:|/ "info"|\.git/info')
DOCTOR_LOCAL_HELPERS = "src/aidd/setup/doctor_checks.py"
DOCTOR_HELPER_NAMES = (
    (re.compile(r"\bok = lambda m: out\.append\(\(\"\", m\)\)"), 'passed = lambda m: out.append(("", m))'),
    (re.compile(r"\bwarn = lambda m: out\.append\(\(\"warning\", m\)\)"), 'warning = lambda m: out.append(("warning", m))'),
    (re.compile(r"\bfail = lambda m: out\.append\(\(\"error\", m\)\)"), 'error = lambda m: out.append(("error", m))'),
    (re.compile(r"(?<![\w.])ok\("), "passed("),
    (re.compile(r"(?<![\w.])warn\("), "warning("),
    (re.compile(r"(?<![\w.])fail\("), "error("),
)

# Row 4. A need's `answer`, in the template, the skill, and the tests that write one in a proposal's front matter.
NEED_ANSWERS = (
    (re.compile(r"\banswer: met\b(?!,)"), "answer: full"),
    (re.compile(r"\banswer: partly_met\b"), "answer: partial"),
    (re.compile(r"\banswer: not_met\b"), "answer: none"),
)
NEED_ANSWER_FILES = (
    "tests/test_client_roles.py",
    "tests/test_delivery_record.py",
    "tests/test_proposal.py",
    "tests/test_proposal_registers.py",
    "tests/test_proposal_sign_off.py",
)

# Row 5. An exploration's pick by eye, by its key and by its name in a sentence.
PICK_WORDS = (("taste_pick", "visual_pick"), ("Taste pick", "Visual pick"), ("taste pick", "visual pick"))

# Row 6. The status JSON's branch state, for an Intent and for a Spec.
BRANCH_KEYS = re.compile(r"\b(?:intent|spec)_branch_state\b")
BRANCH_KEY_KEPT = frozenset(
    {SELF, NAMES_TEST, "tests/fixtures/design/pins.json", "tests/fixtures/design/data_rules/exceptions.json", "tests/fixtures/design/data_rules/judged.json"}
)


def tracked() -> list[str]:
    return subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()


def read(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def rewrite_lines(text: str, words: tuple[tuple[re.Pattern[str], str], ...], kept: re.Pattern[str] | None) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        if kept is None or not kept.search(line):
            for pattern, new in words:
                line = pattern.sub(new, line)
        out.append(line)
    return "".join(out)


def rewrite_doctor(rel: str, text: str) -> str:
    words = DOCTOR_WORDS
    out = []
    for line in text.splitlines(keepends=True):
        if not DOCTOR_LINE_KEPT.search(line):
            for pattern, new in words:
                if pattern.pattern == '"info"' and DOCTOR_NOTE_KEPT.search(line):
                    continue
                line = pattern.sub(new, line)
            if rel in DOCTOR_SOURCES:
                for pattern, new in DOCTOR_LINE_WORDS:
                    line = pattern.sub(new, line.rstrip("\n")) + ("\n" if line.endswith("\n") else "")
        out.append(line)
    text = "".join(out)
    if rel == DOCTOR_LOCAL_HELPERS:
        for pattern, new in DOCTOR_HELPER_NAMES:
            text = pattern.sub(new, text)
    return text


def plan() -> list[tuple[str, str, object]]:
    """Each row: its label, and the files with the function that rewrites one."""
    every = tracked()
    rows: list[tuple[str, list[str], object]] = []
    rows.append(
        (
            "1 a Task's blocked_by",
            [f for f in every if f not in TASK_LINK_KEPT and (t := read(f)) and TASK_LINK.search(t)],
            lambda rel, t: TASK_LINK.sub("blocked_by", t),
        )
    )
    rows.append(("2 the order file's owner", list(ORDER_FILES), lambda rel, t: ORDER_PERSON.sub("owner", t)))
    rows.append(("3 doctor's result words", [*DOCTOR_SOURCES, *DOCTOR_TESTS], rewrite_doctor))
    rows.append(("4 a need's answer", [".agents/skills/aidd/assets/proposal.md", *NEED_ANSWER_FILES], lambda rel, t: rewrite_lines(t, NEED_ANSWERS, None)))
    rows.append(
        (
            "5 an exploration's visual_pick",
            [f for f in every if f not in (SELF, NAMES_TEST) and (t := read(f)) and any(old in t for old, _ in PICK_WORDS)],
            lambda rel, t: _replace_all(t, PICK_WORDS),
        )
    )
    rows.append(
        (
            "6 the status JSON's branch_state",
            [f for f in every if f not in BRANCH_KEY_KEPT and (t := read(f)) and BRANCH_KEYS.search(t)],
            lambda rel, t: BRANCH_KEYS.sub("branch_state", t),
        )
    )
    return rows  # type: ignore[return-value]


def _replace_all(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def main() -> int:
    total = 0
    for label, files, rewrite in plan():  # type: ignore[misc]
        changed = []
        for rel in files:
            text = read(rel)
            if text is None:
                continue
            updated = rewrite(rel, text)
            if updated != text:
                (ROOT / rel).write_text(updated, encoding="utf-8")
                changed.append(rel)
        total += len(changed)
        print(f"row {label}: {len(changed)} file(s) changed")
        for rel in changed:
            print(f"  {rel}")
    print(f"{total} file change(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
