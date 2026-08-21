import unittest

from civicmesh.gossip.config import GossipConfig


class GossipConfigValidationTests(unittest.TestCase):
    def test_default_config_is_valid(self) -> None:
        config = GossipConfig()

        self.assertGreater(config.fanout, 0)
        self.assertGreater(config.partial_view_size, 0)

    def test_zero_fanout_is_a_valid_configuration(self) -> None:
        config = GossipConfig(fanout=0)

        self.assertEqual(config.fanout, 0)

    def test_negative_fanout_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GossipConfig(fanout=-1)

    def test_non_positive_partial_view_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GossipConfig(partial_view_size=0)

    def test_non_positive_failure_timeout_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GossipConfig(failure_timeout_seconds=0)

    def test_non_positive_gossip_interval_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GossipConfig(gossip_interval_seconds=-5)


class GossipConfigRngTests(unittest.TestCase):
    def test_build_rng_with_seed_is_deterministic(self) -> None:
        config = GossipConfig(rng_seed=123)

        first = config.build_rng().sample(range(1000), 5)
        second = config.build_rng().sample(range(1000), 5)

        self.assertEqual(first, second)

    def test_build_rng_without_seed_returns_a_random_instance(self) -> None:
        config = GossipConfig(rng_seed=None)

        rng = config.build_rng()

        self.assertTrue(hasattr(rng, "sample"))


if __name__ == "__main__":
    unittest.main()
