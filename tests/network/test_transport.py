from civicmesh.gossip.peer import PeerInfo
from civicmesh.network import TCPTransport
from civicmesh.pubsub.models import Message


def test_message_roundtrip_dict():

    msg = Message(
        topic="santiago",
        channel="objetivo",
        payload={
            "value": 10,
        },
        ttl=5,
        priority=10,
        origin="peer-1",
    )

    msg.seen_by.add(
        "peer-1"
    )

    restored = Message.from_dict(
        msg.to_dict()
    )

    assert restored == msg


def test_priority_changes_retry_count(
    monkeypatch,
):

    transport = TCPTransport(
        "127.0.0.1",
        0,
        peer_id="peer-1",
    )

    target = PeerInfo(
        "peer-2",
        "127.0.0.1",
        9999,
    )

    calls = []

    def always_fail(
        *args,
        **kwargs,
    ):
        calls.append(1)

        raise OSError(
            "fallo simulado"
        )

    monkeypatch.setattr(
        transport,
        "_exchange",
        always_fail,
    )

    low = Message(
        "santiago",
        "subjetivo",
        {},
        3,
        5,
        "peer-1",
    )

    assert (
        transport.send_pubsub(
            target,
            low,
        )
        is False
    )

    assert len(calls) == 1

    calls.clear()

    high = Message(
        "santiago",
        "objetivo",
        {},
        5,
        10,
        "peer-1",
    )

    assert (
        transport.send_pubsub(
            target,
            high,
        )
        is False
    )

    assert len(calls) == 2

def test_simulated_failure_depends_on_priority(
    monkeypatch,
):

    transport = TCPTransport(
        "127.0.0.1",
        0,
        peer_id="peer-1",
        simulate_first_send_failure=True,
    )

    target = PeerInfo(
        "peer-2",
        "127.0.0.1",
        9999,
    )

    calls = []

    def successful_exchange(
        *args,
        **kwargs,
    ):
        calls.append(1)
        return None

    monkeypatch.setattr(
        transport,
        "_exchange",
        successful_exchange,
    )

    # Prioridad baja:
    # solo tiene un intento y ese intento falla.
    low = Message(
        topic="santiago",
        channel="subjetivo",
        payload={},
        ttl=3,
        priority=5,
        origin="peer-1",
    )

    assert (
        transport.send_pubsub(
            target,
            low,
        )
        is False
    )

    assert len(calls) == 0

    # Prioridad alta:
    # el primer intento falla, pero el segundo funciona.
    high = Message(
        topic="santiago",
        channel="objetivo",
        payload={},
        ttl=3,
        priority=10,
        origin="peer-1",
    )

    assert (
        transport.send_pubsub(
            target,
            high,
        )
        is True
    )

    assert len(calls) == 1