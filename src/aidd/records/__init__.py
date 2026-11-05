"""Records: the history of what happened, one immutable file each, such as a person's answer to an ask
(`decision`) or an action the agent reported (`report`).

The children: files (the record types, writing a record after checking it, and reading the records back) and
sharing (pushing and pulling them through the ref `refs/aidd/records`).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "RecordError",
    "add_record",
    "pull_records",
    "pulled_ids",
    "push_records",
    "push_url",
    "read_records",
    "record_problems",
    "record_types",
    "records_dir",
    "written_with_mcp",
]

if TYPE_CHECKING:
    from aidd.records.files import RecordError as RecordError
    from aidd.records.files import add_record as add_record
    from aidd.records.files import read_records as read_records
    from aidd.records.files import record_problems as record_problems
    from aidd.records.files import record_types as record_types
    from aidd.records.files import records_dir as records_dir
    from aidd.records.files import written_with_mcp as written_with_mcp
    from aidd.records.sharing import pull_records as pull_records
    from aidd.records.sharing import pulled_ids as pulled_ids
    from aidd.records.sharing import push_records as push_records
    from aidd.records.sharing import push_url as push_url
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "RecordError": "files",
            "add_record": "files",
            "pull_records": "sharing",
            "pulled_ids": "sharing",
            "push_records": "sharing",
            "push_url": "sharing",
            "read_records": "files",
            "record_problems": "files",
            "record_types": "files",
            "records_dir": "files",
            "written_with_mcp": "files",
        },
    )
