from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median

# Asegurar que el paquete civicmesh sea importable sin requerir pip install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from civicmesh.analytics.metrics import (
    calculate_convergence,
    calculate_perception_gap,
)
from civicmesh.analytics.storage import read_metrics
from civicmesh.pubsub.topology import normalize_topic


EXPERIMENTS = [
    {
        "experiment": "baseline-crime",
        "domain": "crime",
        "objective_ttl": 5,
        "subjective_ttl": 3,
        "objective_fanout": 3,
        "subjective_fanout": 2,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "none",
    },
    {
        "experiment": "baseline-air",
        "domain": "air",
        "objective_ttl": 5,
        "subjective_ttl": 3,
        "objective_fanout": 3,
        "subjective_fanout": 2,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "none",
    },
    {
        "experiment": "failure-crime",
        "domain": "crime",
        "objective_ttl": 5,
        "subjective_ttl": 3,
        "objective_fanout": 3,
        "subjective_fanout": 2,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "peer-3",
    },
    {
        "experiment": "fanout-low-crime",
        "domain": "crime",
        "objective_ttl": 5,
        "subjective_ttl": 3,
        "objective_fanout": 1,
        "subjective_fanout": 1,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "none",
    },
    {
        "experiment": "ttl-low-crime",
        "domain": "crime",
        "objective_ttl": 1,
        "subjective_ttl": 1,
        "objective_fanout": 1,
        "subjective_fanout": 1,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "none",
    },
    {
        "experiment": "priority-crime",
        "domain": "crime",
        "objective_ttl": 3,
        "subjective_ttl": 3,
        "objective_fanout": 1,
        "subjective_fanout": 1,
        "objective_priority": 10,
        "subjective_priority": 5,
        "failure": "simulated-first-send",
    },
]


def percentage(
    value: float,
    total: float,
) -> float:

    if total == 0:
        return 0.0

    return round(
        100.0 * value / total,
        2,
    )


def latest_network_state(
    records: list[dict],
) -> tuple[int | None, int | None]:

    network = [
        record
        for record in records
        if record.get("record_type")
        == "network_state"
    ]

    if not network:
        return None, None

    latest_by_peer: dict[str, dict] = {}

    for record in network:

        peer_id = record.get("peer_id")

        if not peer_id:
            continue

        current = latest_by_peer.get(
            peer_id
        )

        if (
            current is None
            or record.get("timestamp", 0)
            >= current.get("timestamp", 0)
        ):
            latest_by_peer[
                peer_id
            ] = record

    alive_values = []
    dead_values = []

    for record in latest_by_peer.values():

        alive = record.get(
            "alive_peers",
            record.get("alive"),
        )

        dead = record.get(
            "dead_peers",
            record.get("dead"),
        )

        if alive is not None:
            alive_values.append(
                int(alive)
            )

        if dead is not None:
            dead_values.append(
                int(dead)
            )

    alive_result = (
        int(median(alive_values))
        if alive_values
        else None
    )

    dead_result = (
        int(median(dead_values))
        if dead_values
        else None
    )

    return (
        alive_result,
        dead_result,
    )


