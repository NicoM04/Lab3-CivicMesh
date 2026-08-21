"""Identidad e información de un peer dentro de la red CivicMesh.

Este módulo modela únicamente el estado de un peer tal como lo ve la capa
de Gossip/Membership. No contiene lógica de publicación/suscripción ni de
transporte: eso corresponde a otras capas.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class PeerStatus(Enum):
    """Estado de un peer según lo determina la capa de membership."""

    ALIVE = "alive"
    DEAD = "dead"


@dataclass(frozen=True)
class PeerInfo:
    """Información mínima necesaria para identificar y contactar un peer.

    Es inmutable: cualquier actualización (last_seen, status) produce una
    nueva instancia mediante ``PeerInfo.touched`` o ``PeerInfo.with_status``,
    evitando estado mutable compartido entre estructuras.
    """

    peer_id: str
    host: str
    port: int
    status: PeerStatus = PeerStatus.ALIVE
    last_seen: float = 0.0

    def __post_init__(self) -> None:
        if not self.peer_id:
            raise ValueError("peer_id no puede estar vacío")
        if not self.host:
            raise ValueError("host no puede estar vacío")
        if not (0 <= self.port <= 65535):
            raise ValueError(f"port fuera de rango válido: {self.port}")

    @property
    def address(self) -> tuple[str, int]:
        """Dirección (host, port) del peer."""
        return (self.host, self.port)

    def touched(self, now: float) -> "PeerInfo":
        """Devuelve una copia con ``last_seen`` actualizado y estado ALIVE.

        Recibir cualquier señal (heartbeat, gossip, mensaje directo) de un
        peer implica que está vivo, incluso si antes se lo había marcado
        como DEAD por timeout.
        """
        return replace(self, last_seen=now, status=PeerStatus.ALIVE)

    def with_status(self, status: PeerStatus) -> "PeerInfo":
        """Devuelve una copia con el estado reemplazado."""
        return replace(self, status=status)

    def marked_dead(self, now: float) -> "PeerInfo":
        """Devuelve una copia marcada ``DEAD`` con ``last_seen`` en ``now``.

        Actualizar ``last_seen`` aquí (y no solo el estado) importa para el
        merge de Gossip: ``last_seen`` funciona como marca de versión de la
        última afirmación conocida sobre este peer, viva o muerta. Si no
        avanzara, una declaración de caída nunca podría ganarle, vía
        last-writer-wins, al último registro ``ALIVE`` que ya tuviera otro
        peer para el mismo ``last_seen``.
        """
        return replace(self, status=PeerStatus.DEAD, last_seen=now)

    def is_alive(self) -> bool:
        return self.status is PeerStatus.ALIVE

    def to_dict(self) -> dict[str, object]:
        """Representación serializable (JSON-friendly) del peer.

        Permite que la información de membership viaje por un transporte
        real (bytes/JSON) sin acoplar este módulo a ningún mecanismo de
        Pub/Sub ni de red concreto.
        """
        return {
            "peer_id": self.peer_id,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "last_seen": self.last_seen,
        }

    @staticmethod
    def from_dict(data: dict[str, object]) -> "PeerInfo":
        return PeerInfo(
            peer_id=str(data["peer_id"]),
            host=str(data["host"]),
            port=int(data["port"]),  # type: ignore[arg-type]
            status=PeerStatus(data["status"]),
            last_seen=float(data["last_seen"]),  # type: ignore[arg-type]
        )
