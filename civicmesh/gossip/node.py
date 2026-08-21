"""Punto de integración de la capa de red/Gossip: un peer en ejecución.

``Node`` conecta la identidad propia, la tabla de membership y el
servicio de gossip, y expone el JOIN inicial. Es también la
implementación concreta de ``PeerDirectory`` (ver
``civicmesh.gossip.interfaces``): otras capas (Pub/Sub) deberían depender
de esa interfaz reducida y no de ``Node`` directamente cuando sea posible.
"""

from __future__ import annotations

from collections.abc import Iterable

from civicmesh.gossip.config import GossipConfig
from civicmesh.gossip.gossip import GossipService
from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.metrics import GossipMetrics, MembershipMetrics
from civicmesh.gossip.peer import PeerInfo


class Node:
    """Representa a este peer en ejecución dentro de la red CivicMesh.

    Parameters
    ----------
    self_info:
        Identidad y datos de contacto de este peer.
    partial_view_size:
        Tamaño máximo de la vista parcial de membership.
    fanout:
        Cantidad de vecinos contactados por ronda de gossip.
    """

    def __init__(self, self_info: PeerInfo, partial_view_size: int, fanout: int) -> None:
        self.self_info = self_info
        self.membership = MembershipTable(
            self_id=self_info.peer_id, partial_view_size=partial_view_size
        )
        self.gossip = GossipService(
            membership=self.membership, fanout=fanout, self_info=self_info
        )

    @classmethod
    def from_config(cls, self_info: PeerInfo, config: GossipConfig) -> "Node":
        """Construye un ``Node`` a partir de una :class:`GossipConfig`
        reproducible, en vez de pasar cada parámetro suelto."""
        return cls(
            self_info=self_info,
            partial_view_size=config.partial_view_size,
            fanout=config.fanout,
        )

    def join(self, seeds: PeerInfo | Iterable[PeerInfo], now: float) -> None:
        """Inicia el proceso de JOIN registrando uno o más peers semilla.

        Acepta un único ``PeerInfo`` o una colección de ellos, para ser
        compatible con un despliegue que arranca con 1-2 seeds leídos de
        un ``hostfile.txt`` (ver :mod:`civicmesh.gossip.bootstrap`).

        En esta iteración el JOIN es puramente de dominio: registra a los
        seeds como primeros contactos conocidos. La obtención activa de la
        vista de cada seed (pedirle su lista de peers por red) depende de
        un transporte real; el lado que RECIBE esa solicitud está
        modelado en :meth:`handle_join_request`, y la respuesta se aplica
        con :meth:`handle_join_response`, reutilizando la misma lógica de
        merge que usa Gossip.
        """
        seed_list = [seeds] if isinstance(seeds, PeerInfo) else list(seeds)
        if not seed_list:
            raise ValueError("join requiere al menos un peer seed")
        for seed in seed_list:
            if seed.peer_id == self.self_info.peer_id:
                raise ValueError("un peer no puede usarse a sí mismo como seed")
        for seed in seed_list:
            self.membership.register_peer(seed, now)

    def handle_join_request(self, new_peer: PeerInfo, now: float) -> GossipPayload:
        """Lado del seed al recibir una solicitud de JOIN de ``new_peer``.

        Registra directamente al peer entrante (así el seed también lo
        conoce, no solo al revés) y le devuelve su vista de membership
        actual para que el nuevo peer arme su vista inicial mediante
        :meth:`handle_join_response`.
        """
        self.membership.register_peer(new_peer, now)
        return self.gossip.build_payload(now)

    def handle_join_response(self, payload: GossipPayload, now: float) -> None:
        """Incorpora la vista de membership devuelta por el seed (u otro
        peer) al completar el JOIN."""
        self.gossip.merge_incoming(payload, now=now)

    def handle_gossip_message(self, payload: GossipPayload, now: float) -> None:
        """Procesa un mensaje de gossip recibido de otro peer.

        Registra/actualiza al emisor directamente (incluso si nunca se lo
        había visto) y aplica el merge del resto de la vista que trae el
        payload.
        """
        self.gossip.merge_incoming(payload, now=now)

    def detect_failed_peers(self, now: float, timeout_seconds: float) -> list[str]:
        """Ejecuta la detección de timeouts sobre la tabla de membership."""
        return self.membership.detect_timeouts(now, timeout_seconds)

    # --- Interfaz consumida por Pub/Sub (civicmesh.gossip.interfaces.PeerDirectory) ---

    def get_known_peers(self) -> list[PeerInfo]:
        return self.membership.get_known_peers()

    def get_alive_peers(self) -> list[PeerInfo]:
        return self.membership.get_alive_peers()

    def get_partial_view(self) -> list[PeerInfo]:
        return self.membership.get_partial_view()

    # --- Observabilidad (consumible por Rol 4) ---

    def get_membership_metrics(self) -> MembershipMetrics:
        return self.membership.metrics()

    def get_gossip_metrics(self) -> GossipMetrics:
        return self.gossip.metrics()