def summarize_experiment(
    runs_dir: Path,
    spec: dict,
    topic: str,
    expected_peers: int,
    expected_steps: int,
) -> dict:

    experiment = spec["experiment"]
    domain = spec["domain"]

    metrics_dir = (
        runs_dir
        / experiment
        / "metrics"
    )

    records = read_metrics(
        metrics_dir
    )

    publisher_records = read_metrics(
        metrics_dir / "publisher"
    )

    normalized_topic = normalize_topic(
        topic
    )

    topic_records = [
        record
        for record in records
        if (
            record.get("record_type")
            == "topic_state"
            and record.get("domain")
            == domain
            and normalize_topic(
                str(
                    record.get(
                        "topic",
                        "",
                    )
                )
            )
            == normalized_topic
        )
    ]

    # -----------------------------------------------------
    # Estado objetivo/subjetivo deduplicado por peer y paso
    # -----------------------------------------------------

    objective: dict[
        tuple[str, int],
        float,
    ] = {}

    subjective: dict[
        tuple[str, int],
        float,
    ] = {}

    for record in topic_records:

        peer_id = record.get(
            "peer_id"
        )

        sim_time = record.get(
            "sim_time"
        )

        value = record.get(
            "value"
        )

        if (
            peer_id is None
            or sim_time is None
            or value is None
        ):
            continue

        key = (
            str(peer_id),
            int(sim_time),
        )

        channel = record.get(
            "channel"
        )

        if channel == "objetivo":
            objective[key] = float(
                value
            )

        elif channel == "subjetivo":
            subjective[key] = float(
                value
            )

    expected_total = (
        expected_peers
        * expected_steps
    )

    objective_coverage = percentage(
        len(objective),
        expected_total,
    )

    subjective_coverage = percentage(
        len(subjective),
        expected_total,
    )

    # -----------------------------------------------------
    # Convergencia temporal
    # -----------------------------------------------------

    values_by_step: dict[
        int,
        list[float],
    ] = {}

    for (
        peer_id,
        sim_time,
    ), value in objective.items():

        del peer_id

        values_by_step.setdefault(
            sim_time,
            []
        ).append(value)

    convergence_steps = 0
    full_mesh_steps = 0
    spreads = []
    peer_counts = []

    for sim_time in range(
        expected_steps
    ):

        values = values_by_step.get(
            sim_time,
            [],
        )

        peer_counts.append(
            len(values)
        )

        if not values:
            continue

        result = calculate_convergence(
            values
        )

        if result["spread"] is not None:
            spreads.append(
                float(
                    result["spread"]
                )
            )

        if (
            len(values) >= 2
            and result["converged"]
        ):
            convergence_steps += 1

        if (
            len(values)
            == expected_peers
            and result["converged"]
        ):
            full_mesh_steps += 1

    convergence_rate = percentage(
        convergence_steps,
        expected_steps,
    )

    full_mesh_convergence = percentage(
        full_mesh_steps,
        expected_steps,
    )

    average_peers = (
        round(
            sum(peer_counts)
            / expected_steps,
            2,
        )
        if expected_steps
        else 0.0
    )

    min_peers = (
        min(peer_counts)
        if peer_counts
        else 0
    )

    mean_spread = (
        round(
            sum(spreads)
            / len(spreads),
            4,
        )
        if spreads
        else None
    )

    # -----------------------------------------------------
    # Brecha percepción-realidad
    # -----------------------------------------------------

    paired_keys = sorted(
        set(objective)
        & set(subjective)
    )

    mean_gap = None
    mean_absolute_gap = None

    if paired_keys:

        objective_values = [
            objective[key]
            for key in paired_keys
        ]

        subjective_values = [
            subjective[key]
            for key in paired_keys
        ]

        gap = calculate_perception_gap(
            objective_values,
            subjective_values,
            domain,
        )

        mean_gap = round(
            float(
                gap["mean_gap"]
            ),
            4,
        )

        mean_absolute_gap = round(
            float(
                gap[
                    "mean_absolute_gap"
                ]
            ),
            4,
        )

    gap_unit = (
        "index_0_1"
        if domain == "crime"
        else "ug_m3"
    )

    # -----------------------------------------------------
    # Propagación dentro de la malla
    # -----------------------------------------------------

    message_events = [
        record
        for record in records
        if record.get("record_type")
        == "message_event"
    ]

    received = sum(
        record.get("event")
        == "received"
        for record in message_events
    )

    forwarded = sum(
        record.get("event")
        == "forwarded"
        for record in message_events
    )

    dropped = sum(
        record.get("event")
        == "dropped"
        for record in message_events
    )

    unique_msg_ids = len(
        {
            record.get("msg_id")
            for record in message_events
            if record.get("msg_id")
        }
    )

    # -----------------------------------------------------
    # Eventos registrados por el publicador
    # -----------------------------------------------------

    publisher_events = [
        record
        for record in publisher_records
        if record.get("record_type")
        == "message_event"
    ]

    def publisher_count(
        channel: str,
        event: str,
    ) -> int:

        return sum(
            record.get("channel")
            == channel
            and record.get("event")
            == event
            for record in publisher_events
        )

    # -----------------------------------------------------
    # Estado final de red
    #
    # Usamos mediana de la última observación de cada peer.
    # Esto evita que el estado antiguo del peer que murió
    # domine la corrida failure-crime.
    # -----------------------------------------------------

    alive_peers, dead_peers = (
        latest_network_state(
            records
        )
    )

    availability = None

    if (
        alive_peers is not None
        and dead_peers is not None
        and (
            alive_peers
            + dead_peers
        ) > 0
    ):
        availability = round(
            alive_peers
            / (
                alive_peers
                + dead_peers
            ),
            4,
        )

    result = {
        **spec,
        "objective_records":
            len(objective),
        "subjective_records":
            len(subjective),

        "objective_coverage_pct":
            objective_coverage,
        "subjective_coverage_pct":
            subjective_coverage,

        "value_convergence_pct":
            convergence_rate,

        "full_mesh_convergence_pct":
            full_mesh_convergence,

        "avg_objective_peers_per_step":
            average_peers,

        "min_objective_peers_per_step":
            min_peers,

        "mean_objective_spread":
            mean_spread,

        "paired_gap_samples":
            len(paired_keys),

        "mean_gap":
            mean_gap,

        "mean_absolute_gap":
            mean_absolute_gap,

        "gap_unit":
            gap_unit,

        "received":
            received,

        "forwarded":
            forwarded,

        "dropped":
            dropped,

        "unique_mesh_msg_ids":
            unique_msg_ids,

        "publisher_obj_published":
            publisher_count(
                "objetivo",
                "published",
            ),

        "publisher_obj_forwarded":
            publisher_count(
                "objetivo",
                "forwarded",
            ),

        "publisher_obj_dropped":
            publisher_count(
                "objetivo",
                "dropped",
            ),

        "publisher_subj_published":
            publisher_count(
                "subjetivo",
                "published",
            ),

        "publisher_subj_forwarded":
            publisher_count(
                "subjetivo",
                "forwarded",
            ),

        "publisher_subj_dropped":
            publisher_count(
                "subjetivo",
                "dropped",
            ),

        "alive_peers":
            alive_peers,

        "dead_peers":
            dead_peers,

        "availability":
            availability,
    }

    return result


