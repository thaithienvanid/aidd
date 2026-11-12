"""A config that says `delegation.default_branch_deploys: true` never gets a looser deploy answer than "a merge into the default branch
deploys", in the reader of an earlier shape and in `aidd upgrade`.

Invariant. The retired key `true` is cut only where an `environments` entry of the same config lists the branch that
`delegation.default_branch` names, by the rule the risk rules use for a push. Anywhere else the reader refuses the config, so the
load fails at the old name and a delegated merge defers, and the upgrade leaves the key for a person. `false` is cut, and a value
that is no boolean is refused. The reader and the upgrade give the same data for each input.
"""

import copy
import tempfile
import unittest
from pathlib import Path

from migration_fixture import CONFIG, Repo
from test_delegation_check import Case, codes
from test_delegation_check import Repo as GitRepo

from aidd import config
from aidd.kernel import documents
from aidd.setup import migrating

KEY = "default_branch_deploys"
MAIN = [{"name": "production", "branches": ["main"]}]


def text_of(environments: str, branch: str, key: str) -> str:
    return f'aidd_version: "1.0.0"\nprofile: team\n{environments}delegation:\n  set_by: "A B <a@b.c>"\n  decides: [git.merge]\n  review_due: "2099-01-01"\n{branch}{key}'


def envs(*entries: tuple[str, str]) -> str:
    return "environments:\n" + "".join(f"  - name: {name}\n    branches: {branches}\n" for name, branches in entries)


DEFAULT = "  default_branch: main\n"
TRUE = f"  {KEY}: true\n"

# name: (the config text, what the reader does, what the upgrade does). A reader that cuts leaves the key out of the data it reads;
# one that refuses gives the text back as it was, so the load fails at the old name.
CUT, REFUSED = "cut", "refused"
CASES = {
    "the key is absent": (text_of(envs(("production", "[main]")), DEFAULT, ""), None, None),
    "false and no environments": (text_of("", DEFAULT, f"  {KEY}: false\n"), CUT, CUT),
    "false and environments that do not list the branch": (text_of(envs(("staging", "[release/*]")), DEFAULT, f"  {KEY}: false\n"), CUT, CUT),
    "false and no default branch": (text_of("", "", f"  {KEY}: false\n"), CUT, CUT),
    "true and no environments": (text_of("", DEFAULT, TRUE), REFUSED, REFUSED),
    "true and an empty environments": (text_of("environments: []\n", DEFAULT, TRUE), REFUSED, REFUSED),
    "true and environments that do not name the branch": (text_of(envs(("staging", "[release/*]")), DEFAULT, TRUE), REFUSED, REFUSED),
    "true and an environment with no branches": (text_of("environments:\n  - name: staging\n", DEFAULT, TRUE), REFUSED, REFUSED),
    "true and a wildcard that does not reach the branch": (text_of(envs(("production", "['main/*']")), DEFAULT, TRUE), REFUSED, REFUSED),
    "true and a name that holds only the start of the branch": (text_of(envs(("production", "[mai]")), DEFAULT, TRUE), REFUSED, REFUSED),
    "true and no default branch": (text_of(envs(("production", "[main]")), "", TRUE), REFUSED, REFUSED),
    "true and an environment that names the branch": (text_of(envs(("staging", "[release/*]"), ("production", "[main]")), DEFAULT, TRUE), CUT, CUT),
    "true and an environment whose wildcard reaches the branch": (text_of(envs(("production", "['ma*']")), DEFAULT, TRUE), CUT, CUT),
    "true and a default branch that is no main": (text_of(envs(("production", "[trunk]")), "  default_branch: trunk\n", TRUE), CUT, CUT),
    "a quoted true": (text_of(envs(("production", "[main]")), DEFAULT, f'  {KEY}: "true"\n'), REFUSED, REFUSED),
    "a quoted yes": (text_of(envs(("production", "[main]")), DEFAULT, f'  {KEY}: "yes"\n'), REFUSED, REFUSED),
    "a number": (text_of(envs(("production", "[main]")), DEFAULT, f"  {KEY}: 1\n"), REFUSED, REFUSED),
    "an empty list": (text_of(envs(("production", "[main]")), DEFAULT, f"  {KEY}: []\n"), REFUSED, REFUSED),
    "a list": (text_of(envs(("production", "[main]")), DEFAULT, f"  {KEY}: [true]\n"), REFUSED, REFUSED),
}


def without_key(data: dict) -> dict:
    out = copy.deepcopy(data)
    out["delegation"].pop(KEY, None)
    return out


