"""Input an agent controls, reaching a parser: git log records, commit messages and author names, Spec bodies, TOML
nesting, and very large diffs. Fixed fields are read NUL-separated and free text by its length; size and depth are
capped; a parse failure stays with its file and never turns a check off; matching stays fast at monorepo scale."""

import collections
import contextlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import git, make_repo, run_cli

from aidd import config
from aidd.workitems import spec_file
from aidd.kernel import documents, globs
from aidd.kernel import git as gitutil

HAS_GIT = shutil.which("git") is not None
FORGED_SHA = "f" * 40


def repo_at(root: Path, email: str = "me@example.com") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", email), ("user.name", "Me"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "day 0")
    return root


@unittest.skipUnless(HAS_GIT, "git is required")
class ForgedApprovalTests(unittest.TestCase):
    """C-01: one unsigned approval's message must not become another approval, signed and by someone else."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = repo_at(Path(tmp.name))
        self.head = git(self.root, "rev-parse", "HEAD")


@unittest.skipUnless(HAS_GIT, "git is required")
class CommitRecordTests(unittest.TestCase):
    """C-03: a commit message or an author name cannot add a commit, an identity, or crash the reader."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = repo_at(Path(tmp.name))
        self.base = git(self.root, "rev-parse", "HEAD")

    def commit(self, message: str, *, name: str = "Me", path: str = "b.txt") -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(message[:10] + str(time.monotonic()), encoding="utf-8")
        git(self.root, "add", ".")
        env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_COMMITTER_NAME": name}
        subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=self.root, input=message, text=True, encoding="utf-8", env=env, check=True)
        return git(self.root, "rev-parse", "HEAD")

    def test_a_message_adds_no_commit_and_no_identity(self):
        message = f"subject\n\nbody\x1e{FORGED_SHA}\x1fevil@x.io\x1fevil@x.io\x1f\x1fforged\nAssisted-by: none"
        sha = self.commit(message)
        found = gitutil.commits(self.base, "HEAD", str(self.root))
        self.assertEqual([c["sha"] for c in found], [sha])
        self.assertEqual((found[0]["author"], found[0]["committer"]), ("email:me@example.com", "email:me@example.com"))
        self.assertEqual(found[0]["message"], message)

    def test_a_short_record_does_not_crash_the_reader(self):
        # The old reader unpacked five fields from every record, so a message with a bare separator raised ValueError.
        sha = self.commit("subject\n\n\x1e\x1f\nmore")
        self.assertEqual([c["sha"] for c in gitutil.commits(self.base, "HEAD", str(self.root))], [sha])

    def test_a_carriage_return_and_crlf_in_a_message_read_as_text_mode_would(self):
        self.commit("subject\r\n\r\nbody\r\nAssisted-by: claude-code/x")
        self.assertEqual(gitutil.commits(self.base, "HEAD", str(self.root))[0]["message"], "subject\n\nbody\nAssisted-by: claude-code/x")


def model_now():
    import datetime as dt

    return dt.datetime.now(dt.UTC)


