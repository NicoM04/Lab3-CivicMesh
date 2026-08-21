import random
import tempfile
import unittest
from pathlib import Path

from civicmesh.gossip.bootstrap import load_hostfile, parse_hostfile, select_seeds
from civicmesh.gossip.peer import PeerInfo


class ParseHostfileTests(unittest.TestCase):
    def test_parses_valid_lines(self) -> None:
        lines = ["peer-a 10.0.0.1 9000", "peer-b 10.0.0.2 9001"]

        peers = parse_hostfile(lines)

        self.assertEqual(
            [(p.peer_id, p.host, p.port) for p in peers],
            [("peer-a", "10.0.0.1", 9000), ("peer-b", "10.0.0.2", 9001)],
        )

    def test_ignores_blank_lines_and_comments(self) -> None:
        lines = ["# hostfile de ejemplo", "", "peer-a 10.0.0.1 9000", "   "]

        peers = parse_hostfile(lines)

        self.assertEqual(len(peers), 1)

    def test_rejects_malformed_line(self) -> None:
        with self.assertRaises(ValueError):
            parse_hostfile(["peer-a 10.0.0.1"])

    def test_rejects_non_numeric_port(self) -> None:
        with self.assertRaises(ValueError):
            parse_hostfile(["peer-a 10.0.0.1 not-a-port"])


class LoadHostfileTests(unittest.TestCase):
    def test_reads_peers_from_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hostfile_path = Path(tmp_dir) / "hostfile.txt"
            hostfile_path.write_text("peer-a 10.0.0.1 9000\npeer-b 10.0.0.2 9001\n", encoding="utf-8")

            peers = load_hostfile(hostfile_path)

            self.assertEqual({p.peer_id for p in peers}, {"peer-a", "peer-b"})


class SelectSeedsTests(unittest.TestCase):
    def _peers(self, count: int) -> list[PeerInfo]:
        return [PeerInfo(peer_id=f"peer-{i}", host="10.0.0.1", port=9000 + i) for i in range(count)]

    def test_excludes_self_from_candidates(self) -> None:
        peers = self._peers(3)

        seeds = select_seeds(peers, self_id="peer-0", max_seeds=2, rng=random.Random(1))

        self.assertNotIn("peer-0", [p.peer_id for p in seeds])

    def test_returns_all_candidates_when_fewer_than_max_seeds(self) -> None:
        peers = self._peers(2)

        seeds = select_seeds(peers, self_id="peer-0", max_seeds=2, rng=random.Random(1))

        self.assertEqual({p.peer_id for p in seeds}, {"peer-1"})

    def test_bounds_selection_to_max_seeds(self) -> None:
        peers = self._peers(10)

        seeds = select_seeds(peers, self_id="peer-0", max_seeds=2, rng=random.Random(1))

        self.assertEqual(len(seeds), 2)

    def test_selection_is_deterministic_with_same_seed(self) -> None:
        peers = self._peers(10)

        first = select_seeds(peers, self_id="peer-0", max_seeds=2, rng=random.Random(99))
        second = select_seeds(peers, self_id="peer-0", max_seeds=2, rng=random.Random(99))

        self.assertEqual([p.peer_id for p in first], [p.peer_id for p in second])


if __name__ == "__main__":
    unittest.main()
