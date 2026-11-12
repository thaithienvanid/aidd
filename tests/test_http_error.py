"""A failed request shows people a URL without the secrets it can carry."""

from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd.kernel import http


class HttpErrorRedactionTest(unittest.TestCase):
    def test_userinfo_query_and_fragment_are_not_shown(self):
        for status in (404, 0):
            with self.subTest(status=status):
                err = http.HttpError(status, "https://user:pass@example.com:8443/a/b?token=x&k=v#frag-secret", "boom")
                self.assertEqual(err.url, "https://example.com:8443/a/b")
                for secret in ("user", "pass", "token", "x&k", "frag-secret"):
                    self.assertNotIn(secret, str(err))
                self.assertIn("https://example.com:8443/a/b", str(err))

    def test_a_plain_url_and_a_bare_host_are_unchanged(self):
        self.assertEqual(http.HttpError(500, "https://example.com/p", "x").url, "https://example.com/p")
        self.assertEqual(http.HttpError(0, "example.com", "x").url, "example.com")

    def test_an_unparseable_url_is_not_echoed(self):
        err = http.HttpError(0, "https://[secret@/x", "x")
        self.assertNotIn("secret", str(err))


if __name__ == "__main__":
    unittest.main()
