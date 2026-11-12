"""A push reads as its words say, and a setting that may redirect it only raises the level.

The invariant (A6, final shape): the level of every `git push` is the stricter of the reading of its words (`push_reach`, as it
was at bc6b843f) and one raise-only check of git's settings (`push_config.redirects`). The check holds a closed list of three facts:
for the remote the push resolves to, `remote.<name>.push` is set, or `remote.<name>.mirror` is true; and `push.default` is `upstream`,
`tracking`, or `matching`. With all of them off the check adds nothing, so the level is the words' reading: the same function,
called with the check off. With one on, every push reads as one that may reach the default branch, with a note, except that
`remote.<name>.push` does not count for a push whose every refspec names its destination (`<src>:<dst>`). Any other
setting changes no level.
"""

from __future__ import annotations

import functools
import itertools
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import shared_reads

from aidd import config, risk
from aidd.risk import push_config

RS = risk.rule_set(None)


def reads_once(test):
    """Run a test that only reads the repository with aidd's git reads shared: each ref and setting is read once for all its rows.
    The block fails the test if the repository's refs, HEAD, or config change inside it (`shared_reads.shared_git_reads`)."""

    @functools.wraps(test)
    def wrapped(self):
        with shared_reads.shared_git_reads(self.repo):
            return test(self)

    return wrapped


def answer(line: str, cwd: str, rs: risk.RuleSet = RS) -> dict:
    return risk.command_level(rs, line, cwd=cwd)


def words_reading(line: str, cwd: str) -> dict:
    """The reading of the words alone: the same function, with the check of settings off."""
    with mock.patch.object(push_config, "redirects", return_value=[]):
        return answer(line, cwd)


