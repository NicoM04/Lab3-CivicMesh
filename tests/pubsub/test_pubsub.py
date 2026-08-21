import pytest
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

@pytest.fixture
def pubsub():
    mock_gossip = Mock()
    mock_gossip.get_known_peers.return_value = []
    return PubSub(peer_id="p1", gossip_layer=mock_gossip)

def test_should_forward_ttl_expired(pubsub):
    # 1. should_forward con TTL agotado -> False
    msg = make_msg(ttl=0)
    # Incluso si hay alguien muy interesado, no se envía por TTL agotado
    local_view = [fake_peer("p2", ["santiago"])]
    assert pubsub.should_forward(msg, "santiago", local_view) is False

def test_should_forward_dedup(pubsub):
    # 2. should_forward con mensaje ya visto (dedup) -> False
    msg = make_msg(msg_id="mensaje_repetido")
    pubsub.seen_ids.add("mensaje_repetido")
    local_view = [fake_peer("p2", ["santiago"])]
    assert pubsub.should_forward(msg, "santiago", local_view) is False

def test_should_forward_no_interested_peers(pubsub):
    # 3. should_forward sin peers interesados en el tópico ni vecinos -> False
    msg = make_msg(topic="santiago")
    # p2 está suscrito a "vitacura", que en nuestra topología NO es vecina de santiago
    local_view = [fake_peer("p2", ["vitacura"])]
    assert pubsub.should_forward(msg, "santiago", local_view) is False

def test_should_forward_with_neighbor_interest(pubsub):
    # 4. should_forward con peer interesado en tópico vecino -> True
    msg = make_msg(topic="santiago")
    # p2 está suscrito a "providencia", que SÍ es vecina de santiago
    local_view = [fake_peer("p2", ["providencia"])]
    assert pubsub.should_forward(msg, "santiago", local_view) is True

def test_fanout_respected(pubsub):
    # 5. Selección de targets respeta el fanout configurado
    msg = make_msg(channel="objetivo")
    # En default config, 'objetivo' tiene fanout=3
    peers = [fake_peer(f"p{i}", ["santiago"]) for i in range(10)]
    targets = pubsub.select_forward_targets(msg, peers)
    assert len(targets) == 3

def test_ttl_decreases_and_hop_increases(pubsub):
    # 6. TTL decrece / hop_count aumenta correctamente en cada reenvío.
    msg = make_msg(ttl=5, topic="santiago")
    # Para que decida reenviar, simulamos que hay un peer interesado en gossip
    pubsub.gossip_layer.get_known_peers.return_value = [fake_peer("p2", ["santiago"])]
    
    pubsub.handle_incoming(msg, "p0")
    
    # El mensaje original mutó tras ser procesado (listo para forward)
    assert msg.ttl == 4
    assert msg.hop_count == 1
    assert msg.msg_id in pubsub.seen_ids

def test_channels_independent_config(pubsub):
    # 8. Canal objetivo y subjetivo usan TTL/prioridad distintos (test que instancia ambos y verifica que no se mezclan).
    msg_obj = pubsub.publish("santiago", "objetivo", {})
    assert msg_obj.ttl == 5
    assert msg_obj.priority == 10

    msg_subj = pubsub.publish("santiago", "subjetivo", {})
    assert msg_subj.ttl == 3
    assert msg_subj.priority == 5

def test_subscription_neighbors_delivery(pubsub):
    # 9. Suscripción a vecinos: un peer suscrito a providencia con include_neighbors=True
    # debe considerar mensajes de santiago como de interés (según tu grafo de adyacencia).
    callback = Mock()
    pubsub.on_message(callback)
    
    # Nos suscribimos a providencia pidiendo vecinos
    pubsub.subscribe("providencia", {"objetivo"}, include_neighbors=True)
    
    # Llega un mensaje de santiago (vecino de providencia)
    msg_santiago = make_msg(topic="santiago", channel="objetivo")
    pubsub.handle_incoming(msg_santiago, "p0")
    
    # El callback DEBIÓ ser llamado porque pedimos vecinos
    callback.assert_called_once_with(msg_santiago)

def test_subscription_neighbors_exclusion(pubsub):
    # Verificamos la contraparte: si NO pedimos vecinos, ignoramos mensajes de comunas vecinas.
    callback = Mock()
    pubsub.on_message(callback)
    
    # Nos suscribimos a providencia SIN vecinos
    pubsub.subscribe("providencia", {"objetivo"}, include_neighbors=False)
    
    msg_santiago = make_msg(topic="santiago", channel="objetivo")
    pubsub.handle_incoming(msg_santiago, "p0")
    
    # El callback NO debió ser llamado
    callback.assert_not_called()
