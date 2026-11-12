"""`aidd recall`: a search of what the team already wrote, through the index, a cache of the files.

Each test builds a small git repository with every source recall reads, and searches it. The answer is data, so the
tests read its fields: where each match is, its order, its snippet, and how it searched."""

import contextlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, run_cli

from aidd import recall, records, workitems
from aidd.cli import mcp_server
from aidd.kernel import index, json_schema
from aidd.recall import sources

RECORD_ID = "20261105T100000000Z-abcd1234"
DOCS = {
    "specs/SPEC-1.md": "---\nid: SPEC-1\n---\n# Retry the payment job\n\nThe retry budget is three tries.\n",
    "specs/SPEC-1/test-plan-retries.md": "# Test plan\n\nA job past its retry budget stops.\n",
    "docs/decisions/0001-queue.md": "# 1. Queue\n\nWe keep one retry budget per queue.\n",
    "docs/GLOSSARY.md": "| Term | Meaning |\n| --- | --- |\n| Retry budget | How many tries a job gets. |\n",
    "docs/product/brief.md": "# Request\n\nNo job may retry past its budget.\n",
    "docs/retros/improvement-log.md": "# Improvement log\n\n| Retry budget alerts | 2026-12-01 |\n",
}


class RecallCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        for rel, text in DOCS.items():
            self.write(rel, text)
        folder = self.root / ".git" / "aidd" / "records" / "2026" / "11"
        folder.mkdir(parents=True)
        record = {
            "id": RECORD_ID,
            "type": "report",
            "recorded_at": "2026-11-05T10:00:00Z",
            "by": "agent:x/y",
            "data": {"action": "pr.open", "said": "Opened the retry budget PR."},
        }
        (folder / f"{RECORD_ID}.json").write_text(json.dumps(record), encoding="utf-8")
        git(self.root, "add", "-A")
        env = {**os.environ, "GIT_COMMITTER_DATE": "2026-01-02T03:04:05+07:00", "GIT_AUTHOR_DATE": "2026-01-02T03:04:05+07:00"}
        git(
            self.root,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "Add the retry budget",
            env=env,
        )

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def search(self, *words: str, **kw) -> dict:
        return recall.search(self.root, None, list(words), **kw)


class SourcesTests(RecallCase):
    def test_each_source_is_found_with_where_it_is(self):
        answer = self.search("retry", "budget")
        self.assertEqual(answer["method"], "full_text")
        by_source = {m["source"]: m for m in answer["matches"]}
        self.assertEqual(set(by_source), {"record", "spec", "adr", "glossary", "product-brief", "improvement-log", "commit"})
        self.assertEqual(by_source["record"]["id"], RECORD_ID)
        self.assertEqual(by_source["commit"]["sha"], git(self.root, "rev-parse", "--short", "HEAD"))
        self.assertEqual(by_source["commit"]["at"], "2026-01-01T20:04:05Z", "a commit's time is in UTC")
        self.assertEqual((by_source["adr"]["path"], by_source["adr"]["line"]), ("docs/decisions/0001-queue.md", 3))
        spec_paths = {m["path"] for m in answer["matches"] if m["source"] == "spec"}
        self.assertEqual(spec_paths, {"specs/SPEC-1.md", "specs/SPEC-1/test-plan-retries.md"}, "a Spec's own documents are searched too")

    def test_an_intent_and_its_folder_are_searched_with_the_specs(self):
        self.write("product/intents/INTENT-1.md", "---\nid: INTENT-1\n---\n# Cap the retry budget\n")
        self.write("product/intents/INTENT-1/notes.md", "The retry budget was agreed.\n")
        paths = {m["path"] for m in self.search("retry", "budget")["matches"] if m["source"] == "spec"}
        self.assertEqual(paths - {"specs/SPEC-1.md", "specs/SPEC-1/test-plan-retries.md"}, {"product/intents/INTENT-1.md", "product/intents/INTENT-1/notes.md"})

    def test_newest_first_then_by_source_path_and_line(self):
        matches = self.search("budget")["matches"]
        self.assertEqual([m["source"] for m in matches[:2]], ["record", "commit"], "the dated matches come first, newest first")
        rest = [(m["source"], m["path"], m["line"]) for m in matches[2:]]
        self.assertEqual(rest, sorted(rest))
        self.assertTrue(all("at" not in m for m in matches[2:]))

    def test_a_line_must_hold_every_word(self):
        matches = self.search("budget", "queue")["matches"]
        self.assertEqual([(m["path"], m["line"]) for m in matches], [("docs/decisions/0001-queue.md", 3)])

    def test_the_index_follows_the_files(self):
        self.assertEqual(self.search("zebra")["matches"], [])
        self.write("docs/GLOSSARY.md", DOCS["docs/GLOSSARY.md"] + "| Zebra | A striped test term. |\n")
        self.assertEqual([m["line"] for m in self.search("zebra")["matches"]], [4], "a changed file is read again")
        (self.root / "docs/GLOSSARY.md").unlink()
        self.assertEqual(self.search("zebra")["matches"], [], "a removed file leaves the index")

    def test_a_removed_worktrees_rows_leave_the_index(self):
        self.search("budget")
        path = workitems.index_path(self.root)
        stale = f"recall:{self.root}-removed-worktree:glossary"
        with contextlib.closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("INSERT INTO passage (text, place, ref, line, at) VALUES ('old budget', ?, 'x.md', 1, NULL)", (stale,))
            conn.execute("INSERT INTO passage_source (name, stamp) VALUES (?, 's')", (stale,))
        self.search("budget")
        with contextlib.closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM passage WHERE place = ?", (stale,)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM passage_source WHERE name = ?", (stale,)).fetchone()[0], 0)

    def test_the_limit_caps_the_matches_and_says_more_matched(self):
        answer = self.search("budget", limit=2)
        self.assertEqual((len(answer["matches"]), answer["more"]), (2, True))
        self.assertFalse(self.search("budget", limit=recall.MAX_MATCHES)["more"])
        for bad in (0, recall.MAX_MATCHES + 1):
            with self.assertRaises(ValueError):
                self.search("budget", limit=bad)