class ARepositoryOnFeat(unittest.TestCase):
    """A repository on `feat`, tracking `origin/main`, with remotes `origin` and `other`; git's settings are put back after each row."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = str(Path(cls.tmp.name).resolve() / "repo")
        Path(cls.repo).mkdir()
        helpers.git(cls.repo, "init", "-q", "-b", "main")
        Path(cls.repo, "notes.txt").write_text("x\n", encoding="utf-8")
        helpers.git(cls.repo, "add", "-A")
        helpers.git(cls.repo, "commit", "-q", "-m", "base")
        for remote in ("origin", "other"):
            helpers.git(cls.repo, "remote", "add", remote, f"https://example.invalid/{remote}.git")
        for branch in ("main", "feat"):
            helpers.git(cls.repo, "update-ref", f"refs/remotes/origin/{branch}", "HEAD")
        helpers.git(cls.repo, "switch", "-q", "-c", "feat")
        helpers.git(cls.repo, "branch", "-q", "-u", "origin/main", "feat")
        cls.config_file = Path(cls.repo, ".git", "config")
        cls.base_config = cls.config_file.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.addCleanup(lambda: self.config_file.write_text(self.base_config, encoding="utf-8"))

    def configure(self, settings: dict[str, str]) -> None:
        for key, value in settings.items():
            helpers.git(self.repo, "config", "--local", key, value)

    def reading(self):
        """The block in which aidd reads each ref and setting once; configure before it, never inside it."""
        return shared_reads.shared_git_reads(self.repo)


# The grammar: each option with and without its value, in each position, and each refspec form, bare and in a wrapper.
OPTIONS = (
    "",
    "-u",
    "--set-upstream",
    "-q",
    "--no-verify",
    "--force-with-lease",
    "-o x",
    "--push-option x",
    "--push-option=x",
    "--repo=other",
    "--exec x",
    "--bogus",
)
REFSPECS = ("", "feat", "HEAD", "feat:feat", "feat:main", "main", ":old", "v1.0", "refs/heads/*:refs/heads/*")
WRAPPERS = ("{}", "sh -c '{}'", "env {}", "sudo {}")


def grammar() -> list[str]:
    lines = []
    for option, refspec, wrapper in itertools.product(OPTIONS, REFSPECS, WRAPPERS):
        for at in (0, 1, 2):
            words = ["origin", refspec] if refspec else ["origin"]
            words = [*words[:at], *option.split(), *words[at:]] if option else words
            lines.append(wrapper.format(" ".join(["git push", *words])))
    return sorted(set(lines))[::17]  # about 50 lines, spread over the whole grammar


class TheWordsReadingIsWhatItWasWithEverySettingOffTests(ARepositoryOnFeat):
    @reads_once
    def test_the_level_and_the_actions_are_the_words_reading_for_every_row(self):
        for line in grammar():
            with self.subTest(line=line):
                found, words = answer(line, self.repo), words_reading(line, self.repo)
                self.assertEqual(found, words)
                self.assertNotIn("notes", found)

    @reads_once
    def test_the_rows_the_review_named_keep_the_level_they_had(self):
        # An option that takes a value was read as the remote, so these asked before; they must not drop.
        for line in (
            "git push -o merge_request.merge_when_pipeline_succeeds origin feat",
            "git push --push-option merge_request.merge_when_pipeline_succeeds origin feat",
            "git push --exec x origin feat",
            "git push --receive-pack x origin feat",
        ):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "ask")

    @reads_once
    def test_a_git_variable_before_another_command_touches_no_push(self):
        self.assertEqual(answer("GIT_PAGER=cat git log; git push origin feat", self.repo)["level"], "allow")


class AnySettingOnTheClosedListRaisesEveryPushTests(ARepositoryOnFeat):
    # The three facts, each as git settings: the strict level shows for the push with or without a refspec.
    ON = (
        {"remote.origin.push": "refs/heads/feat:refs/heads/main"},
        {"remote.origin.push": "HEAD"},
        {"remote.origin.mirror": "true"},
        {"push.default": "upstream"},
        {"push.default": "tracking"},
        {"push.default": "matching"},
    )
    LINES = (
        "git push",
        "git push origin",
        "git push origin feat",
        "git push -u origin feat",
        "git push origin HEAD",
        "sh -c 'git push origin feat'",
        "env git push",
    )

    def test_each_setting_raises_each_push_and_is_named(self):
        for settings in self.ON:
            self.configure(settings)
            try:
                with self.reading():  # the setting stays as it is for every line
                    for line in self.LINES:
                        with self.subTest(settings=settings, line=line):
                            found = answer(line, self.repo)
                            self.assertEqual(found["level"], "ask", found)
                            key = next(iter(settings))
                            self.assertTrue(any(key in n and "git config --get-regexp" in n for n in found["notes"]), found.get("notes"))
            finally:
                self.config_file.write_text(self.base_config, encoding="utf-8")

    def test_a_push_that_names_a_refspec_reads_the_remotes_push_setting(self):
        self.configure({"remote.origin.push": "refs/heads/feat:refs/heads/main"})
        self.assertEqual(answer("git push origin feat", self.repo)["level"], "ask")

    def test_only_the_remote_the_push_resolves_to_counts(self):
        self.configure({"remote.other.push": "refs/heads/feat:refs/heads/main"})
        self.assertEqual(answer("git push", self.repo)["level"], "allow")  # origin
        self.assertEqual(answer("git push origin feat", self.repo)["level"], "allow")
        self.assertEqual(answer("git push other feat", self.repo)["level"], "ask")
        self.assertEqual(answer("git push -o x other feat", self.repo)["level"], "ask", "with an option that takes a value, any word may be the remote")
        self.assertEqual(answer("git push --repo=other", self.repo)["level"], "ask")
        self.configure({"branch.feat.pushRemote": "other"})
        self.assertEqual(answer("git push", self.repo)["level"], "ask")

    def test_a_false_mirror_raises_nothing(self):
        self.configure({"remote.origin.mirror": "false"})
        self.assertEqual(answer("git push", self.repo)["level"], "allow")


class APushThatNamesEveryDestinationIsNotRemappedByTheRemotesPushTests(ARepositoryOnFeat):
    """Invariant: git ranks a command line's refspecs above `remote.<name>.push` and applies that setting only to a `<src>` with no
    `:<dst>`. So with it set, a push whose every refspec is `<src>:<dst>` reads as its words do, and any other push still asks.
    `remote.<name>.mirror` and `push.default` raise as before."""

    PUSH = {"remote.origin.push": "refs/heads/feat:refs/heads/main"}
    NAMED = (
        "git push origin feat:feat",
        "git push origin +feat:feat",
        "git push origin feat:feat HEAD:feat",
        "git push -u origin feat:feat",
        "git push origin :old",
        "sh -c 'git push origin feat:feat'",
        "env git push origin feat:feat",
    )
    NOT_NAMED = (
        "git push",
        "git push origin",
        "git push origin feat",
        "git push origin HEAD",
        "git push origin feat feat:feat",  # one refspec has no destination
        "git push origin feat:",  # an empty destination names none
        "git push origin tag v1",
        "git push -o x origin feat:feat",  # with an option that takes a value, no word is known to be a refspec
        "git push --repo origin feat:feat",
        "git push --delete origin feat",
    )

    def test_a_push_that_names_every_destination_reads_as_its_words_do(self):
        self.configure(self.PUSH)
        with self.reading():
            for line in self.NAMED:
                with self.subTest(line=line):
                    found = answer(line, self.repo)
                    self.assertEqual(found, words_reading(line, self.repo))
                    self.assertNotIn("notes", found)
            self.assertEqual(answer("git push origin feat:feat", self.repo)["level"], "allow", "an ordinary push of one's own branch is not asked")

    def test_every_other_push_still_asks_and_names_the_setting(self):
        self.configure(self.PUSH)
        with self.reading():
            for line in self.NOT_NAMED:
                with self.subTest(line=line):
                    found = answer(line, self.repo)
                    self.assertEqual(found["level"], "ask", found)
                    self.assertTrue(any("remote.origin.push" in n for n in found["notes"]), found.get("notes"))

    def test_naming_the_default_branch_still_asks_for_its_own_reason(self):
        self.configure(self.PUSH)
        with self.reading():
            for line in ("git push origin feat:main", "git push origin HEAD:main", "git push origin feat:feat main:main"):
                with self.subTest(line=line):
                    self.assertEqual(answer(line, self.repo)["level"], "ask")

    def test_a_mirror_and_a_redirecting_default_still_raise_a_push_that_names_every_destination(self):
        for settings in ({"remote.origin.mirror": "true"}, {"push.default": "upstream"}, {"push.default": "matching"}):
            with self.subTest(settings=settings):
                self.configure(settings)
                try:
                    self.assertEqual(answer("git push origin feat:feat", self.repo)["level"], "ask")
                finally:
                    self.config_file.write_text(self.base_config, encoding="utf-8")

    def test_the_same_holds_for_a_push_to_another_remote_with_the_setting(self):
        self.configure({"remote.other.push": "refs/heads/feat:refs/heads/main"})
        self.assertEqual(answer("git push other feat:feat", self.repo), words_reading("git push other feat:feat", self.repo))


class ADashCOnTheGitCommandCountsAsTheConfigDoesTests(ARepositoryOnFeat):
    """The three facts count when a `-c` or `--config-env` on the same git command sets them, never any other key."""

    ASKS = (
        "git -c remote.origin.push=HEAD:main push",
        "git -c remote.origin.push=HEAD:main push origin feat",
        "git -c Remote.origin.PUSH=x push",
        "git -c remote.origin.mirror=true push origin feat",
        "git -c remote.origin.mirror push",
        "git -c push.followTags=true push origin feat",
        "git -c Push.FollowTags push origin feat",
        "git -c branch.feat.pushRemote=other push",
        "git --config-env=remote.other.push=VAR push origin feat",
        "git -c push.default=upstream push",
        "git -c push.default=matching push origin feat",
        "git --config-env=push.default=VAR push",
        "git --config-env push.default=VAR push origin feat",
        "git --config-env=remote.origin.push=VAR push",
        "GIT_X=1 git -c push.default=matching push",
        "sh -c 'git -c push.default=upstream push'",
        "git -c include.path=/tmp/x.cfg push origin feat",
        "git -c includeIf.gitdir:/x/.path=/tmp/x.cfg push",
        "git --config-env=include.path=VAR push",
    )
    # Another key reads as it did: `-c push.*` and `-c remote.*` already ask through the tag and release patterns, so the rows are the keys that never did.
    ALLOWS = (
        "git -c user.name=x push origin feat",
        "git -c core.editor=vi push",
        "git --config-env=user.name=VAR push",
    )

    @reads_once
    def test_the_three_facts_raise_a_push(self):
        for line in self.ASKS:
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found["level"], "ask", found)
                self.assertTrue(any("git config --get-regexp" in n for n in found["notes"]), found.get("notes"))

    @reads_once
    def test_any_other_key_changes_no_level(self):
        for line in self.ALLOWS:
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found["level"], "allow", found)
                self.assertNotIn("notes", found)

    def test_a_dash_c_adds_to_the_config_and_never_hides_it(self):
        self.configure({"remote.origin.push": "HEAD:main"})
        self.assertEqual(answer("git -c remote.origin.push= push origin feat", self.repo)["level"], "ask")


class TheCommandCheckReadsTheSameWordsTheMatcherDidTests(ARepositoryOnFeat):
    """A `-c` key that may steer a push is found in the words the matcher read for that call, so every form the matcher accepts as a
    push shows it. No value is read: a valueless key and a key from the environment count the same as any other."""

    PUSHES = ("git push origin feat", "git push", "git push -u origin feat")
    FORMS = ("{}", "({})", "( {} )", "{{ {}; }}", "{} >/dev/null", "{} 2>&1", "{} </dev/null", "sh -c '{}'", "env {}", "sudo {}", "time {}", "FOO=1 {}")

    @reads_once
    def test_every_form_with_a_steering_key_reads_strict_and_names_it(self):
        for push, form in itertools.product(self.PUSHES, self.FORMS):
            line = form.format(push.replace("git push", "git -c remote.x.push=HEAD:main push", 1))
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found["level"], "ask", found)
                self.assertTrue(any("remote.x.push" in n for n in found["notes"]), found.get("notes"))

    @reads_once
    def test_the_same_forms_without_the_key_read_as_the_words_do(self):
        for push, form in itertools.product(self.PUSHES, self.FORMS):
            line = form.format(push)
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found, words_reading(line, self.repo))
                self.assertNotIn("notes", found)

    @reads_once
    def test_the_second_of_two_pushes_on_a_line_keeps_its_key(self):
        for line in (
            "git push origin feat && git -c remote.x.push=HEAD:main push origin feat",
            "git -c remote.x.push=HEAD:main push origin feat && git push origin feat",
            "git push origin feat; git -c remote.x.push=HEAD:main push origin feat",
        ):
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found["level"], "ask")
                self.assertTrue(any("remote.x.push" in n for n in found["notes"]), found.get("notes"))
        self.assertEqual(answer("git push origin feat && git push origin feat", self.repo)["level"], "allow")

    @reads_once
    def test_a_command_with_no_git_words_that_the_matcher_read_as_a_push_reads_strict(self):
        self.assertEqual(push_config.steering_keys(["echo", "hi"]), [push_config.UNREADABLE])
        self.assertEqual(push_config.steering_keys(["FOO=1", "git", "-c", "user.name=x", "push"]), [])


class AMirrorIsReadAsGitReadsIt(ARepositoryOnFeat):
    """`remote.<name>.mirror` is a boolean, and git parses it: `yes`, `on`, `1`, and a key with no value are true."""

    def with_config(self, text: str) -> None:
        self.config_file.write_text(self.base_config + text, encoding="utf-8")

    def test_each_spelling_git_reads_as_true_raises_the_push(self):
        for spelling in ("= true", "= yes", "= on", "= 1", "= 2", "", "= banana"):
            with self.subTest(spelling=spelling):
                self.with_config(f'[remote "origin"]\n\tmirror {spelling}\n')
                self.assertEqual(answer("git push", self.repo)["level"], "ask")

    def test_each_spelling_git_reads_as_false_raises_nothing(self):
        for spelling in ("= false", "= no", "= off", "= 0"):
            with self.subTest(spelling=spelling):
                self.with_config(f'[remote "origin"]\n\tmirror {spelling}\n')
                self.assertEqual(answer("git push", self.repo)["level"], "allow")

    def test_a_mirror_set_twice_has_its_last_value_as_in_git(self):
        """Both directions: a false then a true is a mirror, and a true then a false is none."""
        for values, level in ((("false", "true"), "ask"), (("true", "false"), "allow")):
            with self.subTest(values=values):
                self.with_config("".join(f'[remote "origin"]\n\tmirror = {v}\n' for v in values))
                self.assertEqual(answer("git push", self.repo)["level"], level)

    def test_a_push_key_with_no_value_counts_as_set(self):
        self.with_config('[remote "origin"]\n\tpush\n')
        self.assertEqual(answer("git push origin feat", self.repo)["level"], "ask")


class APatternRefspecReachesTheDefaultBranchTests(ARepositoryOnFeat):
    """`*` in a refspec sends every branch it matches, the default one too. It only raises: the rest reads as before."""

    LINES = (
        "git push origin 'refs/heads/*:refs/heads/*'",
        "git push origin '+refs/heads/*:refs/heads/*'",
        "git push origin 'feat*'",
        "git push origin 'refs/tags/*:refs/tags/*'",
    )

    @reads_once
    def test_each_pattern_reads_as_the_default_branch(self):
        for line in self.LINES:
            with self.subTest(line=line):
                found = answer(line, self.repo)
                self.assertEqual(found["level"], "ask")
                self.assertIn("default", {e["branch"] for e in found["actions"]})

    @reads_once
    def test_a_pattern_never_hides_an_environment_the_push_reaches(self):
        rs = risk.rule_set(config.load_text('aidd_version: "1.0.0"\nprofile: team\nenvironments:\n  - {name: prod, tags: ["*"]}\n'))
        found = answer("git push origin 'refs/tags/*:refs/tags/*'", self.repo, rs)
        self.assertIn("deploy.run", {e["action"] for e in found["actions"]})


class TheWordsReadingKeepsWhatItNeverReadTests(ARepositoryOnFeat):
    """Exact option names only, and `GIT_DIR` and `GIT_WORK_TREE` name another repository: both as before. An abbreviated option
    name, or any other variable, is not read."""

    @reads_once
    def test_an_abbreviated_option_name_is_not_read(self):
        for line in ("git push --mir origin feat", "git push --al origin feat", "git push --bran origin feat"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "allow")
        for line in ("git push --mirror origin feat", "git push --all origin feat"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "ask")

    @reads_once
    def test_a_git_directory_names_another_repository(self):
        for line in ("GIT_DIR=/tmp/x git push origin feat", "GIT_WORK_TREE=/tmp/x git push origin feat"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "ask")
        self.assertEqual(answer("GIT_PAGER=cat git push origin feat", self.repo)["level"], "allow")


class AHarmlessSettingChangesNoLevelTests(ARepositoryOnFeat):
    HARMLESS = (
        {"push.followTags": "true"},
        {"push.autoSetupRemote": "true"},
        {"push.gpgSign": "if-asked"},
        {"push.useForceIfIncludes": "true"},
        {"push.default": "simple"},
        {"push.default": "current"},
        {"push.default": "nothing"},
        {"branch.feat.merge": "refs/heads/other-name"},  # an upstream of another name, under the default `simple`
        {"branch.feat.pushRemote": "origin"},
        {"remote.pushDefault": "origin"},
        {"push.pushOption": "x"},
        {"remote.other.mirror": "true"},  # another remote's
    )
    ORDINARY = ("git push", "git push origin", "git push origin feat", "git push -u origin feat", "git push origin HEAD")

    def test_ordinary_pushes_keep_their_level(self):
        for settings in self.HARMLESS:
            self.configure(settings)
            try:
                with self.reading():  # the setting stays as it is for every line
                    for line in self.ORDINARY:
                        with self.subTest(settings=settings, line=line):
                            found = answer(line, self.repo)
                            self.assertEqual(found["level"], "allow", found)
                            self.assertNotIn("notes", found)
            finally:
                self.config_file.write_text(self.base_config, encoding="utf-8")

    @reads_once
    def test_the_default_branch_still_asks(self):
        for line in ("git push origin main", "git push -u origin main", "git push origin feat:main"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "ask")


class OnlyAnUnreadableBranchReadsStrictTests(ARepositoryOnFeat):
    """The strict reading of an unknown branch holds for a push or a merge whose branch git cannot tell, never for an action that
    reads no branch."""

    CONFIG = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: git.commit, branch: default, level: ask}\n'

    def rules(self) -> risk.RuleSet:
        return risk.rule_set(config.load_text(self.CONFIG))

    @reads_once
    def test_a_commit_on_a_readable_branch_keeps_its_level(self):
        rs = self.rules()
        for line in ("git commit -m x", "git commit --amend"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo, rs)["level"], "allow")

    def test_a_push_or_a_merge_from_a_detached_head_reads_strict(self):
        helpers.git(self.repo, "switch", "-q", "--detach")
        self.addCleanup(lambda: helpers.git(self.repo, "switch", "-q", "feat"))
        for line in ("git push", "git push origin", "git merge feat"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo)["level"], "ask")


if __name__ == "__main__":
    unittest.main()
