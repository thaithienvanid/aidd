"""schemas/item-types.json: one row for each type of thing aidd tracks or writes. The registry reads as its schema says, and it
agrees with the code both ways: a type the code names has a row, and a row has its use. A list of types that cannot read the
registry (a schema's enum, a page's table) is pinned equal to it here, so a new type is a row, and one test fails where a copy
drifts. No module of `src/aidd` keeps its own list of types."""

from __future__ import annotations

import ast
import re
import unittest

import helpers  # noqa: F401  # puts src/ on the path and makes the run hermetic
from helpers import ROOT

from aidd import config, workitems
from aidd.cli import grammar
from aidd.kernel import json_schema, resources
from aidd.knowledge import explanations
from aidd.workitems import authoring, backlog, objects, spec_file

SRC = ROOT / "src" / "aidd"
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
REGISTRY = resources.load_json("item-types.json")
ROWS = REGISTRY["types"]
DOCUMENTS = resources.load_json("roles.json")["loop"]["documents"]
SPEC_DOC_TYPES = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["type"]["enum"]
# The templates in the skill's assets that no type of `aidd new` starts from: the first config `aidd init` writes, and two
# templates the delivery team's roles read.
NOT_A_TYPE = {"config.yaml", "module-readme.md", "release-notes.md"}
# The types with no row in `loop.documents`, because no role owns them as a document: the three work items, the postmortem and
# the exploration (their own schemas say who writes them), and the contract (the delivery manager's engagement).
NO_DOCUMENT_ROW = {"spec", "intent", "proposal", "postmortem", "exploration", "contract"}
# A list of three or more types that lives in the code, with why it is no copy of the registry.
OWN_LISTS = {
    "src/aidd/config/model.py": "DOC_TYPES (importing the config reads no data file; a test here ties it to spec.schema.json) and the required-docs matrix",
    "src/aidd/docsgen/schema_tables.py": "FIELD_SCHEMAS: the schema each `fields:` block documents, which a config and an evidence file have too",
    "src/aidd/recall/sources.py": "ONE_PER_REPOSITORY: the repository documents `aidd recall` reads, a choice and not a list of types",
    "src/aidd/setup/migrating.py": "_TYPE_SURFACE: the retired-names surface each of three front matter types is read as, which no other type has",
}


