"""Módulo de analítica y métricas para CivicMesh (Rol 4: Líder de Analítica y Estadística).

Proporciona utilidades para el cálculo de convergencia, brecha de percepción,
disponibilidad de peers, estadísticas de propagación y almacenamiento en JSONL.
"""

from .metrics import (
    calculate_convergence,
    calculate_perception_gap,
    calculate_peer_availability,
    calculate_propagation_stats,
)

from .storage import (
    write_metric,
    read_metrics,
)

__all__ = [
    "calculate_convergence",
    "calculate_perception_gap",
    "calculate_peer_availability",
    "calculate_propagation_stats",
    "write_metric",
    "read_metrics",
]