"""Instrumentación mínima de la capa de Gossip/Membership.

No es una plataforma de métricas: son estructuras de solo lectura que
exponen contadores ya disponibles en ``MembershipTable``/``GossipService``,
pensadas para que el rol de analítica/visualización las consuma más
adelante sin tener que leer el estado interno de esas clases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MembershipMetrics:
    """Estado cuantitativo de la tabla de membership en un instante dado."""

    known_peers: int
    alive_peers: int
    dead_peers: int
    partial_view_size_limit: int


@dataclass(frozen=True)
class GossipMetrics:
    """Actividad acumulada del servicio de gossip desde su creación."""

    rounds_run: int
    messages_sent: int
    messages_received: int
