"""What the pages promise, checked as facts rather than as exact sentences: a section another page or a
message points at, a command a page tells the reader to run, and a rule a page states. A rewrite that keeps the fact
passes; one that drops it fails. Each row names the regression it guards.

A pin of an exact wording stays where the wording is the contract: a platform's own setting name, a template's table
header that a role fills, a legal citation, or a rule quoted verbatim into adopters' files."""

import contextlib
import io
import shlex
import unittest

from helpers import ROOT, anchors, says

from aidd.cli import parser as cli_parser


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The body under the first heading line that starts with `heading`, up to the next heading of its level or higher."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    level = len(heading.split(" ", 1)[0])
    body = []
    for line in lines[start + 1 :]:
        marks = line.split(" ", 1)[0]
        if marks and set(marks) == {"#"} and len(marks) <= level:
            break
        body.append(line)
    return "\n".join(body)


# A section that a message, a guide, or another page sends the reader to.
ANCHORS = (
    ("docs/TROUBLESHOOTING.md", "a-flag-is-past-its-cleanup-date", "the fix for `aidd doctor`'s warning on a flag past its cleanup date"),
    ("docs/CONTROLS.md", "what-aidd-builds-into-the-product-when-compliance-is-on", "the controls ADOPTION's compliance section links"),
    ("docs/HOW-TO.md", "explore-get-feedback-iterate--fast", "the explore recipe"),
    ("docs/HOW-TO.md", "product-defaults-and-how-to-turn-one-off", "how to turn a product default off"),
    (".agents/skills/aidd/references/spec.md", "specialist-returns-fixed-templates", "the return template the specialist roles fill"),
)

# A command a page tells the reader to run: the page names it with these words in one line, and the example parses.
COMMANDS = (
    (
        "plugins/aidd-team/commands/explore.md",
        ("`aidd new exploration", "--title", "--owner", "--timebox"),
        "new exploration specs/SPEC-1/explore/x --title q --owner product-designer --timebox 30m",
        "the explore command starts an exploration with `aidd new`, with the question, an owner, and a timebox",
    ),
    (
        "README.md",
        ("aidd init", "--profile solo", "--approvers email:"),
        "init --profile solo --approvers email:you@example.com",
        "the solo setup names its Approver in the email form, which works with no platform login",
    ),
    (
        "docs/HOW-TO.md",
        ("`aidd new authz",),
        "new authz 'Admin API' --spec SPEC-12",
        "the how-to tests access control with an authorization matrix",
    ),
    ("docs/HOW-TO.md", ("`aidd new design-system`",), "new design-system", "the how-to sets up one design system"),
    ("docs/HOW-TO.md", ("`aidd new architecture`",), "new architecture", "the how-to sets up one architecture overview"),
    (
        "plugins/aidd-team/commands/autopilot.md",
        ("`--spec <ID>`", "when"),
        "autopilot note 'spec.implement done' --session s1 --spec SPEC-1",
        "an autopilot note names a Spec only when the step worked on one",
    ),
)

# A rule a page states, found as one sentence holding every term, inside the named section when one is given.
STATEMENTS = (
    (
        ".agents/skills/aidd/references/loop.md",
        None,
        ("base branch", "before", "Merge approval", "not after"),
        "the base is taken in before Merge approval, never after it",
    ),
    (
        ".agents/skills/aidd/references/loop.md",
        None,
        ("new Verify", "new approval"),
        "a merge after approval changes the head, so it needs a new Verify and approval",
    ),
    ("llms-install.md", "## 5. Hand back", ("`aidd init`", "`Restart ...`", "pass it on"), "the install hands back init's restart line"),
    ("docs/METHOD.md", "## 4. Objects", ("Proposal", "Initiative", "Epic", "optional"), "a team may start with a Spec"),
    ("docs/METHOD.md", "### 5.3 Autopilot", ("On `ask`", "lease", "`aidd autopilot stop`"), "the run gives its lease back whenever it asks a person"),
    ("CONTRIBUTING.md", None, ("`aidd context`", "minor release"), "an experimental command may change in a minor release"),
    ("plugins/aidd-team/skills/test-design/SKILL.md", None, ("decision table", "as written"), "the verifier reads a Spec's decision table as written"),
    ("plugins/aidd-team/skills/aidd-team/SKILL.md", None, ("`aidd test`", "red on base"), "the red run is `aidd test`'s evidence, not a read-only role's"),
    ("plugins/aidd-team/commands/rollout.md", None, ("Optional", "clean window"), "folding the Design into the architecture docs is an optional follow-up"),
    ("plugins/aidd-team/commands/rollout.md", None, ("only if", "author agrees"), "the follow-up opens only with the author's agreement"),
)


class DocFactTests(unittest.TestCase):
    def test_every_section_a_reader_is_sent_to_exists(self):
        for page, anchor, why in ANCHORS:
            with self.subTest(page=page, anchor=anchor):
                self.assertIn(anchor, anchors(ROOT / page), why)

    def test_every_command_a_page_teaches_is_named_and_parses(self):
        parser = cli_parser.build_parser()
        for page, words, example, why in COMMANDS:
            with self.subTest(page=page, example=example):
                self.assertTrue(any(all(w in line for w in words) for line in read(page).splitlines()), (why, words))
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    try:
                        parser.parse_args(shlex.split(example))
                    except SystemExit:
                        self.fail(f"{why}: `aidd {example}` does not parse: {err.getvalue()}")

    def test_every_rule_a_page_states_is_there(self):
        for page, heading, terms, why in STATEMENTS:
            with self.subTest(page=page, terms=terms):
                text = read(page)
                self.assertTrue(says(section(text, heading) if heading else text, *terms), (why, terms))

    def test_a_statement_holds_its_terms_in_one_sentence(self):
        """The check reads sentences, so terms spread across a page never pass for a rule nobody states."""
        self.assertTrue(says("Plan runs first. It is done when `aidd validate` passes.", "`aidd validate`", "done"))
        self.assertFalse(says("Plan runs first. It is done when `aidd validate` passes.", "Plan", "`aidd validate`"))


if __name__ == "__main__":
    unittest.main()
