"""Where an Intent lives: `<product_dir>/intents/INTENT-n.md`, with `INTENT-n/` beside it for its evidence and decision cards.
The folder is the `intent` row of schemas/item-types.json, and this module is the one place that turns it into a path. Every
reader and writer of an Intent's place goes through it: `aidd new intent`, the folders the work walk reads, the slice lookup,
the approval lookup across a move a person makes, and the readers of a commit.

An Intent outside that folder is read by the work walk, so no Intent goes unread, and `aidd validate` reports it with the `git mv`
that moves it. aidd moves no Intent itself."""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.kernel import git, globs, regular_files

# The most earlier names of one file the history is asked for: a file renamed more often than this has a person's attention already.
MAX_FORMER_NAMES = 20


def in_product_dir(path: str, product_dir: str) -> str:
    """A path of the registry (schemas/item-types.json) with `{product}` replaced by the config's `product_dir`, in the one form git
    prints paths in. The one place that replaces `{product}`."""
    return globs.normal_dir(path.replace("{product}", product_dir))


def intents_folder(product_dir: str) -> str:
    """The folder that holds every Intent file, `product/intents` for the default `product_dir`."""
    return in_product_dir(config.item_type_rows()["intent"]["folder"], product_dir)


def product_file(item_type: str, product_dir: str) -> str:
    """The one file of the product scope's type `item_type` (`brd`, `prd`, `standing-outcomes`, or `intent-order`): the path its row's
    `files` gives, such as `product/brd.md`. The one function that says where each of these files is."""
    return in_product_dir(config.item_type_rows()[item_type]["files"][0]["path"], product_dir)


def intent_file(product_dir: str, intent_id: str) -> str:
    """The Intent `intent_id`'s file, such as `product/intents/INTENT-3.md`."""
    return f"{intents_folder(product_dir)}/{intent_id}.md"


def former_intent_names(root: Path, rel: str, tip: str = "HEAD") -> list[str]:
    """Every other name the file `rel` had in the history of `tip`, newest first, from git's own record of renames (`git log --follow`):
    the places an Intent lay in before a person moved it, whatever the folder it was in or the name it had. Empty when git cannot say, such
    as outside a repository, and in a shallow clone only what the clone holds, so a lookup that needs more fails closed."""
    out = git.run(["log", "--follow", "--name-only", "-z", "--format=", tip, "--", rel], str(root), check=False)
    names = (n for n in out.split("\0") if n and n != rel and not regular_files.is_outside(n))
    return list(dict.fromkeys(names))[:MAX_FORMER_NAMES]


def work_folders(specs_dir: str, product_dir: str) -> tuple[str, ...]:
    """The folders that hold Specs and Intents, in the order a walk reads them: the specs folder, then the Intents' folder. The walk
    reads an Intent a person left in the specs folder too, so it is reported (`in_intents_folder`) and never lost. The Intents' folder
    is left out when the specs folder holds it, so no file is read twice."""
    specs, intents = globs.normal_dir(specs_dir), intents_folder(product_dir)
    return (specs,) if intents == specs or intents.startswith(specs + "/") else (specs, intents)


def in_intents_folder(rel: str, product_dir: str) -> bool:
    """Whether the Intent file `rel` lies in the Intents' folder, the one place an Intent lives."""
    return rel.startswith(intents_folder(product_dir) + "/")
