"""Nine change types, and `aidd risk --dimension`; the levels of a risk rule read from their data.

The type never raises the route: a risk dimension does, whether an area carries it or the author declares it. Five types were
retired, each for a type and a dimension, and each value a person typed is a row of schemas/retired-names.json that the CLI reads.
The proof compares with the commit before the change (tests/fixtures/start-answers/routes.json): every request, with a retired
type typed as its row says, takes the route, the edit level, and the Spec approval it took then, so no answer got more permissive."""

import argparse
import contextlib
import io
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import control_tables
from helpers import aidd_here, make_repo, src_pythonpath

from aidd import config, risk, workitems
from aidd.cli import arguments, mcp_server
from aidd.cli import parser as cli_parser
from aidd.cli.commands import work
from aidd.kernel import documents, resources, retired_names, strict_yaml
from aidd.setup import migrating
from aidd.workitems import authoring, validation

START = json.loads((control_tables.ANSWERS / "routes.json").read_text(encoding="utf-8"))
RETIRED = [row for row in retired_names.rows("cli_value") if row["old"].startswith("--change-type ")]
DIMENSIONS = resources.load_json("common.schema.json")["$defs"]["dimension"]["enum"]
RETIRED_TYPES = sorted(set(control_tables.CHANGE_TYPES_BEFORE) - set(arguments.CHANGE_TYPES))


def choices(command: str, flag: str) -> list[str]:
    """The values the parser takes after `flag` of `aidd <command>`."""
    top = cli_parser.build_parser()
    sub = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction)).choices[command]
    return list(next(a for a in sub._actions if flag in a.option_strings).choices)


class TheRoutesAsBefore(unittest.TestCase):
    def test_each_request_takes_the_route_it_took_and_a_retired_type_as_its_row_says(self):
        self.assertEqual(sorted(START), sorted(control_tables.route_cases()), "the table and its answers are one set")
        for key, case in control_tables.route_cases().items():
            with self.subTest(key):
                now, then = control_tables.route_answer(*case), START[key]
                self.assertEqual({k: now[k] for k in ("route", "edit", "spec_approval")}, {k: then[k] for k in ("route", "edit", "spec_approval")})
                self.assertLessEqual(set(then["dimensions"]), set(now["dimensions"]), "a declared dimension only adds")

    def test_the_types_that_raised_the_route_still_do_through_their_rows(self):
        """The table holds a path in no area under each type, so a retired type that raised it shows here, not only on paths an area raises."""
        raised = {t: START[f"solo|README.md|{t}"]["route"] for t in ("data", "security", "compliance", "infra", "deps")}
        self.assertEqual(raised, {"data": "major", "security": "major", "compliance": "major", "infra": "normal", "deps": "minor"})


