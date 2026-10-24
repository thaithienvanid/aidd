"""Every command's handler is named, not imported, by the grammar (aidd.cli.parser.Handler): each name must resolve to
the handler it means, and building the parser must load none of them.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import unittest

from helpers import ROOT

from aidd.cli import parser


def _commands(p: argparse.ArgumentParser, prefix: str = "") -> dict[str, argparse.ArgumentParser]:
    """Every command and command-group action by its full name (`record verify`)."""
    out: dict[str, argparse.ArgumentParser] = {}
    for action in p._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                full = f"{prefix} {name}".strip()
                out[full] = sub
                out |= _commands(sub, full)
    return out


class HandlerTests(unittest.TestCase):
    def test_every_named_handler_resolves_to_its_function(self):
        handlers = 0
        for name, sub in _commands(parser.build_parser()).items():
            func = sub.get_default("func")
            if isinstance(func, parser.Handler):
                handlers += 1
                with self.subTest(command=name):
                    module = __import__(f"aidd.cli.commands.{func.group}", fromlist=["_"])
                    target = getattr(module, func.__name__)
                    self.assertTrue(callable(target))
                    self.assertEqual(target.__name__, func.__name__)
        self.assertGreater(handlers, 30)

    def test_building_the_parser_loads_no_command(self):
        code = "import sys\nfrom aidd.cli import parser\nparser.build_parser()\nprint(sorted(m for m in sys.modules if m.startswith('aidd.cli.commands.')))"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", env={"PYTHONPATH": str(ROOT / "src")}, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