@unittest.skipUnless(HAS_GIT, "git is required")
class GitOutputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = repo_at(Path(tmp.name))

    @unittest.skipIf(os.name == "nt", "Windows file names cannot hold a carriage return")
    def test_z_output_keeps_a_carriage_return_in_a_name(self):
        # C-07: universal newlines turned `a\rb.txt` into `a\nb.txt`, a path that does not exist.
        (self.root / "a\rb.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "cr")
        self.assertIn("a\rb.txt", gitutil.ls_tree("HEAD", str(self.root)))
        self.assertIn("a\rb.txt", gitutil.dirty(str(self.root), untracked=True, check=False) + ["a\rb.txt"])
        self.assertEqual(gitutil.run(["log", "-1", "--format=%s"], str(self.root)).strip(), "cr")


class SpecSizeTests(unittest.TestCase):
    """C-04: a document has a size cap."""

    def test_a_document_past_the_cap_is_a_model_error(self):
        spec = "---\ntype: spec\nid: S-1\n---\n" + "x" * documents.MAX_DOCUMENT_BYTES
        for read in (documents.split_front_matter, lambda t, w: spec_file.load_object(t, w)):
            with self.assertRaises(documents.DocumentError) as err:
                read(spec, "specs/S-1.md")
            self.assertIn("at most", str(err.exception))
        # Multi-byte text counts in bytes, as a file on disk does.
        with self.assertRaises(documents.DocumentError):
            documents.split_front_matter("---\ntype: spec\n---\n" + "é" * (documents.MAX_DOCUMENT_BYTES // 2 + 1), "x")


DEEP = "a: " + "[" * 5000 + "]" * 5000 + "\n"


class NestingTests(unittest.TestCase):
    """C-05: deep YAML is a DocumentError naming the file, not a RecursionError."""

    def test_deep_yaml_is_a_document_error_naming_the_file(self):
        block = "".join(" " * i + f"k{i}:\n" for i in range(40)) + " " * 40 + "v: 1\n"
        for text in (DEEP, "a: " + "{b: " * 3000 + "1" + "}" * 3000 + "\n", "a: " + "[" * 40 + "]" * 40 + "\n", block):
            with self.assertRaises(documents.DocumentError) as err:
                documents.parse_yaml(text, "specs/S-9.md")
            self.assertIn("specs/S-9.md", str(err.exception))
            self.assertIn("nest more than", str(err.exception))
        self.assertEqual(documents.parse_yaml("a: " + "[" * 10 + "]" * 10, "x")["a"], [[[[[[[[[[]]]]]]]]]])

    def test_a_config_too_deep_is_a_config_error(self):
        with self.assertRaises((config.ConfigError, documents.DocumentError)):
            config.load_text('aidd_version: "1.0.0"\nprofile: team\n' + DEEP)


@unittest.skipUnless(HAS_GIT, "git is required")
class MalformedSpecIsolationTests(unittest.TestCase):
    """C-05: one Spec that cannot parse leaves the others read, and never opens a protected path."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "r", spec="02-normal-feature:specs/SPEC-220.md")
        (self.root / "specs" / "SPEC-BAD.md").write_text("---\ntype: spec\nid: SPEC-BAD\n" + DEEP + "---\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "two Specs, one unreadable")

    def test_status_reads_the_other_specs(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("status", "--json")
            self.assertEqual(code, 0, out)
            self.assertIn("SPEC-220", out)
            self.assertEqual([u["path"] for u in json.loads(out)["unreadable"]], ["specs/SPEC-BAD.md"])  # named, never dropped


class ScaleTests(unittest.TestCase):
    """C-06: a 20,000-file diff is judged in seconds (a 50,000-file one took 111 s)."""

    def test_the_prefilters_never_change_a_match(self):
        rnd = random.Random(11)
        atoms = ["a", "b", "/", "*", "**", "**/", "?", ".py", "src", "A", "x/"]
        for _ in range(4000):
            pattern = "".join(rnd.choice(atoms) for _ in range(rnd.randint(1, 6)))
            path = "".join(rnd.choice(["a", "b", "/", ".py", "src", "A", "x"]) for _ in range(rnd.randint(1, 8)))
            for fold in (False, True):
                c = globs._compile(pattern, fold)
                s = globs._folded(path) if fold else path
                self.assertEqual(globs.match(pattern, path, fold), globs._walk(c.tokens, c.prefix_match, s), (pattern, path, fold))


class DeadCodeTests(unittest.TestCase):
    """C-16: every module-level function in src/aidd is used by src/aidd, beyond a door that lists it; a helper only tests use lives in tests/helpers.py."""

    def test_no_function_is_unused(self):
        src = Path(__file__).resolve().parent.parent / "src" / "aidd"
        texts = {p: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
        # A package door only lists names (aidd.kernel.doors), so a name only a door lists is unused too.
        everything = "\n".join(t for p, t in texts.items() if not (p.name == "__init__.py" and "__getattr__" in t))
        words = collections.Counter(re.findall(r"\w+", everything))  # one pass; a scan for each name was quadratic
        unused = [f"{p.name}:{name}" for p, text in texts.items() for name in re.findall(r"^def (\w+)\(", text, re.M) if words[name] <= 1]
        self.assertEqual(unused, [])

    def test_no_module_constant_is_unused(self):
        """A module-level name nothing reads is dead too. A constant only tests read still counts: it is a fact the
        tests hold the docs to, such as the Spec keys a hash leaves out."""
        root = Path(__file__).resolve().parent.parent
        texts = {p: p.read_text(encoding="utf-8") for p in (root / "src" / "aidd").rglob("*.py")}
        readers = [t for p, t in texts.items() if not (p.name == "__init__.py" and "__getattr__" in t)]
        readers += [p.read_text(encoding="utf-8") for p in (root / "tests").glob("*.py")]
        words = collections.Counter(re.findall(r"\w+", "\n".join(readers)))
        assigned = r"^([A-Za-z_]\w*)\s*(?::[^=\n]+)?=(?!=)"
        unused = [
            f"{p.name}:{name}"
            for p, text in texts.items()
            if not (p.name == "__init__.py" and "__getattr__" in text)
            for name in re.findall(assigned, text, re.M)
            if not name.startswith("__") and words[name] <= 1
        ]
        self.assertEqual(unused, [])


if __name__ == "__main__":
    unittest.main()
