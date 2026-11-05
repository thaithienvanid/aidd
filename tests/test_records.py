"""Records: one immutable file of history for each answered ask and each reported action, in the clone's shared git
folder. Writing checks a record's shape and refuses a secret's value; reading keeps every record it can parse."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git

from aidd import records
from aidd.cli import mcp_server
from aidd.kernel import secret_patterns
from aidd.records import files

BY = "agent:claude-code/claude-opus-5-5"
APPROVAL = {
    "action": "git.push.force",
    "question": {"type": "approval", "text": "Force-push feat/refunds? It replaces 2 commits there."},
    "covers": {"command": "git push --force-with-lease origin feat/refunds", "head": "ab1d6f9"},
    "answer": {"outcome": "accept", "words": "yes, push it", "by": "Ada"},
}
CHOICE = {
    "question": {"type": "choice", "text": "Which layout?", "options": [{"id": "a", "label": "Cards"}, {"id": "b", "label": "Table"}]},
    "answer": {"outcome": "accept", "words": "the table", "picked": ["b"], "by": "Ada"},
}


def envelope(record_type: str, data: dict) -> dict:
    return {"id": "20261105T032447123Z-c97fd11c", "type": record_type, "at": "2026-11-05T03:24:47Z", "by": BY, "data": data}


def with_(base: dict, path: str, value) -> dict:
    """`base` with the value at a dotted `path` replaced, or removed when `value` is None."""
    out = json.loads(json.dumps(base))
    *parents, last = path.split(".")
    node = out
    for p in parents:
        node = node[p]
    if value is None:
        node.pop(last)
    else:
        node[last] = value
    return out


class RecordShapeTests(unittest.TestCase):
    def test_a_record_is_written_only_when_its_type_and_its_facts_are_right(self):
        ok = [
            ("decision", APPROVAL),
            ("decision", CHOICE),
            ("decision", with_(with_(CHOICE, "question.multiple", True), "answer.picked", ["a", "b"])),
            ("decision", with_(APPROVAL, "answer.outcome", "decline")),
            ("decision", with_(with_(APPROVAL, "answer.outcome", "cancel"), "answer.words", "")),
            (
                "decision",
                {"question": {"type": "text", "text": "What should the button say?"}, "answer": {"outcome": "accept", "words": "Refund", "by": "Ada"}},
            ),
            ("report", {"action": "pr.open", "covers": {"branch": "feat/refunds"}, "said": "Opened PR #12."}),
            ("report", {"action": "secret.use", "covers": {"command": "deploy --token $DEPLOY_TOKEN https://example.com/x"}, "said": "Used DEPLOY_TOKEN."}),
        ]
        for record_type, data in ok:
            with self.subTest(data=data):
                self.assertEqual(files.record_problems(envelope(record_type, data)), [])
        wrong = [
            ("decision", with_(APPROVAL, "action", None), "missing required field 'action'"),
            ("decision", with_(APPROVAL, "question.options", [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]), "forbidden shape"),
            ("decision", with_(CHOICE, "question.options", None), "missing required field 'options'"),
            ("decision", with_(CHOICE, "answer.picked", ["c"]), "c is not an option's id"),
            ("decision", with_(CHOICE, "answer.picked", ["a", "b"]), "allows one pick"),
            ("decision", with_(CHOICE, "answer.picked", None), "names the option ids picked"),
            ("decision", with_(APPROVAL, "answer.picked", ["a"]), "only an accepted choice has picks"),
            ("decision", with_(APPROVAL, "answer.outcome", "maybe"), "answer.outcome"),
            ("decision", with_(APPROVAL, "answer.words", None), "missing required field 'words'"),
            ("decision", with_(APPROVAL, "answer.words", ""), "shorter than 1"),
            ("decision", with_(CHOICE, "answer.picked", ["b", "b"]), "items must be unique"),
            ("decision", with_(CHOICE, "question.options", [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]), "its own id"),
            ("report", {"action": "pr.open", "said": "x", "extra": 1}, "extra"),
            ("audit", {}, "is not a record type aidd knows"),
        ]
        # Each known shape is refused with one fixed message that names no type, so nothing the scan read is printed.
        secret_cases = [
            ("report", {"action": "pr.open", "said": "".join(("used ghp_", "abcdefghijklmnopqrstuvwxyz0123456789"))}, "a GitHub token"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("deploy AKIA", "ABCDEFGHIJKLMNOP"))), "an AWS access key id"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("psql postgres://app:", "hunter2pw@db.internal/app"))), "a password in a URL"),
            ("report", {"action": "pr.open", "said": "".join(("set OPENAI key sk-proj-", "abcdefghijklmnopqrstuvwxyz12"))}, "an OpenAI or Anthropic key"),
            ("report", {"action": "pr.open", "said": "".join(("posted with xoxb-", "1234567890-abcdefghij"))}, "a Slack token"),
            ("decision", with_(APPROVAL, "answer.words", "".join(("yes, the password=", "CorrectHorse9 works"))), "a credential assignment"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("deploy GITHUB_TOKEN=", "abcd1234efgh5678"))), "a credential assignment"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("curl -H 'Authorization: Bear", "er abcdefghijklmnop1234'"))), "a bearer token"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("mysql -u app -p", "hunter22 shop"))), "a password on a command line"),
            ("report", {"action": "pr.open", "said": "x" * 5000 + "".join((" ghp_", "abcdefghijklmnopqrstuvwxyz0123456789"))}, "a GitHub token"),
            # Disguised: a zero-width or soft-hyphen character inside, fullwidth letters, or a password in a list.
            ("report", {"action": "pr.open", "said": "".join(("used ghp_abcdefghij​", "klmnopqrstuvwxyz0123456789"))}, "a GitHub token"),
            ("report", {"action": "pr.open", "said": "".join(("used ｇｈｐ＿", "abcdefghijklmnopqrstuvwxyz0123456789"))}, "a GitHub token"),
            ("decision", with_(APPROVAL, "covers.command", "".join(("deploy AKIA­", "ABCDEFGHIJKLMNOP"))), "an AWS access key id"),
            ("report", {"action": "pr.open", "said": "x", "covers": {"password": ["ok", "".join(("hunter2", "hunter2"))]}}, "a credential assignment"),
            ("report", {"action": "pr.open", "said": "x", "covers": {"token": [["".join(("hunter2", "hunter2"))]]}}, "a credential assignment"),
            ("report", {"action": "pr.open", "said": "x", "covers": {"ｐａｓｓｗｏｒｄ": "".join(("hunter2", "hunter2"))}}, "a credential assignment"),
        ]
        for record_type, data, kind in secret_cases:
            with self.subTest(secret=kind):
                self.assertEqual(files.record_problems(envelope(record_type, data)), [files.REFUSED_VALUE_MESSAGE])
                self.assertTrue(any(kind in secret_patterns.secret_types(t, loose=True) for t in files._strings(data)), kind)
        for record_type, data, needle in wrong:
            with self.subTest(needle=needle):
                problems = files.record_problems(envelope(record_type, data))
                self.assertTrue(any(needle in p for p in problems), problems)
        token = "".join(("ghp_", "abcdefghijklmnopqrstuvwxyz0123456789"))
        for name, record in (
            ("a wrong-typed field", envelope("decision", with_(APPROVAL, "covers.head", ["x", token]))),
            ("an unknown key", envelope("report", {"action": "pr.open", "said": "x", token: 1})),
            ("a bad pick", envelope("decision", with_(CHOICE, "answer.picked", [token]))),
            ("a bad subject", {**envelope("decision", APPROVAL), "subject": f"{token} x"}),
        ):
            with self.subTest(secret_in=name):
                problems = files.record_problems(record)
                self.assertEqual(len(problems), 1, problems)
                self.assertEqual(problems, [files.REFUSED_VALUE_MESSAGE])
                self.assertNotIn(token, problems[0])
        deep: list = []
        for _ in range(1500):  # built by hand: Python 3.11's json reads no array this deep
            deep = [deep]
        for name, record, needle in (
            ("a lone surrogate", envelope("report", {"action": "pr.open", "said": "\ud800"}), "not valid Unicode"),
            ("deep nesting", envelope("report", {"action": "pr.open", "said": "x", "covers": {"k": deep}}), "deeper"),
            ("a pick that is an object", envelope("decision", with_(CHOICE, "answer.picked", [{}])), "answer.picked"),
            (
                "a password split over a key",
                envelope("report", {"action": "pr.open", "said": "x", "covers": {"password": "hunter2hunter2"}}),
                "a key, a token, or a password",
            ),
        ):
            with self.subTest(hostile=name):
                problems = files.record_problems(record)
                self.assertTrue(any(needle in p for p in problems), problems)
        loud = files.record_problems(envelope("decision", with_(CHOICE, "answer.picked", ["\x1b[2J\u202e" + "z" * 5000])))
        self.assertTrue(loud and all(len(p) <= 300 and "\x1b" not in p and "\u202e" not in p for p in loud), loud)
        self.assertIsNone(files.parse_record(json.dumps(envelope("report", {"action": "pr.open", "said": "\ud800"})).encode()))
        for field, value in (
            ("by", "claude"),
            ("by", "agent:x\x1b[2J"),
            ("by", "agent:x\u202e"),
            ("by", "agent:x\x9b2J"),
            ("subject", "SPEC-4\x1b[2J"),
            ("id", "1"),
            ("at", "yesterday"),
        ):
            with self.subTest(field=field):
                self.assertTrue(files.record_problems({**envelope("decision", APPROVAL), field: value}))


class RecordFileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Ada Person")
        git(self.root, "config", "user.email", "ada@example.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "init")

    def test_every_worktree_reads_one_history_outside_the_working_tree_newest_first(self):
        first, path = records.add_record("decision", with_(APPROVAL, "answer.by", None), by=BY, subject="SPEC-4", cwd=str(self.root))
        self.assertEqual(first["data"]["answer"]["by"], "Ada Person", "the person is named by their git name")
        self.assertEqual(path.relative_to(self.root / ".git" / "aidd" / "records").parts[2], f"{first['id']}.json")
        self.assertEqual(git(self.root, "status", "--porcelain"), "", "no record is in the working tree")
        other = self.root.parent / "other"
        git(self.root, "worktree", "add", "-q", "-b", "feat", str(other))
        second, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(other))
        found, unreadable = records.read_records(str(self.root))
        self.assertEqual([r["id"] for r in found], [second["id"], first["id"]])
        self.assertEqual(unreadable, [])
        self.assertEqual([r["id"] for r in records.read_records(str(other), subject="SPEC-4")[0]], [first["id"]])
        self.assertEqual([r["id"] for r in records.read_records(str(other), record_type="report")[0]], [second["id"]])

    def test_a_record_is_never_overwritten_and_a_wrong_one_is_never_written(self):
        with mock.patch.object(files, "_new_id", return_value="20261105T032447123Z-c97fd11c"):
            records.add_record("decision", APPROVAL, by=BY, cwd=str(self.root))
            with self.assertRaises(FileExistsError):
                records.add_record("decision", with_(APPROVAL, "answer.words", "no"), by=BY, cwd=str(self.root))
        with self.assertRaises(records.RecordError):
            records.add_record("report", {"action": "pr.open"}, by=BY, cwd=str(self.root))
        found, _ = records.read_records(str(self.root))
        self.assertEqual([r["data"]["answer"]["words"] for r in found], ["yes, push it"])

    def test_a_record_of_a_type_this_aidd_does_not_know_is_kept_and_junk_is_named(self):
        folder = records.records_dir(str(self.root)) / "2027" / "01"
        folder.mkdir(parents=True)
        newer = {**envelope("audit", {"signed": True}), "id": "20270101T000000000Z-00000000", "hash": "abc"}
        (folder / f"{newer['id']}.json").write_text(json.dumps(newer), encoding="utf-8")
        (folder / "20270101T000000001Z-11111111.json").write_text("{not json", encoding="utf-8")
        odd = {**envelope("note", {"question": "what now?", "answer": 3}), "id": "20270101T000000002Z-22222222"}
        (folder / f"{odd['id']}.json").write_text(json.dumps(odd), encoding="utf-8")
        found, unreadable = records.read_records(str(self.root))
        self.assertEqual(found, [odd, newer])
        self.assertEqual(aidd_subprocess("records", cwd=self.root).returncode, 0, "a record of any shape lists")
        newer["subject"] = "SPEC-4\x1b]0;owned\x07"  # a pulled record is another's text: printed, it never drives the terminal
        (folder / f"{newer['id']}.json").write_text(json.dumps(newer), encoding="utf-8")
        listed = aidd_subprocess("records", cwd=self.root).stdout
        self.assertIn("SPEC-4 ]0;owned ", listed)
        self.assertNotIn("\x1b", listed)
        self.assertEqual([Path(u).name for u in unreadable], ["20270101T000000001Z-11111111.json"])

    def test_the_command_and_the_mcp_tool_write_as_the_agent_never_as_a_person(self):
        data = json.dumps(APPROVAL)
        refused = aidd_subprocess("records", "add", "--type", "decision", "--by", "person:Ada", "--data", data, cwd=self.root)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("never a person's name", refused.stderr)
        added = aidd_subprocess("records", "add", "--type", "decision", "--by", "claude-code/claude-opus-5-5", "--data", "-", cwd=self.root, input=data)
        self.assertEqual(added.returncode, 0, added.stderr)
        is_error, text = mcp_server.call(
            "record", {"type": "report", "by": "codex/gpt-5", "data": {"action": "pr.open", "said": "Opened PR #12."}}, str(self.root)
        )
        self.assertFalse(is_error, text)
        self.assertEqual(mcp_server.call("record", {"type": "report", "by": "codex/gpt-5", "data": "x"}, str(self.root))[0], True)
        listed = aidd_subprocess("records", "--json", cwd=self.root)
        out = json.loads(listed.stdout)
        self.assertEqual([r["by"] for r in out["records"]], ["agent:codex/gpt-5", BY])
        self.assertEqual(files.json_schema.validate(out, "records.schema.json#/$defs/list"), [])

    def test_the_mcp_tool_says_it_wrote_and_never_answers_with_the_git_name(self):
        """The MCP tool runs with no prompt, so its decision never takes the person's git name as who answered."""
        unnamed = with_(APPROVAL, "answer.by", None)
        is_error, text = mcp_server.call("record", {"type": "decision", "by": "codex/gpt-5", "data": unnamed}, str(self.root))
        self.assertTrue(is_error, text)
        self.assertIn("answer.by", text)
        self.assertEqual(records.read_records(str(self.root))[0], [])
        self.assertEqual(files._WRITTEN_WITH.get(), "cli", "the mark ends with the call, even a refused one")
        is_error, text = mcp_server.call("record", {"type": "decision", "by": "codex/gpt-5", "data": APPROVAL}, str(self.root))
        self.assertFalse(is_error, text)
        records.add_record("decision", unnamed, by=BY, cwd=str(self.root))
        found = records.read_records(str(self.root))[0]
        self.assertEqual({r["written_with"]: r["data"]["answer"]["by"] for r in found}, {"mcp": "Ada", "cli": "Ada Person"})
        self.assertEqual(aidd_subprocess("records", cwd=self.root).stdout.count("through the MCP tool"), 1)
        self.assertTrue(files.record_problems({**envelope("decision", APPROVAL), "written_with": "person"}))
        self.assertEqual(files.record_problems({**envelope("decision", APPROVAL), "written_with": "mcp"}), [])


