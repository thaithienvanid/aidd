"""A config's `extends`: its parents, read from the repository or fetched by URL, and the organization's preset."""

from __future__ import annotations

import os
import urllib.parse

from aidd.kernel import documents, egress, http, json_schema


def org_preset_text() -> str | None:
    """An org preset the gate injects as the implicit root parent (AIDD_ORG_PRESET=path)."""
    path = os.environ.get("AIDD_ORG_PRESET")
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


MAX_EXTENDS_DEPTH = 5


def collect_extends(
    text: str, read, fetch=egress.fetch_text, out: dict[str, str] | None = None, depth: int = 0, warnings: list[str] | None = None
) -> dict[str, str]:
    """Every parent config in the extends chain, keyed by path or url. With `read` None (an org preset, which lives
    outside the repository), a parent named by path is not read, with a warning that says why."""
    out = {} if out is None else out
    warnings = [] if warnings is None else warnings
    if depth > MAX_EXTENDS_DEPTH:
        warnings.append(f"extends chain is deeper than {MAX_EXTENDS_DEPTH}; the parents beyond it are not read")
        return out
    try:
        raw = documents.parse_yaml(text, "config")
    except documents.DocumentError:
        return out
    for parent in raw.get("extends", []):
        if not isinstance(parent, dict):
            continue
        errs = json_schema.validate(parent, "config.schema.json#/$defs/extends")
        if errs:
            url = parent.get("url") or parent.get("path") or ""
            parsed = urllib.parse.urlsplit(url) if url else None
            if parsed and parsed.scheme and parsed.scheme.lower() != "https":
                msg = f"extends {url!r}: refused scheme {parsed.scheme!r}"
            else:
                msg = f"extends {url!r}: does not match schema: {'; '.join(errs)}"
            warnings.append(msg)
            continue
        key = parent.get("path") or parent.get("url")
        if not key or key in out:
            continue
        if "path" in parent and read is None:
            warnings.append(f"extends {parent['path']!r}: {ORG_PRESET_BY_URL}")
            continue
        if "url" in parent:
            try:
                egress.check_public_address(*egress.host_and_port(parent["url"]))
            except http.HttpError as exc:
                warnings.append(f"extends {parent['url']!r}: {exc.body}")
                continue
        try:
            t = read(parent["path"]) if "path" in parent else fetch(parent["url"])
        except http.HttpError as exc:
            # Every failure is named, with its cause: the config that needed this parent will not load without it.
            warnings.append(f"extends {parent.get('url', key)!r}: {exc.body if 'refusing' in str(exc) else exc}")
            t = None
        except Exception as exc:
            warnings.append(f"extends {parent.get('url', key)!r}: cannot fetch it: {type(exc).__name__}: {exc}")
            t = None
        if t is not None:
            out[key] = t
            collect_extends(t, read, fetch, out, depth + 1, warnings=warnings)
    return out


# An org preset (AIDD_ORG_PRESET) is injected by the platform team, so a repository must not
# loosen it by adding entries: these keys are locked for it even when the preset does not list them.
# A parent the repository chose itself is covered by the repository's own review of its config.
ORG_PRESET_LOCKS = ("disabled_rules", "rule_exclusions", "scope_exclude_paths")
# An org preset lives outside every repository, so no repository file can be its parent.
ORG_PRESET_BY_URL = "an org preset lives outside the repository, so it names its parents by url only (with a sha256 pin)"
