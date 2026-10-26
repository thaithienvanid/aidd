"""Input an agent controls, reaching a parser: git log records, commit messages and author names, Spec bodies, TOML
nesting, and very large diffs. Fixed fields are read NUL-separated and free text by its length; size and depth are
capped; a parse failure stays with its file and never turns a check off; matching stays fast at monorepo scale."""

import collections
import contextlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import decide, example, git, make_repo, run_cli

from aidd.workitems import repo_reads
from aidd.guard import pre_tool
from aidd.guard import denial_log
from aidd.guard import edit_check
from aidd.guard import approval_commands
from aidd.platforms import local_context
from aidd.gate import test_runner
from aidd.gate import policy
from aidd.gate import routing
from aidd import config
from aidd.workitems import decision_records, branch_specs, spec_file, spec_history
from aidd.kernel import documents, globs, http
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

    def forge(self) -> None:
        # What the old reader split on: a record separator, then a well-formed record with a good signature by boss.
        line = f"/aidd approve-spec SPEC-1 {'0' * 32} {self.head}"
        body = f"note\x1e{FORGED_SHA}\x1fboss@x.io\x1f2026-09-01T10:00:00+00:00\x1fG\x1fboss@x.io\x1f{line}\n{decision_records.MERGE_TRAILER}: {self.head}"
        decision_records.record_local_approval(body, str(self.root))

    def test_a_message_cannot_forge_a_signed_approval_by_someone_else(self):
        self.forge()
        for require in (False, True):
            reviews, comments, notes = decision_records.load_local_approvals(str(self.root), require_signed=require)
            people = {x["user"] for x in (*reviews, *comments)}
            self.assertNotIn("email:boss@x.io", people)
            self.assertFalse([x for x in (*reviews, *comments) if x.get("verified")])
            self.assertTrue(any("control separator" in n for n in notes), notes)

    def test_the_local_gate_does_not_count_it(self):
        (self.root / ".aidd").mkdir()
        cfg = 'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: [email:boss@x.io]\ngates:\n  local_approvals: signed\n'
        (self.root / ".aidd/config.yaml").write_text(cfg, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        (self.root / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "b")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.forge()
        ctx = local_context.build_local_context(repo=str(self.root), base="main", body="", run_policy=False)
        self.assertEqual([x for x in (*ctx["reviews"], *ctx["comments"]) if x["user"] == "email:boss@x.io"], [])
        self.assertEqual(decide(ctx).record.get("approved_by") or [], [])

    def test_an_ordinary_approval_still_reads_back(self):
        decision_records.record_local_approval(decision_records.approve_merge_line(self.head, branch="feat"), str(self.root))
        reviews, _, _ = decision_records.load_local_approvals(str(self.root))
        self.assertEqual([(r["user"], r["commit_sha"], r["branch"]) for r in reviews], [("email:me@example.com", self.head, "feat")])


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

    def test_an_author_name_cannot_claim_another_authors_spec(self):
        (self.root / "specs").mkdir()
        self.commit("add S-1", name="Me\x1eboss@x.io\x1fBoss", path="specs/S-1.md")
        found = repo_reads.authors(self.root, "HEAD", "specs")
        self.assertIn("email:me@example.com", found["specs/S-1.md"])
        self.assertNotIn("boss@x.io", found["specs/S-1.md"])

    def test_an_author_name_cannot_add_a_status_transition(self):
        (self.root / "specs").mkdir()
        spec = self.root / "specs/S-1.md"
        spec.write_text("---\nkind: spec\nid: S-1\nstatus: draft\n---\n", encoding="utf-8")
        git(self.root, "add", ".")
        forged = f"Eve\x1e{FORGED_SHA}\x1f2020-01-01T00:00:00Z\x1fMallory"
        env = {**os.environ, "GIT_AUTHOR_NAME": forged, "GIT_COMMITTER_NAME": forged}
        subprocess.run(["git", "commit", "-qm", "S-1"], cwd=self.root, env=env, check=True)
        held = spec_history.status_transitions(self.root, "specs/S-1.md", model_now())
        self.assertEqual([(t["commit"], t["by"]) for t in held], [(git(self.root, "rev-parse", "HEAD"), forged)])
        self.assertNotIn(FORGED_SHA, [t["commit"] for t in held])


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

    @unittest.skipIf(os.name == "nt", "symbolic links need privileges on Windows")
    def test_a_symlink_hashes_as_git_stores_it(self):
        # C-08: hash-object followed the link and hashed the file it points to.
        (self.root / "target.txt").write_text("the target's content\n", encoding="utf-8")
        os.symlink("target.txt", self.root / "link.txt")
        got = gitutil.hash_files(["link.txt", "target.txt"], str(self.root))
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "link")
        tree = gitutil.ls_tree("HEAD", str(self.root))
        self.assertEqual(got, {"link.txt": tree["link.txt"], "target.txt": tree["target.txt"]})
        self.assertNotEqual(got["link.txt"], got["target.txt"])

    def test_many_paths_hash_in_one_call_without_the_command_line(self):
        names = [f"d/f{i:05d}.txt" for i in range(3000)]
        (self.root / "d").mkdir()
        for n in names:
            (self.root / n).write_text(n, encoding="utf-8")
        calls: list[list[str]] = []
        real = gitutil._git

        def spy(args, *a, **kw):
            calls.append(list(args))
            return real(args, *a, **kw)

        with mock.patch.object(gitutil, "_git", spy):
            got = gitutil.hash_files(names, str(self.root))
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "many")
        tree = gitutil.ls_tree("HEAD", str(self.root))
        self.assertEqual(got, {n: tree[n] for n in names})
        self.assertTrue(all(len(c) < 10 for c in calls), [len(c) for c in calls])


