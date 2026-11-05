"""The transcript reader: a recorded event stream becomes the files a run opened, its tool calls, and its usage.

Nothing here runs a model. The streams are small text written in each test, and the hook captures in tests/fixtures/live.
"""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run_cli

from aidd.evals import read_transcript, transcripts


def line(**event) -> str:
    return json.dumps(event)


def use(name: str, ident: str | None = None, parent: str | None = None, **tool_input) -> str:
    block = {"type": "tool_use", "name": name, "input": tool_input} | ({"id": ident} if ident else {})
    return line(type="assistant", message={"id": f"msg-{ident}", "content": [block]}, parent_tool_use_id=parent)


RESULT = line(
    type="result",
    subtype="success",
    total_cost_usd=0.25,
    usage={"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40},
)


class FilesOpenedTests(unittest.TestCase):
    def test_which_calls_open_a_file(self):
        cases = {
            "reads, in order, repeats kept": (
                [use("Read", "a", file_path="x.md"), use("Read", "b", file_path="y.md"), use("Read", "c", file_path="x.md")],
                ("x.md", "y.md", "x.md"),
            ),
            "a write or an edit is a call, not an open": (
                [use("Write", "a", file_path="x.md"), use("Edit", "b", file_path="x.md"), use("Bash", "c", command="cat x.md")],
                (),
            ),
            "a notebook read": ([use("NotebookRead", "a", notebook_path="n.ipynb")], ("n.ipynb",)),
            "a read with no path": ([use("Read", "a")], ()),
            "a subagent's read counts": ([use("Read", "a", parent="toolu_parent", file_path="x.md")], ("x.md",)),
        }
        for name, (events, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(read_transcript("\n".join(events)).files_opened, expected)


class ToolCallTests(unittest.TestCase):
    def test_calls_in_order_with_input_id_and_parent(self):
        text = "\n".join([use("Skill", "a", skill="aidd"), use("Bash", "b", parent="p1", command="git status")])
        a, b = read_transcript(text).tool_calls
        self.assertEqual((a.name, a.input, a.id, a.parent), ("Skill", {"skill": "aidd"}, "a", None))
        self.assertEqual((b.name, b.input, b.id, b.parent), ("Bash", {"command": "git status"}, "b", "p1"))

    def test_what_is_skipped(self):
        cases = {
            "an id seen twice counts once": [use("Read", "a", file_path="x"), use("Read", "a", file_path="x")],
            "a broken line": ["{not json", use("Read", "a", file_path="x")],
            "a line that is not an object": ["[1, 2]", "3", '"text"', "", use("Read", "a", file_path="x")],
            "text and tool results": [
                line(type="assistant", message={"content": [{"type": "text", "text": "Read x"}]}),
                line(type="user", message={"content": [{"type": "tool_result", "tool_use_id": "z", "content": "ok"}]}),
                use("Read", "a", file_path="x"),
            ],
            "a block with no name": [line(type="assistant", message={"content": [{"type": "tool_use", "input": {}}]}), use("Read", "a", file_path="x")],
        }
        for name, events in cases.items():
            with self.subTest(name):
                self.assertEqual([c.name for c in read_transcript("\n".join(events)).tool_calls], ["Read"])

    def test_a_call_without_an_id_is_kept_each_time(self):
        text = "\n".join([use("Bash", command="ls"), use("Bash", command="ls")])
        self.assertEqual(len(read_transcript(text).tool_calls), 2)

    def test_a_stream_that_is_empty_or_garbage_is_an_empty_transcript(self):
        for text in ("", "\n\n", "not a stream at all"):
            with self.subTest(text=text):
                self.assertEqual(read_transcript(text), transcripts.Transcript((), (), None))


class UsageTests(unittest.TestCase):
    def test_the_result_event_gives_tokens_and_cost(self):
        got = read_transcript("\n".join([use("Read", "a", file_path="x"), RESULT])).usage
        self.assertEqual(got, transcripts.Usage(10, 20, 30, 40, 0.25))

    def test_a_result_with_only_part_of_it(self):
        cases = {
            "cost only": (line(type="result", total_cost_usd=1.5), transcripts.Usage(cost_usd=1.5)),
            "tokens only": (line(type="result", usage={"input_tokens": 7}), transcripts.Usage(input_tokens=7)),
            "neither": (line(type="result", subtype="error_max_turns"), None),
            "an error result still costs": (
                line(type="result", subtype="error_max_turns", is_error=True, total_cost_usd=0.5, usage={"input_tokens": 3}),
                transcripts.Usage(input_tokens=3, cost_usd=0.5),
            ),
            "a wrong type is not a count": (line(type="result", total_cost_usd="free", usage={"input_tokens": "7", "output_tokens": True}), None),
        }
        for name, (event, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(read_transcript(event).usage, expected)

    def test_a_run_cut_short_sums_each_message_once(self):
        def message(ident: str, input_tokens: int, output_tokens: int) -> str:
            return line(type="assistant", message={"id": ident, "content": [], "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}})

        text = "\n".join([message("m1", 5, 1), message("m1", 5, 9), message("m2", 7, 2)])
        self.assertEqual(read_transcript(text).usage, transcripts.Usage(input_tokens=12, output_tokens=11))

    def test_the_last_result_wins_over_message_usage(self):
        text = "\n".join([line(type="assistant", message={"id": "m", "usage": {"input_tokens": 1}}), RESULT])
        self.assertEqual(read_transcript(text).usage.cost_usd, 0.25)


class SourceTests(unittest.TestCase):
    def test_a_path_and_its_text_read_the_same(self):
        text = "\n".join([use("Read", "a", file_path="x.md"), RESULT])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "run.jsonl"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(read_transcript(path), read_transcript(text))

    def test_the_hook_captures_in_tests_fixtures_read_as_calls_with_no_cost(self):
        live = ROOT / "tests" / "fixtures" / "live"
        pre = {
            p.name: sum(json.loads(raw).get("hook") == "pre-tool" for raw in p.read_text(encoding="utf-8").splitlines())
            for p in live.glob("claude-code-*.jsonl")
        }
        self.assertTrue(pre)
        for name, expected in pre.items():
            with self.subTest(name):
                got = read_transcript(live / name)
                self.assertEqual(len(got.tool_calls), expected)
                self.assertIsNone(got.usage)
                self.assertTrue(all(c.name and c.id for c in got.tool_calls))

    def test_a_hook_capture_gives_the_subagent_as_parent(self):
        got = read_transcript(ROOT / "tests" / "fixtures" / "live" / "claude-code-2.1.312.jsonl")
        self.assertEqual([c.name for c in got.tool_calls][:2], ["Write", "Edit"])
        self.assertTrue(any(c.parent for c in got.tool_calls))
        self.assertFalse(got.tool_calls[0].parent)


class CommandTests(unittest.TestCase):
    def test_aidd_eval_transcript_prints_the_reading_as_json(self):
        code, out = run_cli("eval", "transcript", str(ROOT / "tests" / "fixtures" / "live" / "claude-code-2.1.312.jsonl"))
        self.assertEqual(code, 0, out)
        self.assertTrue(json.loads(out)["tool_calls"])

    def test_it_takes_exactly_one_file(self):
        for argv in ((), ("a.jsonl", "b.jsonl")):
            with self.subTest(argv=argv):
                self.assertEqual(run_cli("eval", "transcript", *argv)[0], 2)


class HostileInputTests(unittest.TestCase):
    def test_hostile_lines_never_stop_the_read(self):
        cases = {
            "nested past the recursion limit": "[" * 200000,
            "a cost too large for a float": '{"type": "result", "total_cost_usd": ' + "9" * 401 + "}",
            "an infinite cost": '{"type": "result", "total_cost_usd": 1e400}',
        }
        for name, text in cases.items():
            with self.subTest(name):
                got = read_transcript(text)
                self.assertEqual(got.tool_calls, ())
                self.assertIsNone(got.usage)

    def test_a_file_past_the_cap_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.jsonl"
            with big.open("wb") as f:
                f.truncate(transcripts.MAX_TRANSCRIPT_BYTES + 1)
            with self.assertRaises(ValueError):
                read_transcript(big)


if __name__ == "__main__":
    unittest.main()
