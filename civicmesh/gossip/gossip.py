"""Lógica de rondas de Gossip: selección de vecinos (fanout) y merge de
la información recibida.

Esta capa depende de ``MembershipTable`` pero no conoce transporte real:
``run_round`` construye el payload y selecciona destinatarios; el envío
efectivo se delega a un ``GossipTransport`` opcional (ver
``civicmesh.gossip.interfaces``). Sin transporte, ``run_round`` sigue
siendo útil y testeable: devuelve qué se habría enviado y a quién.
"""

from __future__ import annotations

import random

from civicmesh.gossip.interfaces import GossipTransport
from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.metrics import GossipMetrics
from civicmesh.gossip.peer import PeerInfo


class GossipService:
    """Selecciona vecinos y coordina el intercambio de membership.

    Parameters
    ----------
    membership:
        Tabla de membership local sobre la que opera este servicio.
    fanout:
        Cantidad de vecinos a contactar en cada ronda. ``0`` es un valor
        válido (ronda sin destinos, ver :meth:`select_gossip_targets`). Si
        hay menos peers vivos disponibles que ``fanout``, se contacta a
        todos los disponibles (sin error).
    self_info:
        Identidad completa (incluye host/port) de este peer. Se adjunta
        como remitente en cada payload saliente para que el receptor
        pueda registrarlo directamente, incluso si nunca lo había visto
        antes (descubrimiento vía gossip, no solo vía JOIN).
    """

    def __init__(self, membership: MembershipTable, fanout: int, self_info: PeerInfo) -> None:
        if fanout < 0:
            raise ValueError("fanout no puede ser negativo")
        if self_info.peer_id != membership.self_id:
            raise ValueError("self_info.peer_id debe coincidir con membership.self_id")
        self.membership = membership
        self.fanout = fanout
        self.self_info = self_info
        self.rounds_run = 0
        self.messages_sent = 0
        self.messages_received = 0

    def select_gossip_targets(self, rng: random.Random | None = None) -> list[PeerInfo]:
        """Selecciona hasta ``fanout`` peers vivos, sin repetir y sin
        incluirse a sí mismo, para intercambiar información en esta ronda.

        Con ``fanout == 0`` devuelve siempre una lista vacía (ronda
        deshabilitada). Si hay menos peers vivos que ``fanout``, devuelve
        todos los disponibles. Los peers marcados ``DEAD`` nunca son
        candidatos, porque se parte de ``get_alive_peers()``. ``rng``
        permite determinismo en tests.
        """
        alive = self.membership.get_alive_peers()
        if len(alive) <= self.fanout:
            return alive
        rng = rng if rng is not None else random.Random()
        return rng.sample(alive, self.fanout)

    def build_payload(self, now: float) -> GossipPayload:
        """Construye el payload de gossip con el conocimiento actual de la
        tabla de membership local.

        El remitente (``sender``) se marca como visto ``now`` (la hora
        local de este peer al enviar), para que el receptor pueda
        registrarlo con una marca de actividad fresca.
        """
        return GossipPayload.create(
            sender=self.self_info.touched(now),
            peers=self.membership.get_known_peers(),
            sent_at=now,
        )

    def merge_incoming(self, payload: GossipPayload, now: float) -> None:
        """Aplica un payload de gossip recibido de otro peer.

        Registra al remitente directamente, con ``now`` (la hora local de
        este receptor) como su nueva marca de actividad — aunque nunca se
        lo hubiera visto antes: esto es lo que permite el descubrimiento
        transitivo vía gossip, no solo vía JOIN explícito. Luego fusiona
        el resto de la vista que trae el payload (``payload.peers``) con
        la tabla local, usando la política de merge por ``last_seen`` más
        reciente (ver :meth:`MembershipTable.merge`).
        """
        self.membership.register_peer(payload.sender, now=now)
        self.membership.merge(list(payload.peers))
        self.messages_received += 1

    def run_round(
        self,
        now: float,
        transport: GossipTransport | None = None,
        rng: random.Random | None = None,
    ) -> list[PeerInfo]:
        """Ejecuta una ronda de gossip:

        1. consulta los peers activos de la vista (:meth:`select_gossip_targets`);
        2. si hay ``transport``, arma el payload actual y lo envía a cada
           destino seleccionado.

        Devuelve los peers seleccionados como destinatarios de esta ronda,
        independientemente de si hubo transporte o no. Esto permite testear
        la selección/fanout sin depender de red real.
        """
        targets = self.select_gossip_targets(rng=rng)
        self.rounds_run += 1
        if transport is not None:
            payload = self.build_payload(now)
            for target in targets:
                transport.send(target, payload)
                self.messages_sent += 1
        return targets

    def metrics(self) -> GossipMetrics:
        """Actividad acumulada de este servicio desde su creación."""
        return GossipMetrics(
            rounds_run=self.rounds_run,
            messages_sent=self.messages_sent,
            messages_received=self.messages_received,
        )
