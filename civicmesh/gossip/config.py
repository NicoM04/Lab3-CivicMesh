"""Configuración reproducible de la capa de Gossip/Membership.

Agrupa en un único lugar los parámetros que hoy están dispersos como
argumentos sueltos (``fanout``, ``partial_view_size``) o que todavía no
tienen dueño explícito (``failure_timeout_seconds``, ``gossip_interval_seconds``,
``rng_seed``), para evitar números mágicos y facilitar reproducibilidad
entre corridas/experimentos.

El proyecto no tiene todavía un ``config.yaml`` compartido entre roles.
``GossipConfig`` es la porción de esa configuración que le corresponde a
esta capa; si más adelante se define un ``config.yaml`` general, sus
claves esperadas para la sección de gossip son las mismas que los campos
de esta clase (ver ``docs/gossip.md``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class GossipConfig:
    """Parámetros de Gossip/Membership para un peer.

    Parameters
    ----------
    fanout:
        Vecinos contactados por ronda de gossip. ``0`` deshabilita el
        envío (ronda sin destinos) sin ser un error.
    partial_view_size:
        Tamaño máximo de la vista parcial de membership.
    failure_timeout_seconds:
        Antigüedad de ``last_seen`` a partir de la cual un peer ALIVE se
        marca DEAD en :meth:`MembershipTable.detect_timeouts`.
    gossip_interval_seconds:
        Intervalo esperado entre rondas de gossip. No implementado como
        scheduler en esta iteración (no hay bucle real); documentado aquí
        para que quien construya el bucle de ejecución (Rol 5) tenga un
        único lugar del que leerlo.
    rng_seed:
        Semilla para la fuente de aleatoriedad usada en fanout/vista
        parcial. ``None`` usa aleatoriedad no determinista (uso normal en
        producción); un entero fijo da corridas reproducibles (tests,
        experimentos).
    """

    fanout: int = 3
    partial_view_size: int = 5
    failure_timeout_seconds: float = 30.0
    gossip_interval_seconds: float = 5.0
    rng_seed: int | None = None

    def __post_init__(self) -> None:
        if self.fanout < 0:
            raise ValueError("fanout no puede ser negativo")
        if self.partial_view_size <= 0:
            raise ValueError("partial_view_size debe ser mayor a 0")
        if self.failure_timeout_seconds <= 0:
            raise ValueError("failure_timeout_seconds debe ser mayor a 0")
        if self.gossip_interval_seconds <= 0:
            raise ValueError("gossip_interval_seconds debe ser mayor a 0")

    def build_rng(self) -> random.Random:
        """Fuente de aleatoriedad consistente con ``rng_seed``."""
        return random.Random(self.rng_seed) if self.rng_seed is not None else random.Random()
