"""Reusable component partials (`components/<name>.html`) expanded at build time for product prototypes."""

from __future__ import annotations

import base64
import html
import json
import re
import stat
from collections.abc import Callable
from pathlib import Path

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_USES = 500
MAX_EXPANSION_BYTES = 2_000_000
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}
MAX_IMAGE_BYTES = 2_000_000
MAX_IMAGES_BYTES = 20_000_000
DATA_IMAGE = re.compile(r"data:image/(?:png|jpeg|gif|webp|avif|svg\+xml);base64,[A-Za-z0-9+/]+={0,2}")
_USE_OPEN = re.compile(r"<!--\s*aidd:use\b")
_USE_COMMENT = re.compile(r"<!--\s*aidd:use\b(.*?)-->", re.S)
_USE_HEAD = re.compile(r"^\s*([a-z0-9-]+)((?:\s+[a-zA-Z_][a-zA-Z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'<>]+))*)\s*$", re.S)
_ATTR = re.compile(r"([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'<>]+))")
_PARAM = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_-]*)\}\}")
_SECTION = re.compile(r"<section\b", re.I)


def _read_component(folder: Path, name: str, caller: str, line_no: int, problems: list[str]) -> str | None:
    if not KEBAB.match(name):
        problems.append(f"{caller}:{line_no}: component include `{name}` must use lowercase words joined by hyphens")
        return None
    comp_dir = folder / "components"
    path = comp_dir / f"{name}.html"
    if comp_dir.is_symlink() or path.is_symlink():
        problems.append(f"components/{name}.html cannot be a symlink; keep component files inside components/")
        return None
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(folder.resolve()):
            problems.append(f"components/{name}.html must stay inside components/")
            return None
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            problems.append(f"components/{name}.html is not a plain file")
            return None
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(f"{caller}:{line_no}: components/{name}.html does not exist; create it or remove <!-- aidd:use {name} -->")
        return None
    except (OSError, ValueError) as exc:
        problems.append(f"components/{name}.html cannot be read ({exc}): save it as UTF-8 text")
        return None
    if _SECTION.search(text):
        problems.append(f"components/{name}.html holds a <section>; partials are reusable blocks, so draw screens in flows/")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _substitute(text: str, attrs: dict[str, str], label: str, caller: str, problems: list[str]) -> str:
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in attrs:
            return html.escape(attrs[key], quote=True)
        missing.append(key)
        return ""

    out = _PARAM.sub(repl, text)
    for key in dict.fromkeys(missing):
        problems.append(f"{label}: missing `{key}=...` parameter on <!-- aidd:use --> in {caller} for {{{{{key}}}}}")
    return out


def _iter_chunks(text: str, label: str, problems: list[str]) -> list[tuple[int, str]]:
    """Group lines, coalescing multi-line `<!-- aidd:use ... -->` directives under their opening line number."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks: list[tuple[int, str]] = []
    idx = 0
    while idx < len(lines):
        start_line = idx + 1
        chunk = lines[idx]
        if (opened := _USE_OPEN.search(chunk)) and "-->" not in chunk[opened.start() :]:
            while idx + 1 < len(lines) and "-->" not in chunk[opened.start() :]:
                idx += 1
                chunk += "\n" + lines[idx]
            if "-->" not in chunk[opened.start() :]:
                problems.append(f"{label}:{start_line}: unclosed <!-- aidd:use directive; close it with -->")
        chunks.append((start_line, chunk))
        idx += 1
    return chunks


def _emit_expanded(
    prefix: str, suffix: str, comp_lines: list[str], comp_owners: list[tuple[str, int]], lines_out: list[str], owners_out: list[tuple[str, int]]
) -> None:
    if len(comp_lines) == 1:
        lines_out.append(prefix + comp_lines[0] + suffix)
        owners_out.append(comp_owners[0])
        return
    lines_out.append(prefix + comp_lines[0])
    owners_out.append(comp_owners[0])
    for mid, own in zip(comp_lines[1:-1], comp_owners[1:-1], strict=True):
        lines_out.append(mid)
        owners_out.append(own)
    lines_out.append(comp_lines[-1] + suffix)
    owners_out.append(comp_owners[-1])


def _expand_text(
    folder: Path,
    label: str,
    text: str,
    problems: list[str],
    partials: dict[str, str],
    stack: tuple[str, ...],
    budget: list[int],
) -> tuple[str, list[tuple[str, int]]]:
    """Expand `<!-- aidd:use ... -->` directives in `text` and return `(expanded, per_line_owners)`."""
    lines_out: list[str] = []
    owners_out: list[tuple[str, int]] = []
    for line_no, raw_chunk in _iter_chunks(text, label, problems):
        match = _USE_COMMENT.search(raw_chunk)
        if not match or _USE_COMMENT.search(raw_chunk, match.end()):
            if match:
                problems.append(f"{label}:{line_no}: put each <!-- aidd:use ... --> directive on its own line")
            lines_out.append(raw_chunk)
            owners_out.append((label, line_no))
            continue
        parsed = _USE_HEAD.match(match.group(1))
        if not parsed:
            problems.append(f"{label}:{line_no}: malformed component include; write <!-- aidd:use <name> key=value -->")
            lines_out.append(raw_chunk)
            owners_out.append((label, line_no))
            continue
        name = parsed.group(1)
        if name in stack:
            problems.append(f"{label}:{line_no}: component include `{name}` loops back to itself ({' -> '.join([*stack, name])})")
            lines_out.append("")
            owners_out.append((label, line_no))
            continue
        budget[0] += 1
        if budget[0] > MAX_USES:
            problems.append(f"{label}:{line_no}: too many component includes (limit {MAX_USES}); simplify nested includes")
            break
        raw_comp = partials.get(f"components/{name}.html")
        if raw_comp is None:
            raw_comp = _read_component(folder, name, label, line_no, problems)
            if raw_comp is None:
                lines_out.append("")
                owners_out.append((label, line_no))
                continue
            partials[f"components/{name}.html"] = raw_comp
        attrs = {m.group(1): html.unescape(next(v for v in m.groups()[1:] if v is not None)) for m in _ATTR.finditer(parsed.group(2))}
        filled = _substitute(raw_comp.rstrip("\r\n"), attrs, f"components/{name}.html", f"{label}:{line_no}", problems)
        expanded_comp, comp_owners = _expand_text(folder, f"components/{name}.html", filled, problems, partials, (*stack, name), budget)
        budget[1] += len(expanded_comp)
        if budget[1] > MAX_EXPANSION_BYTES:
            problems.append(f"{label}:{line_no}: expanded component markup exceeds {MAX_EXPANSION_BYTES} bytes")
            break
        prefix, suffix = raw_chunk[: match.start()], raw_chunk[match.end() :]
        _emit_expanded(prefix, suffix, expanded_comp.split("\n"), comp_owners, lines_out, owners_out)
    return "\n".join(lines_out), owners_out


def expand_flow(folder: Path, flow_id: str, text: str, problems: list[str], partials: dict[str, str]) -> tuple[str, list[tuple[str, int]]]:
    """Expand component includes in one flow file and return `(expanded_text, per_line_owners)`."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    label = f"flows/{flow_id}.html"
    if not _USE_OPEN.search(normalized):
        return normalized, [(label, n) for n in range(1, normalized.count("\n") + 2)]
    return _expand_text(folder, label, normalized, problems, partials, (f"flow:{flow_id}",), [0, 0])


