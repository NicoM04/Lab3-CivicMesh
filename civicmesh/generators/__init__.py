"""Paquete de generadores, replay de datos y modelos de percepción (Rol 3: Líder de Datos).

Exporta las clases y funciones principales para la generación estocástica de eventos
(Dominio A), reproducción de series reales (Dominio B) y modelado de percepción ciudadana.
"""

from civicmesh.generators.config_loader import get_rng, load_config
from civicmesh.generators.perception import (
    PerceptionModelA,
    PerceptionModelB,
    aggregate_gossip,
    sigmoid,
)
from civicmesh.generators.poisson import DEFAULT_LAMBDAS, CrimeGenerator
from civicmesh.generators.replay import (
    AirQualityReplay,
    calculate_distance,
    idw_extrapolate,
)

__all__ = [
    "load_config",
    "get_rng",
    "CrimeGenerator",
    "DEFAULT_LAMBDAS",
    "AirQualityReplay",
    "idw_extrapolate",
    "calculate_distance",
    "PerceptionModelA",
    "PerceptionModelB",
    "aggregate_gossip",
    "sigmoid",
]
