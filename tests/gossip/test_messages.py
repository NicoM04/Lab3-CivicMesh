"""Tests unitarios para mensajes y payloads de Gossip."""

import unittest
from dataclasses import FrozenInstanceError

from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo, PeerStatus


def make_peer(peer_id: str, port: int = 9000) -> PeerInfo:
    return PeerInfo(
        peer_id=peer_id,
        host="127.0.0.1",
        port=port,
        status=PeerStatus.ALIVE,
        last_seen=100.0,
        subscribed_topics=frozenset(["santiago"]),
    )


class TestGossipMessages(unittest.TestCase):
    def test_gossip_payload_creation_and_sender_id(self) -> None:
        sender = make_peer("peer-1", 9001)
        peer_b = make_peer("peer-2", 9002)
        payload = GossipPayload.create(sender=sender, peers=[peer_b], sent_at=150.0)

        self.assertEqual(payload.sender_id, "peer-1")
        self.assertEqual(payload.sender, sender)
        self.assertEqual(payload.peers, (peer_b,))
        self.assertEqual(payload.sent_at, 150.0)

    def test_gossip_payload_is_frozen(self) -> None:
        sender = make_peer("peer-1", 9001)
        payload = GossipPayload(sender=sender, peers=(), sent_at=10.0)

        with self.assertRaises(FrozenInstanceError):
            payload.sent_at = 20.0  # type: ignore

    def test_gossip_payload_serialization_roundtrip(self) -> None:
        sender = make_peer("peer-1", 9001)
        peers = [make_peer("peer-2", 9002), make_peer("peer-3", 9003)]
        original = GossipPayload.create(sender=sender, peers=peers, sent_at=12345.67)

        data = original.to_dict()
        self.assertIn("sender", data)
        self.assertIn("peers", data)
        self.assertEqual(data["sent_at"], 12345.67)

        reconstructed = GossipPayload.from_dict(data)
        self.assertEqual(reconstructed.sender, original.sender)
        self.assertEqual(reconstructed.peers, original.peers)
        self.assertEqual(reconstructed.sent_at, original.sent_at)
        self.assertEqual(reconstructed.sender_id, "peer-1")


if __name__ == "__main__":
    unittest.main()
