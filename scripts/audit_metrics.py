import argparse
from collections import Counter, defaultdict

from civicmesh.analytics import (
    read_metrics,
    calculate_convergence,
)

from civicmesh.pubsub.topology import normalize_topic


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--metrics-dir",
        required=True,
    )

    parser.add_argument(
        "--domain",
        choices=["crime", "air"],
        required=True,
    )

    parser.add_argument(
        "--topic",
        required=True,
    )

    parser.add_argument(
        "--expected-steps",
        type=int,
        default=None,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    topic = normalize_topic(args.topic)

    records = read_metrics(
        args.metrics_dir
    )

    if not records:
        print("ERROR: no existen métricas.")
        return

    print()
    print("=== AUDITORÍA CIVICMESH ===")
    print()

    print(
        f"Registros totales: {len(records)}"
    )

    # -----------------------------------------------------
    # Estado tópico × canal
    # -----------------------------------------------------

    topic_records = [
        record
        for record in records
        if (
            record.get("record_type")
            == "topic_state"
            and record.get("domain")
            == args.domain
            and record.get("topic")
            == topic
        )
    ]

    peer_ids = sorted(
        {
            record["peer_id"]
            for record in topic_records
        }
    )

    print()
    print("Peers con topic_state:")
    print(peer_ids)

    if not peer_ids:
        print(
            "ERROR: ningún peer tiene "
            "topic_state."
        )
        return

    # -----------------------------------------------------
    # Canales y pasos por peer
    # -----------------------------------------------------

    print()
    print("=== ESTADO POR PEER ===")

    for peer_id in peer_ids:

        peer_records = [
            record
            for record in topic_records
            if record["peer_id"]
            == peer_id
        ]

        channels = Counter(
            record["channel"]
            for record in peer_records
        )

        times = sorted(
            {
                record["sim_time"]
                for record in peer_records
            }
        )

        print()
        print(peer_id)
        print(
            f"  objetivo: "
            f"{channels.get('objetivo', 0)}"
        )
        print(
            f"  subjetivo: "
            f"{channels.get('subjetivo', 0)}"
        )
        print(
            f"  sim_time: {times}"
        )

        if args.expected_steps is not None:

            expected = list(
                range(
                    args.expected_steps
                )
            )

            missing = [
                step
                for step in expected
                if step not in times
            ]

            if missing:
                print(
                    f"  ADVERTENCIA: "
                    f"faltan pasos {missing}"
                )
            else:
                print(
                    "  pasos completos: Sí"
                )

    # -----------------------------------------------------
    # Convergencia
    # -----------------------------------------------------

    print()
    print("=== CONVERGENCIA OBJETIVA ===")

    objective_by_time = defaultdict(
        list
    )

    for record in topic_records:

        if (
            record["channel"]
            == "objetivo"
        ):
            objective_by_time[
                record["sim_time"]
            ].append(
                record["value"]
            )

    for sim_time in sorted(
        objective_by_time
    ):

        values = objective_by_time[
            sim_time
        ]

        result = calculate_convergence(
            values
        )

        print(
            f"t={sim_time}: "
            f"valores={values} | "
            f"spread={result['spread']} | "
            f"convergente="
            f"{result['converged']}"
        )

    # -----------------------------------------------------
    # Eventos Pub/Sub
    # -----------------------------------------------------

    message_records = [
        record
        for record in records
        if (
            record.get("record_type")
            == "message_event"
        )
    ]

    print()
    print("=== PROPAGACIÓN PUB/SUB ===")

    event_counts = Counter(
        record.get("event")
        for record in message_records
    )

    print(
        f"received: "
        f"{event_counts.get('received', 0)}"
    )

    print(
        f"forwarded: "
        f"{event_counts.get('forwarded', 0)}"
    )

    print(
        f"dropped: "
        f"{event_counts.get('dropped', 0)}"
    )

    hops = [
        record["hop_count"]
        for record in message_records
        if (
            record.get("hop_count")
            is not None
        )
    ]

    ttls = [
        record["ttl"]
        for record in message_records
        if (
            record.get("ttl")
            is not None
        )
    ]

    if hops:
        print(
            f"hop_count: "
            f"min={min(hops)}, "
            f"max={max(hops)}"
        )

    if ttls:
        print(
            f"TTL observado: "
            f"min={min(ttls)}, "
            f"max={max(ttls)}"
        )

    # -----------------------------------------------------
    # Seguimiento por msg_id
    # -----------------------------------------------------

    messages = defaultdict(
        list
    )

    for record in message_records:

        msg_id = record.get(
            "msg_id"
        )

        if msg_id:
            messages[msg_id].append(
                record
            )

    propagated_messages = 0

    for msg_records in messages.values():

        peers = {
            record["peer_id"]
            for record in msg_records
        }

        if len(peers) >= 2:
            propagated_messages += 1

    print()
    print("=== TRAZABILIDAD ===")

    print(
        f"msg_id únicos: "
        f"{len(messages)}"
    )

    print(
        "mensajes observados por "
        f"2+ peers: "
        f"{propagated_messages}"
    )

    # -----------------------------------------------------
    # Estado de red
    # -----------------------------------------------------

    network_records = [
        record
        for record in records
        if (
            record.get("record_type")
            == "network_state"
        )
    ]

    print()
    print("=== ESTADO DE RED ===")

    for peer_id in sorted(
        {
            record["peer_id"]
            for record in network_records
        }
    ):

        peer_network = [
            record
            for record in network_records
            if record["peer_id"]
            == peer_id
        ]

        latest = max(
            peer_network,
            key=lambda record:
                record.get(
                    "timestamp",
                    0,
                ),
        )

        print(
            f"{peer_id}: "
            f"vivos={latest['alive_peers']} | "
            f"muertos={latest['dead_peers']}"
        )

    print()
    print("=== FIN AUDITORÍA ===")
    print()


if __name__ == "__main__":
    main()