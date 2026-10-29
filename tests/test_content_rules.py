"""Specialists asked by content (V8): a risk rule's `content` patterns match the lines a diff adds, and a rule below
major that names `specialists` asks those pools on any route, not only on major."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config
from aidd.gate import content_rules, inputs, routing

RULES = """aidd_version: "1.0.0"
profile: team
owners:
  approvers: ["@lead"]
  specialists:
    data: ["@dba"]
risk_rules:
  - name: raw-sql
    paths: ["src/**/*.py"]
    exclude: ["src/legacy/**"]
    content: ['\\.execute\\(\\s*f["'']']
    specialists: [data]
  - name: model-api
    content: ['\\banthropic\\.', '\\bopenai\\.']
    route: normal
    dimensions: [third_party]
"""

SQL = 'cur.execute(f"select * from users where id = {uid}")'


def cfg(text: str = RULES) -> config.Config:
    return config.load_text(text)


class MatchTests(unittest.TestCase):
    def match(self, added: dict[str, list[str]]) -> list[dict]:
        return content_rules.matches(content_rules.rules(routing.active_rules(cfg())), list(added), lambda p: added[p])

    def test_an_added_line_matches_only_in_the_rules_paths(self):
        got = self.match({"src/app/db.py": ["x = 1", SQL], "src/legacy/db.py": [SQL], "web/db.ts": [SQL], "SRC/App/Q.PY": [SQL]})
        self.assertEqual(got, [{"rule": "raw-sql", "path": "src/app/db.py"}, {"rule": "raw-sql", "path": "SRC/App/Q.PY"}])

    def test_a_rule_without_paths_reads_every_file(self):
        self.assertEqual(self.match({"lib/ask.ts": ["const r = await anthropic.messages.create(req)"]}), [{"rule": "model-api", "path": "lib/ask.ts"}])

    def test_what_is_not_read_counts_as_a_match(self):
        """Fail closed: a line too long to search, and every file past the cap, ask the rule's pool."""
        long = self.match({"src/app/db.py": ["x" * (content_rules.MAX_LINE + 1)]})
        self.assertEqual(sorted(m["rule"] for m in long), ["model-api", "raw-sql"])  # model-api reads every file
        added = {f"src/app/m{i}.py": ["x = 1"] for i in range(content_rules.MAX_FILES)} | {"src/app/late.py": ["x = 1"], "web/late.ts": ["y"]}
        got = self.match(added)  # nothing matches in the files read; the two past the cap ask each rule that reads them
        self.assertEqual(got, [{"rule": "raw-sql", "path": "src/app/late.py"}, {"rule": "model-api", "path": "web/late.ts"}])

    def test_a_pattern_anchored_to_a_line_reads_each_part_another_language_splits(self):
        text = RULES.replace("['\\banthropic\\.', '\\bopenai\\.']", "['^import openai$']")
        active = content_rules.rules(routing.active_rules(cfg(text)))
        for sep in ("\r", "\u2028", "\u2029", "\x0c"):
            with self.subTest(sep=repr(sep)):
                got = content_rules.matches(active, ["lib/a.js"], lambda p, sep=sep: [f"x = 1{sep}import openai"])
                self.assertEqual(got, [{"rule": "model-api", "path": "lib/a.js"}])

    def test_a_file_that_could_not_be_read_counts_as_a_match(self):
        self.assertEqual(
            content_rules.matches(content_rules.rules(routing.active_rules(cfg())), ["src/app/db.py"], lambda p: None),
            [
                {"rule": "raw-sql", "path": "src/app/db.py"},
                {"rule": "model-api", "path": "src/app/db.py"},
            ],
        )

    def test_a_pattern_that_does_not_compile_is_a_config_error(self):
        with self.assertRaisesRegex(config.ConfigError, "not a regular expression"):
            cfg(RULES.replace("['\\banthropic\\.', '\\bopenai\\.']", "['(unclosed']"))


