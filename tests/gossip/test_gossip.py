import random
import unittest

from civicmesh.gossip.gossip import GossipService
from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo


def make_peer(peer_id: str, port: int = 9000, last_seen: float = 0.0) -> PeerInfo:
    return PeerInfo(peer_id=peer_id, host="127.0.0.1", port=port, last_seen=last_seen)


def build_service(self_id: str, fanout: int, peer_count: int) -> GossipService:
    table = MembershipTable(self_id=self_id, partial_view_size=max(peer_count, 1))
    for i in range(peer_count):
        table.register_peer(make_peer(f"peer-{i}"), now=0.0)
    self_info = make_peer(self_id, port=9999)
    return GossipService(membership=table, fanout=fanout, self_info=self_info)


class ConstructorValidationTests(unittest.TestCase):
    def test_negative_fanout_is_rejected(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        with self.assertRaises(ValueError):
            GossipService(membership=table, fanout=-1, self_info=make_peer("self"))

    def test_self_info_must_match_membership_self_id(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        with self.assertRaises(ValueError):
            GossipService(membership=table, fanout=2, self_info=make_peer("someone-else"))


class FanoutSelectionTests(unittest.TestCase):
    def test_fanout_zero_selects_no_targets(self) -> None:
        service = build_service(self_id="self", fanout=0, peer_count=5)

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual(targets, [])

    def test_fanout_one_selects_at_most_one(self) -> None:
        service = build_service(self_id="self", fanout=1, peer_count=5)

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual(len(targets), 1)

    def test_fanout_smaller_than_available_peers_selects_exactly_fanout(self) -> None:
        service = build_service(self_id="self", fanout=3, peer_count=10)

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual(len(targets), 3)

    def test_fanout_equal_to_available_peers_selects_all(self) -> None:
        service = build_service(self_id="self", fanout=4, peer_count=4)

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual({t.peer_id for t in targets}, {f"peer-{i}" for i in range(4)})

    def test_fanout_larger_than_available_peers_selects_all_available(self) -> None:
        service = build_service(self_id="self", fanout=10, peer_count=3)

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual(len(targets), 3)

    def test_selected_targets_have_no_duplicates(self) -> None:
        service = build_service(self_id="self", fanout=5, peer_count=20)

        targets = service.select_gossip_targets(rng=random.Random(9))
        target_ids = [t.peer_id for t in targets]

        self.assertEqual(len(target_ids), len(set(target_ids)))

    def test_self_is_never_selected_as_a_target(self) -> None:
        service = build_service(self_id="self", fanout=5, peer_count=5)

        targets = service.select_gossip_targets(rng=random.Random(3))

        self.assertNotIn("self", [t.peer_id for t in targets])

    def test_self_cannot_be_smuggled_in_via_merge_and_then_selected(self) -> None:
        service = build_service(self_id="self", fanout=5, peer_count=5)

        service.membership.merge([make_peer("self", last_seen=999.0)])
        targets = service.select_gossip_targets(rng=random.Random(3))

        self.assertNotIn("self", [t.peer_id for t in targets])

    def test_only_alive_peers_are_selected(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)
        service = GossipService(membership=table, fanout=5, self_info=make_peer("self"))

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual(targets, [])

    def test_dead_peers_are_excluded_even_when_alive_peers_remain(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)
        table.touch("peer-b", now=100.0)
        service = GossipService(membership=table, fanout=5, self_info=make_peer("self"))

        targets = service.select_gossip_targets(rng=random.Random(1))

        self.assertEqual([t.peer_id for t in targets], ["peer-b"])

    def test_selection_is_deterministic_with_same_seed(self) -> None:
        service = build_service(self_id="self", fanout=3, peer_count=15)

        first = service.select_gossip_targets(rng=random.Random(2024))
        second = service.select_gossip_targets(rng=random.Random(2024))

        self.assertEqual([p.peer_id for p in first], [p.peer_id for p in second])


class RunRoundTests(unittest.TestCase):
    def test_run_round_without_transport_returns_targets_and_does_not_raise(self) -> None:
        service = build_service(self_id="self", fanout=2, peer_count=5)

        targets = service.run_round(now=1.0, rng=random.Random(1))

        self.assertEqual(len(targets), 2)

    def test_run_round_with_transport_sends_payload_to_each_target(self) -> None:
        service = build_service(self_id="self", fanout=2, peer_count=5)

        sent: list[tuple[str, GossipPayload]] = []

        class RecordingTransport:
            def send(self, target: PeerInfo, payload: GossipPayload) -> None:
                sent.append((target.peer_id, payload))

        targets = service.run_round(now=1.0, transport=RecordingTransport(), rng=random.Random(1))

        self.assertEqual(len(sent), len(targets))
        self.assertTrue(all(payload.sender_id == "self" for _, payload in sent))


class MergeIncomingTests(unittest.TestCase):
    def test_merge_incoming_applies_payload_to_membership(self) -> None:
        service = build_service(self_id="self", fanout=2, peer_count=0)
        payload = GossipPayload.create(
            sender=make_peer("peer-x", last_seen=5.0),
            peers=[make_peer("peer-y", last_seen=5.0)],
            sent_at=5.0,
        )

        service.merge_incoming(payload, now=5.0)

        known_ids = {p.peer_id for p in service.membership.get_known_peers()}
        self.assertEqual(known_ids, {"peer-x", "peer-y"})

    def test_merge_incoming_registers_a_previously_unknown_sender(self) -> None:
        # Descubrimiento vía gossip: el emisor directo de un mensaje debe
        # quedar registrado con host/port, no solo "tocado" (que sería
        # no-op si era desconocido).
        service = build_service(self_id="self", fanout=2, peer_count=0)
        payload = GossipPayload.create(
            sender=PeerInfo(peer_id="new-peer", host="10.0.0.5", port=7000),
            peers=[],
            sent_at=3.0,
        )

        service.merge_incoming(payload, now=3.0)

        known = service.membership.get_known_peers()
        self.assertEqual(len(known), 1)
        self.assertEqual(known[0].address, ("10.0.0.5", 7000))
        self.assertTrue(known[0].is_alive())


class GossipMetricsTests(unittest.TestCase):
    def test_metrics_track_rounds_and_messages(self) -> None:
        service = build_service(self_id="self", fanout=2, peer_count=3)

        class RecordingTransport:
            def send(self, target: PeerInfo, payload: GossipPayload) -> None:
                pass

        service.run_round(now=1.0, transport=RecordingTransport(), rng=random.Random(1))
        service.run_round(now=2.0, transport=RecordingTransport(), rng=random.Random(1))
        incoming = GossipPayload.create(sender=make_peer("peer-z"), peers=[], sent_at=1.0)
        service.merge_incoming(incoming, now=1.0)

        metrics = service.metrics()

        self.assertEqual(metrics.rounds_run, 2)
        self.assertEqual(metrics.messages_sent, 4)  # 2 destinos x 2 rondas
        self.assertEqual(metrics.messages_received, 1)


if __name__ == "__main__":
    unittest.main()