class TheReader(unittest.TestCase):
    def test_each_input_is_cut_or_refused_as_the_invariant_says(self):
        for name, (text, reader, _) in CASES.items():
            with self.subTest(name):
                read = config.in_todays_shape(text)
                if reader is None:
                    self.assertEqual(read, text, "no retired name: the text is read as it is")
                elif reader == REFUSED:
                    self.assertEqual(read, text, "refused: the text is returned as written, so the load that follows fails at the old name")
                else:
                    self.assertEqual(documents.parse_yaml(read, CONFIG), without_key(documents.parse_yaml(text, CONFIG)))

    def test_a_refused_config_fails_to_load_and_says_what_to_do_and_a_cut_one_loads(self):
        for name, (text, reader, _) in CASES.items():
            with self.subTest(name):
                read = config.in_todays_shape(text)
                if reader == REFUSED:
                    with self.assertRaises(config.ConfigError) as caught:
                        config.load_text(read)
                    said = str(caught.exception)
                    self.assertIn(f"delegation.{KEY}", said)
                    self.assertNotIn("`aidd upgrade --yes` moves it", said, "the upgrade leaves this one, so the line must not say it moves it")
                    self.assertIn("leaves this one for a person", said)
                    self.assertIn("`branches`", said, "the next step that works: list the branch in an environment")
                else:
                    config.load_text(read)


class TheUpgrade(Repo):
    shape = "today"

    def plan(self, text: str) -> migrating.Plan:
        (self.root / CONFIG).write_bytes(text.encode("utf-8"))
        return migrating.plan(self.root)

    def test_each_input_is_cut_or_left_for_a_person_as_the_invariant_says(self):
        for name, (text, _, upgrade) in CASES.items():
            with self.subTest(name):
                found = self.plan(text)
                if upgrade is None:
                    self.assertEqual((found.lines, found.texts), ([], {}))
                elif upgrade == REFUSED:
                    self.assertEqual(found.texts, {}, "the file stays as it is")
                    [(kind, line)] = found.lines
                    self.assertEqual(kind, "manual")
                    for part in (CONFIG, f"delegation.{KEY}", "`environments`", "`branches`", "`delegation.default_branch`", "`aidd upgrade` again"):
                        self.assertIn(part, line)
                else:
                    [(kind, line)] = found.lines
                    self.assertEqual(kind, "migrate")
                    self.assertIn(f"cut delegation.{KEY} = ", line)
                    written = documents.parse_yaml(found.texts[CONFIG], CONFIG)
                    self.assertEqual(written, without_key(documents.parse_yaml(text, CONFIG)))
                    self.assertEqual(written, documents.parse_yaml(config.in_todays_shape(text), CONFIG), "the upgrade writes what the reader reads")

    def test_a_cut_true_names_the_environment_that_says_it(self):
        found = self.plan(CASES["true and an environment that names the branch"][0])
        self.assertIn("production", found.lines[0][1])
        self.assertNotIn("staging", found.lines[0][1])

    def test_a_config_left_for_a_person_is_cut_by_a_second_run_once_the_person_lists_the_branch(self):
        left = CASES["true and environments that do not name the branch"][0]
        self.assertEqual(self.plan(left).texts, {})
        fixed = left.replace("[release/*]", "[release/*, main]")
        self.assertEqual(self.plan(fixed).lines[0][0], "migrate")


class TheDelegateCheck(Case):
    """The delegate reads the default branch's config in today's shape, so a tip config that still says `true` must defer."""

    ENVIRONMENTS = [{"name": "staging", "branches": ["release/*"]}]

    def checked(self, environments, extra: str) -> dict:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        repo = GitRepo(Path(folder.name).resolve(), environments=environments, extra=extra, decides="[git.merge]")
        return repo.check(repo.change())

    def test_a_tip_config_that_says_the_default_branch_deploys_defers_a_delegated_merge(self):
        result = self.checked(self.ENVIRONMENTS, f"  {KEY}: true\n")
        self.assertEqual(codes(result), ["config_unreadable"])

    def test_honest_configs_are_read_as_before(self):
        """A config with no such key decides as it did. With `false`, or a `true` that an environment backs, the tip still loads: the
        head's own copy of the key is what the head's `aidd test` refuses, which is the unchanged answer for a person who has not upgraded."""
        self.assertEqual(codes(self.checked(self.ENVIRONMENTS, "")), [], "no key: nothing defers")
        for name, environments, extra in (
            ("false", self.ENVIRONMENTS, f"  {KEY}: false\n"),
            ("true, with an environment that lists the default branch", MAIN, f"  {KEY}: true\n"),
        ):
            with self.subTest(name):
                self.assertNotIn("config_unreadable", codes(self.checked(environments, extra)), "the tip's config loads")


if __name__ == "__main__":
    unittest.main()