# The handoff regex spec_hash used before 1.0.0: quadratic on a long body. The line scanner must remove exactly what it did.
OLD_HANDOFF = re.compile(r"^```aidd-handoff[ \t]*\r?\n.*?^```[ \t]*$\r?\n?", re.S | re.M)


class SpecSizeTests(unittest.TestCase):
    """C-04: the handoff strip is linear, and a document has a size cap."""

    def test_the_scanner_removes_exactly_what_the_regex_removed(self):
        pieces = ["```aidd-handoff\n", "```aidd-handoff \r\n", "```\n", "``` \n", "```\r\n", "```", "text\n", "\n", "````\n", "```python\n", "x```\n", "\r\n"]
        rnd = random.Random(7)
        for _ in range(3000):
            body = "".join(rnd.choice(pieces) for _ in range(rnd.randint(0, 12)))
            self.assertEqual(spec_file.strip_handoffs(body), OLD_HANDOFF.sub("", body), repr(body))

    def test_a_pathological_body_hashes_in_linear_time(self):
        # 200 KB of unclosed handoff fences: the regex rescans to the end from every one of them.
        body = "```aidd-handoff\nx\n" * 11000
        spec = "---\nkind: spec\nid: S-1\n---\n" + body
        self.assertLess(len(spec.encode()), documents.MAX_DOCUMENT_BYTES)
        t = time.monotonic()
        spec_file.spec_hash(spec, {})
        self.assertLess(time.monotonic() - t, 2.0)

    def test_a_document_past_the_cap_is_a_model_error(self):
        spec = "---\nkind: spec\nid: S-1\n---\n" + "x" * documents.MAX_DOCUMENT_BYTES
        for read in (documents.split_front_matter, lambda t, w: spec_file.load_object(t, w), lambda t, w: spec_file.spec_hash(t, {})):
            with self.assertRaises(documents.DocumentError) as err:
                read(spec, "specs/S-1.md")
            self.assertIn("at most", str(err.exception))
        # Multi-byte text counts in bytes, as a file on disk does.
        with self.assertRaises(documents.DocumentError):
            documents.split_front_matter("---\nkind: spec\n---\n" + "é" * (documents.MAX_DOCUMENT_BYTES // 2 + 1), "x")


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
        (self.root / "specs" / "SPEC-BAD.md").write_text("---\nkind: spec\nid: SPEC-BAD\n" + DEEP + "---\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "two Specs, one unreadable")

    def hook(self, rel: str) -> str:
        event = {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": str(self.root / rel), "content": "x"}}
        out = io.StringIO()
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        return out.getvalue()

    def test_the_guard_still_denies_a_protected_path(self):
        answer = self.hook(".github/workflows/deploy.yml")
        self.assertIn('"deny"', answer)
        self.assertIn("protected path", answer)
        self.assertEqual(edit_check.check_edit(str(self.root), ".github/workflows/deploy.yml")[0], "deny")

    def test_the_guard_denies_a_protected_path_whatever_the_spec_reader_raises(self):
        with mock.patch.object(branch_specs, "active_specs", side_effect=RecursionError("boom")):
            decision, why = edit_check.check_edit(str(self.root), ".github/workflows/deploy.yml")
        self.assertEqual(decision, "deny")
        self.assertIn("RecursionError", why)

    def test_list_and_its_branch_view_read_the_other_specs(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("list", "--json")
            self.assertEqual(code, 0, out)
            self.assertIn("SPEC-220", out)
            code, out = run_cli("list", "--branch", "--json")
            self.assertEqual(code, 0, out)
            self.assertIn("SPEC-220", out)


class ScaleTests(unittest.TestCase):
    """C-06: a 20,000-file diff is judged in seconds (a 50,000-file one took 111 s)."""

    def ctx(self, n: int) -> dict:
        ctx = example("02-normal-feature")
        ctx["files"] = [{"path": f"src/mod{i % 200}/sub{i % 7}/f{i}.py", "previous_path": None, "additions": 1, "deletions": 0} for i in range(n)]
        return ctx

    def test_the_gate_judges_20000_files_in_seconds(self):
        ctx = self.ctx(20000)
        # CPU time, not wall time: the bound is the judgment's own cost, which a busy machine running tests in parallel never adds to.
        t = time.process_time()
        decide(ctx)
        self.assertLess(time.process_time() - t, 15.0)  # about 1 s here; generous for a slow CI runner

    def test_the_risk_scan_of_20000_paths_is_fast(self):
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n')
        paths = [f"src/mod{i % 200}/sub{i % 7}/f{i}.py" for i in range(20000)] + ["db/migrations/1.sql", ".github/workflows/x.yml"]
        t = time.process_time()  # CPU time, as above: the scan's own cost, whatever else the machine runs
        hits = routing.scan(paths, cfg)
        self.assertLess(time.process_time() - t, 10.0)
        self.assertEqual({h.path for h in hits}, {"db/migrations/1.sql", ".github/workflows/x.yml"})

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

    def test_a_pattern_set_answers_as_match_any_does(self):
        # A PatternSet files each pattern under a key and tests a path only against what its keys find: never another answer.
        rnd = random.Random(12)
        atoms = ["a", "b", "/", "*", "**", "**/", "?", ".py", "src", "src/", "A", "x/", "ab", "/**"]
        names = ["a", "b", "/", ".py", "src", "A", "x", "ab", "bab"]
        for _ in range(600):
            patterns = ["".join(rnd.choice(atoms) for _ in range(rnd.randint(1, 6))) for _ in range(rnd.randint(1, 12))]
            for fold in (False, True):
                found = globs.PatternSet(patterns, fold)
                for _ in range(12):
                    path = "".join(rnd.choice(names) for _ in range(rnd.randint(1, 8)))
                    want = [i for i, p in enumerate(patterns) if globs.match(p, path, fold)]
                    self.assertEqual(found.matching(path), want, (patterns, path, fold))
                    self.assertEqual(found.first(path), globs.first_match(patterns, path, fold), (patterns, path, fold))

    def test_the_risk_scan_matches_what_every_pattern_says(self):
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n')
        rules = [r for r in routing.active_rules(cfg) if not r.get("content")]
        patterns = list(routing.protected_paths(cfg)) + [p for r in rules for p in r.get("paths", [])]
        found = globs.PatternSet(patterns, fold_case=True)
        # Paths built from the patterns' own plainest forms, so most of them match something, and some plain ones.
        paths = [globs.sample_path(p) for p in patterns] + [globs.literal_form(p) for p in patterns] + ["README.md", "src/app.py", "a/B/Auth.py"]
        for path in paths:
            want = [i for i, p in enumerate(patterns) if globs.match(p, path, True)]
            self.assertEqual(found.matching(path), want, path)


class StreamingLogCapTests(unittest.TestCase):
    """C-09: a test command's log stays under the cap while it runs, not only after it exits."""

    def test_the_log_never_grows_past_the_cap(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "green-x.log"
            probe = (
                "import os, sys, time\n"
                "sys.stdout.buffer.write(b'A' * 400000); sys.stdout.flush(); time.sleep(0.5)\n"
                "size = os.path.getsize(sys.argv[1])\n"
                "sys.exit(0 if size <= 3000 else 1)\n"
            )
            with mock.patch.object(test_runner, "MAX_LOG_BYTES", 2000):
                result = test_runner.run_test_command([sys.executable, "-c", probe, str(log)], cwd=d, log=log, timeout_seconds=60)
            self.assertEqual(result["status"], "passed", log.read_bytes()[-200:])
            data = log.read_bytes()
            self.assertLessEqual(len(data), 2000 + len(test_runner.TRUNCATED))
            self.assertTrue(data.endswith(test_runner.TRUNCATED))


class PolicyEnvironmentTests(unittest.TestCase):
    """C-10: the Policy command sees no credential-like variable unless the base config names it."""

    PROBE = [sys.executable, "-c", "import os; print('allow', os.environ.get('ACME_API_TOKEN', '-'), os.environ.get('VENDOR_SECRET', '-'))"]

    def test_credentials_are_dropped_unless_passed_by_name(self):
        with mock.patch.dict(os.environ, {"ACME_API_TOKEN": "t0k", "VENDOR_SECRET": "s3c"}):
            self.assertEqual(policy.run_policy_command(self.PROBE)["detail"], "- -")
            self.assertEqual(policy.run_policy_command(self.PROBE, pass_env=["ACME_API_TOKEN"])["detail"], "t0k -")

    def test_the_base_config_names_them(self):
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\npolicy:\n  command: [x]\n  pass_env: [ACME_API_TOKEN]\n')
        with mock.patch.dict(os.environ, {"ACME_API_TOKEN": "t0k", "VENDOR_SECRET": "s3c"}):
            got = policy.evaluate(self.PROBE, cwd=".", change_id="1", base_sha="a", head_sha="b", paths=[], body="", head_files={}, cfg=cfg)
        self.assertEqual(got["detail"], "t0k -")


class ApiSizeTests(unittest.TestCase):
    """C-15: every API read has a size limit."""

    def test_get_and_paginate_pass_a_limit(self):
        seen = []

        def transport(method, url, auth=None, data=None, headers=None, timeout_seconds=30, max_bytes=None):
            seen.append(max_bytes)
            return 200, {}, b"[]"

        client = http.JsonClient("t", "https://api.example.com", transport=transport)
        client.get("/x")
        client.paginate("/y")
        self.assertEqual(seen, [http.MAX_API_BYTES, http.MAX_API_BYTES])


@unittest.skipUnless(HAS_GIT, "git is required")
class SpecIdTests(unittest.TestCase):
    """C-12: `aidd hash SPEC-1` hashes the Spec whose id that is."""

    def test_an_id_resolves_to_its_spec(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "r", spec="02-normal-feature:specs/SPEC-220.md")

            with contextlib.chdir(root):
                by_path = run_cli("hash", "specs/SPEC-220.md", "--worktree")
                by_id = run_cli("hash", "SPEC-220", "--worktree")
                missing = run_cli("hash", "SPEC-404", "--worktree")
        self.assertEqual(by_path[0], 0, by_path[1])
        self.assertEqual(by_id, by_path)
        self.assertEqual(missing[0], 2)
        self.assertIn("no Spec has the id SPEC-404", missing[1])


class SigningConfigGuardTests(unittest.TestCase):
    """C-02: an agent may read commit signing settings, never change them."""

    def test_writes_to_signing_settings_are_denied(self):
        for cmd in (
            "git config gpg.ssh.allowedSignersFile /tmp/mine",
            "git config --global user.signingkey ~/.ssh/agent",
            "git config --local gpg.format openpgp",
            "git config set gpg.ssh.program /tmp/always-good",
            "git config --unset user.signingKey",
            "git config --remove-section gpg",
            "git -C . config --file .git/config gpg.program x",
            "git config -e",
            "cd x && git config GPG.SSH.ALLOWEDSIGNERSFILE y",
        ):
            why = approval_commands.forbidden_action(cmd)
            self.assertIsNotNone(why, cmd)
            self.assertEqual(denial_log.reason_code(why or ""), "signing_config", cmd)

    def test_reads_and_other_keys_are_allowed(self):
        for cmd in (
            "git config --get gpg.format",
            "git config gpg.format",
            "git config user.email me@x.io",
            "git config --list",
            "git config get user.signingkey",
        ):
            self.assertIsNone(approval_commands.forbidden_action(cmd), cmd)


@unittest.skipUnless(HAS_GIT and shutil.which("ssh-keygen"), "git and ssh-keygen are required")
class PinnedSignersTests(unittest.TestCase):
    """C-02: whose signatures count comes from the base branch, never from this machine's git config."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.root = repo_at(self.dir / "repo")
        self.person = self.key("person")
        self.agent = self.key("agent")
        self.head = git(self.root, "rev-parse", "HEAD")

    def key(self, name: str) -> Path:
        path = self.dir / name
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(path)], check=True)
        return path

    def pub(self, key: Path) -> str:
        return Path(f"{key}.pub").read_text(encoding="utf-8").strip()

    def sign_with(self, key: Path) -> None:
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", str(key))):
            git(self.root, "config", k, v)
        decision_records.record_local_approval(decision_records.approve_merge_line(self.head), str(self.root))

    def test_a_signature_from_a_listed_key_counts_with_no_machine_trust_at_all(self):
        self.sign_with(self.person)
        git(self.root, "config", "--unset", "gpg.format")
        signers = f"me@example.com {self.pub(self.person)}\n"
        reviews, _, _ = decision_records.load_local_approvals(str(self.root), require_signed=True, signers=signers)
        self.assertEqual([r["verified"] for r in reviews], [True])

    def test_this_machines_allowed_signers_and_program_change_nothing(self):
        self.sign_with(self.agent)
        mine = self.dir / "agents_list"
        mine.write_text(f"me@example.com {self.pub(self.agent)}\n", encoding="utf-8")
        git(self.root, "config", "gpg.ssh.allowedSignersFile", str(mine))
        self.assertEqual([r["verified"] for r in decision_records.load_local_approvals(str(self.root))[0]], [True])  # the machine's own opinion
        signers = f"me@example.com {self.pub(self.person)}\n"
        reviews, _, notes = decision_records.load_local_approvals(str(self.root), require_signed=True, signers=signers)
        self.assertEqual([r["verified"] for r in reviews], [False])
        self.assertTrue(any("not signed with a trusted key" in n for n in notes), notes)

    def test_the_local_gate_reads_the_signers_from_the_base_branch(self):
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text(
            'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: [email:me@example.com]\ngates:\n  local_approvals: signed\n', encoding="utf-8"
        )
        (self.root / ".aidd/allowed_signers").write_text(f"me@example.com {self.pub(self.person)}\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        # The branch lists the agent's key too: it does not count, because the base branch's file decides.
        (self.root / ".aidd/allowed_signers").write_text(f"me@example.com {self.pub(self.agent)}\n", encoding="utf-8")
        (self.root / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "b")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.sign_with(self.agent)
        ctx = local_context.build_local_context(repo=str(self.root), base="main", body="", run_policy=False)
        self.assertEqual([r["verified"] for r in ctx["reviews"]], [False])
        self.sign_with(self.person)
        ctx = local_context.build_local_context(repo=str(self.root), base="main", body="", run_policy=False)
        self.assertEqual(sorted(r["verified"] for r in ctx["reviews"]), [False, True])


class DeadCodeTests(unittest.TestCase):
    """C-16: every module-level function in src/aidd is used by src/aidd; a helper only tests use lives in tests/helpers.py."""

    def test_no_function_is_unused(self):
        src = Path(__file__).resolve().parent.parent / "src" / "aidd"
        texts = {p: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
        everything = "\n".join(texts.values())
        words = collections.Counter(re.findall(r"\w+", everything))  # one pass; a scan for each name was quadratic
        unused = [f"{p.name}:{name}" for p, text in texts.items() for name in re.findall(r"^def (\w+)\(", text, re.M) if words[name] <= 1]
        self.assertEqual(unused, [])


if __name__ == "__main__":
    unittest.main()