class TheDeclaredDimension(unittest.TestCase):
    def test_a_declared_dimension_raises_the_route_as_an_area_does(self):
        """The revert proof of the declared dimensions: were the route to drop the declared dimensions, `--dimension security` would answer minor."""
        rs = risk.rule_set(None)
        for dimension in resources.load_json("common.schema.json")["$defs"]["dimension"]["enum"]:
            with self.subTest(dimension):
                want = "major" if dimension in config.MAJOR_DIMENSIONS else "normal"
                self.assertEqual(risk.route_for(rs, ["README.md"], risk.DeclaredRisk((dimension,))).route, want)
        self.assertEqual(risk.route_for(rs, ["README.md"], risk.DeclaredRisk()).route, "minor")
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            done = aidd_here("risk", "--paths", "README.md", "--dimension", "security", "--json", cwd=root)
            self.assertEqual(json.loads(done.stdout)["route"], "major")
            self.assertIn("security", json.loads(done.stdout)["dimensions"])

    def test_the_next_step_carries_what_was_declared_so_the_spec_it_writes_takes_the_route(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            answer = json.loads(aidd_here("risk", "--paths", "README.md", "--dimension", "data", "--irreversible", "--json", cwd=root).stdout)
            self.assertIn("--paths README.md --dimension data --irreversible`", answer["next"]["what"])
            made = aidd_here("new", "spec", "Drop a column", "--paths", "README.md", "--dimension", "data", "--irreversible", cwd=root)
            self.assertEqual(made.returncode, 0, made.stderr)
            spec, _ = documents.split_front_matter((root / "specs" / "SPEC-1.md").read_text(encoding="utf-8"), "SPEC-1")
            self.assertEqual((spec["route"], spec["risk"]["dimensions"], spec["risk"]["irreversible"]), (answer["route"], ["data"], True))

    def test_honest_work_with_a_type_and_no_dimension_is_not_raised(self):
        """A build or docs change to a file in no area stays minor: the type alone never asks for a Spec."""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            for change_type in arguments.CHANGE_TYPES:
                with self.subTest(change_type):
                    done = aidd_here("risk", "--paths", "README.md", "--change-type", change_type, "--json", cwd=root)
                    self.assertEqual(json.loads(done.stdout)["route"], "minor")


class TheRetiredTypes(unittest.TestCase):
    def test_each_row_names_a_value_the_flag_no_longer_takes_and_values_it_takes(self):
        self.assertEqual(len(RETIRED), 5)
        for row in RETIRED:
            with self.subTest(row["id"]):
                flag, value = row["old"].split()
                for command in ("risk", "new"):
                    self.assertNotIn(value, choices(command, flag))
                    new = row["new"].split()
                    for new_flag, new_value in zip(new[::2], new[1::2], strict=True):
                        self.assertIn(new_value, choices(command, new_flag))

    def test_a_retired_type_is_refused_with_what_to_type_now(self):
        with tempfile.TemporaryDirectory() as d:
            for row in RETIRED:
                value = row["old"].split()[1]
                for argv in (("risk", "--paths", "README.md", "--change-type", value), ("new", "spec", "T", "--change-type", value)):
                    with self.subTest(argv=argv):
                        done = aidd_here(*argv, cwd=d)
                        first = done.stderr.splitlines()[0]
                        self.assertEqual(done.returncode, 2)
                        self.assertIn(f"--change-type: '{value}' was retired in 1.0.0: type `{row['new']}`.", first)
            self.assertEqual(os.listdir(d), [], "a refused value writes nothing")

    def test_the_mcp_tool_takes_the_dimensions_and_refuses_a_retired_type_with_the_same_words(self):
        with tempfile.TemporaryDirectory() as d:
            root = str(make_repo(Path(d) / "r", "solo"))
            bad, said = mcp_server.call("risk", {"paths": ["README.md"], "dimensions": ["security", "cost"]}, root)
            self.assertFalse(bad, said)
            self.assertEqual((json.loads(said)["route"], json.loads(said)["dimensions"]), ("major", ["cost", "security"]))
            for args, words in (
                ({"paths": ["README.md"], "change_type": "infra"}, "type `--change-type build --dimension availability`"),
                ({"paths": ["README.md"], "dimensions": "security"}, "dimensions must be a list of strings"),
                ({"command": "ls", "dimensions": ["data"]}, "`dimensions` is a risk dimension of planned paths"),
            ):
                with self.subTest(args=args):
                    bad, said = mcp_server.call("risk", args, root)
                    self.assertTrue(bad)
                    self.assertIn(words, said)


class TheRouteARiskGives(unittest.TestCase):
    def test_it_is_the_router_s_answer_for_every_set_of_dimensions(self):
        """`config.route_of_risk`, which `aidd validate` and `aidd new spec` read, answers as `aidd risk` does for declared risk on
        no path, over every set of dimensions, with and without `--irreversible`."""
        rs = risk.rule_set(None)
        for n in range(len(DIMENSIONS) + 1):
            for dims, irreversible in itertools.product(itertools.combinations(DIMENSIONS, n), (False, True)):
                want = risk.route_for(rs, [], risk.DeclaredRisk(dims, irreversible)).route
                self.assertEqual(config.route_of_risk(dims, irreversible), want, (dims, irreversible))

    def test_new_spec_with_a_declared_risk_and_no_paths_takes_its_route(self):
        """Without --paths, the route --dimension and --irreversible give wins over the default and a lower --route; an emergency
        stays one. The revert proof: without it, `aidd new spec --dimension security` writes `route: normal`."""
        cases = [((d,), False, None) for d in DIMENSIONS]
        cases += [((), True, None), ((), False, None), (("cost",), False, "major"), (("data",), False, "normal"), (("security",), False, "emergency")]
        for dims, irreversible, route in cases:
            with self.subTest(dims=dims, irreversible=irreversible, route=route):
                args = argparse.Namespace(type="spec", paths=None, route=route, dimension=list(dims) or None, irreversible=irreversible)
                with contextlib.redirect_stdout(io.StringIO()):
                    got = work._spec_route(args, None)
                chosen = route or "normal"
                need = config.route_of_risk(dims, irreversible)
                want = chosen if chosen == "emergency" or config.ROUTE_RANK[chosen] >= config.ROUTE_RANK[need] else need
                self.assertEqual(got, (want, None))
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            done = aidd_here("new", "spec", "Rotate the keys", "--dimension", "security", cwd=root)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("route: major", done.stdout)
            spec, _ = documents.split_front_matter((root / "specs" / "SPEC-1.md").read_text(encoding="utf-8"), "SPEC-1")
            self.assertEqual((spec["route"], spec["risk"]["dimensions"]), ("major", ["security"]))


def spec_with(change_type: str, route: str, scope: str, status: str = "approved", dimensions: tuple[str, ...] = ()) -> dict:
    """A Spec's front matter with these fields, the rest as a template writes it."""
    return {
        "type": "spec",
        "id": "SPEC-1",
        "title": "t",
        "status": status,
        "change_type": change_type,
        "route": route,
        "risk": {"summary": "s", "dimensions": list(dimensions), "irreversible": False},
        "tasks": [{"id": "T1", "scope": [scope]}],
    }


def upgraded(data: dict) -> dict:
    """What `aidd upgrade --yes` writes for a Spec that holds `data`, read back."""
    text = strict_yaml.dump(data)
    block = migrating._Block("specs/SPEC-1.md", "spec", text, (0, len(text)))
    migrating._migrate_block(block, migrating._Ctx())
    assert not [w for k, w in block.lines if k == "manual"], block.lines
    return documents.parse_yaml(block.text, "upgraded")


class TheRetiredTypesInASpec(unittest.TestCase):
    """Invariant: for a Spec with each retired type, on each route and profile, scoped to a path of each built-in area, the old file
    read in memory, the file `aidd upgrade --yes` writes, and the shape written by hand are one reading, so every check that reads
    the Spec (`aidd validate`, the required documents, `aidd status`, the delegate's approved copy, the base view) answers alike. The
    dimension each type becomes gives the route the type took on the commit before it was retired (routes.json), so the route a Spec
    stored then is never below it now, and an upgrade is no revision."""

    def test_the_old_file_the_upgraded_file_and_the_new_shape_read_alike(self):
        scopes = sorted({p for _, paths, _ in control_tables.route_cases().values() for p in paths if not p.startswith("**")})
        cells = 0
        for old, route, profile, scope in itertools.product(RETIRED_TYPES, ("normal", "major", "emergency"), ("solo", "team"), scopes):
            kind, dimension = workitems.change_type_of(old)
            data = spec_with(old, route, scope)
            by_hand = spec_with(kind, route, scope, dimensions=(dimension,) if dimension else ())
            cfg = config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["@x"]\n')
            with self.subTest(old=old, route=route, profile=profile, scope=scope):
                in_memory = workitems.todays_shape(data)
                self.assertEqual(in_memory, by_hand)
                self.assertEqual(upgraded(data), by_hand)
                self.assertEqual(authoring.required_docs(in_memory, cfg), authoring.required_docs(by_hand, cfg))
                then = START[f"{profile}|README.md|{old}"]["route"]
                honest = route == "emergency" or config.ROUTE_RANK[route] >= config.ROUTE_RANK[then]
                refused = validation.route_findings(Path("specs/SPEC-1.md"), in_memory)
                self.assertEqual(refused == [], honest, "only a route below the one the type took is refused")
                cells += 1
        self.assertGreater(cells, 400)

    def test_each_type_s_dimension_gives_the_route_the_type_took(self):
        """The revert proof of the split: were `infra` read as `build` alone, or `security` as `feat` alone, the route the Spec's risk
        gives would fall below the route the type took, and a check that reads it would ask for less."""
        for old in RETIRED_TYPES:
            kind, dimension = workitems.change_type_of(old)
            with self.subTest(old):
                self.assertIn(kind, arguments.CHANGE_TYPES)
                for profile in ("solo", "team"):
                    self.assertEqual(config.route_of_risk([dimension] if dimension else [], False), START[f"{profile}|README.md|{old}"]["route"])

    def test_the_type_a_row_leaves_out_is_the_one_the_cli_takes_when_none_is_typed(self):
        for command in ("risk", "new"):
            self.assertEqual(str(default_of(command, "--change-type")), workitems.DEFAULT_CHANGE_TYPE, command)
        self.assertEqual(workitems.NewObject("spec", "SPEC-1", "t").ctype, workitems.DEFAULT_CHANGE_TYPE)


def default_of(command: str, flag: str) -> object:
    top = cli_parser.build_parser()
    sub = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction)).choices[command]
    return next(a for a in sub._actions if flag in a.option_strings).default


