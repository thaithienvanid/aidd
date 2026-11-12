"""aidd-team's prototype tool: a design shown in the viewer, checked, and turned into a component contract."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import re
import sys
import tempfile
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent


def _sibling(name: str) -> ModuleType:
    """Load a sibling module by file path so the tool works without installation."""
    key = f"aidd_team_tools.{HERE / name}"
    if key in sys.modules:
        return sys.modules[key]
    if not (HERE / f"{name}.py").is_file():
        raise FileNotFoundError(f"the prototype tool's {name}.py is missing beside {Path(__file__).name}: reinstall aidd-team")
    spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"the prototype tool's {name}.py cannot be loaded beside {Path(__file__).name}: reinstall aidd-team")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module


try:
    design_checks = _sibling("design_checks")
except FileNotFoundError as missing:
    if __name__ != "__main__":
        raise
    print(missing, file=sys.stderr)
    raise SystemExit(2) from None

FORMAT = 1
BUILD = "aidd prototype"

APP = "design/app"
SITEMAP = "sitemap.json"
SHELL = "shell.html"
FLOWS = "flows"
VIEW = ".aidd/views/prototype.html"
MARKERS = {"navigation": "<!-- aidd:navigation -->", "screens": "<!-- aidd:screens -->"}
FLOW_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
CORE_STATES = ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCREEN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
COMMENT_TYPES = ("change", "remove", "add", "question")
DIRECTIONS, EXPLORATION_FILE = "directions", "exploration.md"
MAX_ROUNDS, MAX_ITEMS, MAX_TEXT, MAX_TOTAL = 20, 200, 500, 200_000
MAX_FILE_BYTES = 1_000_000

_PRODUCT = re.compile(r'(<template id="product">\n)(.*)(</template>\n<script type="application/json" id="fixtures">)', re.S)
_FIXTURES = re.compile(r'(<script type="application/json" id="fixtures">)(.*?)(</script(?:[\s/][^>]*)?>)', re.S)
_CONFIG = re.compile(r'(<script type="application/json" id="viewer-config">)(.*?)(</script(?:[\s/][^>]*)?>)', re.S)
_DEVICES = re.compile(r'(<script type="application/json" id="devices">)(.*?)(</script(?:[\s/][^>]*)?>)', re.S)
_TITLE = re.compile(r"<title>.*?</title>", re.S | re.I)
_SPEC_META = re.compile(r'<meta\s+name="aidd-spec"\s+content="([^"]*)"', re.I)
_SPEC_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")
_SPEC_IN_PATH = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9]*-[0-9]+)/design/")
_DESIGN_FORMAT = re.compile(r"""<html\b[^>]*\bdata-aidd-prototype\s*=\s*["']?([^"'\s>]*)""", re.I)
_SAFE_PATH = re.compile(r"[A-Za-z0-9._/][A-Za-z0-9._/-]*\Z")
_POLICY = re.compile(r'<meta http-equiv="Content-Security-Policy" content="[^"]*">')
_SCRIPT = re.compile(r"<script>(.*?)</script(?:[\s/][^>]*)?>", re.S | re.I)
_ANY_SCRIPT = re.compile(r"<script\b", re.I)
_DATA_SCRIPT = re.compile(r'<script type="application/json"', re.I)
_SCRIPT_SRC = re.compile(r"script-src [^;]*")
_STYLE_SRC_ELEM = re.compile(r"style-src-elem [^;]*")
_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style(?:[\s/][^>]*)?>", re.S | re.I)
_STATELESS = re.compile(r"^screen `[^`]*` has no state:")
_TEMPLATE_OPEN = '<template id="product">'
_FIXTURES_OPEN = '<script type="application/json" id="fixtures">'
_q = design_checks.quoted


def _partials() -> ModuleType:
    return _sibling("prototype_partials")


_partial_mod = _partials()
IMAGE_TYPES = _partial_mod.IMAGE_TYPES
MAX_IMAGE_BYTES = _partial_mod.MAX_IMAGE_BYTES
MAX_IMAGES_BYTES = _partial_mod.MAX_IMAGES_BYTES
_IMAGE_FIELD = re.compile(r"""\bdata-image\s*=\s*["']?([^"'\s>]+)""", re.I)
DATA_IMAGE = _partial_mod.DATA_IMAGE


def _product() -> ModuleType:
    return _sibling("prototype_product")


def _rounds() -> ModuleType:
    return _sibling("prototype_rounds")


def _contracts() -> ModuleType:
    return _sibling("prototype_contracts")


def product_prototype_dir(root: Path, docs_dir: str = "docs") -> Path:
    return root / docs_dir / APP


def new_product_prototype(root: Path, *, docs_dir: str = "docs", product: str = "", today: dt.date | None = None) -> list[Path]:
    return list(_product().new_product_prototype(HERE, root, docs_dir=docs_dir, product=product, today=today, build_cmd=BUILD))


def project_tokens(root: Path) -> str | None:
    return _product().project_tokens(root)


def with_project_tokens(design: str, root: Path) -> str:
    return str(_product().with_project_tokens(design, root))


def _state_problems(label: str, screen: str, state: str) -> list[str]:
    return list(_product()._state_problems(label, screen, state))


def product_name_problem(name: object) -> str:
    return str(_product().product_name_problem(name))


def load(root: Path, docs_dir: str = "docs") -> tuple[dict, str, list[Any], list[str]]:
    return _product().load(root, docs_dir, format_version=FORMAT, newer_fn=_newer, tool=_self())


def check(sitemap: dict, flows: list[Any]) -> list[str]:
    return list(_product().check(sitemap, flows))


def product_body(sitemap: dict, shell: str, flows: list[Any]) -> str:
    return str(_product().product_body(sitemap, shell, flows))


def direction_of(root: Path, design: Path) -> tuple[str, Path, str]:
    return _rounds().direction_of(root, design)


def comments_file(direction: str = "") -> str:
    return str(_rounds().comments_file(direction))


def round_comments(folder: Path, direction: str = "") -> tuple[list[dict], list[str]]:
    return _rounds().round_comments(folder, direction)


def component_contract(parts: list[str]) -> dict:
    return dict(_contracts().component_contract(parts))


def kebab(text: str) -> str:
    return str(_contracts().kebab(text))


def stories_of(index: object) -> set[tuple[str, str]]:
    return set(_contracts().stories_of(index))


def missing_stories(contract: dict, stories: set[tuple[str, str]]) -> list[str]:
    return list(_contracts().missing_stories(contract, stories))


def _fixed(text: str) -> Callable[[re.Match[str]], str]:
    def replace(_match: re.Match[str]) -> str:
        return text

    return replace


def _page_policy(template: str, body: str) -> str:
    found = _POLICY.search(template)
    if not found or not _SCRIPT_SRC.search(found.group(0)) or not _STYLE_SRC_ELEM.search(found.group(0)):
        raise ValueError("the viewer's Content-Security-Policy changed: the tool's files changed")
    policy = _SCRIPT_SRC.sub("script-src " + script_hashes(template), found.group(0), count=1)
    return _STYLE_SRC_ELEM.sub("style-src-elem " + style_hashes(template, body), policy, count=1)


def style_hashes(*texts: str) -> str:
    blocks = [block.replace("\r\n", "\n").replace("\r", "\n") for text in texts for block in _STYLE.findall(text)]
    hashes = dict.fromkeys(f"'sha256-{base64.b64encode(hashlib.sha256(b.encode('utf-8')).digest()).decode('ascii')}'" for b in blocks)
    return " ".join(hashes) or "'none'"


def script_hashes(template: str) -> str:
    scripts = _SCRIPT.findall(template)
    if len(_ANY_SCRIPT.findall(template)) != len(scripts) + len(_DATA_SCRIPT.findall(template)):
        raise ValueError("the viewer holds a script element the page's policy cannot name: the tool's files changed")
    hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(s.encode('utf-8')).digest()).decode('ascii')}'" for s in scripts]
    return " ".join(hashes) or "'none'"


