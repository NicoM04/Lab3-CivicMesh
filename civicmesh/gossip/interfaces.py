"""Interfaces entre la capa de Gossip y el resto de CivicMesh.

PeerDirectory es el contrato de solo lectura que Pub/Sub usa para
consultar la red de peers sin acoplarse a Membership.

GossipTransport define el envío de payloads Gossip. La implementación
TCP/JSON concreta vive en civicmesh.network.transport.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo


@runtime_checkable
class PeerDirectory(Protocol):
    """Contrato de solo lectura del estado de peers."""

    def get_known_peers(
        self,
    ) -> list[PeerInfo]:
        ...

    def get_alive_peers(
        self,
    ) -> list[PeerInfo]:
        ...

    def get_partial_view(
        self,
    ) -> list[PeerInfo]:
        ...


class GossipTransport(Protocol):
    """Contrato para transportar Gossip entre procesos."""

    def send(
        self,
        target: PeerInfo,
        payload: GossipPayload,
    ) -> None:
        ...