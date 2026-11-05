"""What the pages promise, checked as facts rather than as exact sentences: a section another page or a
message points at, a command a page tells the reader to run, and a rule a page states. A rewrite that keeps the fact
passes; one that drops it fails. Each row names the regression it guards.

A pin of an exact wording stays where the wording is the contract: a platform's own setting name, a template's table
header that a role fills, a legal citation, or a rule quoted verbatim into adopters' files."""

import contextlib
import io
import re
import shlex
import unittest

import helpers
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
    ("docs/GUIDE.md", "every-coding-agent", "the harness list that the counts and the README link"),
    (".agents/skills/aidd/references/spec-returns.md", "specialist-returns-fixed-templates", "the return template the specialist roles fill"),
)

# A command a page tells the reader to run: the page names it with these words in one line, and the example parses.
COMMANDS = (
    (
        "plugins/aidd-team/commands/specify.md",
        ("`aidd new exploration", "--title", "--role", "--timebox"),
        "new exploration specs/SPEC-1/explore/x --title q --role product-designer --timebox 30m",
        "the specify command's explore mode starts an exploration with `aidd new`, with the question, an owner, and a timebox",
    ),
    (
        "README.md",
        ("aidd init", "--aidd-team"),
        "init --aidd-team",
        "the README sets up the delivery team with `aidd init --aidd-team`",
    ),
    (
        "docs/GLOSSARY.md",
        ("`aidd new authz-matrix`",),
        "new authz-matrix 'Admin API' --spec SPEC-12",
        "the glossary tests access control with an authorization matrix",
    ),
    ("docs/GLOSSARY.md", ("`aidd new design-system`",), "new design-system", "the glossary sets up one design system"),
    ("docs/GLOSSARY.md", ("`aidd new architecture`",), "new architecture", "the glossary sets up one architecture overview"),
)

# A rule a page states, found as one sentence holding every term, inside the named section when one is given.
STATEMENTS = (
    (
        ".agents/skills/aidd/references/loop.md",
        None,
        ("default branch", "before", "Merge approval", "never a rebase"),
        "the default branch is taken in with a merge before Merge approval, never a rebase of a pushed branch",
    ),
    (
        ".agents/skills/aidd/references/loop.md",
        None,
        ("new Verify", "new ask"),
        "a new head after the yes needs a new Verify and a new ask",
    ),
    ("llms-install.md", "## 5. Hand back", ("`aidd init`", "`Restart ...`", "pass it on"), "the install hands back init's restart line"),
    ("docs/METHOD.md", "### 4.3 Work items", ("Proposal", "Intent", "optional"), "a team may start with a Spec"),
    ("docs/METHOD.md", "### 6.6 Headless runs", ("`ask`", "stop"), "a headless run stops at an ask"),
    ("CONTRIBUTING.md", None, ("experimental", "minor release"), "an experimental name may change in a minor release"),
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

    METHOD_LINK = re.compile(r"METHOD(?:\.md)?#([\w-]+)")
    METHOD_NUMBER = re.compile(r"METHOD(?:\.md)? §(\d+(?:\.\d+)?)(\]\([^)]*METHOD\.md#([\w-]+)\))?")

    def test_a_citation_of_the_method_names_a_section_that_exists_and_never_a_bare_number(self):
        """Invariant: every `METHOD.md#anchor` in a shipped file resolves to a heading, and a section number is cited
        only as the text of a link whose anchor is that section. A bare `§5` stays right only until a section moves,
        and `roles.schema.json` once sent a reader to the gates for the loop."""
        method = anchors(ROOT / "docs/METHOD.md")
        found = []
        for rel in helpers.repo_files():
            if not rel.endswith((".md", ".json", ".py", ".yaml", ".yml")) or rel.startswith(("tests/", "evals/", "docs/rfcs/")) or rel == "CHANGELOG.md":
                continue
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            found += [f"{rel}: #{m[1]} is no heading of METHOD.md" for m in self.METHOD_LINK.finditer(text) if m[1] not in method]
            for m in self.METHOD_NUMBER.finditer(text):
                if not (m[3] and m[3].startswith(m[1].replace(".", "") + "-")):
                    found.append(f"{rel}: cite METHOD.md §{m[1]} as a link to its anchor, such as `[METHOD.md §{m[1]}](METHOD.md#...)`")
        self.assertEqual(found, [])

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

    def test_the_readme_lists_every_coding_agent_aidd_wires_in_alphabetical_order(self):
        """The README's agents bullet names each harness label once, sorted: a new harness without a name there drifts from the count."""
        from aidd import config

        bullet = next(line for line in read("README.md").splitlines() if line.startswith("- **Your agents.**"))
        listed = bullet.split("in alphabetical order: ", 1)[1].split(". ", 1)[0]
        listed = re.sub(r"<!--.*?-->", "", listed, flags=re.S)  # generated-block markers, not part of the sentence
        names = [n.removeprefix("and ") for n in listed.split(", ")]
        self.assertEqual(names, sorted(h.label for h in config.HARNESSES.values()))

    def test_a_statement_holds_its_terms_in_one_sentence(self):
        """The check reads sentences, so terms spread across a page never pass for a rule nobody states."""
        self.assertTrue(says("Plan runs first. It is done when `aidd validate` passes.", "`aidd validate`", "done"))
        self.assertFalse(says("Plan runs first. It is done when `aidd validate` passes.", "Plan", "`aidd validate`"))


if __name__ == "__main__":
    unittest.main()