class TheStoredRouteAndItsRisk(unittest.TestCase):
    """`aidd validate` refuses an open Spec whose stored route is below the route its declared risk gives, and names the step; an
    ended one gets a warning, since no step is left to route. The revert proof: without the check, every row below passes."""

    def test_a_route_below_its_risk_is_refused_while_the_work_is_open(self):
        product = itertools.product(
            ("normal", "major", "emergency"),
            ((), ("cost",), ("security",), ("availability", "data")),
            (False, True),
            ("draft", "approved", "in_review", "done"),
        )
        for route, dims, irreversible, status in product:
            data = spec_with("feat", route, "src/", status=status, dimensions=dims)
            data["risk"]["irreversible"] = irreversible
            found = validation.route_findings(Path("specs/SPEC-1.md"), data)
            need = config.route_of_risk(dims, irreversible)
            below = route != "emergency" and config.ROUTE_RANK[route] < config.ROUTE_RANK[need]
            with self.subTest(route=route, dims=dims, irreversible=irreversible, status=status):
                self.assertEqual(bool(found), below)
                if below:
                    [said] = found
                    self.assertEqual(said.startswith("warning: "), status == "done")
                    self.assertIn(f"route {route} is below {need}", said)
                    self.assertEqual(f"set `route: {need}`" in said, status != "done")
                    self.assertEqual("`spec.revise`" in said, status in ("approved", "in_review"))

    def test_an_honest_spec_from_before_the_types_were_cut_has_a_path(self):
        """Honest work this can newly stop: a Spec that `aidd new spec --change-type data` wrote with no --paths, on the default route
        normal, before the types were cut. Upgraded, it holds the dimension `data`, so `aidd validate` refuses it and names the step;
        on major it passes."""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            made = aidd_here("new", "spec", "Drop a column", cwd=root)
            self.assertEqual(made.returncode, 0, made.stderr)
            rel = root / "specs" / "SPEC-1.md"
            rel.write_text(rel.read_text(encoding="utf-8").replace("change_type: feat", "change_type: data", 1), encoding="utf-8")
            said = aidd_here("validate", "specs/SPEC-1.md", cwd=root)
            self.assertIn("`change_type: data` was retired in 1.0.0", said.stdout + said.stderr)
            self.assertIn("`aidd upgrade --yes` moves it", said.stdout + said.stderr)
            migrating.apply(root, migrating.plan(root))
            said = aidd_here("validate", "specs/SPEC-1.md", cwd=root)
            self.assertIn("route normal is below major", said.stdout + said.stderr)
            rel.write_text(rel.read_text(encoding="utf-8").replace("route: normal", "route: major", 1), encoding="utf-8")
            said = aidd_here("validate", "specs/SPEC-1.md", cwd=root)
            self.assertNotIn("is below", said.stdout + said.stderr)


class TheLevels(unittest.TestCase):
    def test_the_levels_follow_their_data(self):
        """The revert proof of levels as data: the levels are read from schemas/risks.json, so a copy with another order is followed, by
        the rules and by the config's lock check alike, and a tuple written in the code would not follow it."""
        program = (
            "import json\nfrom aidd.kernel import resources\nreal = resources.load_json\n"
            "def load(name):\n    data = real(name)\n    return {**data, 'levels': data['levels'][::-1]} if name == 'risks.json' else data\n"
            "resources.load_json = load\nfrom aidd.risk import rules\nfrom aidd.config import loading\n"
            "print(json.dumps([list(rules.LEVELS), sorted(loading._level_rank(), key=loading._level_rank().get)]))\n"
        )
        env = {**os.environ, "PYTHONPATH": src_pythonpath()}
        done = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, check=True)
        self.assertEqual(json.loads(done.stdout), [["ask", "report", "allow"], ["ask", "report", "allow"]])


if __name__ == "__main__":
    unittest.main()
