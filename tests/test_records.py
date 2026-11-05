"""Records: one immutable file of history for each answered ask and each reported action, in the clone's shared git
folder. Writing checks a record's shape and refuses a secret's value; reading keeps every record it can parse."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_here, git, write_executable

from aidd import records
from aidd.cli import mcp_server
from aidd.kernel import secret_patterns
from aidd.records import files, sharing

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
        self.assertEqual(aidd_here("records", cwd=self.root).returncode, 0, "a record of any shape lists")
        newer["subject"] = "SPEC-4\x1b]0;owned\x07"  # a pulled record is another's text: printed, it never drives the terminal
        (folder / f"{newer['id']}.json").write_text(json.dumps(newer), encoding="utf-8")
        listed = aidd_here("records", cwd=self.root).stdout
        self.assertIn("SPEC-4 ]0;owned ", listed)
        self.assertNotIn("\x1b", listed)
        self.assertEqual([Path(u).name for u in unreadable], ["20270101T000000001Z-11111111.json"])

    def test_the_command_and_the_mcp_tool_write_as_the_agent_never_as_a_person(self):
        data = json.dumps(APPROVAL)
        refused = aidd_here("records", "add", "--type", "decision", "--by", "person:Ada", "--data", data, cwd=self.root)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("never a person's name", refused.stderr)
        added = aidd_here("records", "add", "--type", "decision", "--by", "claude-code/claude-opus-5-5", "--data", "-", cwd=self.root, input=data)
        self.assertEqual(added.returncode, 0, added.stderr)
        is_error, text = mcp_server.call(
            "record", {"type": "report", "by": "codex/gpt-5", "data": {"action": "pr.open", "said": "Opened PR #12."}}, str(self.root)
        )
        self.assertFalse(is_error, text)
        self.assertEqual(mcp_server.call("record", {"type": "report", "by": "codex/gpt-5", "data": "x"}, str(self.root))[0], True)
        listed = aidd_here("records", "--json", cwd=self.root)
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
        self.assertEqual(aidd_here("records", cwd=self.root).stdout.count("through the MCP tool"), 1)
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

    def blobless_clone(self, name: str) -> Path:
        """A clone that leaves every blob out until something asks for it, as `git clone --filter=blob:none` makes."""
        git(self.remote, "config", "uploadpack.allowFilter", "true")
        path = self.base / name
        git(self.base, "clone", "-q", "--filter=blob:none", f"file://{self.remote}", str(path))
        git(path, "config", "user.name", name)
        git(path, "config", "user.email", f"{name}@example.com")
        return path

    def remote_records(self) -> list[str]:
        return sorted(git(self.remote, "ls-tree", "-r", "--name-only", "refs/aidd/records").splitlines())

    def test_a_blobless_clone_pulls_every_record_and_a_push_from_it_drops_none(self):
        for words in ("yes", "go ahead"):
            records.add_record("decision", with_(APPROVAL, "answer.words", words), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        theirs = self.remote_records()
        self.assertEqual(len(theirs), 2)
        carol = self.blobless_clone("carol")
        added, refused = records.pull_records("origin", str(carol))
        self.assertEqual((len(added), refused), (2, []), "the fetch asks for the blobs the clone's filter would leave out")
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(carol))
        self.assertEqual(records.push_records("origin", str(carol)), (0, 3))
        self.assertEqual(len(self.remote_records()), 3, "the remote keeps the records of everyone who pushed")
        self.assertTrue(set(theirs) <= set(self.remote_records()))
        self.assertEqual(len(records.pull_records("origin", str(self.ada))[0]), 1)

    def test_a_record_without_its_content_here_fails_closed_after_a_full_fetch_and_a_push_never_goes_on(self):
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        before = git(self.remote, "rev-parse", "refs/aidd/records")
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #13."}, by=BY, cwd=str(self.bo))
        with mock.patch.object(files.git, "raw_objects", return_value={}) as read, mock.patch.object(files.git, "attempt", wraps=files.git.attempt) as attempts:
            for call in (records.pull_records, records.push_records):
                with self.subTest(call=call.__name__), self.assertRaisesRegex(files.git.GitError, r"no content, even after a full fetch.*origin lacks them"):
                    call("origin", str(self.bo))
        self.assertTrue(any("--refetch" in c.args[0] for c in attempts.call_args_list), "it fetched everything once more before it gave up")
        self.assertEqual(git(self.remote, "rev-parse", "refs/aidd/records"), before, "nothing was pushed")
        self.assertTrue(read.called)

    def test_a_clone_whose_tracking_ref_is_at_the_tip_without_the_blobs_gets_them_by_the_one_full_fetch(self):
        """A clone that pulled with its filter on: the tracking ref is current, so a plain fetch sends nothing."""
        for words in ("yes", "go ahead"):
            records.add_record("decision", with_(APPROVAL, "answer.words", words), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        carol = self.blobless_clone("carol")
        git(carol, "fetch", "-q", "origin", f"+{sharing.REF}:{sharing._tracking('origin')}")  # inherits the filter
        self.assertEqual(files.git.raw_objects(list(files.git.ls_tree(sharing._tracking("origin"), str(carol)).values()), str(carol)), {})
        added, refused = records.pull_records("origin", str(carol))
        self.assertEqual((len(added), refused), (2, []))

    def test_a_file_the_pull_refused_stays_on_the_remote_and_blocks_nobody(self):
        good, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        junk = "2026/11/20261105T000000000Z-aaaaaaaa.json"
        self.push_junk(good, {junk: "not json"})
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #13."}, by=BY, cwd=str(self.bo))
        pulled, held = records.push_records("origin", str(self.bo))
        self.assertEqual((pulled, held), (1, 2))
        self.assertIn(junk, self.remote_records(), "the file stays on the remote, untouched")
        self.assertEqual(len(self.remote_records()), 3, "the junk file and both records")
        self.assertEqual(git(self.remote, "show", f"refs/aidd/records:{junk}"), "not json")

    def test_a_path_git_refuses_in_the_remotes_tree_blocks_no_push_and_drops_on_the_next(self):
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        self.push_bad_path()
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #13."}, by=BY, cwd=str(self.bo))
        pulled, held = records.push_records("origin", str(self.bo))
        self.assertEqual((pulled, held), (1, 2))
        self.assertEqual(len(self.remote_records()), 2, "both records; the path that is no record is gone")
        self.assertNotIn(".git/config", self.remote_records())

    def test_a_copy_of_a_record_in_another_folder_is_refused_and_never_shown_first(self):
        record, _ = records.add_record("decision", with_(APPROVAL, "answer.words", "no, stop"), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        records.pull_records("origin", str(self.bo))
        folder = files.records_dir(str(self.bo))
        [own] = list(folder.glob("*/*/*.json"))
        copy = folder / "2099" / "12" / own.name  # not the year and month of the id
        copy.parent.mkdir(parents=True)
        forged = json.loads(own.read_text(encoding="utf-8"))
        forged["data"]["answer"]["words"] = "yes"
        copy.write_text(json.dumps(forged), encoding="utf-8")
        before = git(self.remote, "rev-parse", "refs/aidd/records")
        with self.assertRaisesRegex(ValueError, "folder is not the year and month of its id"):
            records.push_records("origin", str(self.bo))
        self.assertEqual(git(self.remote, "rev-parse", "refs/aidd/records"), before, "nothing was pushed")
        found, unreadable = records.read_records(str(self.bo))
        self.assertEqual([r["data"]["answer"]["words"] for r in found if r["id"] == record["id"]], ["no, stop"], "one record has the id, and it is the first")
        [named] = [u for u in unreadable if "2099" in u]
        self.assertIn(f"a second file with the id {record['id']}", named)

    def test_a_record_is_judged_by_its_id_not_by_its_path(self):
        record, _ = records.add_record("decision", with_(APPROVAL, "answer.words", "no, stop"), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        records.pull_records("origin", str(self.ada))  # brings the tracking ref up to what was pushed
        theirs = sharing._commit_of(sharing._tracking("origin"), str(self.ada))
        held = sharing._remote_entries(theirs, str(self.ada))
        self.assertEqual(len(held), 1)
        forged = json.dumps({**record, "data": {**record["data"], "answer": {**record["data"]["answer"], "words": "yes"}}}).encode()
        elsewhere = f"2099/12/{record['id']}.json"  # a path the remote does not hold, with an id it does
        with self.assertRaisesRegex(ValueError, "differ from the ones origin holds with the same id"):
            sharing._records_commit("origin", {elsewhere: forged}, str(self.ada))

    def test_a_copy_in_another_folder_already_on_the_remote_blocks_no_clone_s_push(self):
        """From an aidd before the folder check, or plain git: the copy is a refused file, and the genuine record stays."""
        record, _ = records.add_record("decision", with_(APPROVAL, "answer.words", "no, stop"), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        carol = self.clone("carol")
        records.pull_records("origin", str(carol))
        genuine = f"{record['id'][:4]}/{record['id'][4:6]}/{record['id']}.json"
        before = git(self.remote, "show", f"refs/aidd/records:{genuine}")
        forged = {**record, "data": {**record["data"], "answer": {**record["data"]["answer"], "words": "yes"}}}
        self.push_junk(record, {f"2099/12/{record['id']}.json": json.dumps(forged)})
        dave = self.clone("dave")  # a fresh clone, on its first push
        for name, clone in (("ada", self.ada), ("carol", carol), ("dave", dave)):
            with self.subTest(clone=name):
                records.add_record("report", {"action": "pr.open", "said": f"Opened by {name}."}, by=BY, cwd=str(clone))
                records.push_records("origin", str(clone))
                self.assertEqual(git(self.remote, "show", f"refs/aidd/records:{genuine}"), before, "the genuine record is unchanged")
        self.assertEqual(len(self.remote_records()), 5, "the genuine record, the copy, and one record from each clone")
        self.assertIn(f"2099/12/{record['id']}.json", self.remote_records(), "the copy stays as it is, refused and harmless")

    def test_a_record_file_is_shared_only_from_its_ids_own_year_and_month(self):
        record, _ = records.add_record("decision", with_(APPROVAL, "answer.words", "yes"), by=BY, cwd=str(self.ada))
        raw = json.dumps(record).encode()
        year, month = record["id"][:4], record["id"][4:6]
        cases = {
            f"{year}/{month}/{record['id']}.json": "",
            f"{year}/{int(month) % 12 + 1:02d}/{record['id']}.json": "its folder is not the year and month of its id",
            f"2099/{month}/{record['id']}.json": "its folder is not the year and month of its id",
        }
        for name, why in cases.items():
            with self.subTest(name=name):
                self.assertEqual(sharing._share_problem(name, raw), why)

    def test_a_local_file_that_differs_from_a_remote_record_only_by_case_names_what_to_move(self):
        good, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        name = f"{good['id'][:4]}/{good['id'][4:6]}/{good['id']}.json"
        clash = files.records_dir(str(self.bo)) / name
        clash.parent.mkdir(parents=True)
        clash.write_text("{}", encoding="utf-8")  # as a case-insensitive file system sees a copy renamed by case
        with mock.patch.object(sharing, "_local_names", return_value={}), self.assertRaises(files.git.GitError) as caught:
            records.pull_records("origin", str(self.bo))
        said = str(caught.exception)
        self.assertIn(f".git/aidd/records/{name}", said)
        self.assertIn("differs only by case", said)
        self.assertIn("move it out of .git/aidd/records/", said)
        self.assertNotIn("FileExistsError", said)

    def push_bad_path(self) -> None:
        """Push a commit whose tree holds `.git/config`: git refuses that path in an index, and a plain bare remote takes it."""
        hostile = self.base / "bad-path"
        git(self.base, "clone", "-q", str(self.remote), str(hostile))
        git(hostile, "fetch", "-q", "origin", "refs/aidd/records:refs/aidd/records")
        sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=hostile, input="[core]\n", capture_output=True, text=True, check=True).stdout.strip()
        inner = subprocess.run(["git", "mktree"], cwd=hostile, input=f"100644 blob {sha}\tconfig\n", capture_output=True, text=True, check=True).stdout.strip()
        top = git(hostile, "ls-tree", "refs/aidd/records")  # the records stay, and the bad path sits beside them
        tree = subprocess.run(
            ["git", "mktree"], cwd=hostile, input=f"{top}\n040000 tree {inner}\t.git\n", capture_output=True, text=True, check=True
        ).stdout.strip()
        commit = git(hostile, "commit-tree", tree, "-p", "refs/aidd/records", "-m", "bad path").strip()
        git(hostile, "push", "-q", "origin", f"{commit}:refs/aidd/records")

    def test_a_pushed_record_is_never_rewritten_by_a_local_edit(self):
        decision = with_(APPROVAL, "answer.words", "no, stop")
        name, _ = records.add_record("decision", decision, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        records.pull_records("origin", str(self.bo))
        [path] = list(files.records_dir(str(self.bo)).glob("*/*/*.json"))
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["data"]["answer"]["words"] = "yes"
        path.write_text(json.dumps(edited), encoding="utf-8")
        before = git(self.remote, "rev-parse", "refs/aidd/records")
        with self.assertRaisesRegex(
            ValueError,
            r"(?s)differ from the ones origin holds with the same id.*\.git/aidd/records/\d{4}/\d{2}/.*\.json.*out of \.git/aidd/records/.*new record with `aidd records add`",
        ):
            records.push_records("origin", str(self.bo))
        self.assertEqual(git(self.remote, "rev-parse", "refs/aidd/records"), before, "nothing was pushed")
        shown = git(self.remote, "show", f"refs/aidd/records:{path.relative_to(files.records_dir(str(self.bo))).as_posix()}")
        self.assertIn("no, stop", shown, "the remote keeps what ada wrote")
        self.assertNotIn('"yes"', shown)

    def test_a_failed_full_fetch_reports_git_s_error_and_not_that_the_remote_lacks_the_records(self):
        for words in ("yes", "go ahead"):
            records.add_record("decision", with_(APPROVAL, "answer.words", words), by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        carol = self.blobless_clone("carol")
        git(carol, "fetch", "-q", "origin", f"+{sharing.REF}:{sharing._tracking('origin')}")  # at the tip, with no blobs
        real = files.git.attempt

        def refetch_fails(args, *rest, **kw):
            return (1, "fatal: unknown option `refetch'") if "--refetch" in args else real(args, *rest, **kw)

        with mock.patch.object(files.git, "attempt", refetch_fails), self.assertRaises(files.git.GitError) as caught:
            records.pull_records("origin", str(carol))
        said = str(caught.exception)
        self.assertIn("the full fetch that would bring them failed: fatal: unknown option", said)
        self.assertIn("needs git 2.36 or newer", said)
        self.assertNotIn("lacks them", said)

    def push_junk(self, good: dict, entries: dict[str, str]) -> None:
        """Push `entries` (file name -> text) into the remote's records ref, beside what it holds."""
        hostile = self.base / "hostile"
        git(self.base, "clone", "-q", str(self.remote), str(hostile))
        git(hostile, "fetch", "-q", "origin", "refs/aidd/records:refs/aidd/records")
        index = self.base / "hostile-index"
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        git(hostile, "read-tree", "refs/aidd/records", env=env)
        for name, text in entries.items():
            sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=hostile, input=text, capture_output=True, text=True, check=True).stdout.strip()
            git(hostile, "update-index", "--add", "--cacheinfo", f"100644,{sha},{name}", env=env)
        tree = git(hostile, "write-tree", env=env).strip()
        commit = git(hostile, "commit-tree", tree, "-p", "refs/aidd/records", "-m", "hostile").strip()
        git(hostile, "push", "-q", "origin", f"{commit}:refs/aidd/records")

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
                self.assertEqual(aidd_here(*argv, cwd=self.ada).returncode, 2)
        self.assertFalse(files.git.run(["ls-remote", str(self.remote)], str(self.ada)).strip(), "nothing reached the remote")
        self.assertEqual(aidd_here("records", "push", "origin", cwd=self.ada).returncode, 0)
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
        write_executable(hook, "#!/bin/sh\necho 'protected ref' >&2\nexit 1\n")
        with self.assertRaisesRegex(files.git.GitError, "refused the records: .*protected ref"):
            records.push_records("origin", str(self.ada))
        self.assertEqual(files.git.run(["rev-parse", "-q", "--verify", "refs/aidd/records"], str(self.ada), check=False).strip(), "")

    def test_a_pulled_file_that_is_no_record_is_skipped_and_named_and_a_pulled_record_is_marked(self):
        good, _ = records.add_record("report", {"action": "pr.open", "said": "Opened PR #12."}, by=BY, cwd=str(self.ada))
        records.push_records("origin", str(self.ada))
        entries = {
            "2026/11/20261105T000000000Z-aaaaaaaa.json": "[" * 100_000 + "]" * 100_000,
            "2026/11/20261105T000000001Z-bbbbbbbb.json": json.dumps({**good, "id": "20261105T000000001Z-bbbbbbbb", "by": "agent:x\u202e"}),
            "2026/11/20261105T000000002Z-cccccccc.json": json.dumps(
                {**good, "id": "20261105T000000002Z-cccccccc", "data": {"said": "".join(("token=", "abcdefgh12345678"))}, "type": "note"}
            ),
        }
        self.push_junk(good, entries)
        added, refused = records.pull_records("origin", str(self.bo))
        self.assertEqual(added, [f"2026/11/{good['id']}.json"])
        self.assertEqual(sorted(r.split(":")[0] for r in refused), sorted(entries))
        listed = aidd_here("records", cwd=self.bo)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("pulled from a remote", listed.stdout)
        self.assertEqual(json.loads(aidd_here("records", "--json", cwd=self.bo).stdout)["pulled"], [good["id"]])


if __name__ == "__main__":
    unittest.main()
