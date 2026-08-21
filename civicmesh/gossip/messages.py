"""Mensajes intercambiados por la capa de Gossip.

Separar los mensajes del transporte permite testear la lógica de Gossip
sin sockets ni procesos reales: un mensaje es solo una estructura de datos
inmutable que viaja entre peers (en memoria durante los tests, o vía la
implementación de transporte que provea el rol de integración/red real).
"""

from __future__ import annotations

from dataclasses import dataclass

from civicmesh.gossip.peer import PeerInfo


@dataclass(frozen=True)
class GossipPayload:
    """Contenido de una ronda de gossip enviada de un peer a otro.

    ``sender`` es la identidad completa (host/port incluidos) de quien
    envía, no solo su id: así el receptor puede registrar al emisor
    directamente aunque nunca lo hubiera visto antes (descubrimiento vía
    gossip, no solo vía JOIN explícito). ``peers`` es la vista de
    membership (parcial o completa, según decida el emisor) que se ofrece
    para que el receptor haga merge del resto de la red.
    """

    sender: PeerInfo
    peers: tuple[PeerInfo, ...]
    sent_at: float

    @property
    def sender_id(self) -> str:
        return self.sender.peer_id

    @staticmethod
    def create(sender: PeerInfo, peers: list[PeerInfo], sent_at: float) -> "GossipPayload":
        return GossipPayload(sender=sender, peers=tuple(peers), sent_at=sent_at)

    def to_dict(self) -> dict[str, object]:
        """Representación serializable (JSON-friendly) del mensaje."""
        return {
            "sender": self.sender.to_dict(),
            "peers": [p.to_dict() for p in self.peers],
            "sent_at": self.sent_at,
        }

    @staticmethod
    def from_dict(data: dict[str, object]) -> "GossipPayload":
        return GossipPayload(
            sender=PeerInfo.from_dict(data["sender"]),  # type: ignore[arg-type]
            peers=tuple(PeerInfo.from_dict(p) for p in data["peers"]),  # type: ignore[union-attr]
            sent_at=float(data["sent_at"]),  # type: ignore[arg-type]
        )
