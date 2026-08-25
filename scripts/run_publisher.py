from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from threading import Lock

# Asegurar que el paquete civicmesh sea importable sin requerir pip install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from civicmesh.generators.config_loader import (
    load_config,
)

from civicmesh.generators.perception import (
    PerceptionModelA,
    PerceptionModelB,
)

from civicmesh.generators.poisson import (
    CrimeGenerator,
)

from civicmesh.generators.replay import (
    AirQualityReplay,
)

from civicmesh.gossip.peer import PeerInfo
from civicmesh.pubsub.models import Message
from civicmesh.runtime import PeerRuntime


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--domain",
        choices=[
            "crime",
            "air",
        ],
        required=True,
    )

    parser.add_argument(
        "--comuna",
        default="Santiago",
    )

    parser.add_argument(
        "--peer-id",
        default="publisher-1",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=9100,
    )

    parser.add_argument(
        "--seed-id",
        default="peer-1",
    )

    parser.add_argument(
        "--seed-host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--seed-port",
        type=int,
        default=9001,
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
    )

    parser.add_argument(
        "--steps",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--metrics-dir",
        default="runs/real/metrics",
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
        pubsub_config=(
            config.get("pubsub")
        ),
        metrics_dir=(
            Path(args.metrics_dir)
            / "publisher"
        ),
        simulate_first_send_failure=(
            args.simulate_first_send_failure
        ),
    )

    runtime.subscribe(
        args.comuna,
        {
            "objetivo",
            "subjetivo",
        },
    )

    rumor_buffer: list[float] = []

    rumor_lock = Lock()

    def collect_rumor(
        msg: Message,
    ) -> None:

        if (
            msg.channel
            != "subjetivo"
            or
            msg.origin
            == args.peer_id
        ):
            return

        value = msg.payload.get(
            "value"
        )

        if isinstance(
            value,
            (int, float),
        ):

            with rumor_lock:

                rumor_buffer.append(
                    float(value)
                )

    runtime.on_message(
        collect_rumor
    )

    runtime.start()

    seed = PeerInfo(
        peer_id=args.seed_id,
        host=args.seed_host,
        port=args.seed_port,
    )

    # Reintentar conexión al seed durante el arranque distribuido
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            runtime.join(seed)
            break
        except (ConnectionRefusedError, OSError) as err:
            if attempt == max_retries:
                raise
            time.sleep(1.0)

    time.sleep(0.5)

    seed_value = int(
        config.get(
            "seed",
            42,
        )
    )

    if args.domain == "crime":

        crime_cfg = config[
            "dominio_a"
        ]

        generator = CrimeGenerator(
            seed=seed_value,
            lambdas=crime_cfg[
                "lambdas"
            ],
            delta_t=float(
                config.get(
                    "delta_t",
                    1.0,
                )
            ),
        )

        p_cfg = crime_cfg[
            "percepcion"
        ]

        perception = (
            PerceptionModelA(
                comuna=args.comuna,
                alpha=p_cfg[
                    "alpha"
                ],
                beta_0=p_cfg[
                    "beta_0"
                ],
                beta_1=p_cfg[
                    "beta_1"
                ],
                beta_2=p_cfg[
                    "beta_2"
                ],
                sigma_epsilon=p_cfg[
                    "sigma_epsilon"
                ],
                seed=seed_value,
            )
        )

        for step in range(
            args.steps
        ):

            objective = (
                generator.generate_event(
                    args.comuna,
                    t=step,
                )
            )

            objective_payload = {
                **objective,

                "domain":
                    "crime",

                "metric":
                    "crime_total",

                "unit":
                    "count",

                "value":
                    objective["total"],
            }

            runtime.publish(
                args.comuna,
                "objetivo",
                objective_payload,
            )

            with rumor_lock:

                rumors = list(
                    rumor_buffer
                )

                rumor_buffer.clear()

            subjective = (
                perception.update(
                    objective["total"],
                    rumors,
                )
            )

            runtime.publish(
                args.comuna,
                "subjetivo",
                {
                    "comuna":
                        args.comuna,

                    "t":
                        step,

                    "domain":
                        "crime",

                    "metric":
                        "insecurity_index",

                    "unit":
                        "index_0_1",

                    "value":
                        subjective,
                },
            )

            time.sleep(
                args.interval
            )

    else:

        air_cfg = config[
            "dominio_b"
        ]

        replay = AirQualityReplay(
            air_cfg[
                "dataset_path"
            ]
        )

        p_cfg = air_cfg[
            "percepcion"
        ]

        perception = (
            PerceptionModelB(
                comuna=args.comuna,
                alpha=p_cfg[
                    "alpha"
                ],
                gamma=p_cfg[
                    "gamma"
                ],
                delta=p_cfg[
                    "delta"
                ],
                sigma_epsilon=p_cfg[
                    "sigma_epsilon"
                ],
                clip_min=p_cfg[
                    "clip_min"
                ],
                clip_max=p_cfg[
                    "clip_max"
                ],
                seed=seed_value,
            )
        )

        for step in range(
            args.steps
        ):

            objective = (
                replay.get_value(
                    args.comuna,
                    step,
                )
            )

            objective_payload = {
                **objective,

                "domain":
                    "air",

                "metric":
                    "pm2_5",

                "unit":
                    "ug_m3",

                "value":
                    objective[
                        "pm2_5"
                    ],
            }

            runtime.publish(
                args.comuna,
                "objetivo",
                objective_payload,
            )

            with rumor_lock:

                rumors = list(
                    rumor_buffer
                )

                rumor_buffer.clear()

            subjective = (
                perception.update(
                    objective[
                        "pm2_5"
                    ],
                    rumors,
                )
            )

            runtime.publish(
                args.comuna,
                "subjetivo",
                {
                    "comuna":
                        args.comuna,

                    "t":
                        step,

                    "domain":
                        "air",

                    "metric":
                        "perceived_pm2_5",

                    "unit":
                        "ug_m3",

                    "value":
                        subjective,
                },
            )

            time.sleep(
                args.interval
            )

    time.sleep(0.5)

    runtime.stop()


if __name__ == "__main__":
    main()