import unittest

from civicmesh.gossip.config import GossipConfig
from civicmesh.gossip.interfaces import PeerDirectory
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.node import Node
from civicmesh.gossip.peer import PeerInfo


def make_peer(peer_id: str, port: int = 9000, last_seen: float = 0.0) -> PeerInfo:
    return PeerInfo(peer_id=peer_id, host="127.0.0.1", port=port, last_seen=last_seen)


class JoinTests(unittest.TestCase):
    def test_join_registers_single_seed_peer(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        node.join(make_peer("seed"), now=1.0)

        self.assertEqual([p.peer_id for p in node.get_known_peers()], ["seed"])

    def test_join_registers_multiple_seed_peers(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        node.join([make_peer("seed-a"), make_peer("seed-b")], now=1.0)

        known_ids = {p.peer_id for p in node.get_known_peers()}
        self.assertEqual(known_ids, {"seed-a", "seed-b"})

    def test_join_rejects_self_as_seed(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        with self.assertRaises(ValueError):
            node.join(make_peer("self"), now=1.0)

    def test_join_rejects_empty_seed_list(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        with self.assertRaises(ValueError):
            node.join([], now=1.0)

    def test_join_response_merges_full_view_from_seed(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)
        node.join(make_peer("seed"), now=1.0)

        response = GossipPayload.create(
            sender=make_peer("seed", last_seen=1.0),
            peers=[make_peer("peer-b", last_seen=1.0)],
            sent_at=1.0,
        )
        node.handle_join_response(response, now=1.0)

        known_ids = {p.peer_id for p in node.get_known_peers()}
        self.assertEqual(known_ids, {"seed", "peer-b"})


class JoinHandshakeBetweenTwoNodesTests(unittest.TestCase):
    """Ambos lados del JOIN modelados de punta a punta, sin transporte real."""

    def test_seed_learns_about_the_joining_peer(self) -> None:
        seed = Node(self_info=make_peer("seed"), partial_view_size=5, fanout=2)
        newcomer = Node(self_info=make_peer("newcomer"), partial_view_size=5, fanout=2)

        newcomer.join(seed.self_info, now=0.0)
        response = seed.handle_join_request(newcomer.self_info, now=0.0)
        newcomer.handle_join_response(response, now=0.0)

        self.assertIn("newcomer", [p.peer_id for p in seed.get_known_peers()])
        self.assertIn("seed", [p.peer_id for p in newcomer.get_known_peers()])

    def test_joining_peer_learns_seed_existing_view(self) -> None:
        seed = Node(self_info=make_peer("seed"), partial_view_size=5, fanout=2)
        seed.join(make_peer("veteran"), now=0.0)
        newcomer = Node(self_info=make_peer("newcomer"), partial_view_size=5, fanout=2)

        newcomer.join(seed.self_info, now=0.0)
        response = seed.handle_join_request(newcomer.self_info, now=0.0)
        newcomer.handle_join_response(response, now=0.0)

        known_ids = {p.peer_id for p in newcomer.get_known_peers()}
        self.assertEqual(known_ids, {"seed", "veteran"})


class FromConfigTests(unittest.TestCase):
    def test_from_config_uses_configured_fanout_and_view_size(self) -> None:
        config = GossipConfig(fanout=1, partial_view_size=2, rng_seed=7)

        node = Node.from_config(self_info=make_peer("self"), config=config)

        self.assertEqual(node.gossip.fanout, 1)
        self.assertEqual(node.membership.partial_view_size, 2)


class PeerDirectoryInterfaceTests(unittest.TestCase):
    def test_node_satisfies_peer_directory_protocol(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        self.assertIsInstance(node, PeerDirectory)

    def test_get_alive_peers_reflects_timeouts(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)
        node.join(make_peer("seed"), now=0.0)

        node.detect_failed_peers(now=100.0, timeout_seconds=10.0)

        self.assertEqual(node.get_alive_peers(), [])
        self.assertEqual(len(node.get_known_peers()), 1)


class GossipMessageHandlingTests(unittest.TestCase):
    def test_handle_gossip_message_registers_previously_unknown_sender(self) -> None:
        # Antes del fix, un sender nunca visto no podía descubrirse (touch
        # era no-op sobre peers desconocidos). Este test fija el contrato.
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)

        payload = GossipPayload.create(
            sender=PeerInfo(peer_id="stranger", host="10.0.0.9", port=8080),
            peers=[],
            sent_at=1.0,
        )
        node.handle_gossip_message(payload, now=1.0)

        known = node.get_known_peers()
        self.assertEqual([p.peer_id for p in known], ["stranger"])
        self.assertEqual(known[0].address, ("10.0.0.9", 8080))

    def test_handle_gossip_message_touches_sender_and_merges_peers(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)
        node.join(make_peer("peer-a"), now=0.0)
        node.detect_failed_peers(now=100.0, timeout_seconds=10.0)
        self.assertEqual(node.get_alive_peers(), [])

        payload = GossipPayload.create(
            sender=make_peer("peer-a", last_seen=100.0),
            peers=[make_peer("peer-c", last_seen=100.0)],
            sent_at=100.0,
        )
        node.handle_gossip_message(payload, now=100.0)

        alive_ids = {p.peer_id for p in node.get_alive_peers()}
        self.assertEqual(alive_ids, {"peer-a", "peer-c"})


class MetricsTests(unittest.TestCase):
    def test_membership_and_gossip_metrics_are_exposed(self) -> None:
        node = Node(self_info=make_peer("self"), partial_view_size=5, fanout=2)
        node.join([make_peer("peer-a"), make_peer("peer-b")], now=0.0)

        membership_metrics = node.get_membership_metrics()
        gossip_metrics = node.get_gossip_metrics()

        self.assertEqual(membership_metrics.known_peers, 2)
        self.assertEqual(membership_metrics.alive_peers, 2)
        self.assertEqual(gossip_metrics.rounds_run, 0)


if __name__ == "__main__":
    unittest.main()
