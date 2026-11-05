"""`aidd test --changed` names the moves that weaken a check (R334): a new skip marker, a new suppression comment, a
deleted test file, a lowered coverage floor, and lost assertions (R351), from the merge base, untracked files included; never a moved marker, a
stricter check, or a word in prose."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd.testing import weakening


@unittest.skipUnless(shutil.which("git"), "git is required")
class WeakeningMovesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Ada")
        git(self.root, "config", "user.email", "ada@example.com")
        self.write("tests/test_a.py", "def test_a():\n    assert True\n")
        self.write("tests/test_b.py", "def test_b():\n    assert True\n")
        self.write("tests/test_moved.py", "import pytest\n\n@pytest.mark.skip\ndef test_m():\n    pass\n")
        self.write("pyproject.toml", "[tool.coverage.report]\nfail_under = 90\n")
        self.write("setup.cfg", "[coverage:report]\nfail_under = 80\n")
        self.write("src/app.py", "x = 1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        self.base = git(self.root, "rev-parse", "HEAD").strip()

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def test_each_move_is_named_once_and_a_stricter_or_moved_check_is_not(self):
        self.write("tests/test_a.py", "import pytest\n\n@pytest.mark.skip(reason='later')\ndef test_a():\n    assert True\n")
        self.write("src/app.py", "x = 1  # noqa: E501\n")
        self.write("pyproject.toml", "[tool.coverage.report]\nfail_under = 80\n")
        self.write("setup.cfg", "[coverage:report]\nfail_under = 85\n")  # stricter: nothing to say
        self.write("tests/test_moved.py", "import pytest\n\n\n@pytest.mark.skip\ndef test_m():\n    pass\n")  # moved, not added
        self.write("docs/notes.md", "Never add `# noqa` to hide a finding.\n")  # prose
        self.write("web/view.test.ts", "// eslint-disable-next-line\nit('works', () => {})\n")  # untracked
        (self.root / "tests" / "test_b.py").unlink()
        notes = weakening.weakening_notes(str(self.root), self.base)
        joined = "\n".join(notes)
        self.assertTrue(all(n.startswith("a change may weaken a check: ") for n in notes), notes)
        for expected in (
            "tests/test_a.py adds a skip marker (pytest skip or xfail)",
            "src/app.py adds a suppression comment (noqa)",
            "pyproject.toml lowers the coverage floor fail_under in [tool.coverage.report] from 90 to 80",
            "web/view.test.ts adds a suppression comment (eslint-disable)",
            "tests/test_b.py is a test file, deleted",
        ):
            self.assertIn(expected, joined)
        for quiet in ("setup.cfg", "tests/test_moved.py", "docs/notes.md"):
            self.assertNotIn(quiet, joined)
        self.assertEqual(len(notes), 5, notes)

    def test_git_settings_paths_renames_and_strings_never_change_the_answer(self):
        # A person's git settings change diff headers; aidd forces its own, so the answer stays the same.
        git(self.root, "config", "diff.mnemonicPrefix", "true")
        git(self.root, "config", "diff.noprefix", "true")
        self.write("tests/test_é.py", "import unittest\n\n@unittest.skip('x')\nclass T(unittest.TestCase):\n    pass\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "a test with a non-ASCII name")
        git(self.root, "mv", "tests/test_moved.py", "tests/test_renamed.py")  # a rename is no deletion, and no new skip
        self.write(
            "tests/test_a.py",
            "import unittest, shutil\n\n"
            "@unittest.skipUnless(shutil.which('git'), 'git')\n"  # conditional: no move
            "def test_a():\n"
            "    text = '@pytest.mark.skip  # noqa'\n"  # inside a string: no move
            "    assert True\n"
            "++ b/NOTES.md\n"  # content that looks like a header
            "@unittest.skip('later')\n"
            "def test_late():\n    pass\n",
        )
        self.write("pyproject.toml", "[tool.other]\nx = 1\n")  # the floor is gone
        self.write("tests/coverage_floors.py", 'FLOORS = [\n    ("the risk rules", "src/aidd/risk/*", 80),\n]\n')
        notes = weakening.weakening_notes(str(self.root), self.base)
        joined = "\n".join(notes)
        self.assertIn("tests/test_a.py adds a skip marker (unittest skip)", joined)
        self.assertIn("tests/test_é.py adds a skip marker (unittest skip)", joined)  # a non-ASCII path, read as is
        self.assertIn("pyproject.toml removes the coverage floor fail_under in [tool.coverage.report]", joined)
        self.assertNotIn("test_moved.py", joined)
        self.assertNotIn("test_renamed.py", joined)
        self.assertNotIn("noqa", joined)
        self.assertEqual(sum("tests/test_a.py" in n for n in notes), 1, notes)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "floors")
        floors_base = git(self.root, "rev-parse", "HEAD").strip()
        self.write("tests/coverage_floors.py", 'FLOORS = [\n    ("the risk rules", "src/aidd/risk/*", 70),\n]\n')
        self.assertIn(
            "tests/coverage_floors.py lowers the coverage floor the risk rules from 80 to 70", "\n".join(weakening.weakening_notes(str(self.root), floors_base))
        )

    def test_comments_fixtures_moves_and_floors_read_as_meant(self):
        self.write("src/app.py", 'print("don\'t")  # noqa: T201\n')  # an apostrophe before a comment opens no string
        self.write(
            "tests/test_fixture.py",
            'TEXT = """\n@pytest.mark.skip\ndef test_x():\n    pass\n"""\n',  # a test file's text in a fixture: no move
        )
        (self.root / "tests" / "test_b.py").rename(self.root / "tests" / "test_b2.py")  # moved with mv, not added
        self.write("setup.cfg", "[coverage:report]\nfail_under = 85\n")  # was 80: it rises
        notes = weakening.weakening_notes(str(self.root), self.base)
        joined = "\n".join(notes)
        self.assertIn("src/app.py adds a suppression comment (noqa)", joined)
        self.assertNotIn("test_fixture.py", joined)
        self.assertNotIn("test_b", joined)
        self.assertNotIn("setup.cfg", joined)  # 80 to 85 rises
        self.write("pyproject.toml", "[tool.coverage.report]\nfail_under = 85\n")  # was 90: it lowers
        self.assertIn(
            "pyproject.toml lowers the coverage floor fail_under in [tool.coverage.report] from 90 to 85",
            "\n".join(weakening.weakening_notes(str(self.root), self.base)),
        )
        # Reordering the sections hides nothing: each floor is compared with its own section's.
        self.write("pyproject.toml", "[x]\nfail_under = 85\n[y]\nfail_under = 95\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "two floors")
        two = git(self.root, "rev-parse", "HEAD").strip()
        self.write("pyproject.toml", "[y]\nfail_under = 99\n[x]\nfail_under = 85\n")  # x stays 85, y rises to 99
        self.assertEqual(weakening.weakening_notes(str(self.root), two), [])
        self.write("pyproject.toml", "[y]\nfail_under = 85\n[x]\nfail_under = 99\n")  # y drops to 85, written first
        self.assertIn("lowers the coverage floor fail_under in [y] from 95 to 85", "\n".join(weakening.weakening_notes(str(self.root), two)))

    def test_a_quote_in_a_string_or_comment_hides_nothing_and_a_move_out_of_the_tests_is_a_deletion(self):
        self.write("tests/test_a.py", 'x = \'"""\'  # a triple quote inside a string opens nothing\n\n@pytest.mark.skip\ndef test_a():\n    pass\n')
        self.write(
            "tests/test_moved.py",
            '# a """ in a comment opens nothing\n\n@pytest.mark.skip\ndef test_m():\n    pass\n@pytest.mark.skip\ndef test_n():\n    pass\n',
        )
        self.write("src/unbalanced.py", 'TEXT = """\n@pytest.mark.skip  # noqa\n')  # never closed: unsure, so every line counts
        (self.root / "tests" / "test_b.py").rename(self.root / "scripts_b.py")  # moved out of the tests: no longer runs
        joined = "\n".join(weakening.weakening_notes(str(self.root), self.base))
        self.assertIn("tests/test_a.py adds a skip marker", joined)
        self.assertIn("tests/test_moved.py adds a skip marker", joined)
        self.assertIn("src/unbalanced.py adds a suppression comment (noqa)", joined)
        self.assertIn("tests/test_b.py is a test file, deleted", joined)

    def test_a_change_far_away_never_hides_a_marker_and_a_long_line_keeps_its_end(self):
        self.write("src/svc.py", 'def f():\n    """Do the\n    refund flow."""\n    return 1\n\n\ndef g():\n    return 2\n')
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "a docstring")
        base = git(self.root, "rev-parse", "HEAD").strip()
        # Edit the docstring's closing line, and add a suppression far below, in another hunk.
        self.write("src/svc.py", 'def f():\n    """Do the\n    refund and return flow."""\n    return 1\n\n\ndef g():\n    return 2  # noqa: E501\n')
        self.write("src/long.py", "x = " + "1 + " * 3000 + "1  # noqa\n")  # a comment at the end of a padded line
        joined = "\n".join(weakening.weakening_notes(str(self.root), base))
        self.assertIn("src/svc.py adds a suppression comment (noqa)", joined)
        self.assertIn("src/long.py adds a suppression comment (noqa)", joined)

    def test_a_crafted_line_costs_nothing(self):
        import time

        self.write("pyproject.toml", "fail_under" + " " * 200_000 + "x\n")
        start = time.monotonic()
        weakening.weakening_notes(str(self.root), self.base)
        self.assertLess(time.monotonic() - start, 2.0)
        # Padding a line hides nothing at its start: a long line is cut, never skipped.
        self.write("tests/test_a.py", "import pytest\n\n@pytest.mark.skip  # " + "x" * 10_000 + "\ndef test_a():\n    assert True\n")
        self.assertIn("tests/test_a.py adds a skip marker", "\n".join(weakening.weakening_notes(str(self.root), self.base)))
        # A vast file is cut on its own and says so; it never hides another file's move.
        self.write("aaa.txt", ("y" * 1000 + "\n") * 2000)
        git(self.root, "add", "aaa.txt")
        joined = "\n".join(weakening.weakening_notes(str(self.root), self.base))
        self.assertIn("aaa.txt changes more than 1 MiB, so only its start was read", joined)
        self.assertIn("tests/test_a.py adds a skip marker", joined)

    def test_a_line_break_git_does_not_count_shifts_nothing(self):
        # A form feed and U+2028 break a line for Python's splitlines, never for git: the numbers stay git's.
        self.write("src/ff.py", 'TEXT = """\nfixture\x0c\u2028more\n"""\nx = 1\n')
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "a file with odd breaks")
        base = git(self.root, "rev-parse", "HEAD").strip()
        self.write("src/ff.py", 'TEXT = """\nfixture\x0c\u2028more\n"""\nx = 1  # noqa\n')
        self.assertIn("src/ff.py adds a suppression comment (noqa)", "\n".join(weakening.weakening_notes(str(self.root), base)))

    def test_block_comments_regex_literals_renames_overrides_and_moves_hide_nothing(self):
        self.write("web/a.test.js", '/* " */ it.skip("b")\nconst r = /"/; it.skip("c")\n')
        self.write("src/Svc.java", "/* don't */ @Disabled\nclass Svc {}\n")
        self.write("src/mid.py", 'p = "' + "A" * 6000 + '"; x = 1  # noqa\n')
        self.write("Makefile", "test:\n\tpytest --cov-fail-under=0\n")  # turns the project's floor off
        git(self.root, "mv", "setup.cfg", "tox.ini")
        self.write("tox.ini", "[coverage:report]\nfail_under = 10\n")  # renamed, and lowered from 80
        (self.root / "tests" / "test_b.py").rename(self.root / "tests" / "test_b.txt")  # no longer runs as a test
        joined = "\n".join(weakening.weakening_notes(str(self.root), self.base))
        for expected in (
            "web/a.test.js adds a skip marker (JavaScript skip)",
            "src/Svc.java adds a skip marker (JUnit disable)",
            "src/mid.py adds a suppression comment (noqa)",
            "Makefile sets the coverage floor --cov-fail-under to 0",
            "tox.ini lowers the coverage floor fail_under in [coverage:report] from 80 to 10",
            "tests/test_b.py is a test file, deleted",
        ):
            self.assertIn(expected, joined)

    def test_many_markers_cost_little(self):
        import time

        line = "it.skip(" * 1000
        for i in range(20):
            self.write(f"web/t{i}.test.js", (line + "\n") * 40)
        start = time.monotonic()
        weakening.weakening_notes(str(self.root), self.base)
        self.assertLess(time.monotonic() - start, 5.0)

    def test_a_deleted_config_takes_its_floor_with_it(self):
        (self.root / "setup.cfg").unlink()
        self.assertIn("setup.cfg removes the coverage floor fail_under in [coverage:report]", "\n".join(weakening.weakening_notes(str(self.root), self.base)))

    def test_a_test_file_that_loses_assertions_on_net_is_named_unless_a_test_beside_it_gains_them(self):
        base = {
            "tests/test_py.py": "class T:\n    def test_x(self):\n        self.assertEqual(f(), 1)\n        assert g()\n",
            "web/a.test.js": "it('a', () => {\n  expect(a).toBe(1)\n  expect(b).toBe(2)\n})\n",
            "tests/lib.rs": "fn t() {\n    assert_eq!(a, 1);\n}\n",
            "pkg/x_test.go": 'func TestX(t *testing.T) {\n\tif a != 1 {\n\t\tt.Errorf("a")\n\t}\n}\n',
            "tests/test_moved.py": "def test_m():\n    assert m()\n",
            "tests/test_kept.py": "def test_k():\n    assert k()\n",
            "tests/test_text.py": "# assert x\nDOC = '''\nassert y\n'''\n",
            "src/app.py": "assert x\n",
        }
        for rel, text in base.items():
            self.write(rel, text)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "assertions")
        sha = git(self.root, "rev-parse", "HEAD").strip()
        cases = [  # (what the change writes, each file it names with the assertions it loses)
            ({"tests/test_py.py": "class T:\n    def test_x(self):\n        f()\n"}, {"tests/test_py.py": 2}),
            # Commented out, or wrapped in a docstring with the lines kept: a comment or a string asserts nothing.
            ({"tests/test_py.py": "class T:\n    def test_x(self):\n        # self.assertEqual(f(), 1)\n        assert g()\n"}, {"tests/test_py.py": 1}),
            (
                {"tests/test_py.py": 'class T:\n    def test_x(self):\n        """\n        self.assertEqual(f(), 1)\n        assert g()\n        """\n'},
                {"tests/test_py.py": 2},
            ),
            ({"web/a.test.js": "it('a', () => {\n  expect(a).toBe(1)\n})\n"}, {"web/a.test.js": 1}),
            ({"tests/lib.rs": "fn t() {\n}\n", "pkg/x_test.go": "func TestX(t *testing.T) {\n}\n"}, {"tests/lib.rs": 1, "pkg/x_test.go": 1}),
            # A quote that leaves the line unclear: the assertion it seems to add counts for nothing, so the loss shows.
            ({"web/a.test.js": "it('a', () => {\n  const r = /\"/; // expect(a) expect(b)\n})\n"}, {"web/a.test.js": 2}),
            # Moved to a test file beside it, new or changed: nothing lost on net.
            ({"tests/test_moved.py": "def test_m():\n    m()\n", "tests/test_new.py": "def test_m():\n    assert m()\n"}, {}),
            ({"tests/test_moved.py": "def test_m():\n    m()\n", "tests/test_kept.py": "def test_k():\n    assert k()\n    assert m()\n"}, {}),
            # A test beside it gains fewer than it loses: it is still named.
            (
                {"tests/test_py.py": "class T:\n    def test_x(self):\n        f()\n", "tests/test_kept.py": "def test_k():\n    assert k()\n    assert f()\n"},
                {"tests/test_py.py": 2},
            ),
            # Rewritten, in a comment or a string, or outside the tests: nothing to say.
            ({"tests/test_py.py": "class T:\n    def test_x(self):\n        self.assertEqual(f(), 2)\n        assert g() == 3\n"}, {}),
            ({"tests/test_text.py": "DOC = ''\n"}, {}),
            ({"src/app.py": "x = 1\n"}, {}),
        ]
        for writes, named in cases:
            with self.subTest(writes=sorted(writes)):
                for rel, text in writes.items():
                    self.write(rel, text)
                notes = [n for n in weakening.weakening_notes(str(self.root), sha) if "assertion" in n]
                git(self.root, "checkout", "-q", "--", ".")
                git(self.root, "clean", "-qfd")
                expected = [f"{p} loses {n} assertion{'s' if n > 1 else ''} on net" for p, n in sorted(named.items())]
                self.assertEqual([n.split(", ")[0].removeprefix("a change may weaken a check: ") for n in notes], expected, notes)

    def test_a_branch_that_only_adds_tests_says_nothing(self):
        self.write("tests/test_c.py", "def test_c():\n    assert 1 + 1 == 2\n")
        self.assertEqual(weakening.weakening_notes(str(self.root), self.base), [])


if __name__ == "__main__":
    unittest.main()