class SnippetTests(RecallCase):
    def test_a_snippet_is_one_short_safe_line_around_the_word(self):
        self.write("docs/decisions/0002-long.md", "x " * 300 + "the \x1b[31m marker \x1b[0m word \N{RIGHT-TO-LEFT OVERRIDE} here " + "y " * 300 + "\n")
        (m,) = self.search("marker")["matches"]
        self.assertLessEqual(len(m["snippet"]), 160)
        self.assertIn("marker", m["snippet"])
        self.assertTrue(m["snippet"].startswith("…"), "a long line is cut to just before the word")
        self.assertFalse(any(c in m["snippet"] for c in "\x1b\N{RIGHT-TO-LEFT OVERRIDE}\n"), "no control or bidi character reaches a terminal")


class QueryTests(RecallCase):
    def test_full_text_syntax_in_a_query_is_only_words(self):
        plain = self.search("budget")["matches"]
        for given in (['"budget"'], ["budget*"], ["(budget)"], ["^budget"], ["-budget"], ['"budget', "*"]):
            with self.subTest(given=given):
                self.assertEqual(self.search(*given)["matches"], plain, "quotes, stars, and groups are no syntax")
        for given in (["budget OR zebra"], ["NOT zebra"], ["budget NEAR zebra"], ["text:budget"], ['budget" OR "zebra']):
            with self.subTest(given=given):
                answer = self.search(*given)
                self.assertEqual(answer["matches"], [], "an operator or a column is a word every line must hold, so it never widens the match")
        self.assertEqual(self.search('budget" OR "*')["words"], ["budget", "OR"])
        self.assertEqual(self.search("retry_budget")["words"], ["retry", "budget"], "an underscore splits words, as the full-text search does")

    def test_a_query_with_no_word_is_refused(self):
        for given in (['"*"'], ["( ) ^ -"], [""]):
            with self.subTest(given=given), self.assertRaises(ValueError):
                self.search(*given)
        with self.assertRaises(ValueError):
            self.search(*[f"w{i}" for i in range(17)])


class FallbackTests(RecallCase):
    def test_without_fts5_it_searches_as_plain_text_with_the_same_answer(self):
        with mock.patch.object(index, "PASSAGE_TABLE", "CREATE VIRTUAL TABLE passage USING no_such_module(text)"):
            plain = self.search("retry", "budget")
        self.assertEqual(plain["method"], "substring")
        full = self.search("retry", "budget")
        self.assertEqual(full["method"], "full_text", "a later SQLite with FTS5 adds the table to the same index")
        self.assertEqual(plain["matches"], full["matches"])

    def test_an_index_of_version_1_is_rebuilt_and_then_searched(self):
        path = workitems.index_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE entry (place TEXT, type TEXT, id TEXT, subject TEXT, at TEXT, data TEXT)")
            conn.execute("CREATE TABLE source (name TEXT PRIMARY KEY, stamp TEXT NOT NULL)")
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        answer = self.search("queue")
        self.assertEqual((answer["method"], len(answer["matches"])), ("full_text", 2))
        with contextlib.closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], index.SCHEMA_VERSION)