def literal_lists() -> dict[str, list[str]]:
    """Each place under src/aidd where a tuple, list, set, or dict of string keys holds three or more type names, as
    `path:line` with the names."""
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Tuple | ast.List | ast.Set):
                names = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            elif isinstance(node, ast.Dict):
                names = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            else:
                continue
            if len(set(names) & set(ROWS)) >= 3:
                found[f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"] = sorted(set(names) & set(ROWS))
    return found


class TheRegistry(unittest.TestCase):
    def test_it_reads_as_its_schema_says(self):
        self.assertEqual(json_schema.validate(REGISTRY, "item-types.schema.json"), [])

    def test_a_row_names_a_group_and_a_group_holds_a_row(self):
        self.assertEqual({row["group"] for row in ROWS.values()}, set(REGISTRY["groups"]))

    def test_the_rows_are_in_the_order_aidd_new_lists_them(self):
        """A group's types are in the rows' order, and the choices of `aidd new` are the rows."""
        self.assertEqual(grammar.new_types(), list(ROWS))
        self.assertEqual([t for _, types in grammar.new_type_groups() for t in types], [t for g in REGISTRY["groups"] for t in config.types_in(g)])
        self.assertEqual(sorted(t for _, types in grammar.new_type_groups() for t in types), sorted(ROWS), "each type once")

    def test_each_common_document_is_a_row_once(self):
        self.assertEqual(len(set(config.common_documents())), len(config.common_documents()))
        self.assertLessEqual(set(config.common_documents()), set(ROWS))
        self.assertEqual(grammar.NEW_COMMON_DOCS, config.common_documents())

    def test_each_template_exists_and_each_asset_has_a_type(self):
        named = set()
        for name, row in ROWS.items():
            named |= {row_template for row_template in row.get("templates", {}).values()} | {f["template"] for f in row.get("files", [])}
            for file_name in [*row.get("templates", {}).values(), *(f["template"] for f in row.get("files", []))]:
                with self.subTest(type=name, template=file_name):
                    self.assertTrue((ASSETS / file_name).is_file(), f"{name}: no assets/{file_name}")
        on_disk = {p.name for p in ASSETS.iterdir() if p.is_file()}
        self.assertEqual(sorted(on_disk - named - NOT_A_TYPE), [], "a template of the skill's assets that no row starts a type from")
        self.assertEqual(sorted(NOT_A_TYPE - on_disk), [], "a template this test says no type owns, and the assets lack")

    def test_a_row_is_whole(self):
        """The facts a type's form or group needs are there, and a fact a form cannot have is not."""
        for name, row in ROWS.items():
            with self.subTest(type=name):
                self.assertEqual("statuses" in row, row["form"] == "work_item", "a work item has statuses, and no other type does")
                self.assertEqual("noun" in row, row["form"] == "work_item" or row["group"] == "operations")
                self.assertEqual("id_prefix" in row, row["form"] == "work_item")
                self.assertEqual("without_spec" in row, row["group"] == "standalone")
                self.assertTrue("templates" in row or "files" in row or name == "product-prototype", "a type with no template or file is the prototype")
                self.assertFalse("templates" in row and "files" in row)
                if "schema" in row:
                    self.assertTrue((ROOT / "schemas" / row["schema"]).is_file())
                if "parent" in row:
                    self.assertIn(row["parent"], ROWS)

    def test_each_status_pointer_reaches_the_status_words(self):
        for name in config.types_of_form("work_item"):
            with self.subTest(type=name):
                table = config.status_table(name)
                self.assertEqual(sorted(table["x-groups"]), sorted(table["enum"]))
                self.assertEqual(sorted(table["x-meanings"]), sorted(table["enum"]))
        self.assertEqual(config.status_table("runbook"), {})

    def test_each_document_with_a_role_has_a_row_and_each_exception_is_named(self):
        self.assertLessEqual(set(DOCUMENTS), set(ROWS), "a `loop.documents` type with no row")
        self.assertEqual(set(ROWS) - set(DOCUMENTS), NO_DOCUMENT_ROW)

    def test_a_path_roles_owns_gives_one_path(self):
        for name, row in ROWS.items():
            owned = row.get("folder") == config.ROLES_HOME or any(f["path"] == config.ROLES_HOME for f in row.get("files", []))
            if owned:
                with self.subTest(type=name):
                    self.assertEqual(len(DOCUMENTS[name]["files"]), 1)


class TheCodeAgrees(unittest.TestCase):
    """Each constant that held a list of types reads the rows. A constant is compared with the rows by the fact it names."""

    def test_the_work_item_constants_are_the_rows_that_say_so(self):
        self.assertEqual(backlog.WORK_TYPES, tuple(t for t, r in ROWS.items() if r.get("backlog")))
        self.assertEqual(objects.OBJECT_TYPES, tuple(t for t, r in ROWS.items() if r["form"] != "document"))
        self.assertEqual(objects.DOCUMENT_TYPES, tuple(t for t, r in ROWS.items() if r.get("inside_work_item")))
        self.assertEqual(tuple(objects.OPS_DIRS), tuple(t for t, r in ROWS.items() if r["group"] == "operations"))
        self.assertEqual(objects.PARENT_TYPE, {t: r["parent"] for t, r in ROWS.items() if "parent" in r})
        self.assertEqual(set(objects.TYPE_NAMES), {t for t, r in ROWS.items() if "noun" in r})
        self.assertEqual(tuple(spec_file.ID_PREFIXES), tuple(t for t, r in ROWS.items() if "id_prefix" in r))
        self.assertEqual(grammar.NEW_WORK_ITEMS, tuple(t for t, r in ROWS.items() if r["form"] == "work_item"))
        self.assertEqual(explanations.SCHEMA_TYPES, tuple(t for t, r in ROWS.items() if r.get("explained_by_schema")))

    def test_each_work_item_status_has_the_group_its_schema_gives(self):
        for name in config.types_of_form("work_item"):
            for status, group in config.status_table(name)["x-groups"].items():
                with self.subTest(type=name, status=status):
                    self.assertEqual(backlog.group({"type": name, "status": status}), group)
        for name in ("runbook", "tech-spec", "nope"):
            self.assertIsNone(backlog.group({"type": name, "status": "draft"}), "only a work item has a status group")

    def test_what_load_object_checks_is_each_type_with_a_schema_that_has_no_reader_of_its_own(self):
        self.assertEqual(list(spec_file.OBJECT_SCHEMAS), ["spec", "intent", "proposal", "runbook", "postmortem"])
        for name, schema in spec_file.OBJECT_SCHEMAS.items():
            self.assertEqual(schema, ROWS[name]["schema"])
        self.assertNotIn("exploration", spec_file.OBJECT_SCHEMAS)  # `workitems.load_exploration` checks it

    def test_the_document_constants_are_the_rows_of_their_groups(self):
        self.assertEqual(list(authoring.DOC_TEMPLATES), [t for t, r in ROWS.items() if r["group"] in ("linked", "standalone")])
        self.assertEqual(workitems.UNLINKED_DOCS, frozenset(t for t, r in ROWS.items() if r["group"] == "standalone"))
        self.assertEqual(list(authoring.repo_docs()), [t for t, r in ROWS.items() if "files" in r])
        self.assertEqual(set(authoring.LIVING_TEMPLATES), {"test-plan"})
        self.assertEqual(set(authoring.unlinked_folders()), {"feedback", "service-card"})

    def test_the_documents_aidd_links_as_living_are_the_ones_roles_says_are_living(self):
        """The set the hand-kept list held, read now from `loop.documents`. A runbook is living too, and `aidd new runbook --spec`
        links it as such on its own path, so it is not in the set `aidd new <type> --spec` reads."""
        self.assertEqual(workitems.LIVING_DOCS, frozenset({"acceptance", "data-map", "threat-model", "vendors"}))
        living = {t for t in SPEC_DOC_TYPES if DOCUMENTS.get(t, {}).get("lifecycle") == "living"}
        self.assertEqual(living - workitems.LIVING_DOCS, {"runbook"})

    def test_a_proposal_goes_to_its_own_folder_and_other_types_to_the_folder_the_config_names(self):
        for item_type, folder, tail in (
            ("spec", "tickets", "X-1.md"),
            ("intent", "tickets", "X-1.md"),
            ("proposal", "bids", "X-1/proposal.md"),
            ("runbook", None, "X-1.md"),  # an operations folder is its row's own, whatever the config says
        ):
            with self.subTest(type=item_type):
                item = authoring.NewObject(item_type=item_type, id="X-1", title="t", specs_dir="tickets", proposals_dir="bids")
                path = authoring.object_path(ROOT, item).relative_to(ROOT).as_posix()
                self.assertEqual(path, (f"{objects.OPS_DIRS[item_type]}/" if item_type in objects.OPS_DIRS else f"{folder}/") + tail)


class TheCopiesThatCannotReadTheRegistry(unittest.TestCase):
    """A schema's enum and a page's table spell types out. Each is equal to the rows, or a subset of them where it says so."""

    def test_a_projects_writing_levels_name_each_type_written_as_prose(self):
        enum = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["writing"]["properties"]["controlled"]["items"]["enum"]
        self.assertEqual(enum, sorted(t for t, r in ROWS.items() if "templates" in r or "files" in r))

    def test_the_types_a_spec_links_are_rows(self):
        self.assertEqual(tuple(SPEC_DOC_TYPES), config.DOC_TYPES)
        self.assertLessEqual(set(SPEC_DOC_TYPES) - {"other"}, set(ROWS))
        self.assertLessEqual({t for t, r in ROWS.items() if r["group"] == "linked"}, set(SPEC_DOC_TYPES), "a linked type the schema refuses")

    def test_the_types_with_a_required_docs_rule_are_rows_a_spec_links(self):
        disabled = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["disabled"]["properties"]
        self.assertLessEqual(set(disabled), set(SPEC_DOC_TYPES))
        self.assertLessEqual(set(config.default_docs_required()), set(SPEC_DOC_TYPES))

    def test_the_status_and_trace_schemas_name_the_work_items(self):
        status = resources.load_json("status.schema.json")["properties"]["items"]["items"]["properties"]["type"]["enum"]
        trace = resources.load_json("trace.schema.json")["properties"]["work"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(status, list(config.types_of_form("work_item")))
        self.assertEqual(trace, list(config.types_with("backlog")))

    def test_the_recall_index_reads_repository_documents(self):
        from aidd.recall import sources

        self.assertLessEqual(set(sources.ONE_PER_REPOSITORY), set(config.types_in("repository")))

    def test_the_living_documents_table_of_the_profiles_reference_says_what_the_rows_and_roles_say(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "references" / "profiles.md").read_text(encoding="utf-8")
        table = text.split("## The product's living documents", 1)[1].split("\n\n`aidd new srs", 1)[0]
        rows = [line for line in table.splitlines() if line.startswith("| ") and "`aidd new " in line]
        self.assertEqual(len(rows), 6)
        for line in rows:
            made, home = re.findall(r"`([^`]+)`", line)[:2]
            word = made.split()[2]
            with self.subTest(type=word):
                self.assertIn(word, ROWS)
                folder = (
                    "/".join(DOCUMENTS[word]["files"][0].replace("{docs}", "docs").split("/")[:-1]) if DOCUMENTS[word].get("files") else workitems.THREAT_MODELS
                )
                self.assertTrue(home.startswith(folder) or folder in home, f"{word}: {home} is not in {folder}")

    def test_the_glossary_defines_the_work_item_and_the_typed_document_by_the_rows(self):
        glossary = (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")
        row = lambda term: next(line for line in glossary.splitlines() if line.startswith(f"| {term} |"))  # noqa: E731
        for name in config.types_of_form("work_item"):
            self.assertIn(f"`{name}`", row("Work item"))
        for name in config.types_of_form("typed_document"):
            self.assertIn(f"`{name}`", row("Typed document"))
        for name in objects.OBJECT_TYPES:
            self.assertIn(f"`{name}`", row("Type"))


class NoModuleKeepsItsOwnList(unittest.TestCase):
    def test_no_list_of_three_types_lives_in_the_code_but_the_ones_named_here(self):
        found = literal_lists()
        stray = [f"{where} {names}" for where, names in found.items() if where.split(":")[0] not in OWN_LISTS]
        self.assertEqual(
            stray,
            [],
            "read the rows of schemas/item-types.json (`config.types_in`, `types_with`, `types_of_form`), or name the list in OWN_LISTS with its reason",
        )
        for path in OWN_LISTS:
            self.assertTrue(any(where.startswith(path + ":") for where in found), f"{path} no longer holds a list: drop it from OWN_LISTS")


if __name__ == "__main__":
    unittest.main()
