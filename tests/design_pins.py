"""The pins that hold the design's data still: a digest of each case row, of the judged lists, and of each exception.

    python3 tests/design_pins.py            # say what differs from tests/fixtures/design/pins.json
    python3 tests/design_pins.py --write    # make the pins what the data is now, on purpose

An edited row, a dropped variant or findings key, a relabelled exception, or a widened judged list fails
tests/test_design_pins.py until a person runs `--write` and reads the diff of the pins beside the diff of the data. The pins also
name the revision of the design the data was made from: the design has no version, so it is named by its file, its line count,
the day it was read, and the digest of its text.
"""

from __future__ import annotations

import hashlib
import json
import sys

import data_rules as dr
import graph_cases as lc

PINS = dr.FIXTURES / "pins.json"


def digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute() -> dict:
    """The digests of the data as it is now."""
    return {
        "judged": digest(dr.load_json("judged.json")),
        "plain_words": digest(dr.load_json("plain_words.json")),
        "rows": {row["id"]: digest(row) for rows in lc.all_rows().values() for row in rows},
        "exceptions": {f"{e['rule']} {e['where']}": digest(e) for e in dr.load_json("exceptions.json")},
    }


def load() -> dict:
    return json.loads(PINS.read_text(encoding="utf-8"))


def differences(pinned: dict, now: dict) -> list[str]:
    """What differs from the pins: a changed or a new row or exception, a changed judged list, and a row that is gone. An exception
    that is gone is progress, so it is no difference."""
    out = [] if pinned["judged"] == now["judged"] else ["judged.json differs from its pin"]
    out += [] if pinned["plain_words"] == now["plain_words"] else ["plain_words.json differs from its pin"]
    out += [f"row {i} differs from its pin" for i, d in now["rows"].items() if pinned["rows"].get(i) != d]
    out += [f"row {i} is pinned and gone" for i in pinned["rows"] if i not in now["rows"]]
    out += [f"exception {k} is new or differs from its pin" for k, d in now["exceptions"].items() if pinned["exceptions"].get(k) != d]
    return out


def main(argv: list[str]) -> int:
    now = compute()
    if "--write" in argv:
        head = load()["design"]
        PINS.write_text(json.dumps({"design": head, **now}, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {PINS}")
        return 0
    found = differences(load(), now)
    print("\n".join(found) or "the data is what the pins say")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
