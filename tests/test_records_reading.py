"""Records read the same whenever they were written, and a record this aidd cannot read in full is kept and named, never trusted.

Two readers, two rules. A reader of history is lenient: it reads a retired name as today's (`at` as `recorded_at`, a question
type `approval` as `yes_no`), keeps a record with a type, a field, or a value it does not know, and names it in `partly_read`.
The delegation is strict: it counts an accept only from a record that is today's shape in full, as it was written, and it
counts a defer from any record that parses, since a defer only narrows.

Invariants. (1) A repository whose records hold the old names gives the same answers as its twin in today's names: the
listing, the search, the suggestions, and what a clone pulls. (2) No file is rewritten. (3) For every record on disk, the
delegation counts no accept that the commit before this change did not count, and no defer is lost. (4) A new record never
says a retired name. (5) A record with a secret, a size past the cap, or a missing or mistyped field is never kept by a pull."""

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import ROOT, aidd_here, git

from aidd import config, recall, records, risk
from aidd.cli import mcp_server
from aidd.delegation import action_checks
from aidd.kernel import json_schema, resources, retired_names
from aidd.records import files, sharing

FIXTURES = ROOT / "tests" / "fixtures" / "migration" / "records"
BY = "agent:claude-code/claude-opus-5-5"
HEAD = "c" * 40
DELEGATED = {"decides": ["spec.approve", "git.merge"]}


