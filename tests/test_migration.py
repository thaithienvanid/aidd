"""`aidd upgrade` moves a repository from any earlier shape of aidd's files to today's: once, with a line for every change, and no
value lost (schemas/retired-names.json; setup/migrating.py).

The fixtures are real earlier shapes. `tests/fixtures/migration/pre/` holds the config and the work items with every retired
name, and `today/` holds what they are in today's shape, read and checked by hand against the schemas."""

import copy
import os
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_here, git
from migration_fixture import CONFIG, FIXTURES, WRITTEN, Repo, parsed, tree

from aidd import config, setup, workitems
from aidd.kernel import documents, retired_names, yaml_edit
from aidd.setup import migrating


def moves(surface: str, data: dict, row: dict, path: tuple) -> bool:
    moved = copy.deepcopy(data)
    migrating._READERS[surface](moved, row, path)
    return moved != data


def migration_lines(lines: list[str]) -> list[str]:
    """The lines of an upgrade that say what moved, without the verb that tells a dry run from a real one."""
    return [re.sub(r"^(would migrate|migrated)\s+", "", line) for line in lines if line.startswith(("would migrate", "migrated", "manual", "note     "))]


# A row whose name no file of the repository holds: a flag of a command, and the id of a library standard. `aidd upgrade` moves neither;
# tests/test_retired_names.py and tests/test_delivery_teams.py hold what reads them.
NOT_IN_A_FILE = {"cli_flag", "standard_id"}

# A row that only ever tells a person what to do by hand leaves its file as it was, so no fixture tree can hold it and still be
# "today's shape"; WhereTheEngineStopsShort checks it on a file of its own.
LEFT_FOR_A_PERSON = {"spec-experiment"}


