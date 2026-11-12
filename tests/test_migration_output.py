"""What `aidd upgrade` prints about the values it moves: no credential the file holds. The scrub that hides a credential is the one the
records share (`secret_patterns`), and `migrating.words` applies it to every line. The lines of a real run, with a cut row made for the
test, are in tests/test_upgrade_engine_edges.py.
"""

import time
import unittest

import helpers  # noqa: F401  (puts src on sys.path)

from aidd.kernel import secret_patterns
from aidd.setup import migrating

TOKEN = "ghp_" + "a1B2" * 9


class TheScrubHidesWhatTheDetectorFinds(unittest.TestCase):
    """`scrubbed` shares the detector's patterns, so a line the records would refuse is a line it hides."""

    SAMPLES = (
        "AKIA" + "ABCDEFGHIJKLMNOP",  # joined here, so no key-shaped literal sits in the repository
        "sk_live_" + "a1B2" * 6,
        TOKEN,
        "glpat-" + "a1B2" * 6,
        "xoxb-1234567890-abcdef",
        "sk-ant-" + "a1B2" * 6,
        "AIza" + "a1B2" * 8 + "abc",
        "npm_" + "a1B2" * 9,
        "eyJ" + "a1B2" * 4 + ".eyJ" + "a1B2" * 4 + "." + "a1B2" * 4,
        f"-----BEGIN RSA PRIVATE KEY-----\n{'AAAA' * 8}\n-----END RSA PRIVATE KEY-----",
        "DB_SECRET=hunter2hunter2",
        "https://user:pa55word@host.example.com/x",
        "password: hunter2hunter2",
        "Authorization: Bearer " + "a1B2" * 6,
        "mysql -u root -pSuperSecret1",
        "ｇｈｐ＿" + "a1B2" * 9,
        "gh​p_" + "a1B2" * 9,
    )
    UNCHANGED = ("", "acme/shop", "a: b", "https://example.com/x", "password: ${DB_PASSWORD}", "token: <set me>")

    def test_a_detected_secret_is_hidden_once_and_a_line_with_none_is_kept(self):
        for text in self.SAMPLES:
            with self.subTest(text[:24]):
                self.assertTrue(secret_patterns.secret_types(text, loose=True), "the sample is a secret")
                hidden = secret_patterns.scrubbed(text)
                self.assertEqual(secret_patterns.secret_types(hidden, loose=True), [])
                self.assertIn(secret_patterns.REDACTED, hidden)
                self.assertEqual(secret_patterns.scrubbed(hidden), hidden, "hiding twice changes nothing")
        for text in self.UNCHANGED:
            with self.subTest(text):
                self.assertEqual(secret_patterns.scrubbed(text), text)


class TheWholeValueIsHidden(unittest.TestCase):
    """The patterns cap a match to bound their work on hostile text, and the scrub reads on to the end of the value, so no
    character of a value it recognised as a secret is printed, however long the value is."""

    def test_no_tail_survives_whatever_the_length_and_the_key_stays(self):
        keys = [
            ("password: ", "", ""),
            ("DB_SECRET=", "", ""),
            ("api_key = ", "", ""),
            ("Authorization: Bearer ", "", ""),
            ("mysql -u root -p", "", ""),
            ("password: ", '"', '"'),  # followed directly by a quote
            ("password: ", "", " and more words"),
        ]
        for key, before, after in keys:
            for size in (8, 199, 200, 201, 5000):
                with self.subTest(key=key, size=size, quote=before, after=after):
                    value = "Qz" * ((size - 4) // 2) + "TAIL"
                    line = f"{key}{before}{value}{after}"
                    hidden = secret_patterns.scrubbed(line)
                    if size < (16 if "Bearer" in key else 8):  # shorter than the detector's least: no secret to it
                        self.assertEqual(hidden, line)
                        continue
                    self.assertEqual(hidden, f"{key}{before}{secret_patterns.REDACTED}{before and after or after}")
                    self.assertEqual(secret_patterns.secret_types(hidden, loose=True), [])

    def test_a_url_password_of_any_length_is_found_and_hidden_whole(self):
        """The detector finds a password in a URL past its 200-character cap, since it looks for the `@` once from the colon, and the
        scrub hides the whole value, so `aidd upgrade` prints none of it."""
        for size in (8, 199, 200, 201, 5000):
            with self.subTest(size=size):
                value = ("Qz" * size)[: size - 4] + "TAIL"
                self.assertEqual(len(value), size)
                line = f"postgres://app:{value}@db.example.com/shop"
                self.assertEqual(secret_patterns.secret_types(line, loose=True), ["a password in a URL"])
                hidden = secret_patterns.scrubbed(line)
                self.assertEqual(hidden, "postgres://app:<redacted>@db.example.com/shop")
                printed = migrating.words(migrating.Plan(lines=[("manual", f"x: `project.repo` holds {line}")]), yes=False)
                self.assertNotIn("TAIL", printed[0])
                self.assertNotIn("Qz", printed[0])

    def test_a_line_with_no_secret_stays_and_a_megabyte_of_it_is_fast(self):
        for text in ("name: acme", "a" * 5000, "password"):
            self.assertEqual(secret_patterns.scrubbed(text), text)
        for text in (
            "x" * 1_000_000,
            "key: value " * 90_000,
            "password: " + "x" * 7 + " " + "-" * 1_000_000,
            "postgres://app:" + "x" * 1_000_000,  # a password that never ends in `@`
        ):
            started = time.monotonic()
            secret_patterns.scrubbed(text)
            self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
