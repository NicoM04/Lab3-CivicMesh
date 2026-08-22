import unittest
from unittest.mock import Mock
from civicmesh.pubsub.pubsub import PubSub
from civicmesh.pubsub.models import Message
from civicmesh.gossip.peer import PeerInfo, PeerStatus


def fake_peer(peer_id: str, subscribed_topics: list[str]) -> PeerInfo:
    """Helper para crear peers falsos para los tests."""
    return PeerInfo(
        peer_id=peer_id,
        host="127.0.0.1",
        port=8000,
        status=PeerStatus.ALIVE,
        last_seen=0.0,
        subscribed_topics=frozenset(subscribed_topics)
    )

def make_msg(msg_id="m1", topic="santiago", channel="objetivo", ttl=5, priority=10) -> Message:
    return Message(
        msg_id=msg_id,
        topic=topic,
        channel=channel,
        payload={},
        ttl=ttl,
        priority=priority,
        origin="origin_peer"
    )


class TestPubSub(unittest.TestCase):
    def setUp(self):
        self.mock_gossip = Mock()
        self.mock_gossip.get_known_peers.return_value = []
        self.pubsub = PubSub(peer_id="p1", gossip_layer=self.mock_gossip)

    def test_should_forward_ttl_expired(self):
        # 1. should_forward con TTL agotado -> False
        msg = make_msg(ttl=0)
        local_view = [fake_peer("p2", ["santiago"])]
        self.assertFalse(self.pubsub.should_forward(msg, "santiago", local_view))

    def test_should_forward_dedup(self):
        # 2. should_forward con mensaje ya visto (dedup) -> False
        msg = make_msg(msg_id="mensaje_repetido")
        self.pubsub.seen_ids.add("mensaje_repetido")
        local_view = [fake_peer("p2", ["santiago"])]
        self.assertFalse(self.pubsub.should_forward(msg, "santiago", local_view))

    def test_should_forward_no_interested_peers(self):
        # 3. should_forward sin peers interesados en el tópico ni vecinos -> False
        msg = make_msg(topic="santiago")
        # p2 está suscrito a "vitacura", que en nuestra topología NO es vecina de santiago
        local_view = [fake_peer("p2", ["vitacura"])]
        self.assertFalse(self.pubsub.should_forward(msg, "santiago", local_view))

    def test_should_forward_with_neighbor_interest(self):
        # 4. should_forward con peer interesado en tópico vecino -> True
        msg = make_msg(topic="santiago")
        # p2 está suscrito a "providencia", que SÍ es vecina de santiago
        local_view = [fake_peer("p2", ["providencia"])]
        self.assertTrue(self.pubsub.should_forward(msg, "santiago", local_view))

    def test_fanout_respected(self):
        # 5. Selección de targets respeta el fanout configurado
        msg = make_msg(channel="objetivo")
        # En default config, 'objetivo' tiene fanout=3
        peers = [fake_peer(f"p{i}", ["santiago"]) for i in range(10)]
        targets = self.pubsub.select_forward_targets(msg, peers)
        self.assertEqual(len(targets), 3)

    def test_ttl_decreases_and_hop_increases(self):
        # 6. TTL decrece / hop_count aumenta correctamente en cada reenvío.
        msg = make_msg(ttl=5, topic="santiago")
        self.pubsub.gossip_layer.get_known_peers.return_value = [fake_peer("p2", ["santiago"])]
        
        self.pubsub.handle_incoming(msg, "p0")
        
        self.assertEqual(msg.ttl, 4)
        self.assertEqual(msg.hop_count, 1)
        self.assertIn(msg.msg_id, self.pubsub.seen_ids)

    def test_channels_independent_config(self):
        # 8. Canal objetivo y subjetivo usan TTL/prioridad distintos
        msg_obj = self.pubsub.publish("santiago", "objetivo", {})
        self.assertEqual(msg_obj.ttl, 5)
        self.assertEqual(msg_obj.priority, 10)

        msg_subj = self.pubsub.publish("santiago", "subjetivo", {})
        self.assertEqual(msg_subj.ttl, 3)
        self.assertEqual(msg_subj.priority, 5)

    def test_subscription_neighbors_delivery(self):
        # 9. Suscripción a vecinos entrega el mensaje si está cerca
        callback = Mock()
        self.pubsub.on_message(callback)
        
        self.pubsub.subscribe("providencia", {"objetivo"}, include_neighbors=True)
        msg_santiago = make_msg(topic="santiago", channel="objetivo")
        self.pubsub.handle_incoming(msg_santiago, "p0")
        
        callback.assert_called_once_with(msg_santiago)

    def test_subscription_neighbors_exclusion(self):
        # Si NO pedimos vecinos, ignoramos mensajes de comunas vecinas.
        callback = Mock()
        self.pubsub.on_message(callback)
        
        self.pubsub.subscribe("providencia", {"objetivo"}, include_neighbors=False)
        msg_santiago = make_msg(topic="santiago", channel="objetivo")
        self.pubsub.handle_incoming(msg_santiago, "p0")
        
        callback.assert_not_called()
