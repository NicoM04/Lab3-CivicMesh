import json
from pathlib import Path


def write_metric(metrics_dir, peer_id, metric):
    """
    Guarda una métrica como una línea JSONL en el archivo del peer.
    """

    metrics_path = Path(metrics_dir)
    metrics_path.mkdir(parents=True, exist_ok=True)

    file_path = metrics_path / f"{peer_id}.jsonl"

    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(metric, ensure_ascii=False) + "\n")

    return file_path


def read_metrics(metrics_dir):
    """
    Lee todas las métricas JSONL disponibles en el directorio.
    """

    metrics_path = Path(metrics_dir)

    if not metrics_path.exists():
        return []

    records = []

    for file_path in sorted(metrics_path.glob("*.jsonl")):
        with file_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if line:
                    records.append(json.loads(line))

    return records