class BoundsTests(RecallCase):
    def test_a_file_over_the_cap_or_a_link_is_skipped_and_named(self):
        self.write("specs/SPEC-2.md", "budget\n" * (sources.MAX_FILE_BYTES // 7 + 1))
        (self.root / "specs" / "SPEC-3.md").symlink_to(self.root / "docs" / "GLOSSARY.md")
        answer = self.search("budget")
        self.assertNotIn("specs/SPEC-2.md", {m.get("path") for m in answer["matches"]})
        self.assertNotIn("specs/SPEC-3.md", {m.get("path") for m in answer["matches"]})
        self.assertEqual([s["path"] for s in answer["skipped"]], ["specs/SPEC-2.md", "specs/SPEC-3.md"])


class OutputTests(RecallCase):
    def test_the_json_follows_its_schema(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("recall", "retry", "budget", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(json_schema.validate(data, "recall.schema.json"), [])
        self.assertEqual(len(data["matches"]), 8)

    def test_the_text_names_each_match_once_per_line(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("recall", "queue", "--limit", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("docs/decisions/0001-queue.md:1  ", out)
        self.assertEqual(len(out.splitlines()), 3, "the note, the match, and that more matched")

    def test_the_mcp_tool_answers_with_the_json(self):
        is_error, text = mcp_server.call("recall", {"words": "retry budget", "limit": 1}, str(self.root))
        self.assertFalse(is_error, text)
        self.assertEqual(len(json.loads(text)["matches"]), 1)
        for bad in ({"words": ["retry"]}, {"words": "retry", "limit": "1"}, {"words": "retry", "limit": True}):
            with self.subTest(bad=bad):
                self.assertTrue(mcp_server.call("recall", bad, str(self.root))[0])
        is_error, _ = mcp_server.call("recall", {"words": "--help"}, str(self.root))
        self.assertFalse(is_error, "a word that looks like an option is a word")


class PulledRecordTests(RecallCase):
    """A record that `aidd records pull` added is another clone's text. Its match says so, in every form the answer takes, so an
    agent never reads those words as this clone's own account; no other match says it."""

    def pull(self) -> None:
        (records.records_dir(str(self.root)).parent / "records-pulled").write_text(RECORD_ID + "\n", encoding="utf-8")

    def test_only_a_pulled_records_match_is_marked(self):
        for pulled in (False, True):
            with self.subTest(pulled=pulled):
                if pulled:
                    self.pull()
                matches = self.search("retry", "budget")["matches"]
                marked = {m["source"] for m in matches if m.get("pulled")}
                self.assertEqual(marked, {"record"} if pulled else set())
                self.assertTrue(all(m["pulled"] is True for m in matches if "pulled" in m), "the key is present only when true")

    def test_the_mark_reaches_the_json_the_text_and_the_tool(self):
        self.pull()
        with contextlib.chdir(self.root):
            _, out = run_cli("recall", "retry", "budget", "--json")
            _, text = run_cli("recall", "retry", "budget")
        shown = json.loads(out)
        self.assertEqual(json_schema.validate(shown, "recall.schema.json"), [])
        self.assertEqual([m["id"] for m in shown["matches"] if m.get("pulled")], [RECORD_ID])
        self.assertEqual(len([line for line in text.splitlines() if "pulled from a remote" in line]), 1)
        _, via_tool = mcp_server.call("recall", {"words": "retry budget"}, str(self.root))
        self.assertEqual(json.loads(via_tool), shown)

    def test_a_list_of_pulled_records_that_cannot_be_read_stops_the_answer_that_holds_a_record(self):
        (records.records_dir(str(self.root)).parent / "records-pulled").mkdir()
        with self.assertRaises(ValueError):
            self.search("retry", "budget")
        self.assertEqual(self.search("queue")["matches"][0]["source"], "adr", "an answer with no record needs no list")


if __name__ == "__main__":
    unittest.main()