def image_fields(design: str) -> set[str]:
    return {html.unescape(name) for name in _IMAGE_FIELD.findall(design)}


def with_images(fixtures: object, fields: set[str], folder: Path) -> tuple[object, list[str]]:
    return tuple(_partials().with_images(fixtures, fields, folder, quoted=_q))


@dataclass(frozen=True)
class _Page:
    body: str
    fixtures: str
    config: str
    subtitle: str
    note: str
    title: str


def _device_table() -> str:
    frames = {}
    for key, f in design_checks.device_frames().items():
        frames[key] = {k: f[k] for k in ("name", "platform", "width", "height")}
        if "safe_area" in f:
            frames[key]["safe_area"] = {side: f["safe_area"][side] for side in ("top", "bottom")}
    return json.dumps({"frames": frames}, ensure_ascii=False)


def _in_viewer(page_parts: _Page) -> str:
    template = (HERE / "viewer.html").read_text(encoding="utf-8")
    note = page_parts.note.replace("--", "- -")
    system = (HERE / "system.css").read_text(encoding="utf-8")
    if "</style" in system.lower():
        raise ValueError("system.css holds </style, which would end the viewer's style block: run `aidd gen-docs` from a good tokens.json")
    values = {"title": html.escape(page_parts.title), "subtitle": html.escape(page_parts.subtitle), "note": html.escape(note), "system": system}
    for key in values:
        if template.count("{{" + key + "}}") != 1:
            raise ValueError(f"the viewer no longer has its {{{{{key}}}}}: the tool's files changed")
    template = re.sub(r"\{\{(title|subtitle|note|system)\}\}", lambda m: values[m.group(1)], template)
    steps = (
        (_FIXTURES, lambda m: m.group(1) + "\n" + _script_safe(page_parts.fixtures) + "\n" + m.group(3)),
        (_CONFIG, lambda m: m.group(1) + "\n" + _script_safe(page_parts.config) + "\n" + m.group(3)),
        (_DEVICES, lambda m: m.group(1) + "\n" + _script_safe(_device_table()) + "\n" + m.group(3)),
        (_POLICY, _fixed(_page_policy(template, page_parts.body))),
        (_PRODUCT, lambda m: m.group(1) + page_parts.body + m.group(3)),
    )
    page = template
    for found, replacement in steps:
        page, n = found.subn(replacement, page, count=1)
        if n != 1:
            raise ValueError(f"the viewer no longer has the part `{found.pattern[:40]}` the tool fills: the tool's files changed")
    return page


