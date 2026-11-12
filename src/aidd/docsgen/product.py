"""What aidd says about itself: `schemas/product.json` owns the description (a long and a short form) and the keywords,
and `aidd gen-docs` writes them into every file that states one, so no copy can drift from it.

Markdown pages carry `<!-- aidd:gen product:long -->` or `product:short` blocks. The package metadata, the package
docstring, and the two Claude Code manifests are not Markdown, so `sync` rewrites their one line or key.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from aidd.kernel import resources

FORMS = ("long", "short")
PYPROJECT = Path("pyproject.toml")
PACKAGE_INIT = Path("src/aidd/__init__.py")
PLUGIN = Path(".claude-plugin/plugin.json")
MARKETPLACE = Path(".claude-plugin/marketplace.json")


def data() -> dict:
    """schemas/product.json."""
    return resources.load_json("product.json")


def text(form: str) -> str:
    """`product:long` or `product:short`: the description in that form."""
    if form not in FORMS:
        raise KeyError(form)
    return str(data()[form])


def _toml_line(content: str, key: str, value: object) -> str:
    """`content` with the top-level line `key = ...` set to `value`, written as a TOML basic string or array of them."""
    line = f"{key} = {json.dumps(value, ensure_ascii=False)}"
    return re.sub(rf"^{key} = .*$", lambda _: line, content, count=1, flags=re.M)


def _json_file(path: Path, edit: Callable[[dict], None]) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def sync(root: Path, update: Callable[[Path, str], None]) -> None:
    """Write the description and the keywords into the files that state them; `update(path, new_text)` stores one."""
    product = data()
    long, keywords = str(product["long"]), list(product["keywords"])
    if (path := root / PYPROJECT).is_file():
        update(path, _toml_line(_toml_line(path.read_text(encoding="utf-8"), "description", long), "keywords", keywords))
    if (path := root / PACKAGE_INIT).is_file():
        update(path, re.sub(r'\A"""[^\n]*', lambda _: '"""' + long, path.read_text(encoding="utf-8"), count=1))
    if (path := root / PLUGIN).is_file():
        update(path, _json_file(path, lambda doc: doc.update(description=long, keywords=keywords)))
    if (path := root / MARKETPLACE).is_file():
        update(path, _json_file(path, lambda doc: doc["metadata"].update(description=long)))
