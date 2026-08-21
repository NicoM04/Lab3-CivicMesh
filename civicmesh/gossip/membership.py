"""Membership: registro de peers conocidos y vista parcial de la red.

``MembershipTable`` es el estado central de la capa de Gossip: qué peers
conoce este nodo, cuándo se los vio por última vez, y cuáles se consideran
vivos. No sabe nada de sockets, rondas de gossip ni fanout: eso vive en
``civicmesh.gossip.gossip``.
"""

from __future__ import annotations

import random

from civicmesh.gossip.metrics import MembershipMetrics
from civicmesh.gossip.peer import PeerInfo, PeerStatus


class MembershipTable:
    """Vista de membership de un peer sobre el resto de la red.

    Parameters
    ----------
    self_id:
        Identificador del peer dueño de esta tabla. Se usa para excluirse
        a sí mismo de las consultas de peers conocidos/vivos/vista parcial.
    partial_view_size:
        Tamaño máximo de la vista parcial devuelta por
        :meth:`get_partial_view`. ``None`` o valores <= 0 no están
        permitidos: una vista parcial sin límite deja de ser parcial.
    """

    def __init__(self, self_id: str, partial_view_size: int) -> None:
        if not self_id:
            raise ValueError("self_id no puede estar vacío")
        if partial_view_size <= 0:
            raise ValueError("partial_view_size debe ser mayor a 0")
        self.self_id = self_id
        self.partial_view_size = partial_view_size
        self._peers: dict[str, PeerInfo] = {}

    def register_peer(self, peer: PeerInfo, now: float) -> None:
        """Registra un peer nuevo o actualiza uno existente.

        Si el peer ya era conocido, se actualiza su ``last_seen``/estado en
        lugar de crear una entrada duplicada. El propio peer nunca se
        agrega a su propia tabla.
        """
        if peer.peer_id == self.self_id:
            return
        existing = self._peers.get(peer.peer_id)
        if existing is None:
            self._peers[peer.peer_id] = peer.touched(now)
        else:
            self._peers[peer.peer_id] = existing.touched(now)

    def touch(self, peer_id: str, now: float) -> None:
        """Actualiza ``last_seen`` de un peer ya conocido (heartbeat).

        No hace nada si el peer no está registrado: primero debe llegar un
        ``register_peer`` (p. ej. vía JOIN o gossip) con su información de
        contacto (host/port).
        """
        if peer_id == self.self_id:
            return
        existing = self._peers.get(peer_id)
        if existing is not None:
            self._peers[peer_id] = existing.touched(now)

    def detect_timeouts(self, now: float, timeout_seconds: float) -> list[str]:
        """Marca como DEAD los peers ALIVE cuyo last_seen supera el timeout.

        Devuelve la lista de peer_id recién marcados como caídos (no
        incluye a los que ya estaban DEAD).
        """
        newly_dead: list[str] = []
        for peer_id, peer in self._peers.items():
            if peer.status is PeerStatus.ALIVE and (now - peer.last_seen) > timeout_seconds:
                self._peers[peer_id] = peer.marked_dead(now)
                newly_dead.append(peer_id)
        return newly_dead

    def get_known_peers(self) -> list[PeerInfo]:
        """Todos los peers conocidos (vivos o muertos), sin incluirse a sí
        mismo ni duplicados."""
        return list(self._peers.values())

    def get_alive_peers(self) -> list[PeerInfo]:
        """Peers actualmente considerados vivos, sin incluirse a sí mismo."""
        return [p for p in self._peers.values() if p.status is PeerStatus.ALIVE]

    def get_partial_view(self, rng: random.Random | None = None) -> list[PeerInfo]:
        """Vista parcial determinista de peers vivos.

        Política (peer sampling clásico, sin estado persistente propio):

        - **Inclusión**: solo peers con ``status == ALIVE``; un peer
          marcado ``DEAD`` por :meth:`detect_timeouts` deja de aparecer en
          la vista de inmediato, sin esperar a un ciclo de "limpieza".
        - **Tamaño**: acotado a ``partial_view_size``. Si hay menos peers
          vivos que el límite, se devuelven todos (vista "no llena").
        - **Reemplazo al llenarse**: la vista no es una estructura
          persistente con inserciones/evicciones — cada llamada resamplea
          uniformemente al azar, sin reemplazo, sobre el conjunto de peers
          vivos conocidos *en ese momento*. No hay un evento explícito de
          "descartar un vecino": un peer que deja de salir sorteado en una
          llamada puede volver a salir en la siguiente. Esto evita tener
          que definir una política de expulsión aparte y sigue siendo
          determinista si se inyecta ``rng``.
        - **Duplicados**: imposibles, la tabla interna indexa por
          ``peer_id`` (no puede haber dos entradas del mismo peer).
        - **Peer local**: nunca puede aparecer, porque nunca se registra a
          sí mismo (ver :meth:`register_peer`/:meth:`merge`).

        ``rng`` permite inyectar una fuente de aleatoriedad determinista
        (``random.Random(seed)``) para tests reproducibles; por defecto se
        usa una instancia nueva no sembrada.
        """
        alive = self.get_alive_peers()
        if len(alive) <= self.partial_view_size:
            return alive
        rng = rng if rng is not None else random.Random()
        return rng.sample(alive, self.partial_view_size)

    def merge(self, incoming: list[PeerInfo]) -> None:
        """Combina información de peers recibida (gossip/JOIN) con la tabla
        local.

        Regla de merge: last-writer-wins por ``last_seen``. Si el registro
        entrante es más nuevo que el local (o el peer era desconocido), se
        adopta tal cual (preservando su ``status``, para poder propagar
        también la noticia de que un peer murió). Si es más viejo o igual,
        se descarta. El propio peer nunca se sobreescribe a partir de
        información entrante.
        """
        for incoming_peer in incoming:
            if incoming_peer.peer_id == self.self_id:
                continue
            local = self._peers.get(incoming_peer.peer_id)
            if local is None or incoming_peer.last_seen > local.last_seen:
                self._peers[incoming_peer.peer_id] = incoming_peer

    def time_since_last_seen(self, peer_id: str, now: float) -> float | None:
        """Antigüedad (``now - last_seen``) de un peer conocido.

        Devuelve ``None`` si el peer no está registrado. Útil para
        observabilidad (Rol 4) o para decidir externamente si vale la pena
        forzar un timeout antes del ciclo periódico.
        """
        peer = self._peers.get(peer_id)
        if peer is None:
            return None
        return now - peer.last_seen

    def metrics(self) -> MembershipMetrics:
        """Fotografía cuantitativa del estado actual de la tabla."""
        alive_count = sum(1 for p in self._peers.values() if p.status is PeerStatus.ALIVE)
        return MembershipMetrics(
            known_peers=len(self._peers),
            alive_peers=alive_count,
            dead_peers=len(self._peers) - alive_count,
            partial_view_size_limit=self.partial_view_size,
        )