def assemble(
    sitemap: dict,
    shell: str,
    flows: list[Any],
    rounds: tuple[list[dict], list[str]] = ([], []),
    problems: list[str] | None = None,
    folder: Path | None = None,
) -> str:
    """Assemble the product prototype page inside the viewer."""
    product = str(sitemap.get("product") or "The product")
    data = sitemap.get("fixtures")
    body = product_body(sitemap, shell, flows)
    shown: object = {**(data if isinstance(data, dict) else {}), "product": product}
    if folder is not None:
        shown = with_images(shown, image_fields(body), folder)[0]
    fixtures = json.dumps(shown, ensure_ascii=False, indent=2)
    config = json.dumps(
        {"flows": [{"id": f.id, "title": f.title} for f in flows], "rounds": rounds[0], "round_problems": rounds[1], "problems": problems or []},
        ensure_ascii=False,
    )
    return _in_viewer(
        _Page(
            body,
            fixtures,
            config,
            subtitle="The product prototype: every flow, kept current by each change",
            note="The product prototype, assembled by `aidd prototype` from docs/design/app/: change the sources, never this page.",
            title=f"{product}: product prototype",
        )
    )


def view_prototype_file(root: Path, rel: str, write: bool = True, found: list[str] | None = None) -> tuple[Path | None, list[str]]:
    """Render one prototype file inside the viewer, writing only when `write` is True and checks pass."""
    shown, text, problems = _design_source(root, rel)
    if problems:
        return None, problems
    direction, home, refused = direction_of(root, (root / rel).resolve())
    if refused:
        return None, [refused]
    rounds = round_comments(home, direction) if write else ([], [])
    page, problems = _design_page(text, shown, f"`aidd prototype {shown}`", rounds, found, (root / rel).resolve().parent, direction)
    if problems or page is None or not write:
        return None, problems
    target = _views(root) / f"prototype-{_slug(shown.removesuffix('.html'))}.html"
    _write_page(target, page)
    return target, []


def _design_source(root: Path, rel: str) -> tuple[str, str, list[str]]:
    base = root.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(base) or path.suffix != ".html" or not path.is_file():
        return rel, "", [f"{rel} is no prototype file in this repository: name one, such as specs/<ID>/design/prototype.html"]
    shown = path.relative_to(base).as_posix()
    if not _SAFE_PATH.match(shown):
        return (
            shown,
            "",
            [f"{shown!r}: a prototype file's path takes letters, digits, `.`, `_`, `-` (never first), and `/` only, so aidd can name it in the page"],
        )
    try:
        return shown, path.read_text(encoding="utf-8"), []
    except (OSError, ValueError) as exc:
        return shown, "", [f"{shown} cannot be read ({exc}): save it as UTF-8 text"]


