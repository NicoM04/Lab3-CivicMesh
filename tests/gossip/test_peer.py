import unittest

from civicmesh.gossip.peer import PeerInfo, PeerStatus


class PeerInfoValidationTests(unittest.TestCase):
    def test_valid_peer_can_be_created(self) -> None:
        peer = PeerInfo(peer_id="peer-a", host="127.0.0.1", port=9000)

        self.assertEqual(peer.address, ("127.0.0.1", 9000))
        self.assertTrue(peer.is_alive())

    def test_empty_peer_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PeerInfo(peer_id="", host="127.0.0.1", port=9000)

    def test_empty_host_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PeerInfo(peer_id="peer-a", host="", port=9000)

    def test_out_of_range_port_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PeerInfo(peer_id="peer-a", host="127.0.0.1", port=70000)


class PeerInfoTransitionsTests(unittest.TestCase):
    def test_touched_updates_last_seen_and_forces_alive(self) -> None:
        peer = PeerInfo(peer_id="peer-a", host="127.0.0.1", port=9000, status=PeerStatus.DEAD)

        refreshed = peer.touched(now=42.0)

        self.assertEqual(refreshed.last_seen, 42.0)
        self.assertTrue(refreshed.is_alive())
        # Inmutabilidad: el original no cambia.
        self.assertFalse(peer.is_alive())

    def test_with_status_replaces_only_status(self) -> None:
        peer = PeerInfo(peer_id="peer-a", host="127.0.0.1", port=9000, last_seen=5.0)

        dead = peer.with_status(PeerStatus.DEAD)

        self.assertFalse(dead.is_alive())
        self.assertEqual(dead.last_seen, 5.0)

    def test_marked_dead_bumps_last_seen_so_it_can_outrank_alive_in_merge(self) -> None:
        peer = PeerInfo(peer_id="peer-a", host="127.0.0.1", port=9000, last_seen=5.0)

        dead = peer.marked_dead(now=5.0)

        self.assertFalse(dead.is_alive())
        self.assertEqual(dead.last_seen, 5.0)
        self.assertGreaterEqual(dead.last_seen, peer.last_seen)


class PeerInfoSerializationTests(unittest.TestCase):
    def test_round_trip_through_dict_preserves_all_fields(self) -> None:
        peer = PeerInfo(
            peer_id="peer-a",
            host="10.0.0.1",
            port=9000,
            status=PeerStatus.DEAD,
            last_seen=12.5,
        )

        restored = PeerInfo.from_dict(peer.to_dict())

        self.assertEqual(restored, peer)

    def test_to_dict_status_is_plain_string(self) -> None:
        peer = PeerInfo(peer_id="peer-a", host="10.0.0.1", port=9000)

        data = peer.to_dict()

        self.assertEqual(data["status"], "alive")
        self.assertIsInstance(data["port"], int)


if __name__ == "__main__":
    unittest.main()
