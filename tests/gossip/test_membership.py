import random
import unittest

from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.peer import PeerInfo, PeerStatus


def make_peer(peer_id: str, port: int = 9000, last_seen: float = 0.0) -> PeerInfo:
    return PeerInfo(peer_id=peer_id, host="127.0.0.1", port=port, last_seen=last_seen)


class RegisterPeerTests(unittest.TestCase):
    def test_register_peer_adds_it_to_known_peers(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=10.0)

        known = table.get_known_peers()

        self.assertEqual(len(known), 1)
        self.assertEqual(known[0].peer_id, "peer-a")
        self.assertEqual(known[0].last_seen, 10.0)
        self.assertIs(known[0].status, PeerStatus.ALIVE)

    def test_registering_same_peer_twice_does_not_duplicate(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=1.0)
        table.register_peer(make_peer("peer-a"), now=2.0)

        known = table.get_known_peers()

        self.assertEqual(len(known), 1)
        self.assertEqual(known[0].last_seen, 2.0)

    def test_registering_self_is_ignored(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("self"), now=1.0)

        self.assertEqual(table.get_known_peers(), [])

    def test_known_peers_never_include_self(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=1.0)
        table.register_peer(make_peer("self"), now=1.0)

        peer_ids = {p.peer_id for p in table.get_known_peers()}

        self.assertNotIn("self", peer_ids)
        self.assertEqual(peer_ids, {"peer-a"})


class TouchAndAliveTests(unittest.TestCase):
    def test_touch_updates_last_seen_of_known_peer(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=1.0)

        table.touch("peer-a", now=5.0)

        peer = table.get_known_peers()[0]
        self.assertEqual(peer.last_seen, 5.0)

    def test_touch_on_unknown_peer_is_a_no_op(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)

        table.touch("ghost", now=5.0)

        self.assertEqual(table.get_known_peers(), [])

    def test_get_alive_peers_excludes_dead_peers(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)

        alive_ids = {p.peer_id for p in table.get_alive_peers()}

        self.assertEqual(alive_ids, set())

    def test_get_alive_peers_returns_only_alive(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)
        table.touch("peer-b", now=100.0)

        alive_ids = {p.peer_id for p in table.get_alive_peers()}

        self.assertEqual(alive_ids, {"peer-b"})


