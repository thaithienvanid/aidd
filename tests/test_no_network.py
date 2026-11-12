"""No unit test reaches the network. tests/helpers.py, which every test module imports first, blocks a name lookup
or a connection to any host that is not this machine, records it, and fails the run. A test of a fetch mocks the
fetcher or serves the answer from a local server."""

import socket
import unittest
from unittest import mock

import helpers


class NetworkGuardTests(unittest.TestCase):
    def test_a_lookup_or_a_connection_to_another_host_is_refused_and_recorded(self):
        with mock.patch.object(helpers, "NETWORK_USES", []) as seen:
            with self.assertRaises(helpers.NetworkUsed):
                socket.getaddrinfo("example.invalid", 443)
            # 192.0.2.0/24 is reserved for documentation, so even a broken guard reaches no one.
            with self.assertRaises(helpers.NetworkUsed), socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("192.0.2.1", 443))
            with self.assertRaises(helpers.NetworkUsed):
                socket.create_connection(("192.0.2.1", 443), timeout=1)
            self.assertTrue(socket.getaddrinfo("10.0.0.1", 80))  # a numeric lookup sends nothing; an SSRF check makes it
        self.assertEqual(len(seen), 3, seen)
        self.assertIn("example.invalid", seen[0])

    def test_this_machine_is_allowed(self):
        with mock.patch.object(helpers, "NETWORK_USES", []) as seen:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.bind(("127.0.0.1", 0))
                server.listen(1)
                port = server.getsockname()[1]
                with socket.create_connection(("localhost", port), timeout=5):
                    pass
            self.assertTrue(socket.getaddrinfo("127.0.0.1", 80))
        self.assertEqual(seen, [])

    def test_the_guard_is_not_an_os_error(self):
        # Code that treats an OSError as "unreachable" must not hide a test that reached the network.
        self.assertFalse(issubclass(helpers.NetworkUsed, OSError))


if __name__ == "__main__":
    unittest.main()