def fixture(shape: str) -> dict[str, dict]:
    """The fixture records of `shape` (`pre` has the old names, `today` its twin), by id."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((FIXTURES / shape).glob("*/*/*.json"))}


def put(root: Path, record: dict, text: str | None = None) -> Path:
    """Place `record` in the records folder of the clone at `root`, as a file a writer or a pull left there."""
    path = files.records_dir(str(root)) / record["id"][:4] / record["id"][4:6] / f"{record['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n" if text is None else text, encoding="utf-8")
    return path


def _with(base: dict, path: str, value) -> dict:
    out = copy.deepcopy(base)
    *parents, last = path.split(".")
    node = out
    for p in parents:
        node = node[p]
    node[last] = value
    return out


def clone_of(base: Path, name: str) -> Path:
    root = base / name
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Ada Person")
    git(root, "config", "user.email", "ada@example.com")
    git(root, "commit", "-q", "--allow-empty", "-m", "init")
    return root


def digest(root: Path) -> dict[str, str]:
    folder = files.records_dir(str(root))
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*/*/*.json"))}


class Scratch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()

    def repo_with(self, name: str, shape: str) -> Path:
        root = clone_of(self.base, name)
        for record in fixture(shape).values():
            put(root, record)
        return root


class TheTwoShapesReadTheSame(Scratch):
    """Invariants 1 and 2: the old names and their twin give the same answers, and no file is rewritten."""

    def setUp(self):
        super().setUp()
        self.old, self.new = self.repo_with("old", "pre"), self.repo_with("new", "today")

    def test_each_old_record_reads_as_its_twin_and_the_files_stay_as_they_were(self):
        before = digest(self.old)
        pre, twin = fixture("pre"), fixture("today")
        self.assertEqual(set(pre), set(twin))
        self.assertTrue(all("at" in r and "recorded_at" not in r for r in pre.values()), "the fixture is in the old shape")
        for rid in pre:
            with self.subTest(record=rid):
                self.assertEqual(files.todays_shape(pre[rid]), twin[rid])
        self.assertEqual(records.read_records(str(self.old)), records.read_records(str(self.new)))
        self.assertEqual(digest(self.old), before, "reading rewrote nothing")
        written = records.read_records(str(self.old), as_written=True)[0]
        self.assertEqual({r["id"]: r for r in written}, pre, "as written is the file, byte for byte in content")

    def test_the_listing_the_search_and_the_suggestions_are_the_same_for_both(self):
        for words in (("--json",), ()):
            old, new = aidd_here("records", *words, cwd=self.old), aidd_here("records", *words, cwd=self.new)
            self.assertEqual((old.returncode, old.stderr), (0, ""))
            self.assertEqual(old.stdout, new.stdout, words)
        listed = json.loads(aidd_here("records", "--json", cwd=self.old).stdout)
        self.assertEqual(json_schema.validate(listed, "records.schema.json#/$defs/list"), [])
        self.assertEqual(listed["partly_read"], [], "an old name is read in full, not in part")
        # The search reads the dates and the words: a record that kept `at` or `approval` would be undated, or miss `yes_no`.
        for words in (["push"], ["yes_no"], ["layout"], ["PR"]):
            with self.subTest(words=words):
                found = [m for m in recall.search(self.old, None, words)["matches"] if m["source"] == "record"]
                twin = [m for m in recall.search(self.new, None, words)["matches"] if m["source"] == "record"]
                self.assertTrue(found)
                self.assertEqual(found, twin)
        [dated] = [m for m in recall.search(self.old, None, ["yes_no"])["matches"] if m["source"] == "record"]
        self.assertEqual(dated["at"], "2026-11-01T10:00:00Z")
        self.assertEqual(recall.search(self.old, None, ["approval"])["matches"], [], "the old word is not a second name")
        for root in (self.old, self.new):
            for n in range(10):
                record = copy.deepcopy(fixture("pre" if root == self.old else "today")["20261101T100000000Z-a0000001"])
                record["id"] = f"20261101T1200{n:02d}000Z-b00000{n:02d}"
                put(root, record)
        suggested = [risk.rule_suggestions(risk.rule_set(None), str(root)) for root in (self.old, self.new)]
        self.assertEqual(suggested[0], suggested[1])
        self.assertEqual([(s["action"], s["branch"], s["ask_count"]) for s in suggested[0]["suggestions"]], [("git.push", "shared", 11)])

    def test_a_clone_pushes_old_records_untouched_and_another_pulls_them_in_todays_names(self):
        remote = self.base / "remote.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(remote))
        for root in (self.old, self.new):
            git(root, "remote", "add", "origin", str(remote))
        before = digest(self.old)
        self.assertEqual(records.push_records("origin", str(self.old)), (0, 4))
        sent = git(remote, "ls-tree", "-r", "refs/aidd/records").splitlines()
        self.assertEqual(len(sent), 4)
        for line in sent:
            meta, name = line.split("\t")
            blob = git(remote, "cat-file", "blob", meta.split()[2]).encode() + b"\n"
            self.assertEqual(hashlib.sha256(blob).hexdigest(), before[name], "the remote holds the file as it was written")
        carol = clone_of(self.base, "carol")
        git(carol, "remote", "add", "origin", str(remote))
        added, refused = records.pull_records("origin", str(carol))
        self.assertEqual((len(added), refused), (4, []))
        self.assertEqual(digest(carol), before, "the pull keeps each record byte for byte")
        self.assertEqual(records.read_records(str(carol)), records.read_records(str(self.new)))


class ANewRecordNeverSaysARetiredName(Scratch):
    """Invariant 4. The enum keeps `approval` so an old record validates, and the writer refuses it."""

    def test_a_write_of_the_old_value_is_refused_and_names_the_new_one(self):
        root = clone_of(self.base, "r")
        data = fixture("today")["20261101T100000000Z-a0000001"]["data"]
        old = with_question_type(data, "approval")
        for name, attempt in (
            ("add_record", lambda: records.add_record("decision", old, by=BY, cwd=str(root))),
            ("the command", lambda: aidd_here("records", "add", "--type", "decision", "--by", "claude-code/x", "--data", json.dumps(old), cwd=root)),
            ("the MCP tool", lambda: mcp_server.call("record", {"type": "decision", "by": "claude-code/x", "data": old}, str(root))),
        ):
            with self.subTest(writer=name):
                try:
                    result = attempt()
                    said = json.loads(result[1])["error"]["message"] if name == "the MCP tool" else result.stderr
                except records.RecordError as exc:
                    said = str(exc)
                self.assertIn("'approval' was retired in 1.0.0; write 'yes_no'", said)
        self.assertEqual(records.read_records(str(root))[0], [], "nothing was written")
        written, _ = records.add_record("decision", with_question_type(data, "yes_no"), by=BY, cwd=str(root))
        self.assertEqual(written["data"]["question"]["type"], "yes_no")
        self.assertIn("recorded_at", written)
        self.assertNotIn("at", written)

    def test_the_envelope_has_no_old_name_either(self):
        record = fixture("pre")["20261101T100200000Z-a0000003"]
        self.assertTrue(files.record_problems(record), "the writer's check refuses `at`")
        self.assertEqual(files.record_problems(record, reading=True), [], "the reader's check reads it as `recorded_at`")


def with_question_type(data: dict, value: str) -> dict:
    out = copy.deepcopy(data)
    out["question"]["type"] = value
    return out


class TheRowsOfTheTableAreTrue(unittest.TestCase):
    """Every `record` row has a fixture that holds the old name, and the schemas agree with what the row says."""

    def test_each_record_row_has_an_old_shape_fixture_and_a_twin_that_holds_its_new_name(self):
        rows = retired_names.rows("record")
        self.assertEqual([r["id"] for r in rows], ["record-at", "record-question-type-approval"])
        pre, twin = fixture("pre").values(), fixture("today").values()
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertEqual(row["rule"], "read_both")
                old = [p for r in pre for p in retired_names.paths_in(r, row["old"]) if row.get("read_as") is None or _at(r, p) in row["read_as"]]
                self.assertTrue(old, f"no fixture record holds {row['old']}")
                new = [p for r in twin for p in retired_names.paths_in(r, row["new"]) if row.get("read_as") is None or _at(r, p) in row["read_as"].values()]
                self.assertTrue(new, f"no twin holds {row['new']}")

    def test_the_schemas_keep_what_a_reader_must_read_and_the_writer_must_not_write(self):
        envelope = resources.load_json("records.schema.json")["$defs"]["record"]
        self.assertNotIn("at", envelope["properties"])
        self.assertIn("recorded_at", envelope["required"])
        row = next(r for r in retired_names.rows("record") if "read_as" in r)
        enum = resources.load_json("records.json")["types"]["decision"]["data"]["properties"]["question"]["properties"]["type"]["enum"]
        for old, new in row["read_as"].items():
            self.assertIn(old, enum, "an input enum never narrows: an old record still validates")
            self.assertIn(new, enum)


def _at(record: dict, path: tuple):
    for step in path:
        record = record[step]
    return record


class TheListingNamesWhatItReadsInPart(Scratch):
    """Invariant 5 and the lenient reader: unknown things are kept and named, broken ones are named and never kept by a pull."""

    GOOD = fixture("today")["20261101T100000000Z-a0000001"]
    REPORT = fixture("today")["20261101T100200000Z-a0000003"]

    def variants(self) -> dict[str, dict]:
        """Records a newer aidd writes: an unknown field at every object level, an unknown value in each enum, an unknown type."""

        def with_(base: dict, path: str, value) -> dict:
            out = copy.deepcopy(base)
            *parents, last = path.split(".")
            node = out
            for p in parents:
                node = node[p]
            node[last] = value
            return out

        return {
            "an unknown envelope field": with_(self.GOOD, "hash", "abc"),
            "an unknown data field": with_(self.GOOD, "data.risk_note", "n"),
            "an unknown question field": with_(self.GOOD, "data.question.hint", "h"),
            "an unknown answer field": with_(self.GOOD, "data.answer.channel", "chat"),
            "an unknown covers field": with_(self.GOOD, "data.covers.environment", "staging"),
            "an unknown report field": with_(self.REPORT, "data.link", "x"),
            "an unknown outcome": with_(self.GOOD, "data.answer.outcome", "later"),
            "an unknown question type": with_(self.GOOD, "data.question.type", "ranking"),
            "an unknown written_with": with_(self.GOOD, "written_with", "web"),
            "an unknown record type": {**self.REPORT, "type": "audit", "data": {"signed": True, "keys": [1, {"k": None}]}},
            "an unknown type with empty data": {**self.REPORT, "type": "audit", "data": {}},
        }

    def broken(self) -> dict[str, dict]:
        """Records no newer aidd writes: a required field missing, a field of the wrong type, or text that must never be kept."""

        def without(base: dict, path: str) -> dict:
            out = copy.deepcopy(base)
            *parents, last = path.split(".")
            node = out
            for p in parents:
                node = node[p]
            node.pop(last)
            return out

        token = "".join(("ghp_", "abcdefghijklmnopqrstuvwxyz0123456789"))
        deep: list = []
        for _ in range(40):
            deep = [deep]
        return {
            "no answer": without(self.GOOD, "data.answer"),
            "no said": without(self.REPORT, "data.said"),
            "no author": without(self.REPORT, "by"),
            "no recorded_at": without(self.REPORT, "recorded_at"),
            "a covers.head that is a list": _with(self.GOOD, "data.covers.head", ["x"]),
            "a recorded_at that is no time": {**self.REPORT, "recorded_at": "yesterday"},
            "a secret in an unknown field": {**self.REPORT, "note": token},
            "a secret in an unknown type": {**self.REPORT, "type": "audit", "data": {"k": token}},
            "a record too deep": {**self.REPORT, "data": {"action": "pr.open", "said": "x", "covers": {"k": deep}}},
            "a record too large": {**self.REPORT, "data": {"action": "pr.open", "said": "x" * 70_000}},
            "a lone surrogate": {**self.REPORT, "data": {"action": "pr.open", "said": "\ud800"}},
            "an id that is no id": {**self.REPORT, "id": "7"},
            "an author with a control character": {**self.REPORT, "by": "agent:x\x1b[2J"},
        }

    def test_what_a_newer_aidd_writes_is_kept_and_named_and_never_counted(self):
        for name, record in self.variants().items():
            with self.subTest(record=name):
                self.assertEqual(files.record_problems(record, reading=True), [], "the reader keeps it")
                self.assertTrue(files.record_problems(record), "the writer's own check would not write it")
                root = clone_of(self.base, "r" + hashlib.sha256(name.encode()).hexdigest()[:8])
                put(root, record)
                found, unreadable = records.read_records(str(root))
                self.assertEqual(([r["id"] for r in found], unreadable), ([record["id"]], []))
                self.assertEqual(found[0]["data"], record["data"], "its fields are shown as they are")
                self.assertEqual(records.partly_read(found), [record["id"]])
                listed = aidd_here("records", "--json", cwd=root)
                self.assertEqual(json.loads(listed.stdout)["partly_read"], [record["id"]])
                self.assertEqual(json_schema.validate(json.loads(listed.stdout), "records.schema.json#/$defs/list"), [])
                shown = aidd_here("records", cwd=root)
                self.assertIn("read in part", shown.stdout)
                self.assertIn("1 record(s) are read in part", shown.stderr)

    def test_a_decision_read_in_part_is_never_counted_toward_a_suggestion(self):
        for name, extra, want in (("in full", {}, [("git.push", 10)]), ("in part", {"hash": "abc"}, [])):
            with self.subTest(ten_asks_read=name):
                root = clone_of(self.base, f"counts-{name.replace(' ', '-')}")
                for i in range(10):
                    put(root, {**self.GOOD, **extra, "id": f"20261104T0100{i:02d}000Z-f10000{i:02d}"})
                suggested = risk.rule_suggestions(risk.rule_set(None), str(root))["suggestions"]
                self.assertEqual([(s["action"], s["ask_count"]) for s in suggested], want)

    def test_a_record_read_in_full_is_not_named(self):
        root = clone_of(self.base, "full")
        put(root, self.GOOD)
        put(root, self.REPORT)
        found, _ = records.read_records(str(root))
        self.assertEqual(records.partly_read(found), [])
        self.assertNotIn("read in part", aidd_here("records", cwd=root).stdout)
        self.assertEqual(aidd_here("records", cwd=root).stderr, "")

    def test_what_is_broken_is_refused_by_the_reader_that_shares_and_still_listed_when_it_parses(self):
        for name, record in self.broken().items():
            with self.subTest(record=name):
                problems = files.record_problems(record, reading=True)
                self.assertTrue(problems, "the reader does not keep it")
                self.assertTrue(all("\x1b" not in p and len(p) <= 300 for p in problems))
                file = f"{record['id'][:4]}/{record['id'][4:6]}/{record['id']}.json"
                if record["id"] == "7":
                    continue  # no file can be named for it
                self.assertTrue(sharing._share_problem(file, json.dumps(record, ensure_ascii=False).encode("utf-8", "surrogatepass")))

    def test_a_pull_keeps_what_a_newer_aidd_wrote_byte_for_byte_and_a_push_sends_it_back_whole(self):
        remote = self.base / "remote.git"
        git(self.base, "init", "-q", "--bare", "-b", "main", str(remote))
        newer, carol = clone_of(self.base, "newer"), clone_of(self.base, "carol")
        for i, record in enumerate(self.variants().values()):
            put(newer, {**record, "id": f"20261102T0000{i:02d}000Z-c00000{i:02d}"})
        for root in (newer, carol):
            git(root, "remote", "add", "origin", str(remote))
        held = digest(newer)
        self.assertEqual(records.push_records("origin", str(newer)), (0, len(held)))
        added, refused = records.pull_records("origin", str(carol))
        self.assertEqual((sorted(added), refused), (sorted(held), []))
        self.assertEqual(digest(carol), held, "kept byte for byte")
        records.add_record("report", {"action": "pr.open", "said": "Opened PR #13."}, by=BY, cwd=str(carol))
        self.assertEqual(records.push_records("origin", str(carol)), (0, len(held) + 1))
        self.assertEqual(len(git(remote, "ls-tree", "-r", "--name-only", "refs/aidd/records").splitlines()), len(held) + 1)
        self.assertEqual(len(records.partly_read(records.read_records(str(carol))[0])), len(held), "all of them are named, and the new one is not")


class TheDelegationCountsOnlyWhatItWroteInFull(Scratch):
    """Invariant 3. The check against the commit before this change: no accept counts now that did not count, no defer is lost."""

    ACCEPT = fixture("today")["20261101T100300000Z-a0000004"]

    def table(self) -> dict[str, dict]:
        def mutate(path: str, value=None, *, drop: bool = False) -> dict:
            out = copy.deepcopy(self.ACCEPT)
            *parents, last = path.split(".")
            node = out
            for p in parents:
                node = node[p]
            node.pop(last) if drop else node.__setitem__(last, value)
            return out

        old = {("at" if k == "recorded_at" else k): v for k, v in self.ACCEPT.items()}
        return {
            "the delegate's accept": self.ACCEPT,
            "an accept in the old shape (`at`)": old,
            "an accept with an unknown envelope field": mutate("hash", "abc"),
            "an accept with an unknown data field": mutate("data.note", "n"),
            "an accept with an unknown covers field": mutate("data.covers.extra", "e"),
            "an accept with no check": mutate("data.check", drop=True),
            "an accept with a long reason": mutate("data.reason", "r" * 201),
            "an accept with an unknown outcome": mutate("data.outcome", "maybe"),
            "an accept with no recorded_at": mutate("recorded_at", drop=True),
            "an accept by another writer": mutate("by", "agent:claude-code/someone-else"),
            "an accept for another Spec": mutate("data.covers.spec", "SPEC-9"),
            "an accept for another action": mutate("data.action", "git.merge"),
            "an accept that is a defer": mutate("data.outcome", "defer"),
            "a defer in the old shape": {**{("at" if k == "recorded_at" else k): v for k, v in mutate("data.outcome", "defer").items()}},
            "a defer with an unknown field": {**mutate("data.outcome", "defer"), "hash": "abc"},
        }

    def start_accepts(self, root: Path, spec: str) -> set[str]:
        """`delegate_accepts` at the commit before this change: every parsed delegate_answer, as written, from the delegate, not pulled."""
        pulled = sharing.pulled_ids(str(root))
        found = files.read_records(str(root), record_type="delegate_answer", as_written=True)[0]
        out = set()
        for rec in found:
            data = rec.get("data") or {}
            counts = rec.get("id") not in pulled and rec.get("by") == config.DECIDED_BY
            if counts and data.get("action") == "spec.approve" and data.get("outcome") == "accept" and (data.get("covers") or {}).get("spec") == spec:
                out.add(rec["id"])
        return out

    def test_no_accept_counts_now_that_did_not_count_before_and_only_the_unfit_ones_are_lost(self):
        lost, kept = [], []
        for i, (name, record) in enumerate(self.table().items()):
            with self.subTest(record=name):
                root = clone_of(self.base, f"d{i}")
                put(root, {**record, "id": f"20261103T0000{i:02d}000Z-d00000{i:02d}"})
                start = self.start_accepts(root, "SPEC-4")
                now = {r["id"] for r in records.delegate_accepts(str(root), "SPEC-4")}
                self.assertLessEqual(now, start, "an accept counts now that did not count before")
                if start - now:
                    lost.append(name)
                elif now:
                    kept.append(name)
                counted = [head for _when, head in action_checks.approvals(SimpleNamespace(top=str(root), delegation=DELEGATED), "SPEC-4")]
                self.assertEqual(counted, [HEAD] if now else [])
        self.assertEqual(
            sorted(lost),
            sorted(
                [
                    "an accept in the old shape (`at`)",
                    "an accept with an unknown envelope field",
                    "an accept with an unknown data field",
                    "an accept with an unknown covers field",
                    "an accept with no check",
                    "an accept with a long reason",
                    "an accept with no recorded_at",
                ]
            ),
            "the accepts this aidd cannot read in full: the delegate answers again, which is the honest work a stricter reader blocks",
        )
        self.assertEqual(kept, ["the delegate's accept"], "the one accept that was written in full still counts")

    def test_a_defer_is_counted_from_any_record_that_parses_in_either_shape(self):
        """A defer only narrows, so a defer the delegate would not write today still stops the merge."""
        for i, (name, record) in enumerate(self.table().items()):
            with self.subTest(record=name):
                root = clone_of(self.base, f"f{i}")
                put(root, {**record, "id": f"20261103T0100{i:02d}000Z-e00000{i:02d}"})
                before = {
                    r["id"]
                    for r in files.read_records(str(root), record_type="delegate_answer", as_written=True)[0]
                    if (r.get("data") or {}).get("outcome") == "defer"
                }
                after = {r["id"] for r in records.read_records(str(root), record_type="delegate_answer")[0] if (r.get("data") or {}).get("outcome") == "defer"}
                self.assertEqual(after, before)

    def test_a_pulled_accept_and_an_accept_in_the_old_shape_never_stand_behind_the_hook(self):
        from aidd.delegation import answers

        root = clone_of(self.base, "hook")
        record = self.ACCEPT
        covers = {**record["data"]["covers"], "command": "git merge x", "head": "e" * 40}
        accepted = {**record, "data": {**record["data"], "action": "git.merge", "covers": covers}}
        old = {("at" if k == "recorded_at" else k): v for k, v in accepted.items()}
        put(root, old)
        self.assertFalse(answers.accepted_here(str(root), "git.merge", "git merge x", "e" * 40), "an accept in the old shape is not counted")
        shutil.rmtree(files.records_dir(str(root)))
        put(root, accepted)
        self.assertTrue(answers.accepted_here(str(root), "git.merge", "git merge x", "e" * 40), "the same accept in today's shape is")
        pulled = files.records_dir(str(root)).parent / "records-pulled"
        pulled.write_text(accepted["id"] + "\n", encoding="utf-8")
        self.assertFalse(answers.accepted_here(str(root), "git.merge", "git merge x", "e" * 40), "a pulled one never is")


class TheReaderCopyOfTheValidator(unittest.TestCase):
    """`json_schema.validate(open_set=True)` reads as a reader of newer data does, and nothing else is relaxed."""

    SCHEMA = "records.schema.json#/$defs/record"
    GOOD = {"id": "20261105T032447123Z-c97fd11c", "type": "report", "recorded_at": "2026-11-05T03:24:47Z", "by": BY, "data": {}}

    def test_an_unknown_field_and_an_unknown_enum_value_are_no_error_and_everything_else_is(self):
        cases = [
            ("a known record", {}, 0, 0),
            ("an unknown field", {"hash": "x"}, 1, 0),
            ("an unknown enum value", {"written_with": "web"}, 1, 0),
            ("a known enum value", {"written_with": "cli"}, 0, 0),
            ("a missing required field", {"recorded_at": None}, 1, 1),
            ("a wrong type", {"data": []}, 1, 1),
            ("a value past its pattern", {"id": "7"}, 1, 1),
            ("a value past its format", {"recorded_at": "yesterday"}, 1, 1),
        ]
        for name, change, closed, open_ in cases:
            with self.subTest(case=name):
                record = {**self.GOOD, **change}
                record = {k: v for k, v in record.items() if v is not None}
                self.assertEqual(
                    (len(json_schema.validate(record, self.SCHEMA)), len(json_schema.validate(record, self.SCHEMA, open_set=True))), (closed, open_)
                )

    def test_the_conditions_of_a_schema_read_a_value_they_do_not_know_as_none_of_theirs(self):
        data = fixture("today")["20261101T100000000Z-a0000001"]["data"]
        schema = "records.json#/types/decision/data"
        unknown = copy.deepcopy(data)
        unknown["question"]["type"] = "ranking"
        unknown["action"] = "pr.open"
        self.assertEqual(json_schema.validate(unknown, schema, open_set=True), [], "an unknown question type needs no action")
        no_action = copy.deepcopy(data)
        no_action.pop("action")
        for kind in ("yes_no", "approval"):
            no_action["question"]["type"] = kind
            self.assertTrue(json_schema.validate(no_action, schema, open_set=True), f"a {kind} question still needs its action")


if __name__ == "__main__":
    unittest.main()