class TimeoutTests(unittest.TestCase):
    def test_peer_within_timeout_stays_alive(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)

        newly_dead = table.detect_timeouts(now=5.0, timeout_seconds=10.0)

        self.assertEqual(newly_dead, [])
        self.assertTrue(table.get_known_peers()[0].is_alive())

    def test_peer_beyond_timeout_is_marked_dead(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)

        newly_dead = table.detect_timeouts(now=50.0, timeout_seconds=10.0)

        self.assertEqual(newly_dead, ["peer-a"])
        dead_peer = table.get_known_peers()[0]
        self.assertFalse(dead_peer.is_alive())
        # last_seen avanza al detectar la caída: es lo que le permite a
        # este veredicto ganar el merge last-writer-wins frente al último
        # ALIVE que otros peers puedan tener para el mismo peer_id.
        self.assertEqual(dead_peer.last_seen, 50.0)

    def test_already_dead_peer_is_not_reported_again(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.detect_timeouts(now=50.0, timeout_seconds=10.0)

        newly_dead_again = table.detect_timeouts(now=60.0, timeout_seconds=10.0)

        self.assertEqual(newly_dead_again, [])

    def test_peer_exactly_at_timeout_boundary_is_still_alive(self) -> None:
        # Comportamiento definido: el chequeo es estrictamente ">" el
        # timeout, así que exactamente en el borde el peer sigue vivo.
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)

        newly_dead = table.detect_timeouts(now=10.0, timeout_seconds=10.0)

        self.assertEqual(newly_dead, [])
        self.assertTrue(table.get_known_peers()[0].is_alive())

    def test_peer_marked_dead_can_recover_via_touch(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.detect_timeouts(now=50.0, timeout_seconds=10.0)
        self.assertFalse(table.get_known_peers()[0].is_alive())

        table.touch("peer-a", now=51.0)

        peer = table.get_known_peers()[0]
        self.assertTrue(peer.is_alive())
        self.assertEqual(peer.last_seen, 51.0)


class PartialViewTests(unittest.TestCase):
    def test_partial_view_returns_all_when_fewer_peers_than_limit(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)

        view = table.get_partial_view(rng=random.Random(1))

        self.assertEqual({p.peer_id for p in view}, {"peer-a", "peer-b"})

    def test_partial_view_is_bounded_by_partial_view_size(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=2)
        for i in range(10):
            table.register_peer(make_peer(f"peer-{i}"), now=0.0)

        view = table.get_partial_view(rng=random.Random(42))

        self.assertEqual(len(view), 2)

    def test_partial_view_has_no_duplicates_and_excludes_self(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=3)
        for i in range(10):
            table.register_peer(make_peer(f"peer-{i}"), now=0.0)
        table.register_peer(make_peer("self"), now=0.0)

        view = table.get_partial_view(rng=random.Random(7))
        view_ids = [p.peer_id for p in view]

        self.assertEqual(len(view_ids), len(set(view_ids)))
        self.assertNotIn("self", view_ids)

    def test_partial_view_is_deterministic_with_same_seed(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=3)
        for i in range(10):
            table.register_peer(make_peer(f"peer-{i}"), now=0.0)

        first = table.get_partial_view(rng=random.Random(123))
        second = table.get_partial_view(rng=random.Random(123))

        self.assertEqual([p.peer_id for p in first], [p.peer_id for p in second])

    def test_partial_view_returns_exactly_the_limit_when_pool_matches_it(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=4)
        for i in range(4):
            table.register_peer(make_peer(f"peer-{i}"), now=0.0)

        view = table.get_partial_view(rng=random.Random(1))

        self.assertEqual({p.peer_id for p in view}, {f"peer-{i}" for i in range(4)})

    def test_partial_view_pool_grows_as_new_peers_register(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        first_view = table.get_partial_view(rng=random.Random(1))
        self.assertEqual({p.peer_id for p in first_view}, {"peer-a"})

        table.register_peer(make_peer("peer-b"), now=1.0)
        second_view = table.get_partial_view(rng=random.Random(1))

        self.assertEqual({p.peer_id for p in second_view}, {"peer-a", "peer-b"})

    def test_partial_view_excludes_peers_marked_dead_by_timeout(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)
        table.touch("peer-b", now=100.0)

        view = table.get_partial_view(rng=random.Random(1))

        self.assertEqual({p.peer_id for p in view}, {"peer-b"})


class MergeTests(unittest.TestCase):
    def test_merge_registers_unknown_peers(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)

        table.merge([make_peer("peer-a", last_seen=10.0)])

        self.assertEqual({p.peer_id for p in table.get_known_peers()}, {"peer-a"})

    def test_merge_prefers_newer_last_seen(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a", last_seen=1.0), now=1.0)

        table.merge([make_peer("peer-a", last_seen=99.0)])

        self.assertEqual(table.get_known_peers()[0].last_seen, 99.0)

    def test_merge_ignores_stale_information(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a", last_seen=50.0), now=50.0)

        table.merge([make_peer("peer-a", last_seen=1.0)])

        self.assertEqual(table.get_known_peers()[0].last_seen, 50.0)

    def test_merge_never_overwrites_self(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)

        table.merge([make_peer("self", last_seen=999.0)])

        self.assertEqual(table.get_known_peers(), [])

    def test_merge_can_propagate_dead_status(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a", last_seen=1.0), now=1.0)
        dead_report = PeerInfo(
            peer_id="peer-a",
            host="127.0.0.1",
            port=9000,
            status=PeerStatus.DEAD,
            last_seen=2.0,
        )

        table.merge([dead_report])

        self.assertFalse(table.get_known_peers()[0].is_alive())

    def test_merge_is_idempotent(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        incoming = [make_peer("peer-a", last_seen=10.0), make_peer("peer-b", last_seen=10.0)]

        table.merge(incoming)
        state_after_first = {p.peer_id: p.last_seen for p in table.get_known_peers()}
        table.merge(incoming)
        state_after_second = {p.peer_id: p.last_seen for p in table.get_known_peers()}

        self.assertEqual(state_after_first, state_after_second)


class TimeSinceLastSeenTests(unittest.TestCase):
    def test_returns_elapsed_time_for_known_peer(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)
        table.register_peer(make_peer("peer-a"), now=10.0)

        self.assertEqual(table.time_since_last_seen("peer-a", now=15.0), 5.0)

    def test_returns_none_for_unknown_peer(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=5)

        self.assertIsNone(table.time_since_last_seen("ghost", now=15.0))


class MetricsTests(unittest.TestCase):
    def test_metrics_reflect_known_alive_dead_and_limit(self) -> None:
        table = MembershipTable(self_id="self", partial_view_size=7)
        table.register_peer(make_peer("peer-a"), now=0.0)
        table.register_peer(make_peer("peer-b"), now=0.0)
        table.detect_timeouts(now=100.0, timeout_seconds=10.0)

        metrics = table.metrics()

        self.assertEqual(metrics.known_peers, 2)
        self.assertEqual(metrics.alive_peers, 0)
        self.assertEqual(metrics.dead_peers, 2)
        self.assertEqual(metrics.partial_view_size_limit, 7)


if __name__ == "__main__":
    unittest.main()
