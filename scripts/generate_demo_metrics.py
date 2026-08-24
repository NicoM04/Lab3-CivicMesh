from pathlib import Path
import shutil

from civicmesh.analytics import write_metric


METRICS_DIR = Path("runs/demo/metrics")


def add_state(
    peer_id,
    domain,
    sim_time,
    objective,
    subjective,
):
    common = {
        "record_type": "topic_state",
        "peer_id": peer_id,
        "domain": domain,
        "topic": "Santiago",
        "sim_time": sim_time,
    }

    write_metric(
        METRICS_DIR,
        peer_id,
        {
            **common,
            "channel": "objetivo",
            "value": objective,
        },
    )

    write_metric(
        METRICS_DIR,
        peer_id,
        {
            **common,
            "channel": "subjetivo",
            "value": subjective,
        },
    )

def add_network_state(
    peer_id,
    sim_time,
    alive_peers,
    dead_peers,
):
    write_metric(
        METRICS_DIR,
        peer_id,
        {
            "record_type": "network_state",
            "peer_id": peer_id,
            "sim_time": sim_time,
            "known_peers": alive_peers + dead_peers,
            "alive_peers": alive_peers,
            "dead_peers": dead_peers,
        },
    )

def add_message_event(
    peer_id,
    sim_time,
    event,
    hop_count,
    ttl,
):
    write_metric(
        METRICS_DIR,
        peer_id,
        {
            "record_type": "message_event",
            "peer_id": peer_id,
            "sim_time": sim_time,
            "event": event,
            "hop_count": hop_count,
            "ttl": ttl,
        },
    )


def main():

    if METRICS_DIR.parent.exists():
        shutil.rmtree(METRICS_DIR.parent)

    # Calidad del aire
    air_data = {
        "peer-1": [
            (0, 20, 23),
            (1, 25, 28),
            (2, 30, 35),
        ],
        "peer-2": [
            (0, 21, 23),
            (1, 25.5, 28),
            (2, 30, 35),
        ],
        "peer-3": [
            (0, 19, 23),
            (1, 24.5, 28),
            (2, 30, 35),
        ],
    }

    for peer_id, values in air_data.items():
        for sim_time, objective, subjective in values:
            add_state(
                peer_id,
                "air",
                sim_time,
                objective,
                subjective,
            )

        # Estado de red de demostración.
    # En t=3 simulamos la caída de peer-3.

    for sim_time in range(3):
        for peer_id in [
            "peer-1",
            "peer-2",
            "peer-3",
        ]:
            add_network_state(
                peer_id,
                sim_time,
                alive_peers=3,
                dead_peers=0,
            )

    for sim_time in [3, 4]:
        for peer_id in [
            "peer-1",
            "peer-2",
        ]:
            add_network_state(
                peer_id,
                sim_time,
                alive_peers=2,
                dead_peers=1,
            )

    # Delitos
    crime_data = {
        "peer-1": [
            (0, 1, 0.30),
            (1, 2, 0.55),
            (2, 3, 0.80),
        ],
        "peer-2": [
            (0, 2, 0.35),
            (1, 2, 0.55),
            (2, 3, 0.80),
        ],
        "peer-3": [
            (0, 1, 0.25),
            (1, 2, 0.55),
            (2, 3, 0.80),
        ],
    }

    for peer_id, values in crime_data.items():
        for sim_time, objective, subjective in values:
            add_state(
                peer_id,
                "crime",
                sim_time,
                objective,
                subjective,
            )

        # Eventos Pub/Sub de demostración

    demo_messages = [
        ("peer-1", 0, "received", 0, 3),
        ("peer-2", 0, "received", 1, 2),
        ("peer-3", 0, "received", 2, 1),
        ("peer-1", 1, "received", 0, 3),
        ("peer-2", 1, "received", 1, 2),
        ("peer-3", 1, "dropped", 2, 0),
    ]

    for (
        peer_id,
        sim_time,
        event,
        hop_count,
        ttl,
    ) in demo_messages:

        add_message_event(
            peer_id,
            sim_time,
            event,
            hop_count,
            ttl,
        )

    print(
        f"Métricas de demostración creadas en "
        f"{METRICS_DIR}"
    )


if __name__ == "__main__":
    main()