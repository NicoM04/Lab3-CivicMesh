import socket
import threading

from civicmesh.gossip.peer import PeerInfo
from civicmesh.runtime import PeerRuntime


def free_port() -> int:

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:

        sock.bind(
            (
                "127.0.0.1",
                0,
            )
        )

        return int(
            sock.getsockname()[1]
        )


def test_three_real_peers_propagate_pubsub_message():

    ports = [
        free_port()
        for _ in range(3)
    ]

    peers = [
        PeerRuntime(
            f"peer-{index + 1}",
            "127.0.0.1",
            ports[index],
            gossip_interval=10.0,
            failure_timeout=30.0,
        )
        for index in range(3)
    ]

    received = (
        threading.Event()
    )

    received_messages = []

    try:

        for peer in peers:

            peer.subscribe(
                "Santiago",
                {
                    "objetivo",
                    "subjetivo",
                },
            )

            peer.start()

        seed = PeerInfo(
            "peer-1",
            "127.0.0.1",
            ports[0],
        )

        peers[1].join(seed)
        peers[2].join(seed)

        def on_peer3_message(
            msg,
        ):

            received_messages.append(
                msg
            )

            received.set()

        peers[2].on_message(
            on_peer3_message
        )

        peers[1].publish(
            "Santiago",
            "objetivo",
            {
                "domain":
                    "crime",

                "t":
                    0,

                "metric":
                    "crime_total",

                "unit":
                    "count",

                "value":
                    4,
            },
        )

        assert received.wait(
            2.0
        )

        assert (
            received_messages[0]
            .payload["value"]
            == 4
        )

        state = (
            peers[2]
            .get_topic_state()
        )

        assert (
            "santiago"
            in state
        )

        assert (
            "objetivo"
            in state["santiago"]
        )

    finally:

        for peer in reversed(
            peers
        ):
            peer.stop()