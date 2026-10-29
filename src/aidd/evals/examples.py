"""The conformance examples: every examples/<case>/ and each of its mutations, run through the gate and compared with expected.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from aidd import gate, workitems


def load_example(case: Path) -> tuple[dict, dict]:
    ctx = json.loads((case / "context.json").read_text(encoding="utf-8"))
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    cfg_file = ctx.pop("base_config_from", None)
    ctx["base_config"] = (case / cfg_file).read_text(encoding="utf-8") if cfg_file else None
    for repo_path, local in ctx.pop("head_files_from", {}).items():
        ctx["head_files"][repo_path] = (case / local).read_text(encoding="utf-8")
    spec_path = ctx.pop("spec_hash_of", None)
    # The Spec hash at head, where an approved commit's entry says the person read the Spec as it reads now: `{{spec_hash}}`,
    # or for a goal's change each Spec's at `{{spec_hash:<path>}}`.
    hashes = {"{{spec_hash}}": workitems.spec_hash(ctx["head_files"][spec_path], ctx["head_tree"], ctx["head_files"].get)} if isinstance(spec_path, str) else {}
    for path in spec_path if isinstance(spec_path, list) else []:
        hashes[f"{{{{spec_hash:{path}}}}}"] = workitems.spec_hash(ctx["head_files"][path], ctx["head_tree"], ctx["head_files"].get)
    for entry in (ctx.get("approval_commits") or {}).values():
        if entry.get("spec_hash") in hashes:
            entry["spec_hash"] = hashes[entry["spec_hash"]]
        for sid, h in (entry.get("spec_hashes") or {}).items():  # one commit approved for several of a goal's Specs
            entry["spec_hashes"][sid] = hashes.get(h, h)
    for c in ctx["comments"]:
        c["body"] = c["body"].replace("{{head}}", ctx["head_sha"])
    for r in ctx["reviews"]:
        if r.get("commit_sha") == "{{head}}":
            r["commit_sha"] = ctx["head_sha"]
    if ctx.get("evidence") and ctx["evidence"].get("head_sha") == "{{head}}":
        ctx["evidence"]["head_sha"] = ctx["head_sha"]
    return ctx, expected


def _pointer(doc, path: str):
    """The parent container and last key of a JSON pointer (/a/b~1c)."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path.lstrip("/").split("/")]
    node = doc
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    return node, (int(last) if isinstance(node, list) and last.lstrip("-").isdigit() else last)


def apply_ops(ctx: dict, ops: list[dict]) -> dict:
    """Mutation operations, as data, so any reimplementation can replay them:
    set, remove, append (to a list), and replace_text (exactly one occurrence in a string)."""
    for op in ops:
        node, key = _pointer(ctx, op["path"])
        if op["op"] == "set":
            node[key] = op["value"]
        elif op["op"] == "remove":
            del node[key]
        elif op["op"] == "append":
            node[key].append(op["value"])
        elif op["op"] == "replace_text":
            n = node[key].count(op["old"])
            if n != 1:
                raise ValueError(f"replace_text: {op['old']!r} occurs {n} times at {op['path']}; it must occur exactly once")
            node[key] = node[key].replace(op["old"], op["new"], 1)
        else:
            raise ValueError(f"unknown op {op['op']!r}")
    return ctx


EXPECTED_KEYS = ("decision", "failed_rules", "pending_rules", "warn_rules", "findings")


def _compare(d, expected: dict) -> tuple[bool, dict, dict]:
    """Every key is compared: a missing key is a failed case, never a silently narrower one."""
    got = {
        "decision": d.decision,
        "failed_rules": d.rules_at("fail"),
        "pending_rules": d.rules_at("pending"),
        "warn_rules": d.rules_at("warn"),
        "findings": d.codes(),
    }
    want = {k: expected.get(k) for k in EXPECTED_KEYS}
    return all(got[k] == want[k] for k in EXPECTED_KEYS), got, want


def _cases(root: Path, sep: str):
    """(name, context, expected) for every case, then every mutation of it (examples/<case>/mutations/*.json), named
    `<case><sep><mutation>`."""
    for case in sorted(p for p in (root / "examples").iterdir() if (p / "context.json").is_file()):
        ctx, expected = load_example(case)
        yield case.name, ctx, expected
        for mfile in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
            m = json.loads(mfile.read_text(encoding="utf-8"))
            yield f"{case.name}{sep}{mfile.stem}", apply_ops(copy.deepcopy(ctx), m["ops"]), m["expected"]


def run_examples(root: Path) -> list[dict]:
    results = []
    for name, ctx, expected in _cases(root, "/"):
        ok, got, want = _compare(gate.decide(ctx), expected)
        results.append({"case": name, "ok": ok, "got": got, "want": want})
    return results


def materialize(root: Path, out: Path) -> int:
    """Write every case and mutation as `<name>/context.json` (resolved) and `<name>/expected.json`.

    A resolved context needs no loader: shared configs, Spec files, hashes, and mutations are all
    applied. Another implementation of the gate runs these and compares its decision and codes.
    """
    n = 0
    for name, ctx, expected in _cases(root, "--"):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "context.json").write_text(json.dumps(ctx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (d / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n += 1
    return n