class RecordSharingTests(unittest.TestCase):
    """Two clones of one remote share their records through `refs/aidd/records`, merged by union."""

    def clone(self, name: str) -> Path:
        path = self.base / name
        git(self.base, "clone", "-q", str(self.remote), str(path))
        git(path, "config", "user.name", name)
        git(path, "config", "user.email", f"{name}@example.com")
        return path

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.remote = self.base / "remote.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.ada, self.bo = self.clone("ada"), self.clone("bo")

    def ids(self, clone: Path) -> list[str]:
        return sorted(r["id"] for r in records.read_records(str(clone))[0])

    def test_two_clones_end_with_the_union_and_nothing_is_replaced(self):
        self.assertEqual(records.pull_records("origin", str(self.ada)), ([], []), "a remote with no records yet")
        for words in ("yes", "go ahead"):
            records.add_record("decision", with_(APPROVAL, "answer.words", words), by=BY, cwd=str(self.ada))
        self.assertEqual(records.push_records("origin", str(self.ada)), (0, 2))
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.bo))
        self.assertEqual(records.push_records("origin", str(self.bo)), (2, 3))
        self.assertEqual(len(records.pull_records("origin", str(self.ada))[0]), 1)
        self.assertEqual(self.ids(self.ada), self.ids(self.bo))
        self.assertEqual(len(self.ids(self.ada)), 3)
        self.assertEqual(records.push_records("origin", str(self.ada)), (0, 3), "nothing new: the same tree, no new commit")
        self.assertEqual(git(self.ada, "rev-parse", "refs/aidd/records"), git(self.bo, "rev-parse", "refs/aidd/records"))

    def test_a_remotes_password_never_reaches_the_message(self):
        git(self.ada, "remote", "add", "leaky", "".join(("https://ada:", "tok3n-value@127.0.0.1:9/x.git")))
        with self.assertRaises(files.git.GitError) as caught:
            records.pull_records("leaky", str(self.ada))
        self.assertNotIn("tok3n-value", str(caught.exception))

    def test_every_command_that_pushes_starts_with_aidd_records_push(self):
        # The ask rule of every harness matches `aidd records push*`, so no other shape may push.
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        shapes = (
            ("records", "--json", "push"),
            ("records", "--type", "decision", "push"),
            ("records", "push", "--json"),
            ("records", "--remote", "origin", "push"),
            ("records", "--", "push"),
            ("--", "records", "push"),
            ("records", "push", "--", "origin"),
        )
        for argv in shapes:
            with self.subTest(argv=argv):
                self.assertEqual(aidd_subprocess(*argv, cwd=self.ada).returncode, 2)
        self.assertFalse(files.git.run(["ls-remote", str(self.remote)], str(self.ada)).strip(), "nothing reached the remote")
        self.assertEqual(aidd_subprocess("records", "push", "origin", cwd=self.ada).returncode, 0)
        self.assertIn("refs/aidd/records", files.git.run(["ls-remote", str(self.remote)], str(self.ada)))

    def test_records_go_only_to_a_remote_the_clone_names(self):
        for remote in (str(self.remote), "https://example.com/x.git", "--upload-pack=touch /tmp/x", "upstream"):
            with self.subTest(remote=remote), self.assertRaisesRegex(ValueError, "not a remote of this clone"):
                records.push_records(remote, str(self.ada))

    def test_push_sends_only_checked_records_and_only_their_own_history(self):
        good, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        folder = records.records_dir(str(self.ada)) / "2026" / "11"
        folder.mkdir(parents=True, exist_ok=True)
        secret = self.base / "secret.txt"
        secret.write_text("".join(("DB_PASSWORD=", "hunter2hunter2\n")), encoding="utf-8")
        planted = {
            "20261105T000000000Z-eeeeeeee.json": lambda p: p.write_text(json.dumps({**good, "id": "20261105T000000000Z-ffffffff"}), encoding="utf-8"),
            "20261105T000000001Z-dddddddd.json": lambda p: p.write_text("".join(("DB_PASSWORD=", "hunter2hunter2")), encoding="utf-8"),
            "20261105T000000002Z-cccccccc.json": lambda p: p.symlink_to(secret),
            "20261105T000000003Z-bbbbbbbb.json": lambda p: p.write_text(
                json.dumps({**good, "id": "20261105T000000003Z-bbbbbbbb", "data": {"action": "pr.open", "said": "".join(("password=", "hunter2hunter2"))}}),
                encoding="utf-8",
            ),
        }
        for name, plant in planted.items():
            with self.subTest(name=name):
                plant(folder / name)
                with self.assertRaisesRegex(ValueError, "nothing was pushed"):
                    records.push_records("origin", str(self.ada))
                (folder / name).unlink()
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (folder.parent / "12").symlink_to(elsewhere, target_is_directory=True)  # a linked month folder
        (elsewhere / "20261201T000000000Z-aaaaaaaa.json").write_text(json.dumps({**good, "id": "20261201T000000000Z-aaaaaaaa"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "its folder, is a link"):
            records.push_records("origin", str(self.ada))
        (folder.parent / "12").unlink()
        self.assertFalse(files.git.run(["ls-remote", str(self.remote)], str(self.ada)).strip(), "nothing reached the remote")
        private = files.git.run(["commit-tree", files.git.run(["write-tree"], str(self.ada)).strip(), "-m", "private"], str(self.ada)).strip()
        files.git.run(["update-ref", "refs/aidd/records", private], str(self.ada))
        records.push_records("origin", str(self.ada))
        pushed = files.git.run(["rev-list", "refs/aidd/records"], str(self.ada)).split()
        self.assertNotIn(private, pushed, "a commit the local ref pointed at never leaves with the records")
        self.assertFalse(files.git.ok(["cat-file", "-e", private], str(self.remote)), "the remote never got it")
        self.assertEqual(sorted(files.git.ls_tree("refs/aidd/records", str(self.ada))), [f"2026/11/{good['id']}.json"])

    def test_a_failed_push_leaves_the_local_ref_where_it_was(self):
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'protected ref' >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        with self.assertRaisesRegex(files.git.GitError, "refused the records: .*protected ref"):
            records.push_records("origin", str(self.ada))
        self.assertEqual(files.git.run(["rev-parse", "-q", "--verify", "refs/aidd/records"], str(self.ada), check=False).strip(), "")

    def test_a_pulled_file_that_is_no_record_is_skipped_and_named_and_a_pulled_record_is_marked(self):
        good, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        hostile = self.base / "hostile"
        git(self.base, "clone", "-q", str(self.remote), str(hostile))
        git(hostile, "fetch", "-q", "origin", "refs/aidd/records:refs/aidd/records")
        entries = {
            "2026/11/20261105T000000000Z-aaaaaaaa.json": "[" * 100_000 + "]" * 100_000,
            "2026/11/20261105T000000001Z-bbbbbbbb.json": json.dumps({**good, "id": "20261105T000000001Z-bbbbbbbb", "by": "agent:x\u202e"}),
            "2026/11/20261105T000000002Z-cccccccc.json": json.dumps(
                {**good, "id": "20261105T000000002Z-cccccccc", "data": {"said": "".join(("token=", "abcdefgh12345678"))}, "type": "note"}
            ),
        }
        index = self.base / "hostile-index"
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        git(hostile, "read-tree", "refs/aidd/records", env=env)
        for name, text in entries.items():
            sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=hostile, input=text, capture_output=True, text=True, check=True).stdout.strip()
            git(hostile, "update-index", "--add", "--cacheinfo", f"100644,{sha},{name}", env=env)
        tree = git(hostile, "write-tree", env=env).strip()
        commit = git(hostile, "commit-tree", tree, "-p", "refs/aidd/records", "-m", "hostile").strip()
        git(hostile, "push", "-q", "origin", f"{commit}:refs/aidd/records")
        added, refused = records.pull_records("origin", str(self.bo))
        self.assertEqual(added, [f"2026/11/{good['id']}.json"])
        self.assertEqual(sorted(r.split(":")[0] for r in refused), sorted(entries))
        listed = aidd_subprocess("records", cwd=self.bo)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("pulled from a remote", listed.stdout)
        self.assertEqual(json.loads(aidd_subprocess("records", "--json", cwd=self.bo).stdout)["pulled"], [good["id"]])


if __name__ == "__main__":
    unittest.main()
