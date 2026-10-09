"""Audit fixes for the GitLab adapter: pagination via X-Next-Page and commit signature verification."""

import unittest

from helpers import FakeTransport, ROOT  # noqa: F401  (puts src on sys.path)

from aidd import gitlab, http

API = "https://gitlab.test/api/v4"


class GitLabPaginationTests(unittest.TestCase):
    def test_paginate_follows_x_next_page(self):
        t = FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits?per_page=100&page=2": ({}, [{"id": "2"}]),
                f"{API}/projects/7/merge_requests/1/commits?per_page=100": ({"x-next-page": "2"}, [{"id": "1"}]),
            }
        )
        items = gitlab.Client("t", API, transport=t).paginate("/projects/7/merge_requests/1/commits")
        self.assertEqual([i["id"] for i in items], ["1", "2"])

    def test_paginate_strict_raises_past_limit(self):
        t = FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits?per_page=100&page=3": ({}, [{"id": "3"}]),
                f"{API}/projects/7/merge_requests/1/commits?per_page=100&page=2": ({"x-next-page": "3"}, [{"id": "2"}]),
                f"{API}/projects/7/merge_requests/1/commits?per_page=100": ({"x-next-page": "2"}, [{"id": "1"}]),
            }
        )
        with self.assertRaises(http.PageLimitError):
            gitlab.Client("t", API, transport=t).paginate("/projects/7/merge_requests/1/commits", limit=2, strict=True)

    def test_commits_truncated_fails_loud(self):
        t = FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits?per_page=100&page=3": ({}, [{"id": "3"}]),
                f"{API}/projects/7/merge_requests/1/commits?per_page=100&page=2": ({"x-next-page": "3"}, [{"id": "2"}]),
                f"{API}/projects/7/merge_requests/1/commits?per_page=100": ({"x-next-page": "2"}, [{"id": "1"}]),
            }
        )
        commits, truncated = gitlab._commits(gitlab.Client("t", API, transport=t), "7", 1, limit=2)
        self.assertTrue(truncated)
        self.assertEqual(commits, [])

    def test_commits_record_signature_verification(self):
        t = FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits?per_page=100": (
                    {},
                    [
                        {"id": "a", "author_email": "a@x.com", "committer_email": "a@x.com", "message": "m"},
                    ],
                ),
                f"{API}/projects/7/repository/commits/a/signature": ({}, {"verification_status": "verified"}),
            }
        )
        commits, truncated = gitlab._commits(gitlab.Client("t", API, transport=t), "7", 1, signatures=True)
        self.assertFalse(truncated)
        self.assertTrue(commits[0]["verified"])

    def test_commit_verification_returns_false_when_unsigned(self):
        t = FakeTransport({})
        self.assertFalse(gitlab._commit_verified(gitlab.Client("t", API, transport=t), "7", "z"))


if __name__ == "__main__":
    unittest.main()
