"""Tests unitarios para PeerRuntime."""

import socket
import unittest

from civicmesh.runtime.peer_runtime import PeerRuntime


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestPeerRuntime(unittest.TestCase):
    def test_runtime_initialization_and_properties(self) -> None:
        port = free_port()
        runtime = PeerRuntime(
            peer_id="peer-test",
            host="127.0.0.1",
            port=port,
            gossip_interval=2.0,
            failure_timeout=10.0,
        )

        self.assertEqual(runtime.peer_id, "peer-test")
        self.assertEqual(runtime.self_info.peer_id, "peer-test")
        self.assertEqual(runtime.self_info.port, port)
        self.assertEqual(runtime.gossip_interval, 2.0)
        self.assertEqual(runtime.failure_timeout, 10.0)

    def test_runtime_subscribe_and_topic_state(self) -> None:
        port = free_port()
        runtime = PeerRuntime(
            peer_id="peer-test",
            host="127.0.0.1",
            port=port,
        )
        runtime.subscribe("Santiago", {"objetivo", "subjetivo"}, include_neighbors=True)
        state = runtime.get_topic_state()
        self.assertIsInstance(state, dict)


if __name__ == "__main__":
    unittest.main()
