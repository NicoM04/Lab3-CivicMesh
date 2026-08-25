from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Asegurar que el paquete civicmesh sea importable sin requerir pip install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from civicmesh.generators.config_loader import load_config
from civicmesh.gossip.peer import PeerInfo
from civicmesh.runtime import PeerRuntime


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--peer-id",
        required=True,
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--topic",
        default="Santiago",
    )

    parser.add_argument(
        "--include-neighbors",
        action="store_true",
    )

    parser.add_argument(
        "--metrics-dir",
        default="runs/real/metrics",
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
    )

    parser.add_argument(
        "--gossip-interval",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--failure-timeout",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--seed-id",
    )

    parser.add_argument(
        "--seed-host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--seed-port",
        type=int,
    )

    parser.add_argument(
        "--simulate-first-send-failure",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:

    args = parse_args()

    config = load_config(
        args.config
    )

    runtime = PeerRuntime(
        peer_id=args.peer_id,
        host=args.host,
        port=args.port,
        gossip_interval=args.gossip_interval,
        failure_timeout=args.failure_timeout,
        pubsub_config=config.get("pubsub"),
        metrics_dir=args.metrics_dir,
        simulate_first_send_failure=(args.simulate_first_send_failure),
    )

    runtime.subscribe(
        args.topic,
        {
            "objetivo",
            "subjetivo",
        },
        include_neighbors=args.include_neighbors,
    )

    runtime.start()

    if args.seed_id:

        if args.seed_port is None:
            raise SystemExit(
                "--seed-port es obligatorio "
                "cuando se usa --seed-id"
            )

        seed = PeerInfo(
            peer_id=args.seed_id,
            host=args.seed_host,
            port=args.seed_port,
        )

        runtime.join(seed)

    print(
        f"{args.peer_id} escuchando en "
        f"{args.host}:{args.port} y "
        f"suscrito a {args.topic}. "
        "Ctrl+C para detener."
    )

    try:
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass

    finally:
        runtime.stop()


if __name__ == "__main__":
    main()