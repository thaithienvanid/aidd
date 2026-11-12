"""Nine change types, and `aidd risk --dimension`; the levels of a risk rule read from their data.

The type never raises the route: a risk dimension does, whether an area carries it or the author declares it. The proof compares
with the commit before the change (tests/fixtures/start-answers/routes.json): every request takes the route, the edit level, and
the Spec approval it took then, so no answer got more permissive."""

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

from aidd import config, risk
from aidd.cli import arguments, mcp_server
from aidd.cli.commands import work
from aidd.kernel import documents, resources
from aidd.workitems import validation

START = json.loads((control_tables.ANSWERS / "routes.json").read_text(encoding="utf-8"))
DIMENSIONS = resources.load_json("common.schema.json")["$defs"]["dimension"]["enum"]


class TheRoutesAsBefore(unittest.TestCase):
    def test_each_request_takes_the_route_it_took(self):
        self.assertEqual(sorted(START), sorted(control_tables.route_cases()), "the table and its answers are one set")
        for key, case in control_tables.route_cases().items():
            with self.subTest(key):
                now, then = control_tables.route_answer(*case), START[key]
                self.assertEqual({k: now[k] for k in ("route", "edit", "spec_approval")}, {k: then[k] for k in ("route", "edit", "spec_approval")})
                self.assertLessEqual(set(then["dimensions"]), set(now["dimensions"]), "a declared dimension only adds")


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


class TheMcpTool(unittest.TestCase):
    def test_the_mcp_tool_takes_the_dimensions_and_refuses_what_is_no_dimension_of_planned_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = str(make_repo(Path(d) / "r", "solo"))
            bad, said = mcp_server.call("risk", {"paths": ["README.md"], "dimensions": ["security", "cost"]}, root)
            self.assertFalse(bad, said)
            self.assertEqual((json.loads(said)["route"], json.loads(said)["dimensions"]), ("major", ["cost", "security"]))
            for args, words in (
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
