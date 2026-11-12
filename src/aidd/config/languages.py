"""What aidd knows about a language (`schemas/languages.json`): which files are its source, and which manifests name a project in
it. One row for each language, so another language is a row and no code. Each fact is read when first asked, never on import."""

from __future__ import annotations

import functools

from aidd.kernel import resources


@functools.cache
def source_extensions() -> tuple[str, ...]:
    """The extensions of every language's source files, each with its dot, for `str.endswith`."""
    return tuple(ext for row in resources.load_json("languages.json")["languages"].values() for ext in row["extensions"])


@functools.cache
def language_gitignore() -> dict[str, tuple[str, ...]]:
    """Each language id in schemas/languages.json that names `.gitignore` lines, with those lines in row order."""
    return {lang: tuple(row["gitignore"]) for lang, row in resources.load_json("languages.json")["languages"].items() if "gitignore" in row}


@functools.cache
def manifest_languages() -> dict[str, str]:
    """Each language manifest mapped back to its language id in schemas/languages.json."""
    return {manifest: lang for lang, row in resources.load_json("languages.json")["languages"].items() for manifest in row.get("manifests", [])}


@functools.cache
def manifest_names() -> frozenset[str]:
    """The file names of every manifest that names a project: each language's, and those of any language. Detection opens a file
    of one of these names and no other."""
    table = resources.load_json("languages.json")
    return frozenset(name for row in table["languages"].values() for name in row.get("manifests", [])) | frozenset(table["manifests_of_any_language"])