def _image_uri(folder: Path, rel: str, budget: list[int], quoted: Callable[[str], str]) -> tuple[str, str]:
    clean = rel.replace("\\", "/")
    root = folder.resolve()
    path = (root / clean).resolve()
    if clean.startswith("/") or re.match(r"^[A-Za-z]:", clean) or ".." in clean.split("/") or not path.is_relative_to(root):
        return "", f"names `{quoted(rel)}`, which is outside the design's folder: put the image beside the design, or under it"
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime is None:
        return "", f"names `{quoted(rel)}`, which is no image file: use {', '.join(sorted(IMAGE_TYPES))}, or a data:image URI"
    try:
        info = path.stat()
    except OSError:
        return "", f"names `{quoted(rel)}`, which is no file in the design's folder"
    if not stat.S_ISREG(info.st_mode):
        return "", f"names `{quoted(rel)}`, which is no file in the design's folder"
    if info.st_size > MAX_IMAGE_BYTES or info.st_size > budget[0]:
        return (
            "",
            f"names `{quoted(rel)}`, larger than the {MAX_IMAGE_BYTES // 1_000_000} MB an image, or the {MAX_IMAGES_BYTES // 1_000_000} MB a page, may take",
        )
    data = path.read_bytes()[: MAX_IMAGE_BYTES + 1]
    budget[0] -= len(data)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", ""


def _fixture_holder(node: dict, key: str) -> tuple[dict, str] | None:
    if key in node and key not in ("__proto__", "constructor", "prototype"):
        return node, key
    parts = key.split(".")
    if any(p in ("__proto__", "constructor", "prototype") for p in parts):
        return None
    cur: object = node
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, dict) else None
    return (cur, parts[-1]) if isinstance(cur, dict) and parts[-1] in cur else None


def _rewrite_image_field(holder: dict, leaf: str, where: str, folder: Path, budget: list[int], problems: list[str], quoted: Callable[[str], str]) -> None:
    val = holder.get(leaf)
    if val is None or val == "":
        return
    if isinstance(val, str) and val.startswith("data:"):
        if not DATA_IMAGE.fullmatch(val):
            problems.append(f"the fixture {where} is a data URI of no image type: use data:image/<png, jpeg, gif, webp, avif, or svg+xml>;base64,")
            holder[leaf] = ""
        return
    uri, why = _image_uri(folder, val, budget, quoted) if isinstance(val, str) else ("", "is no text: name a file beside the design, or a data:image URI")
    if why:
        problems.append(f"the fixture {where} {why}")
    holder[leaf] = uri


def with_images(fixtures: object, fields: set[str], folder: Path, *, quoted: Callable[[str], str]) -> tuple[object, list[str]]:
    if not fields or not isinstance(fixtures, dict):
        return fixtures, []
    problems: list[str] = []
    budget = [MAX_IMAGES_BYTES]
    out = json.loads(json.dumps(fixtures))
    holders: list[tuple[dict, str]] = [(out, "")]
    stack: list[tuple[dict, str]] = [(out, "")]
    while stack:
        cur, prefix = stack.pop()
        for name, val in sorted(cur.items()):
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(val, dict):
                stack.append((val, path))
            elif isinstance(val, list):
                holders.extend((item, f"{quoted(path)}[{i}].") for i, item in enumerate(val) if isinstance(item, dict))
    for root_holder, prefix in holders:
        for key in sorted(fields):
            if resolved := _fixture_holder(root_holder, key):
                _rewrite_image_field(*resolved, f"`{prefix}{quoted(key)}`", folder, budget, problems, quoted)
    return out, list(dict.fromkeys(problems))
