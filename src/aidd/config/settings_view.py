"""Every setting a config may hold, for `aidd config`: its value in this repository, where that value comes from, and
what it does, read from config.schema.json and the profile, so a person never has to search the docs for a key."""

from __future__ import annotations

import json

from aidd.config import baseline, model
from aidd.kernel import resources

THIS_CONFIG, PARENT, DEFAULT, UNSET = "this config", "a parent config", "the default", "not set"
# The settings people most often change after `aidd init`, which `aidd config` offers when this config does not set
# them: how the gate holds work, the team's goal, who publishes, what is always major, and how many approvals each route needs.
SUGGESTED = ("mode", "goal", "publish", "protected_paths", "risk_rules", "gates.approvals")


def _first_sentence(text: str | None, limit: int = 100) -> str:
    text = " ".join(str(text or "").split())
    end = text.find(". ")
    text = text if end < 0 else text[: end + 1]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def settings(cfg: model.Config, own: dict) -> list[dict]:
    """One row per setting: `key` (`gates.approvals` for a gate), `value` (the effective one), `source` (this config, a
    parent config, the profile, the default, or not set), and `what` (the schema's description) with `allowed` (its
    enum) when it has one. `own` is this repository's file alone, without the parents it extends."""
    schema = resources.load_json("config.schema.json")
    common = resources.load_json("common.schema.json")["$defs"]
    rows: list[dict] = []
    for key, spec in schema["properties"].items():
        ref = str(spec.get("$ref") or "")
        if ref.startswith("urn:aidd:1:common#/$defs/"):
            spec = common.get(ref.rsplit("/", 1)[1], spec)  # a shared definition: its description and its values
        if key in ("gates", "limits"):
            mine = own.get(key)
            effective = cfg.gates if key == "gates" else cfg.limits
            rows += [
                _row(f"{key}.{g}", effective.get(g), _source(effective, key, cfg.profile, mine if isinstance(mine, dict) else {}, g), gs)
                for g, gs in (spec.get("properties") or {}).items()
            ]
            continue
        if key in own:
            value, source = cfg.raw.get(key, own[key]), THIS_CONFIG
        elif key in cfg.raw:
            value, source = cfg.raw[key], PARENT
        elif key == "mode":
            value, source = baseline.profile_mode(cfg.profile), f"profile {cfg.profile}"
        elif "default" in spec:
            value, source = spec["default"], DEFAULT
        elif isinstance(getattr(type(cfg), key, None), property):
            value, source = getattr(cfg, key), DEFAULT  # a default the code owns (`specs_dir`: specs)
        else:
            value, source = None, UNSET
        rows.append(_row(key, value, source, spec))
    return rows


def _source(effective: dict, table: str, profile: str, mine: dict, gate: str) -> str:
    """Where a gate's or a limit's effective value comes from: this config, the profile, or a parent that tightened it.
    A value of this config's own that the effective one differs from was looser, so it is ignored (a config only
    tightens). `table` is `gates` or `limits`, and a profile's limits are its own `limits` mapping."""
    if gate not in effective:
        return UNSET
    value = json.dumps(effective[gate], sort_keys=True)
    defaults = baseline.profiles()["profiles"].get(profile) or {}
    defaults = (defaults.get("limits") or {}) if table == "limits" else defaults
    source = f"profile {profile}" if gate in defaults and json.dumps(defaults[gate], sort_keys=True) == value else PARENT
    if gate not in mine:
        return source
    if json.dumps(mine[gate], sort_keys=True) == value:
        return THIS_CONFIG
    return f"{source}; this config's {shown(mine[gate])} is looser, so it is ignored"


def _row(key: str, value: object, source: str, spec: dict) -> dict:
    row = {"key": key, "value": value, "source": source, "what": " ".join(str(spec.get("description") or "").split())}
    if isinstance(spec.get("enum"), list):
        row["allowed"] = spec["enum"]
    return row


def shown(value: object) -> str:
    """A value in one short cell: a scalar as YAML would write it, a list or a mapping by its size."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return f"[{len(value)} item{'' if len(value) == 1 else 's'}]" if value else "[]"
    if isinstance(value, dict):
        return f"{{{len(value)} key{'' if len(value) == 1 else 's'}}}" if value else "{}"
    text = str(value)
    return text if len(text) <= 28 else text[:27] + "…"


def _set_here(row: dict) -> bool:
    """Whether this config or a parent sets the setting, even where a value of this config's is ignored as looser."""
    return row["source"] == PARENT or THIS_CONFIG in row["source"]


def settings_text(rows: list[dict], key: str | None = None, *, brief: bool = False) -> str:
    """The table `aidd config --all` prints; `brief`, the settings this config or a parent sets and those of SUGGESTED it
    does not, as `aidd config` prints them; with `key`, each setting that starts with it, in full."""
    if key:
        picked = [r for r in rows if r["key"] == key or r["key"].startswith(key + ".")]
        if not picked:
            raise ValueError(f"no setting {key!r}: `aidd config --all` lists them all")
        out = []
        for r in picked:
            out.append(f"{r['key']}: {json.dumps(r['value'], ensure_ascii=False)} (from {r['source']})")
            if r.get("allowed"):
                out.append(f"  allowed: {', '.join(json.dumps(a) for a in r['allowed'])}")
            out.append(f"  {r['what']}" if r["what"] else "  (no description)")
        return "\n".join(out) + "\n"
    if not brief:
        lines = _table(rows, max(len(r["key"]) for r in rows))
        lines += ["", "`aidd config <setting>` shows one in full. Set one in .aidd/config.yaml; the gate reads it from the base branch."]
        return "\n".join(lines) + "\n"
    mine = [r for r in rows if _set_here(r)]
    by_key = {r["key"]: r for r in rows}
    offered = [by_key[k] for k in SUGGESTED if k in by_key and by_key[k] not in mine]
    width = max(len(r["key"]) for r in (*mine, *offered))
    lines = _table(mine, width)
    if offered:
        lines += ["", "You may want to set:", *_table(offered, width)[2:]]
    lines += [
        "",
        "All settings: `aidd config --all`. One in full: `aidd config <setting>`.",
        "Set one in .aidd/config.yaml; the gate reads it from the base branch.",
    ]
    return "\n".join(lines) + "\n"


def _table(rows: list[dict], width: int) -> list[str]:
    """The settings' table: its header, a blank line, and one line for each setting."""
    lines = [f"{'Setting':<{width}}  {'Value':<28}  {'From':<16}  What it does", ""]
    for r in rows:
        lines.append(f"{r['key']:<{width}}  {shown(r['value']):<28}  {r['source']:<16}  {_first_sentence(r['what'])}")
    return lines