class RouteTests(unittest.TestCase):
    def assess(self, content: list[dict]) -> routing.Assessment:
        return routing.assess_route(
            paths=["src/app/db.py"],
            cfg=cfg(),
            ctype="feat",
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=2,
            changed_lines=40,
            content=content,
        )

    def test_a_rule_below_major_asks_its_pool_on_any_route(self):
        a = self.assess([{"rule": "raw-sql", "path": "src/app/db.py"}])
        self.assertEqual(a.required_route, "normal")
        self.assertEqual(a.asked, {"data"})
        self.assertEqual(a.pools, set())  # no major pools
        self.assertIn("rule raw-sql matched a line added in src/app/db.py -> at least minor, and asks the data pool", a.reasons)

    def test_the_path_alone_never_matches_a_content_rule(self):
        a = self.assess([])
        self.assertEqual((a.asked, [h.rule for h in a.hits]), (set(), []))

    def test_a_rule_that_forces_major_asks_through_the_major_route(self):
        text = RULES.replace("    specialists: [data]\n", "    specialists: [data]\n    route: major\n", 1)
        a = routing.assess_route(
            paths=["src/app/db.py"],
            cfg=cfg(text),
            ctype="feat",
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=1,
            changed_lines=4,
            content=[{"rule": "raw-sql", "path": "src/app/db.py"}],
        )
        self.assertEqual((a.required_route, a.pools, a.asked), ("major", {"data"}, set()))


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitTests(unittest.TestCase):
    def test_the_adapter_reads_the_added_lines_with_git(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        git(root, "init", "-q", "-b", "main")
        (root / "src" / "app").mkdir(parents=True)
        db = root / "src" / "app" / "db.py"
        db.write_text(SQL + "\n", encoding="utf-8")  # already on the base: never a match
        git(root, "add", "-A")
        git(root, "commit", "-qm", "base")
        base = git(root, "rev-parse", "HEAD").strip()
        db.write_text(SQL + "\nprint('done')\n", encoding="utf-8")
        git(root, "commit", "-qam", "no new SQL")
        files = [{"path": "src/app/db.py", "additions": 1, "deletions": 0}]
        self.assertEqual(inputs.content_matches(str(root), cfg(), base, git(root, "rev-parse", "HEAD").strip(), files), [])
        db.write_text(SQL + "\nprint('done')\n" + SQL.replace("users", "orders") + "\n", encoding="utf-8")
        git(root, "commit", "-qam", "new SQL")
        files = [{"path": "src/app/db.py", "additions": 2, "deletions": 0}]
        got = inputs.content_matches(str(root), cfg(), base, git(root, "rev-parse", "HEAD").strip(), files)
        self.assertEqual(got, [{"rule": "raw-sql", "path": "src/app/db.py"}])
        db.write_text(SQL.replace("execute(", "execute(\r").replace("users", "carts") + "\n", encoding="utf-8", newline="")
        self.assertIn(SQL.replace("execute(", "execute(\r").replace("users", "carts"), content_rules.added_lines(str(root), base, None, "src/app/db.py"))
        with db.open("a", encoding="utf-8") as fh:
            fh.write("++ not a header\n")  # in the working tree: an added line that starts like a header is still read
        self.assertEqual(content_rules.added_lines(str(root), base, None, "src/app/db.py")[-1], "++ not a header")
        # A name git would read as a pathspec names only itself: `q[1].py` never reads `q1.py`.
        (root / "src" / "app" / "q1.py").write_text("x = 1\n", encoding="utf-8")
        (root / "src" / "app" / "q[1].py").write_text(SQL + "\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "glob name")
        head = git(root, "rev-parse", "HEAD").strip()
        self.assertEqual(content_rules.added_lines(str(root), base, head, "src/app/q[1].py"), [SQL])
        self.assertEqual(inputs.content_matches(str(root), None, base, "HEAD", files), [])  # no config, no rules


if __name__ == "__main__":
    unittest.main()
