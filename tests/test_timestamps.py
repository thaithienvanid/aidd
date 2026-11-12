"""The one UTC stamp: every record, run, and note that writes a time writes it this way, and the readers take it back."""

from __future__ import annotations

import datetime as dt
import unittest

import helpers  # noqa: F401  (puts src/ on the path)
from aidd.kernel import timestamps


class UtcStamp(unittest.TestCase):
    def test_a_time_is_written_in_utc_to_the_second(self):
        local = dt.timezone(dt.timedelta(hours=7))
        for at, stamp in (
            (dt.datetime(2026, 9, 28, 10, 0, 0, 999, tzinfo=dt.UTC), "2026-09-28T10:00:00Z"),
            (dt.datetime(2026, 9, 28, 17, 0, 5, tzinfo=local), "2026-09-28T10:00:05Z"),
            (dt.datetime(2026, 9, 28, 10, 0, 7), "2026-09-28T10:00:07Z"),  # no zone: already UTC
        ):
            with self.subTest(stamp):
                self.assertEqual(timestamps.utc_stamp(at), stamp)

    def test_with_no_time_it_is_now_and_reads_back(self):
        stamp = timestamps.utc_stamp()
        read = dt.datetime.strptime(stamp, timestamps.UTC_FORMAT).replace(tzinfo=dt.UTC)
        self.assertLess(abs((dt.datetime.now(dt.UTC) - read).total_seconds()), 60)
        self.assertEqual(timestamps.parse_time(stamp), read)


if __name__ == "__main__":
    unittest.main()