def check_design_file(root: Path, rel: str) -> tuple[list[str], str]:
    """Check one prototype file and return `(problems, ok_summary)`."""
    shown, text, problems = _design_source(root, rel)
    if problems:
        return problems, ""
    _, problems = _design_page(text, shown, f"`{BUILD} {shown}`")
    if refused := direction_of(root, (root / rel).resolve())[2]:
        problems.append(refused)
    if spec_problem := _spec_of(shown, text)[1]:
        problems.append(spec_problem)
    if (data := _FIXTURES.search(text)) is not None:
        problems += _fixture_problems(data.group(2), text, root, rel, shown)
    product = _PRODUCT.search(text)
    format_found = _DESIGN_FORMAT.search(text)
    if product is None or _newer(format_found.group(1) if format_found else 1):
        return problems, ""
    named = format_found.group(1) if format_found else "1"
    found, ok = design_checks.check(text, product.group(2), text.count("\n", 0, product.start(2)) + 1, shown, int(named) if named.isdigit() else 1)
    return [p for p in problems if not _STATELESS.match(p)] + found, ok


def _fixture_problems(raw_fixtures: str, text: str, root: Path, rel: str, shown: str) -> list[str]:
    problems: list[str] = []
    try:
        fixtures = json.loads(raw_fixtures)
    except ValueError:
        return problems
    if isinstance(fixtures, dict) and (product_problem := product_name_problem(fixtures.get("product"))):
        problems.append(product_problem)
    if (product_part := _PRODUCT.search(text)) is not None:
        images = with_images(fixtures, image_fields(product_part.group(2)), (root / rel).resolve().parent)[1]
        problems += [f"{shown}: {problem}" for problem in images]
    return problems


def build_design_file(root: Path, rel: str) -> tuple[Path | None, list[str]]:
    """Build one prototype file, keeping the page even when design checks fail so reviewers can inspect problems."""
    problems = check_design_file(root, rel)[0]
    out, refused = view_prototype_file(root, rel, write=True, found=problems)
    return (None, refused) if out is None else (out, problems)


def _read_design(root: Path, rel: str | None, docs_dir: str, command: str) -> tuple[Any, list[str]]:
    if rel:
        shown, text, problems = _design_source(root, rel)
        product = _PRODUCT.search(text)
        if not problems and product is None:
            problems = [_boundary_problem(text, shown, f"read its {command} by hand")]
        if not problems and product is not None:
            _, problems = _design_page(text, shown, f"`{BUILD} {command} {shown}`")
            problems = [p for p in problems if not _STATELESS.match(p)]
        if problems or product is None:
            return None, problems
        return design_checks.read_design(product.group(2), shown), []
    sitemap, shell, flows, problems = load(root, docs_dir)
    if not sitemap or not shell or problems:
        return None, [*problems, f"fix {docs_dir}/{APP}/ first: the {command} are read only from a design that loads"]
    return design_checks.read_design(product_body(sitemap, shell, flows), APP), []


def screens_of(root: Path, rel: str | None, docs_dir: str = "docs") -> tuple[dict | None, list[str]]:
    reader, problems = _read_design(root, rel, docs_dir, "screens")
    return (None, problems) if reader is None else ({"schema_version": str(FORMAT), "screens": design_checks.screens_of(reader)}, [])


def shots_of(root: Path, rel: str | None, docs_dir: str = "docs", **change: list[str]) -> tuple[dict | None, list[str]]:
    reader, problems = _read_design(root, rel, docs_dir, "shots")
    if reader is None:
        return None, problems
    selection = _sibling("fidelity_shots")
    found, problems = selection.shots(
        reader,
        design_checks.device_frames(),
        components=change.get("components") or [],
        screen_ids=change.get("screens") or [],
        frames=change.get("frames") or list(selection.FULL_FRAMES),
    )
    return (None, problems) if problems else ({"schema_version": str(FORMAT), "shots": found}, [])


def view_example(root: Path) -> Path:
    showcase = (HERE / "examples" / "showcase.html").read_text(encoding="utf-8")
    page, problems = _design_page(showcase, "the showcase", "`aidd prototype --example`", folder=HERE / "examples")
    if page is None:
        raise ValueError(f"the showcase has problems ({'; '.join(problems)}): the tool's files changed")
    target = _views(root) / "prototype-example.html"
    _write_page(target, page)
    return target


