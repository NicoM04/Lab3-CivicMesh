"""Tests unitarios para métricas de la capa de Gossip."""

import unittest
from dataclasses import FrozenInstanceError

from civicmesh.gossip.metrics import GossipMetrics, MembershipMetrics


class TestGossipMetricsDataclass(unittest.TestCase):
    def test_membership_metrics_creation(self) -> None:
        metrics = MembershipMetrics(
            known_peers=10,
            alive_peers=8,
            dead_peers=2,
            partial_view_size_limit=5,
        )
        self.assertEqual(metrics.known_peers, 10)
        self.assertEqual(metrics.alive_peers, 8)
        self.assertEqual(metrics.dead_peers, 2)
        self.assertEqual(metrics.partial_view_size_limit, 5)

    def test_membership_metrics_is_frozen(self) -> None:
        metrics = MembershipMetrics(
            known_peers=5,
            alive_peers=4,
            dead_peers=1,
            partial_view_size_limit=3,
        )
        with self.assertRaises(FrozenInstanceError):
            metrics.known_peers = 10  # type: ignore

    def test_gossip_metrics_creation(self) -> None:
        metrics = GossipMetrics(
            rounds_run=15,
            messages_sent=45,
            messages_received=40,
        )
        self.assertEqual(metrics.rounds_run, 15)
        self.assertEqual(metrics.messages_sent, 45)
        self.assertEqual(metrics.messages_received, 40)

    def test_gossip_metrics_is_frozen(self) -> None:
        metrics = GossipMetrics(
            rounds_run=1,
            messages_sent=2,
            messages_received=2,
        )
        with self.assertRaises(FrozenInstanceError):
            metrics.rounds_run = 5  # type: ignore


if __name__ == "__main__":
    unittest.main()
