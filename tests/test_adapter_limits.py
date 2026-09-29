"""Inputs the change controls cannot steer the adapters' API calls or exhaust their memory."""

import unittest

from helpers import ROOT, FakeTransport  # noqa: F401  (ROOT puts src on sys.path)

from aidd import github, gitlab, http

API = "https://api.test"


class TeamLookupTests(unittest.TestCase):
    def test_a_team_name_cannot_steer_the_api_path(self):
        t = FakeTransport({f"{API}/orgs/acme/teams/leads/members": ({}, [{"login": "lead"}])})
        got = github._team_members(github.Client("t", API, transport=t), ["@acme/leads", "@acme/../../repos/x", "@acme/a?b=c"])
        self.assertEqual(got, {"@acme/leads": ["lead"]})
        self.assertEqual(len(t.calls), 1)  # the malformed names were never requested

    def test_lookups_are_capped(self):
        t = FakeTransport({f"{API}/orgs/acme/teams/": ({}, [])})
        entries = [f"@acme/t{i}" for i in range(github.MAX_TEAM_LOOKUPS + 25)]
        github._team_members(github.Client("t", API, transport=t), entries)
        self.assertEqual(len(t.calls), github.MAX_TEAM_LOOKUPS)

    def test_a_tenant_qualified_team_is_looked_up_without_its_tenant_and_counts(self):
        from aidd.gates import _Pool

        t = FakeTransport({f"{API}/orgs/org/teams/leads/members": ({}, [{"login": "alice"}])})
        got = github._team_members(github.Client("t", API, transport=t), ["acme:@org/leads"])
        self.assertEqual(got, {"acme:@org/leads": ["alice"]})
        pool = _Pool(["acme:@org/leads"], got, tenant="acme")
        self.assertIn("alice", pool)
        self.assertEqual(pool.unresolved, [])
        self.assertNotIn("alice", _Pool(["globex:@org/leads"], {"globex:@org/leads": ["alice"]}, tenant="acme"))
        g = FakeTransport({f"{API}/groups/org%2Fleads/members/all": ({}, [{"username": "bob"}])})
        self.assertEqual(gitlab._group_members(gitlab.Client("t", API, transport=g), ["acme:@org/leads"]), {"acme:@org/leads": ["bob"]})

    def test_gitlab_group_lookups_are_capped(self):
        t = FakeTransport({f"{API}/groups/": ({}, [])})
        gitlab._group_members(gitlab.Client("t", API, transport=t), [f"@acme/g{i}" for i in range(gitlab.MAX_GROUP_LOOKUPS + 5)])
        self.assertEqual(len(t.calls), gitlab.MAX_GROUP_LOOKUPS)


class DownloadCapTests(unittest.TestCase):
    def test_a_download_is_refused_past_its_cap(self):
        def transport(method, url, auth=None, data=None, headers=None, timeout=30, max_bytes=None):
            body = b"x" * 1000
            if max_bytes is not None and len(body) > max_bytes:
                raise http.HttpError(200, url, f"response exceeded maximum size of {max_bytes} bytes")
            return 200, {}, body

        client = github.Client("t", API, transport=transport)
        self.assertEqual(len(client.download("https://dl.test/a.zip")), 1000)
        with self.assertRaises(http.HttpError):
            client.download("https://dl.test/a.zip", max_bytes=100)


if __name__ == "__main__":
    unittest.main()
