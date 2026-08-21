"""Interfaces (protocolos) de frontera entre la capa de red/Gossip y el resto
de CivicMesh.

``PeerDirectory`` es el contrato que otras capas (en particular Pub/Sub,
Rol 2) deben usar para consultar la red de peers. No expone nada sobre
cómo se implementa el gossip, el merge, el fanout, ni el timeout: solo
las consultas que un consumidor externo necesita.

``GossipTransport`` es el punto de extensión para el envío real de
mensajes de gossip (sockets/HTTP/UDP/etc.). En esta iteración no se
implementa ningún transporte real: la lógica de dominio funciona sin él
(ver ``civicmesh.gossip.gossip.GossipService.run_round``), y queda como
abstracción lista para que la capa de integración/red (Rol 5) la
implemente cuando corresponda.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo


@runtime_checkable
class PeerDirectory(Protocol):
    """Contrato de solo lectura que Pub/Sub (u otros consumidores) usan
    para conocer el estado de la red, sin acoplarse a Gossip.
    """

    def get_known_peers(self) -> list[PeerInfo]:
        """Todos los peers conocidos (vivos o muertos), sin incluirse a sí
        mismo."""
        ...

    def get_alive_peers(self) -> list[PeerInfo]:
        """Subconjunto de peers conocidos actualmente considerados vivos."""
        ...

    def get_partial_view(self) -> list[PeerInfo]:
        """Vista parcial (acotada) de peers vivos, tal como la mantiene la
        capa de membership/gossip."""
        ...


class GossipTransport(Protocol):
    """Punto de extensión para el envío real de mensajes de gossip.

    No implementado en esta iteración: se documenta como dependencia para
    el rol de integración/red (Rol 5) o para quien decida construir el
    transporte real sobre esta base de dominio.
    """

    def send(self, target: PeerInfo, payload: GossipPayload) -> None:
        ...
