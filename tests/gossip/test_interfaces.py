"""Tests unitarios para interfaces y protocolos de la capa de Gossip."""

import unittest

from civicmesh.gossip.interfaces import GossipTransport, PeerDirectory
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo, PeerStatus


class DummyPeerDirectory:
    def get_known_peers(self) -> list[PeerInfo]:
        return []

    def get_alive_peers(self) -> list[PeerInfo]:
        return []

    def get_partial_view(self) -> list[PeerInfo]:
        return []


class IncompleteDirectory:
    def get_known_peers(self) -> list[PeerInfo]:
        return []


class DummyGossipTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[PeerInfo, GossipPayload]] = []

    def send(self, target: PeerInfo, payload: GossipPayload) -> None:
        self.sent.append((target, payload))


class TestGossipInterfaces(unittest.TestCase):
    def test_peer_directory_runtime_checkable(self) -> None:
        valid_dir = DummyPeerDirectory()
        self.assertIsInstance(valid_dir, PeerDirectory)

        invalid_dir = IncompleteDirectory()
        self.assertNotIsInstance(invalid_dir, PeerDirectory)

    def test_gossip_transport_contract(self) -> None:
        transport = DummyGossipTransport()
        peer = PeerInfo("p1", "127.0.0.1", 9000, PeerStatus.ALIVE)
        payload = GossipPayload(peer, (), 100.0)

        transport.send(peer, payload)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(transport.sent[0], (peer, payload))


if __name__ == "__main__":
    unittest.main()
