import json
import threading
from pathlib import Path


_write_lock = threading.Lock()


def write_metric(metrics_dir, peer_id, metric):
    """
    Guarda una métrica como una línea JSONL
    en el archivo correspondiente al peer.
    """

    metrics_path = Path(metrics_dir)
    metrics_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = (
        metrics_path
        / f"{peer_id}.jsonl"
    )

    line = (
        json.dumps(
            metric,
            ensure_ascii=False,
        )
        + "\n"
    )

    # Un mismo peer puede tener varios hilos
    # escribiendo métricas simultáneamente.
    with _write_lock:
        with file_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(line)
            file.flush()

    return file_path


def read_metrics(metrics_dir):
    """
    Lee todas las métricas JSONL disponibles.

    Si una línea está siendo escrita mientras
    se realiza la lectura, se ignora esa línea
    incompleta en vez de detener toda la lectura.
    """

    metrics_path = Path(metrics_dir)

    if not metrics_path.exists():
        return []

    records = []

    for file_path in sorted(
        metrics_path.glob("*.jsonl")
    ):

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)

                except json.JSONDecodeError:
                    # Puede ocurrir si otro hilo/proceso
                    # todavía está terminando de escribir
                    # la línea mientras la leemos.
                    continue

                records.append(record)

    return records