class TheMigrationOfEveryRetiredName(Repo):
    def test_a_dry_run_names_every_row_and_changes_nothing(self):
        before = tree(self.root)
        lines = "\n".join(self.upgrade())
        self.assertEqual(tree(self.root), before)
        # A `read_both` row is a record's, which aidd never rewrites: tests/test_records_reading.py holds its fixture. A `manual`
        # row is a value a person types, which no file holds: tests/test_change_types.py holds its fixture.
        for row in (
            r
            for r in retired_names.rows()
            if r["id"] not in LEFT_FOR_A_PERSON and r["rule"] not in ("read_both", "manual") and r["surface"] not in NOT_IN_A_FILE
        ):
            places = [(rel, p) for rel in WRITTEN for p in self.places(rel, row)]
            with self.subTest(row=row["id"]):
                self.assertTrue(places, f"the fixture holds no {row['old']}")
                for rel, path in places:
                    self.assertRegex(lines, rf"would migrate\s+{re.escape(rel)}: .*{re.escape(retired_names.shown(path))}")

    def test_an_upgrade_never_rewrites_a_record_and_a_record_with_the_old_names_is_no_work_for_it(self):
        records = Path(git(self.root, "rev-parse", "--git-path", "aidd/records"))
        records = records if records.is_absolute() else self.root / records
        shutil.copytree(ROOT / "tests" / "fixtures" / "migration" / "records" / "pre", records)
        before = {p.name: p.read_bytes() for p in records.rglob("*.json")}
        self.assertEqual(len(before), 4)
        self.assertFalse([line for line in self.upgrade(yes=True) if "record" in line.lower()], "no line is about a record")
        self.assertEqual({p.name: p.read_bytes() for p in records.rglob("*.json")}, before)

    def test_a_cut_prints_the_value_it_removes_so_it_can_be_found_in_git(self):
        old = parsed(self.root, CONFIG)
        lines = "\n".join(self.upgrade())
        for shown in ("delegate", "acme/shop", "forbidden", "core", "[INT-1, INT-9]", "true"):
            self.assertIn(f" = {shown}", lines)
        self.assertEqual(old["delegation"]["default_branch_deploys"], True)

    def places(self, rel: str, row: dict) -> list:
        """Where the pre tree holds a row's old name: in the file's front matter by its type, or in its handoff note."""
        if row["surface"] == "handoff":
            note = migrating._HANDOFF.search((self.root / rel).read_text(encoding="utf-8"))
            return retired_names.paths_in(documents.parse_yaml(note.group(1), rel), row["old"]) if note else []
        data = parsed(self.root, rel)
        kind = (
            "config" if rel == CONFIG else "sitemap" if rel.endswith(migrating.SITEMAP) else {"opinionated": "standard"}.get(data.get("type"), data.get("type"))
        )
        found = retired_names.paths_in(data, row["old"]) if kind == row["surface"] else []
        # A row that changes only values names its key in today's shape too: a place holds it when the shared reading moves its value.
        return [p for p in found if row["old"] != row["new"] or moves(kind, data, row, p)]

    def test_a_dry_run_and_the_real_run_say_the_same_migration(self):
        dry, real = migration_lines(self.upgrade()), migration_lines(self.upgrade(yes=True))
        self.assertTrue(dry)
        self.assertEqual(dry, real)

    def test_a_dry_run_reads_the_files_as_the_real_run_will(self):
        seen = []
        with mock.patch.object(setup.upgrading, "_bring_up", side_effect=lambda *a, **k: seen.append(config.load_file(CONFIG, str(self.root))) or []):
            self.upgrade()
        self.assertEqual(len(seen), 1, "the rest of the upgrade loads the migrated config in a dry run")
        self.assertNotIn("allow_own_tools", (self.root / CONFIG).read_text(encoding="utf-8"), "and the file on disk is still the old one")

    def test_the_old_shape_does_not_load_and_each_error_names_the_way_out(self):
        with self.assertRaises(config.ConfigError) as caught:
            config.load_file(CONFIG, str(self.root))
        self.assertIn("`aidd upgrade --yes` renames it", str(caught.exception))
        errors, _ = workitems.check_repo(self.root)
        self.assertTrue(any("was retired in 1.0.0; it is now `delivery_team`" in e for e in errors), errors)

    def test_the_real_run_writes_the_tree_that_was_checked_by_hand_and_a_second_run_changes_nothing(self):
        old = parsed(self.root, CONFIG)
        self.upgrade(yes=True)
        for rel in WRITTEN:
            with self.subTest(file=rel):
                self.assertEqual((self.root / rel).read_bytes(), (FIXTURES / "today" / rel).read_bytes())
        errors, _ = workitems.check_repo(self.root)
        self.assertEqual(errors, [])
        cfg = config.load_file(CONFIG, str(self.root))
        self.assertEqual(cfg.get("delegation", "review_due"), old["delegation"]["review_by"])
        self.assertEqual(cfg.get("mcp", "allow_own_tools"), old["mcp"]["approve_own_tools"])
        self.assertEqual(cfg.get("project", "compliance", "support_period", "ends_on"), old["project"]["compliance"]["support_period"]["ends"])
        self.assertEqual(cfg.get("delivery_teams", "core", "approvers"), old["delivery_teams"]["core"]["people"])
        self.assertEqual([r["requirement_level"] for r in cfg.get("project", "rules")], ["must", "should"])
        disabled = {_type: why for _type, why in cfg.get("docs", "disabled").items()}
        self.assertEqual(set(disabled), {"runbook", "tracking-plan"})
        self.assertEqual(parsed(self.root, "specs/INT-2.md")["delivery_team"], "web")
        self.assertEqual(parsed(self.root, "specs/SPEC-1.md")["manual_acceptance"], True)
        self.assertEqual(parsed(self.root, "specs/SPEC-1.md")["route"], "normal")
        after = tree(self.root)
        lines = self.upgrade(yes=True)
        self.assertTrue(lines[0].startswith("nothing to update"), lines)
        self.assertEqual(tree(self.root), after)


class TheTreeInTodaysShape(Repo):
    shape = "today"

    def test_an_upgrade_changes_none_of_its_files_and_says_so(self):
        before = tree(self.root)
        found = migrating.plan(self.root)
        self.assertEqual((found.lines, found.texts), ([], {}))
        lines = self.upgrade(yes=True)
        self.assertEqual([line for line in lines if line.startswith(("migrated", "would migrate", "manual"))], [])
        self.assertEqual({rel: h for rel, h in tree(self.root).items() if rel in WRITTEN}, {rel: before[rel] for rel in WRITTEN})