def _design_page(
    text: str,
    shown: str,
    command: str,
    rounds: tuple[list[dict], list[str]] = ([], []),
    found: list[str] | None = None,
    folder: Path | None = None,
    direction: str = "",
) -> tuple[str | None, list[str]]:
    format_found = _DESIGN_FORMAT.search(text)
    if newer := _newer(format_found.group(1) if format_found else 1):
        return None, [f"{shown} {newer}"]
    product = _PRODUCT.search(text)
    data = _FIXTURES.search(text)
    if not product or not data:
        return None, [_boundary_problem(text, shown)]
    try:
        fixtures = json.loads(data.group(2))
    except ValueError as exc:
        return None, [f"{shown}: its fixtures block is not JSON ({exc})"]
    prod = _product()
    check_part = prod._Sections("", product.group(2), shell=True, label=shown)
    check_part.read()
    if prod._HANDLER.search(product.group(2)) and not any(w.startswith("an event handler") for w in check_part.forbidden):
        check_part.forbidden.append("an event handler: the viewer holds the one runtime")
    problems = [f"{shown} holds {what}" for what in dict.fromkeys(check_part.forbidden)] + list(dict.fromkeys(check_part.problems))
    if problems:
        return None, problems
    named = _TITLE.search(text)
    title = html.unescape(re.sub(r"</?title>", "", named.group(0), flags=re.I)) if named else shown
    spec = _spec_of(shown, text)[0]
    fields = image_fields(product.group(2))
    shown_data = json.dumps(with_images(fixtures, fields, folder)[0], ensure_ascii=False, indent=2) if fields and folder is not None else data.group(2).strip()
    page = _in_viewer(
        _Page(
            product.group(2),
            shown_data,
            json.dumps(
                {
                    "flows": [],
                    "spec": spec,
                    "design": shown if _SAFE_PATH.match(shown) else "",
                    "rounds": rounds[0],
                    "round_problems": rounds[1],
                    "problems": found or [],
                    "direction": direction,
                },
                ensure_ascii=False,
            ),
            subtitle=shown,
            note=f"A view of {shown} in the current viewer, written by {command}: change the design, never this page.",
            title=title,
        )
    )
    return page, []


def _boundary_problem(text: str, shown: str, then: str = "open it as it is") -> str:
    found = [re.search(r"(?m)^" + re.escape(tag), text) for tag in (_TEMPLATE_OPEN, _FIXTURES_OPEN)]
    opened, data = (m.start() if m else -1 for m in found)

    def line(at: int) -> int:
        return text.count("\n", 0, at) + 1

    if opened < 0 and data < 0:
        return f'{shown} has no <template id="product"> and fixtures block: it predates the prototype viewer, so {then}'
    if opened < 0:
        return f'{shown}, line {line(data)}: a fixtures block, but no <template id="product"> line before it: put the design in one'
    if data < 0:
        return f"{shown}, line {line(opened)}: the product's template, but no fixtures block: add {_FIXTURES_OPEN} on the line after its </template>"
    if not text.startswith("\n", opened + len(_TEMPLATE_OPEN)):
        return f'{shown}, line {line(opened)}: <template id="product"> must end its line: start the design on the next line'
    if not text.startswith("</template>\n" + _FIXTURES_OPEN, text.rfind("</template>", 0, data)):
        return f"{shown}, line {line(data)}: the fixtures block must start on the line right after the product's </template>: remove what is between them"
    return f"{shown}, line {line(data)}: the fixtures block has no </script> to end it: add one"


def _spec_of(shown: str, text: str) -> tuple[str, str]:
    found = _SPEC_META.search(text.split('<template id="product">', 1)[0])
    named = html.unescape(found.group(1)) if found else ""
    if not _SPEC_ID.fullmatch(named):
        return "", ""
    in_path = _SPEC_IN_PATH.search(shown)
    if in_path and in_path.group(1).upper() == named.upper():
        return named.upper(), ""
    where = f"the folder names {in_path.group(1)}" if in_path else "the path names no Spec"
    return "", f"{_q(shown)} says it is the design of {_q(named)}, but {where}: put it in specs/{named.upper()}/design/, or name its own Spec"


