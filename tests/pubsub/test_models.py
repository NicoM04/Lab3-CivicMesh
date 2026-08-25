"""Tests unitarios para modelos de datos de Pub/Sub (Message, Subscription)."""

import time
import unittest

from civicmesh.pubsub.models import Message, Subscription


class TestMessageModel(unittest.TestCase):
    def test_message_creation_and_defaults(self) -> None:
        msg = Message(
            topic="santiago",
            channel="objetivo",
            payload={"count": 5},
            ttl=5,
            priority=10,
            origin="peer-1",
        )
        self.assertEqual(msg.topic, "santiago")
        self.assertEqual(msg.channel, "objetivo")
        self.assertEqual(msg.payload, {"count": 5})
        self.assertEqual(msg.ttl, 5)
        self.assertEqual(msg.priority, 10)
        self.assertEqual(msg.origin, "peer-1")
        self.assertTrue(len(msg.msg_id) > 0)
        self.assertLessEqual(msg.timestamp, time.time())
        self.assertEqual(msg.hop_count, 0)
        self.assertEqual(msg.seen_by, set())

    def test_message_serialization_roundtrip(self) -> None:
        original = Message(
            topic="providencia",
            channel="subjetivo",
            payload={"index": 0.75},
            ttl=3,
            priority=5,
            origin="peer-2",
            msg_id="custom-uuid-1234",
            timestamp=1700000000.0,
            hop_count=2,
            seen_by={"peer-1", "peer-2"},
        )
        data = original.to_dict()
        self.assertEqual(data["topic"], "providencia")
        self.assertEqual(data["channel"], "subjetivo")
        self.assertEqual(data["ttl"], 3)
        self.assertEqual(data["priority"], 5)
        self.assertEqual(data["msg_id"], "custom-uuid-1234")
        self.assertEqual(data["hop_count"], 2)
        self.assertEqual(data["seen_by"], ["peer-1", "peer-2"])

        reconstructed = Message.from_dict(data)
        self.assertEqual(reconstructed.topic, original.topic)
        self.assertEqual(reconstructed.channel, original.channel)
        self.assertEqual(reconstructed.payload, original.payload)
        self.assertEqual(reconstructed.ttl, original.ttl)
        self.assertEqual(reconstructed.priority, original.priority)
        self.assertEqual(reconstructed.origin, original.origin)
        self.assertEqual(reconstructed.msg_id, original.msg_id)
        self.assertEqual(reconstructed.timestamp, original.timestamp)
        self.assertEqual(reconstructed.hop_count, original.hop_count)
        self.assertEqual(reconstructed.seen_by, original.seen_by)


class TestSubscriptionModel(unittest.TestCase):
    def test_subscription_creation(self) -> None:
        sub = Subscription(
            topic="santiago",
            channels={"objetivo", "subjetivo"},
            include_neighbors=True,
        )
        self.assertEqual(sub.topic, "santiago")
        self.assertEqual(sub.channels, {"objetivo", "subjetivo"})
        self.assertTrue(sub.include_neighbors)

    def test_subscription_default_neighbors_false(self) -> None:
        sub = Subscription(
            topic="nunoa",
            channels={"objetivo"},
        )
        self.assertFalse(sub.include_neighbors)


if __name__ == "__main__":
    unittest.main()
