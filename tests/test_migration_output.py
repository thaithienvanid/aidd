"""What `aidd upgrade` prints about the values it moves: no credential the file holds, and no change that did not happen.

Invariants. (1) No output line holds a credential that a file holds, in a dry run or with `--yes`, and the line still names the key,
the scrubbed value, and where the full value is. (2) A `migrated` line is printed only for a file whose text was written, and the
dry run says `would migrate` for exactly the files the real run then changes.
"""

import os
import re
import time
import unittest

from migration_fixture import CONFIG, FIXTURES, Repo, tree

from aidd.kernel import secret_patterns
from aidd.setup import migrating

TODAY = (FIXTURES / "today" / CONFIG).read_text(encoding="utf-8")
PEM = "-----BEGIN RSA PRIVATE KEY-----\n    MIIabcBODYofTHEkey\n    -----END RSA PRIVATE KEY-----"
TOKEN = "ghp_" + "a1B2" * 9


class CredentialsAreNeverPrinted(Repo):
    shape = "today"

    # (name, the cut keys written under `project:`, the secret text the file holds, whether a line hides one)
    CASES = {
        "a URL with a user and a password": ("  repo: https://user:s3cretPass@example.com/x.git\n", ("s3cretPass",), True),
        "a token-looking value": (f"  repo: {TOKEN}\n", (TOKEN,), True),
        "a value with no secret": ("  repo: acme/shop\n", (), False),
        "a multi-line value": (f"  repo: |\n    {PEM}\n", ("MIIabcBODYofTHEkey",), True),
        "a dev service URL with a password": ('  dev_services:\n    up: [psql, "postgres://app:pa55wordXY@db.example.com/shop"]\n', ("pa55wordXY",), True),
    }

    def test_no_line_holds_a_credential_the_file_holds_and_the_line_still_says_what_it_was(self):
        for name, (project, secrets, hidden) in self.CASES.items():
            for yes in (False, True):
                with self.subTest(name, yes=yes):
                    (self.root / CONFIG).write_text(TODAY.replace("project:\n", f"project:\n{project}", 1), encoding="utf-8")
                    lines = self.upgrade(yes=yes)
                    shown = "\n".join(lines)
                    for secret in secrets:
                        self.assertNotIn(secret, shown, "the output holds the credential")
                    for line in lines:
                        self.assertEqual(secret_patterns.secret_types(line, loose=True), [], line)
                    cut = [line for line in lines if re.search(r"cut project\.(repo|dev_services)", line)]
                    self.assertEqual(len(cut), 1, "the key still shows")
                    self.assertEqual(secret_patterns.REDACTED in cut[0], hidden)
                    self.assertEqual("history in git holds the full value" in cut[0], hidden, "a hidden value says where the full one is")
                    if not hidden:
                        self.assertIn("= acme/shop", cut[0], "a value with no secret prints as it was")


class OnlyWrittenChangesAreNamed(Repo):
    """The pre-upgrade tree, with one file the write guard refuses: a hard link to a file outside the repository."""

    shape = "pre"
    LINKED = "specs/SPEC-2.md"

    def setUp(self):
        super().setUp()
        outside = self.root.parent / "outside-spec.md"
        outside.write_bytes((self.root / self.LINKED).read_bytes())
        (self.root / self.LINKED).unlink()
        os.link(outside, self.root / self.LINKED)
        self.addCleanup(outside.unlink)

    def test_a_file_the_guard_refused_has_no_migrated_line_and_the_dry_run_says_the_same(self):
        before = tree(self.root)
        dry = self.upgrade()
        self.assertEqual(tree(self.root), before, "a dry run writes nothing")
        real = self.upgrade(yes=True)
        after = tree(self.root)
        changed = {rel for rel in after if after[rel] != before.get(rel)}

        def files(lines: list[str], verb: str) -> set[str]:
            return {m.group(1) for line in lines if (m := re.match(rf"{verb}\s+(\S+?):", line))}

        self.assertIn(self.LINKED, "\n".join(real), "the refused file is still named")
        self.assertTrue(any(line.startswith("manual") and self.LINKED in line and "not changed" in line for line in real))
        self.assertNotIn(self.LINKED, files(real, "migrated"))
        self.assertNotIn(self.LINKED, changed)
        self.assertEqual(files(real, "migrated"), files(dry, "would migrate"), "the dry run says would for exactly what the real run does")
        self.assertTrue(files(real, "migrated") <= changed)
        self.assertTrue(files(real, "migrated"), "the files the guard allowed are still migrated")


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