def _newer(found: object) -> str:
    try:
        number = int(str(found))
    except ValueError:
        return f"names the design format {found!r}, which is no number: write {FORMAT}"
    return f"is design format {number}, newer than this tool's {FORMAT}: update aidd-team" if number > FORMAT else ""


def _views(root: Path) -> Path:
    folder = root / ".aidd" / "views"
    for step in (root / ".aidd", folder):
        if step.is_symlink():
            raise ValueError(f"{step.relative_to(root).as_posix()} is a link: aidd writes pages only into a real folder; remove the link and run again")
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".gitignore").exists():
        _write_page(folder / ".gitignore", "*\n")
    return folder


def _write_page(target: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _script_safe(text: str) -> str:
    """JSON for a script block: no `<`, `>`, or `&` reaches the HTML parser, so no value can close the block."""
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def __getattr__(name: str) -> Any:
    if name in ("Flow", "_Sections"):
        return getattr(_product(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


class _ModuleProxy:
    def __getattr__(self, name: str) -> Any:
        try:
            return globals()[name]
        except KeyError:
            return __getattr__(name)


def _self() -> Any:
    return sys.modules.get(__name__) or _ModuleProxy()


def _product_design_problems(sitemap: dict, shell: str, flows: list[Any], folder: Path) -> tuple[list[str], str]:
    return _product().product_design_problems(_self(), sitemap, shell, flows, folder)


def check_product_prototype(root: Path, docs_dir: str = "docs") -> tuple[list[str], str]:
    """Check the product prototype and return `(problems, summary)`."""
    return _product().check_product_prototype(_self(), root, docs_dir)


def build_product_prototype(root: Path, docs_dir: str = "docs", write: bool = True) -> tuple[Path | None, list[str]]:
    """Assemble the product prototype, check it, and write `.aidd/views/prototype.html` when sound enough to inspect."""
    return _product().build_product_prototype(_self(), root, docs_dir, write)


def contract_of(root: Path, rel: str | None, docs_dir: str = "docs") -> tuple[dict | None, list[str]]:
    """The component contract of a prototype file or the product prototype."""
    return _contracts().contract_of(_self(), root, rel, docs_dir)


def _parser() -> Any:
    return _sibling("prototype_cli").build_parser()


def serve_design(root: Path, rel: str | None, docs_dir: str = "docs", *, lan: bool = False, port: int = 8765) -> int:
    """Serve one design file or the product prototype locally, rebuilding on each request."""
    return int(_sibling("prototype_cli").serve_design(_self(), root, rel, docs_dir, lan=lan, port=port))


def new_design(root: Path, rel: str, title: str, today: dt.date | None = None) -> Path:
    """Write a starter design inside `root`, refusing traversal, symlinks outside `root`, or existing files."""
    base = root.resolve()
    raw = Path(rel)
    if raw.is_absolute():
        raise ValueError(f"{rel} escapes the project folder: pass a path inside it, such as specs/<ID>/design/prototype.html")
    path = (base / raw).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError(f"{rel} escapes the project folder: pass a path inside it, such as specs/<ID>/design/prototype.html")
    shown = path.relative_to(base).as_posix()
    if path.suffix != ".html" or not _SAFE_PATH.match(shown):
        raise ValueError(f"{shown!r}: a prototype file ends with .html and takes letters, digits, `.`, `_`, `-` (never first), and `/` only")
    logical = root / shown
    if path.exists() or path.is_symlink() or logical.is_symlink():
        raise FileExistsError(f"{shown} exists: open it with `{BUILD} {shown}`")
    text = with_project_tokens((HERE / "design.html").read_text(encoding="utf-8"), root)
    values = {"spec": "a sketch", "title": html.escape(title), "spec_link": "#", "today": (today or dt.date.today()).isoformat(), "path": html.escape(shown)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(re.sub(r"\{\{(spec|title|spec_link|today|path)\}\}", lambda m: values[m.group(1)], text), encoding="utf-8")
    return logical


def problems_line(count: int, where: str) -> str:
    return f"{count} problem(s); fix them in {where}"


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def open_page(path: Path) -> str:
    try:
        opened = webbrowser.open(file_url(path))
    except webbrowser.Error:
        opened = False
    return "opened it in your browser" if opened else "no browser opened here: open the address above"


def main(argv: list[str] | None = None) -> int:
    return int(_sibling("prototype_cli").run(_self(), argv))


if __name__ == "__main__":
    BUILD = f"python3 {Path(__file__).as_posix()} build"
    raise SystemExit(main())
