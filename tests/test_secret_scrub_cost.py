"""The secret scrub reads a run of repeated keys in time linear in its length. The invariant: `secret_patterns.scrubbed` reads each
character of a value once, so `password=password=...` costs its length and not its square, and the text it gives is the text the
scrub gave before it read once (the table below holds each case's SHA-256 from that earlier code, over the cases the repository's
tests and the audit used). The cost is counted in reads, never timed: no assertion here depends on the machine's speed.

Secret-shaped values are joined from pieces here, so no literal of one sits in the repository."""

from __future__ import annotations

import hashlib
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on the path)

from aidd.kernel import secret_patterns

# A run of keys with no value, joined here so that no line of this file reads as a key with a value to a secret scanner.
MIXED_KEYS = "password=" + "token:" + "api_key=" + "A_SECRET="

# A recipe is a list of pieces: a string, or (string, count) for the string repeated.
Recipe = list[str | tuple[str, int]]
# (what the case is, its recipe, the SHA-256 of what `scrubbed` gave for it before it read each character once)
TABLE: list[tuple[str, Recipe, str]] = [
    ("no secret", ["Implement: aidd test --changed"], "f07371bcdf956a72f175feb7a1329be34e8058da9f884661627795e61f041af9"),
    ("empty", [""], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("a token", ["gh", "p_", ("a1b2c3d4e5", 3), "a1b2c3", " and more"], "df1a5a073c117e710f1e7513b72b2a51b65a6e05676f86fc0507727b9750b2ad"),
    (
        "a password in a URL",
        ["git push https://u:", "hunter", "2pass", "@example.com/r.git"],
        "6f26bf45d2b0808a04210cfb7a391ed7a3de61846117b57b7100b40a6e7d824c",
    ),
    ("a URL password past the 200 cap", ["https://u:", ("x", 250), "@h"], "c1a54dfd4a1ee495076a6015d216b21087764b564454b98708cf665db08ac89f"),
    ("a credential assignment", ["pass", "word=", "hunter", "2pass"], "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992"),
    ("a credential value of 199", ["pass", "word=", ("x", 199), " tail"], "8ab780e029f04c450109b39036173c45e8e56ac24a5f4c8e7937cb6d1c24bd3c"),
    ("a credential value of 200", ["pass", "word=", ("x", 200), " tail"], "8ab780e029f04c450109b39036173c45e8e56ac24a5f4c8e7937cb6d1c24bd3c"),
    ("a credential value of 201", ["pass", "word=", ("x", 201), " tail"], "8ab780e029f04c450109b39036173c45e8e56ac24a5f4c8e7937cb6d1c24bd3c"),
    ("a credential value past the cap", ["pass", "word=", ("x", 5000), " tail"], "8ab780e029f04c450109b39036173c45e8e56ac24a5f4c8e7937cb6d1c24bd3c"),
    ("a credential in quotes", ["pass", 'word="', "hunter", '2pass" and "x"'], "f0ba4674d75a2bf214a6f9245b040a1fad06bd476e220f0895f04cd7f79f2419"),
    (
        "a credential whose value is a variable",
        ["pass", "word=$", "HOME and ", "pass", "word=<", "x>"],
        "a088decd251db2eb428cc360eff986e2546dcea3d56fc0bd1d9953040c12cb4d",
    ),
    ("a short value", ["pass", "word=abc"], "3b24d522735738d020cd8dcb956301131a85f9d063419721f2d802458f8627cb"),
    ("a secret assignment", ["API_SE", "CRET=", "hunter", "2pass", " tail"], "bf4fe414be1e2b0625cb1420648dc0eae5ec487b31bf6ce34376807130f2782b"),
    ("a secret assignment past the cap", ["API_SE", "CRET=", ("x", 300), " tail"], "bf4fe414be1e2b0625cb1420648dc0eae5ec487b31bf6ce34376807130f2782b"),
    ("a bearer token", ["Authorization: Bear", "er ", ("abcd1234", 4), "== tail"], "ec7c4fee17b0ed5cb581274913948e6eb197eebb92cb30eebee4d69a0fd7a759"),
    ("a mysql password", ["mysql -h db -u root -p", "hunter", "2pass", " mydb"], "152a98e2309ab94c41fb258566bc19a11ab227ee3d66b4090b24f1a47ba2fa48"),
    (
        "two secrets on a line",
        ["pass", "word=", "hunter", "2pass", " and gh", "p_", ("a1b2c3d4e5", 3), "a1b2c3"],
        "fdeaa31a7842e3b2d978a456204ded376870aec8eb5ce8a75906caa2a13b18f3",
    ),
    (
        "a private key block",
        ["x -----BEGIN RSA PRI", "VATE KEY-----\n", ("MIIabc", 20), "\n-----END RSA PRI", "VATE KEY----- y"],
        "1d121f5ccfa305f2be6a0b66f3ce6aa3823090db55232c2235ec4818b226bcbd",
    ),
    ("a private key block with no end", ["-----BEGIN PRI", "VATE KEY-----", ("abc", 50)], "3a2d1afa44d101200100d332f52384e523e7e881b7db0008da228cd94cebdfe1"),
    ("a fullwidth token", ["ｇｈｐ＿", ("a1b2c3d4e5", 3), "a1b2c3"], "3a2d1afa44d101200100d332f52384e523e7e881b7db0008da228cd94cebdfe1"),
    (
        "a zero-width space in a token",
        ["gh", "p_", ("a1b2c3d4e5", 2), "\u200b", "a1b2c3d4e5", "a1b2c3"],
        "3a2d1afa44d101200100d332f52384e523e7e881b7db0008da228cd94cebdfe1",
    ),
    (
        "a run of credentials, twice",
        [("pass", 1), ("word=", 1), ("pass", 1), "word=", "pass", "word=", ("x", 20)],
        "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992",
    ),
    ("a run of credentials, 3 matches", [("password=", 3), ("x", 8)], "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992"),
    ("a run of credentials, 30 matches", [("password=", 30)], "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992"),
    ("a run of credentials, 300 matches", [("password=", 300)], "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992"),
    (
        "a run of credentials, each value of 205",
        [
            (
                "password=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                40,
            )
        ],
        "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992",
    ),
    ("a run of credentials ending in a space", [("password=", 40), " tail"], "8ab780e029f04c450109b39036173c45e8e56ac24a5f4c8e7937cb6d1c24bd3c"),
    ("a run of credentials split by a quote", [("password=", 20), "'", ("password=", 20)], "f229a32299a0fb7f074946edad223dcf1ee945a7d276ba7843095e7ccf1792c4"),
    ("a run of colons", [("token:", 120)], "1decc01f7091864459f8140032a191edf168ba3db3e3df467a0bc054e737cfce"),
    ("a run of keys", [("api_key=", 120)], "16f7b0752c4a42f0b0a408903703ff911bac1c8762d7d93efe5bba875d529f4b"),
    ("a run of secret assignments", [("A_SECRET=", 120)], "f920ca40fb15e4e8ef6410110efcc3ee147651d078b1d40b46efb93fe5aded25"),
    ("a run of mixed keys", [(MIXED_KEYS, 40)], "d88922ac93332bf101d7a070063d1e8da142d905bbdd9bce6936dfaa36f85992"),
    ("a run of keys inside a URL password", [("https://u:", 3), "pass@h"], "359fe9bb09ad0163b331f09c27867f98ce5a72c6b1f985adaf817feb4dff054a"),
    (
        "a run of credentials after a bearer",
        ["Bear", "er ", ("abcd1234", 4), ("password=", 30)],
        "f455e54c1ee074d577ffb847f37d04deeacfb599c9615d7ab17021daaae8f98b",
    ),
    (
        "a run of long credentials with spaces",
        [
            (
                "password=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx ",
                40,
            )
        ],
        "8b6474dda48775f26ea5b169f5385a82d8341554004679aadfdfe88dd1e97833",
    ),
    ("a key with no value", [("password=", 1)], "a184fed6cfdd97ed2f26ab97ac6d70e76ba6c6fdab5a1df9a557aca8cb971645"),
    ("a key and a space", ["password= ", ("x", 10)], "578a8f65f5d70379c300362d02f3ac55106319bfa5f4babbe90a54caaa286b03"),
    ("a key and a tab", ["password=\t", ("x", 10)], "ed9e2463630f3da071ed611848ff8730d73da7f5579e63cf543e868907b7802b"),
]


def build(recipe: Recipe) -> str:
    return "".join(piece if isinstance(piece, str) else piece[0] * piece[1] for piece in recipe)


def reads(text: str) -> int:
    """How many characters `scrubbed` asks a value predicate about: the work a read-on does, one count for each call."""
    count = 0

    def counting(predicate):
        def read(char: str) -> bool:
            nonlocal count
            count += 1
            return predicate(char)

        return read

    wrapped = {name: counting(predicate) for name, predicate in secret_patterns._VALUE_CHARS.items()}
    with mock.patch.dict(secret_patterns._VALUE_CHARS, wrapped):
        secret_patterns.scrubbed(text)
    return count


# Each repeats a key with no space between, so every match starts inside the value of the one before it.
RUNS = {
    "a credential": "password=",
    "a credential with a colon": "token:",
    "a key": "api_key=",
    "a secret assignment": "A_SECRET=",
    "a run of mixed keys": MIXED_KEYS,
}


class ScrubOutputIsUnchanged(unittest.TestCase):
    def test_each_case_gives_the_text_the_scrub_gave_before(self):
        for label, recipe, digest in TABLE:
            with self.subTest(case=label):
                self.assertEqual(hashlib.sha256(secret_patterns.scrubbed(build(recipe)).encode("utf-8")).hexdigest(), digest)


class ScrubReadsEachCharacterOnce(unittest.TestCase):
    def test_the_reads_grow_with_the_length_and_never_pass_it_for_a_pattern(self):
        patterns = len(secret_patterns._VALUE_CHARS)
        for label, key in RUNS.items():
            small, large = key * 200, key * 800
            with self.subTest(run=label):
                self.assertLessEqual(reads(small), len(small) * patterns, "a character is read once for a pattern at most")
                self.assertLessEqual(reads(large), len(large) * patterns)
                # Each character the text gains costs at most one read for a pattern: the read-on of each match was a square before.
                self.assertLessEqual(reads(large) - reads(small), (len(large) - len(small)) * patterns)

    def test_a_value_is_read_to_its_end_whatever_its_cap(self):
        key = "pass" + "word="
        for length in (1, 8, 199, 200, 201, 5000):
            with self.subTest(length=length):
                text = key + "x" * length
                self.assertEqual(secret_patterns.scrubbed(text), key + secret_patterns.REDACTED if length >= 8 else text)
                self.assertLessEqual(reads(text), length)


if __name__ == "__main__":
    unittest.main()