def write_simple_markdown(
    dataframe: pd.DataFrame,
    path: Path,
) -> None:

    columns = [
        "experiment",
        "domain",
        "objective_coverage_pct",
        "subjective_coverage_pct",
        "full_mesh_convergence_pct",
        "received",
        "forwarded",
        "dropped",
        "alive_peers",
        "dead_peers",
        "mean_absolute_gap",
    ]

    table = dataframe[
        columns
    ].copy()

    headers = list(
        table.columns
    )

    lines = [
        "| "
        + " | ".join(headers)
        + " |",
        "| "
        + " | ".join(
            ["---"] * len(headers)
        )
        + " |",
    ]

    for _, row in table.iterrows():

        values = []

        for value in row:

            if pd.isna(value):
                values.append("-")
            else:
                values.append(
                    str(value)
                )

        lines.append(
            "| "
            + " | ".join(values)
            + " |"
        )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--runs-dir",
        default="runs",
    )

    parser.add_argument(
        "--topic",
        default="Santiago",
    )

    parser.add_argument(
        "--expected-peers",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--expected-steps",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--output-dir",
        default="runs/comparison",
    )

    return parser.parse_args()


def main() -> None:

    args = parse_args()

    runs_dir = Path(
        args.runs_dir
    )

    output_dir = Path(
        args.output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    summaries = []

    for spec in EXPERIMENTS:

        metrics_dir = (
            runs_dir
            / spec["experiment"]
            / "metrics"
        )

        if not metrics_dir.exists():

            print(
                "Omitiendo "
                f"{spec['experiment']}: "
                "no existe."
            )

            continue

        summary = summarize_experiment(
            runs_dir=runs_dir,
            spec=spec,
            topic=args.topic,
            expected_peers=(
                args.expected_peers
            ),
            expected_steps=(
                args.expected_steps
            ),
        )

        summaries.append(
            summary
        )

    if not summaries:

        raise SystemExit(
            "No se encontraron experimentos."
        )

    dataframe = pd.DataFrame(
        summaries
    )

    csv_path = (
        output_dir
        / "experiments_summary.csv"
    )

    dataframe.to_csv(
        csv_path,
        index=False,
        encoding="utf-8",
    )

    # Comparación directa entre ambos dominios.
    domain_comparison = dataframe[
        dataframe["experiment"].isin(
            [
                "baseline-crime",
                "baseline-air",
            ]
        )
    ].copy()

    domain_path = (
        output_dir
        / "domain_baseline_comparison.csv"
    )

    domain_comparison.to_csv(
        domain_path,
        index=False,
        encoding="utf-8",
    )

    markdown_path = (
        output_dir
        / "experiments_summary.md"
    )

    write_simple_markdown(
        dataframe,
        markdown_path,
    )

    # Tabla breve en consola.
    display_columns = [
        "experiment",
        "domain",
        "objective_coverage_pct",
        "subjective_coverage_pct",
        "full_mesh_convergence_pct",
        "received",
        "forwarded",
        "dropped",
        "alive_peers",
        "dead_peers",
        "mean_absolute_gap",
    ]

    print(
        "\n=== COMPARACION CIVICMESH ===\n"
    )

    print(
        dataframe[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\nArchivos generados:"
    )

    print(
        f"- {csv_path}"
    )

    print(
        f"- {domain_path}"
    )

    print(
        f"- {markdown_path}"
    )


if __name__ == "__main__":
    main()