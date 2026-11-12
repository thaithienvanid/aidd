"""The delegate's own answers on record, read once for everything that asks whether the delegate said yes."""

from __future__ import annotations

from aidd import config
from aidd.records import files, sharing


def delegate_answers(cwd: str) -> list[dict]:
    """The `delegate_answer` records this clone wrote under the delegate's own name (`config.DECIDED_BY`), newest first,
    as they were written and only when they are today's shape in full: the writer's own check, so a record with a retired
    name, a field this aidd does not know, or a missing field is none. A pulled record is another's text, and one under
    another name is no delegate's, so neither is here."""
    pulled = sharing.pulled_ids(cwd)
    written = files.read_records(cwd, record_type="delegate_answer", as_written=True)[0]
    return [r for r in written if r.get("id") not in pulled and r.get("by") == config.DECIDED_BY and not files.record_problems(r)]


def delegate_accepts(cwd: str, spec_id: str) -> list[dict]:
    """The delegate's accepts of `spec_id`'s approval, newest first: its answers for the action `spec.approve` with the
    outcome `accept` on that Spec."""
    found = []
    for rec in delegate_answers(cwd):
        data = rec.get("data") or {}
        if data.get("action") == "spec.approve" and data.get("outcome") == "accept" and (data.get("covers") or {}).get("spec") == spec_id:
            found.append(rec)
    return found
