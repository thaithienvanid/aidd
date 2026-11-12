"""`aidd new brd`, `prd`, `standing-outcomes`, and `intent-order`: the files of the product scope, written from their templates."""

from __future__ import annotations

import os
from pathlib import Path

from aidd import config
from aidd.kernel import documents, strict_yaml
from aidd.workitems import authoring, intent_paths, product_scope


def new_product_file(root: Path, *, item_type: str, product_dir: str = "product") -> list[Path]:
    """The file of `item_type` from its template, in `product_dir`, never over one. A BRD, a PRD, or the standing outcomes also
    write the intent order when it is missing, so the Intents have a place to be ranked. The standing outcomes stand for a
    product with neither a BRD nor a PRD, so a file of one kind is refused beside the other."""
    names = {t: intent_paths.product_file(t, product_dir) for t in config.types_in("product_scope")}
    beside = ("standing-outcomes",) if item_type in ("brd", "prd") else ("brd", "prd") if item_type == "standing-outcomes" else ()
    if found := next((names[t] for t in beside if (root / names[t]).exists()), None):
        again = "`aidd new standing-outcomes`" if item_type == "standing-outcomes" else "`aidd new brd` or `aidd new prd`"
        raise ValueError(
            f"{found} exists, and standing outcomes stand for a product with neither a BRD nor a PRD, so a product scope holds one or the other. "
            f"Write the items in {found}. To start with the other kind, a person removes {found}, then you run {again} again"
        )
    written = []
    for kind in dict.fromkeys((item_type, product_scope.ORDER)):
        path = root / names[kind]
        if kind != item_type and path.exists():
            continue
        template = (
            intent_order_text(root, [])
            if kind == product_scope.ORDER
            else authoring.template_text(root, kind, config.item_type_rows()[kind]["files"][0]["template"])
        )
        authoring.write_new(path, template, "edit it, then run `aidd validate`: a person approves each change to the product scope", root)
        written.append(path)
    return written


def intent_order_text(root: Path, ids: list[str]) -> str:
    """The intent order's first text: the template of the `intent-order` row (the project's own, when it has one), with `ids` listed
    first to last in `order`. `aidd new` writes it with none. The product
    owner stays a placeholder: a person names who orders the Intents. `order` is set in the front matter, as structure and not as a
    match of text, so a template of any line ending or layout takes it. A template that cannot is a ValueError that names it and what
    it needs."""
    row = config.item_type_rows()["intent-order"]["files"][0]["template"]
    text = authoring.template_text(root, "intent-order", row)
    if not ids:
        return text
    where = f"{authoring.templates_dir(root)}/intent-order.md" if os.path.lexists(root / authoring.templates_dir(root) / "intent-order.md") else f"assets/{row}"
    text = text.lstrip("\ufeff")
    front = documents.FRONT_MATTER.match(text)
    try:
        if front is None:
            raise ValueError("it has no front matter")
        # `order` is emptied where it stands, then listed one id on each line, whatever their number, in the template's own line ending
        head = strict_yaml.append_items(strict_yaml.set_block(front.group(1).replace("\r\n", "\n"), "order", []), "order", ids).rstrip("\n")
        eol = "\r\n" if text.startswith("---\r\n") else "\n"
        result = f"---{eol}{head.replace(chr(10), eol)}{eol}---{eol}{text[front.end() :]}"
        if documents.split_front_matter(result, where)[0].get("order") != ids:
            raise ValueError("`order` did not take the Intents")
    except (ValueError, documents.DocumentError) as exc:
        raise ValueError(
            f"{where} cannot take the {len(ids)} Intents the upgrade orders ({exc}): it needs front matter between `---` lines. "
            "Fix it, or remove it to use aidd's own, then run `aidd upgrade` again. Nothing was changed"
        ) from None
    return result
