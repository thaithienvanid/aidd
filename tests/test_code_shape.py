"""Code shape: four counts over src/aidd, each with a ceiling that only goes down (CONTRIBUTING.md, "Code and imports").

`.importlinter` keeps the packages apart; this keeps the functions in them small. A count above its ceiling fails, and
the message names the next step. A count below its ceiling passes and says which ceiling the change can lower. A person
raises a ceiling only on purpose, with the reason in the change that raises it.
"""

import ast
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

SRC = Path(__file__).resolve().parent.parent / "src" / "aidd"
LONG_FUNCTION, WIDE_FUNCTION, LONG_MODULE = 60, 5, 700
CEILINGS = {
    "functions over 60 lines": 74,
    "functions over 5 parameters": 67,
    "modules over 700 lines": 5,
    "one-letter parameters in public functions": 99,
    "parameters in the widest public function": 13,
}


def parameters(f: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Every parameter a caller passes: positional, keyword-only, and the starred ones; never a method's self or cls."""
    a = f.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
    return names[1:] if names[:1] in (["self"], ["cls"]) else names


def shape(root: Path) -> dict[str, int]:
    """The counts CEILINGS names, over every .py file under `root`."""
    counts = dict.fromkeys(CEILINGS, 0)
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        counts["modules over 700 lines"] += len(text.splitlines()) > LONG_MODULE
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = parameters(node)
                counts["functions over 60 lines"] += node.end_lineno - node.lineno + 1 > LONG_FUNCTION
                counts["functions over 5 parameters"] += len(names) > WIDE_FUNCTION
                if not node.name.startswith("_"):
                    counts["one-letter parameters in public functions"] += sum(len(n) == 1 for n in names)
                    counts["parameters in the widest public function"] = max(counts["parameters in the widest public function"], len(names))
    return counts


def over(counts: dict[str, int]) -> list[str]:
    return [
        f"{name}: {counts[name]}, over its ceiling of {ceiling}. Shorten or split the function (a parameter object for a wide "
        "one), or lower another count in the same change. Raise a ceiling only on purpose, with the reason in the change"
        for name, ceiling in CEILINGS.items()
        if counts[name] > ceiling
    ]


class CodeShapeTests(unittest.TestCase):
    def test_no_count_rises_above_its_ceiling(self):
        counts = shape(SRC)
        self.assertEqual(over(counts), [])
        for name, ceiling in CEILINGS.items():
            if counts[name] < ceiling:
                print(f"code shape: {name} is {counts[name]}, under its ceiling of {ceiling}: lower it in CEILINGS", file=sys.stderr)

    def test_a_long_or_wide_function_counts(self):
        body = "".join(f"    x{i} = {i}\n" for i in range(60))
        with tempfile.TemporaryDirectory() as d:
            Path(d, "m.py").write_text(
                f"def long():\n{body}\n\ndef wide(a, b, c, d, e, f):\n    pass\n\n\nclass C:\n    def five(self, a, b, c, d, e):\n        pass\n",
                encoding="utf-8",
            )
            counts = shape(Path(d))
        self.assertEqual((counts["functions over 60 lines"], counts["functions over 5 parameters"]), (1, 1))
        self.assertEqual((counts["one-letter parameters in public functions"], counts["parameters in the widest public function"]), (11, 6))
        (message,) = over(dict(CEILINGS, **{"functions over 60 lines": CEILINGS["functions over 60 lines"] + 1}))
        self.assertIn("Shorten or split the function", message)


if __name__ == "__main__":
    unittest.main()