class WhereTheEngineStopsShort(Repo):
    """A file the engine cannot place a name in stays as it is, and a line names the file, the name, and the next step."""

    def run_on(self, files: dict[str, str] | None = None, cfg: str | None = None) -> tuple[migrating.Plan, dict[str, str]]:
        for other in ("specs", "proposals", "docs/standards", "docs/runbooks", "docs/postmortems", "docs/design"):  # the files the cases below do not use
            shutil.rmtree(self.root / other, ignore_errors=True)
        for rel, text in (files or {}).items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        (self.root / CONFIG).write_bytes((cfg if cfg is not None else (FIXTURES / "today" / CONFIG).read_text(encoding="utf-8")).encode("utf-8"))
        return migrating.plan(self.root), tree(self.root)

    TODAY = (FIXTURES / "today" / CONFIG).read_text(encoding="utf-8")

    def test_a_name_in_a_flow_mapping_stays_and_the_line_says_what_to_do(self):
        cfg = self.TODAY.replace(
            'delegation:\n  set_by: "A B <a@b.c>"\n  decides: [git.push]\n  default_branch: main\n  review_due: "2027-01-01"\n',
            'delegation: {set_by: "A B <a@b.c>", decides: [git.push], review_by: "2027-01-01"}\n',
        )
        found, _ = self.run_on(cfg=cfg)
        self.assertEqual(found.texts, {})
        [(kind, line)] = found.lines
        self.assertEqual(kind, "manual")
        for part in (CONFIG, "delegation.review_by", "review_due", "by hand", "`aidd upgrade` again"):
            self.assertIn(part, line)

    def test_an_edit_that_does_not_read_back_is_refused(self):
        with mock.patch.object(yaml_edit, "rename_key", return_value="mcp: [broken\n"):
            found, _ = self.run_on(cfg=self.TODAY.replace("allow_own_tools", "approve_own_tools"))
        self.assertEqual(found.texts, {})
        [(kind, line)] = found.lines
        self.assertEqual(kind, "manual")
        self.assertIn("did not read back", line)

    def test_a_rule_check_that_is_a_command_stays_and_the_line_says_how_to_move_it(self):
        cfg = self.TODAY.replace("      enforced_by: [smoke]", '      check: "make lint"')
        found, _ = self.run_on(cfg=cfg)
        self.assertEqual(found.texts, {})
        [(kind, line)] = found.lines
        self.assertEqual(kind, "manual")
        for part in ("project.rules[0].check", "make lint is no name in `tests`", "add the command as a `tests` entry", "`aidd upgrade` again"):
            self.assertIn(part, line)

    def test_a_rename_in_the_tests_of_an_approved_spec_is_noted(self):
        for approved, noted in ((True, True), (False, False)):
            spec = (
                "---\ntype: spec\nid: SPEC-1\ntitle: T\n"
                + ('status: approved\napproved_by: "@x"\napproved_at: "2026-11-01T09:00:00Z"\n' if approved else "")
                + "tests:\n  commands:\n    - name: c\n      command: [a]\n      retries: 1\n---\n"
            )
            found, _ = self.run_on({"specs/SPEC-1.md": spec})
            with self.subTest(approved=approved):
                self.assertIn("reruns: 1", found.texts["specs/SPEC-1.md"])
                self.assertEqual(
                    any(k == "note" and "no revision" in line and "nothing waits for a person" in line for k, line in found.lines), noted, found.lines
                )

    def test_a_name_beside_its_replacement_stays(self):
        cfg = self.TODAY.replace("  allow_own_tools: false", "  allow_own_tools: false\n  approve_own_tools: true")
        found, _ = self.run_on(cfg=cfg)
        self.assertEqual(found.texts, {})
        self.assertIn("`mcp.allow_own_tools` is set too", found.lines[0][1])

    def test_one_name_that_stays_does_not_hold_back_the_others(self):
        cfg = self.TODAY.replace("  allow_own_tools: false", "  allow_own_tools: false\n  approve_own_tools: true").replace(
            '    approvers: ["@y"]', '    people: ["@y"]'
        )
        found, _ = self.run_on(cfg=cfg)
        self.assertEqual(sorted(k for k, _ in found.lines), ["manual", "migrate"])
        self.assertIn('approvers: ["@y"]', found.texts[CONFIG])
        self.assertIn("approve_own_tools: true", found.texts[CONFIG])

    def test_line_endings_stay_and_a_file_that_mixes_them_is_left_alone(self):
        old = "---\r\ntype: spec\r\nid: SPEC-1\r\ntitle: T\r\nuat: true\r\n---\r\n\r\nBody\r\n"
        found, _ = self.run_on({"specs/SPEC-1.md": old})
        self.assertEqual(found.texts["specs/SPEC-1.md"], old.replace("uat:", "manual_acceptance:"))
        mixed = old.replace("title: T\r\n", "title: T\n")
        found, _ = self.run_on({"specs/SPEC-1.md": mixed})
        self.assertEqual(found.texts, {})
        self.assertIn("two kinds of line ending", found.lines[-1][1])

    def test_a_key_with_a_retired_name_in_another_place_is_not_touched(self):
        spec = '---\ntype: spec\nid: SPEC-1\ntitle: T\nowner: "@x"\nnext: later\n---\n\nowner_team: core\n\n```yaml\nuat: true\n```\n'
        cfg = self.TODAY + "\nrisks:\n  rules:\n    - action: spec.approve\n      level: ask\n"
        found, _ = self.run_on({"specs/SPEC-1.md": spec}, cfg)
        self.assertEqual((found.lines, found.texts), ([], {}))

    def test_a_remote_parent_is_named_and_a_parent_in_the_repository_is_moved(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\nmcp:\n  approve_own_tools: true\n'
        cfg = self.TODAY + '\nextends:\n  - path: .aidd/org.yaml\n  - url: https://example.com/org.yaml\n    sha256: "' + "0" * 64 + '"\n'
        found, _ = self.run_on({".aidd/org.yaml": parent}, cfg)
        self.assertEqual(found.texts, {".aidd/org.yaml": parent.replace("approve_own", "allow_own")})
        self.assertTrue(any(k == "note" and "remote" in line for k, line in found.lines), found.lines)

    def test_a_team_that_an_item_names_but_the_config_lacks_is_reported(self):
        found, _ = self.run_on({"specs/SPEC-1.md": "---\ntype: spec\nid: SPEC-1\ntitle: T\nowner_team: nobody\n---\n"})
        self.assertIn("`delivery_teams`", "\n".join(line for k, line in found.lines if k == "note"))
        self.assertIn("delivery_team: nobody", found.texts["specs/SPEC-1.md"])

    def test_an_intent_that_names_another_team_keeps_it(self):
        intent = "---\ntype: intent\nid: INT-5\ntitle: T\ngoal: G\ndelivery_team: web\n---\n"
        cfg = self.TODAY.replace('    approvers: ["@x"]   # the core team\n', '    approvers: ["@x"]   # the core team\n    intents: [INT-5]\n')
        found, _ = self.run_on({"specs/INT-5.md": intent}, cfg)
        self.assertNotIn("specs/INT-5.md", found.texts)
        self.assertTrue(any("INT-5 names web, so it keeps that" in line for _, line in found.lines))

    def test_a_config_that_cannot_be_read_stops_the_upgrade_at_its_line(self):
        with self.assertRaises(ValueError) as caught:
            self.run_on(cfg="aidd_version: '1.0.0\nprofile: team\n")
        self.assertIn(CONFIG, str(caught.exception))
        self.assertIn("then run `aidd upgrade` again", str(caught.exception))

    def test_a_link_is_never_followed(self):
        outside = Path(self.tmp.name) / "outside.yaml"
        outside.write_text('aidd_version: "1.0.0"\nprofile: team\nmcp:\n  approve_own_tools: true\n', encoding="utf-8")
        (self.root / CONFIG).unlink()
        (self.root / CONFIG).symlink_to(outside)
        self.assertEqual(migrating.plan(self.root).texts, {})
        self.assertIn("approve_own_tools", outside.read_text(encoding="utf-8"))

    def test_a_nested_repository_config_is_not_read(self):
        nested = self.root / "packages" / "a" / ".aidd" / "config.yaml"
        nested.parent.mkdir(parents=True)
        nested.write_text('aidd_version: "1.0.0"\nprofile: team\nmcp:\n  approve_own_tools: true\n', encoding="utf-8")
        self.assertEqual(self.run_on()[0].texts, {})

    def test_a_proposal_has_its_front_matter_and_its_handoff_notes_read_where_it_lies(self):
        """A proposal is a surface of its own now, in the specs folder or the proposals folder, as a runbook and a postmortem are in
        theirs; its handoff notes are read as before."""
        proposal = '---\naidd_version: "1.0.0"\ntype: proposal\nid: PROP-1\nowner_team: core\n---\n\n```aidd-handoff\nnext: verifier\n```\n'
        for rel in ("specs/PROP-1.md", "proposals/PROP-1/proposal.md"):
            with self.subTest(rel):
                found, _ = self.run_on({rel: proposal})
                self.assertEqual(found.texts[rel], proposal.replace("next:", "next_role:").replace("owner_team:", "delivery_team:"))
        runbook = '---\naidd_version: "1.0.0"\ntype: runbook\nid: RB-1\nowner_team: core\n---\n'
        found, _ = self.run_on({"docs/runbooks/RB-1.md": runbook, "specs/RB-2.md": runbook.replace("RB-1", "RB-2")})
        self.assertEqual(found.texts["docs/runbooks/RB-1.md"], runbook.replace("owner_team:", "delivery_team:"))
        self.assertEqual(sorted(found.texts), ["docs/runbooks/RB-1.md", "specs/RB-2.md"], "a typed document is read in each folder aidd reads")

    def test_a_sitemap_is_read_as_json_and_one_it_cannot_edit_on_a_line_stays(self):
        one_line = '{"format": 1, "flows": [], "navigation": []}\n'
        cases = {
            "one line": (one_line, None),
            "tabs, and the key last": (
                '{\n\t"flows": [],\n\t"navigation": [],\n\t"format": 1\n}\n',
                '{\n\t"flows": [],\n\t"navigation": [],\n\t"schema_version": "1"\n}\n',
            ),
            "not JSON": ("{format: 1\n", None),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                found, _ = self.run_on({"docs/design/app/sitemap.json": text})
                self.assertEqual(found.texts.get("docs/design/app/sitemap.json"), want)
                if want is None and name == "one line":
                    [(kind, line)] = found.lines
                    self.assertEqual(kind, "manual")
                    for part in ("docs/design/app/sitemap.json", "format", "`aidd upgrade` again"):
                        self.assertIn(part, line)


class TheSpecsCutsAndFolds(WhereTheEngineStopsShort):
    """Each Spec row moves a value to its new place or leaves the file as it was with a line that says what to do by hand."""

    @staticmethod
    def spec(sid: str, extra: str = "", risk: str = "risk:\n  summary: s\n  dimensions: []\n  irreversible: false\n") -> str:
        return f"---\ntype: spec\nid: {sid}\ntitle: T\n{extra}{risk}rollback: r\n---\n\nBody\n"

    def lines_of(self, found, kind: str) -> list[str]:
        return [line for k, line in found.lines if k == kind]

    def test_a_relations_list_moves_by_entry_and_a_blocks_writes_the_other_spec(self):
        files = {
            "specs/SPEC-1.md": self.spec("SPEC-1", "relations: [{type: blocked_by, id: SPEC-2}, {type: blocks, id: SPEC-3}, {type: implements, id: INT-1}]\n"),
            "specs/SPEC-3.md": self.spec("SPEC-3", "blocked_by: [SPEC-9]\n"),
        }
        found, _ = self.run_on(files)
        one, three = (parsed_text(found.texts[f"specs/SPEC-{n}.md"]) for n in (1, 3))
        self.assertEqual((one.get("blocked_by"), one.get("parent"), "relations" in one), (["SPEC-2"], "INT-1", False))
        self.assertEqual(three["blocked_by"], ["SPEC-9", "SPEC-1"], "the waiting Spec is added after the ones it had")
        self.assertEqual(self.lines_of(found, "manual"), [])

    def test_an_entry_with_no_place_leaves_the_whole_list_and_says_why(self):
        cases = {
            "duplicates": "{type: duplicates, id: SPEC-2}",
            "relates_to": "{type: relates_to, id: SPEC-2}",
            "a blocks whose target is no Spec here": "{type: blocks, id: SPEC-77}",
        }
        for name, entry in cases.items():
            with self.subTest(name):
                text = self.spec("SPEC-1", f"relations: [{{type: blocked_by, id: SPEC-5}}, {entry}]\n")
                found, _ = self.run_on({"specs/SPEC-1.md": text})
                self.assertEqual(found.texts, {}, "nothing is half moved")
                [line] = self.lines_of(found, "manual")
                for part in ("specs/SPEC-1.md", "relations", "`aidd upgrade` again"):
                    self.assertIn(part, line)

    def test_an_implements_beside_another_parent_is_left_for_a_person(self):
        text = self.spec("SPEC-1", "parent: INT-2\nrelations: [{type: implements, id: INT-1}]\n")
        found, _ = self.run_on({"specs/SPEC-1.md": text})
        self.assertEqual(found.texts, {})
        self.assertIn("both name an Intent", self.lines_of(found, "manual")[0])

    def test_an_experiment_is_never_moved_or_dropped(self):
        text = self.spec("SPEC-1", "experiment:\n  variants: [a, b]\n")
        found, _ = self.run_on({"specs/SPEC-1.md": text})
        self.assertEqual(found.texts, {})
        [line] = self.lines_of(found, "manual")
        self.assertIn("tracking-plan", line)

    def test_a_residual_risk_and_a_cost_estimate_move_into_risk_and_stay_when_risk_cannot_hold_them(self):
        moved = self.spec("SPEC-1", 'residual_risk: none\ncost_estimate: {monthly: "5 EUR"}\n')
        found, _ = self.run_on({"specs/SPEC-1.md": moved})
        risk = parsed_text(found.texts["specs/SPEC-1.md"])["risk"]
        self.assertEqual((risk["residual"], risk["cost_estimate"]), ("none", {"monthly": "5 EUR"}))
        for name, text in {
            "a risk in flow style": self.spec("SPEC-1", "residual_risk: none\n", risk="risk: {summary: s, dimensions: [], irreversible: false}\n"),
            "a residual already in risk": self.spec(
                "SPEC-1", "residual_risk: none\n", risk="risk:\n  summary: s\n  dimensions: []\n  irreversible: false\n  residual: x\n"
            ),
        }.items():
            with self.subTest(name):
                found, _ = self.run_on({"specs/SPEC-1.md": text})
                self.assertEqual(found.texts, {})
                self.assertEqual(len(self.lines_of(found, "manual")), 1)

    def test_a_second_run_finds_nothing_and_a_front_matter_keeps_its_last_line(self):
        files = {"specs/SPEC-1.md": self.spec("SPEC-1", "residual_risk: none\nlabels: [a]\nblockers: legal\n")}
        found, _ = self.run_on(files)
        text = found.texts["specs/SPEC-1.md"]
        self.assertIn("rollback: r\n---\n", text, "no blank line before the closing fence")
        (self.root / "specs/SPEC-1.md").write_text(text, encoding="utf-8")
        again = migrating.plan(self.root)
        self.assertEqual((again.lines, again.texts), ([], {}))


def parsed_text(text: str) -> dict:
    return documents.split_front_matter(text, "x.md")[0]


class TheEngineInTheUpgrade(Repo):
    def test_only_ask_rules_runs_no_migration(self):
        before = tree(self.root)
        with mock.patch.object(migrating, "plan", side_effect=AssertionError("the migration ran")):
            setup.upgrade(self.root, only="ask-rules", yes=True)
        self.assertEqual({rel: tree(self.root)[rel] for rel in WRITTEN}, {rel: before[rel] for rel in WRITTEN})

    def test_a_file_aidd_may_not_write_stays_and_a_line_names_it(self):
        other = self.root / "second-name.yaml"
        os.link(self.root / CONFIG, other)  # a file with two names: aidd writes none
        found = migrating.plan(self.root)
        self.assertNotIn(CONFIG, found.texts)
        self.assertTrue(any(kind == "manual" and CONFIG in line and "not changed" in line for kind, line in found.lines), found.lines)

    def test_the_command_runs_from_a_folder_inside_the_repository(self):
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        done = aidd_here("upgrade", cwd=sub)
        self.assertIn("would migrate", done.stdout)


if __name__ == "__main__":
    unittest.main()
