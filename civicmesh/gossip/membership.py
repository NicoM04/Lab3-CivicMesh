"""Membership: registro de peers conocidos y vista parcial de la red."""

from __future__ import annotations

import random

from civicmesh.gossip.metrics import MembershipMetrics
from civicmesh.gossip.peer import (
    PeerInfo,
    PeerStatus,
)


class MembershipTable:
    """Vista de membership de un peer."""

    def __init__(
        self,
        self_id: str,
        partial_view_size: int,
    ) -> None:

        if not self_id:
            raise ValueError(
                "self_id no puede estar vacío"
            )

        if partial_view_size <= 0:
            raise ValueError(
                "partial_view_size debe ser mayor a 0"
            )

        self.self_id = self_id
        self.partial_view_size = (
            partial_view_size
        )

        self._peers: dict[
            str,
            PeerInfo,
        ] = {}

    def register_peer(
        self,
        peer: PeerInfo,
        now: float,
    ) -> None:
        """Registra o actualiza un peer."""

        if peer.peer_id == self.self_id:
            return

        # Se utiliza el PeerInfo entrante y no el anterior.
        # Así también se actualizan host, port y subscribed_topics.
        self._peers[
            peer.peer_id
        ] = peer.touched(now)

    def touch(
        self,
        peer_id: str,
        now: float,
    ) -> None:

        if peer_id == self.self_id:
            return

        existing = self._peers.get(
            peer_id
        )

        if existing is not None:

            self._peers[
                peer_id
            ] = existing.touched(now)

    def detect_timeouts(
        self,
        now: float,
        timeout_seconds: float,
    ) -> list[str]:

        newly_dead: list[str] = []

        for (
            peer_id,
            peer,
        ) in self._peers.items():

            if (
                peer.status
                is PeerStatus.ALIVE
                and
                (
                    now
                    - peer.last_seen
                )
                > timeout_seconds
            ):

                self._peers[
                    peer_id
                ] = peer.marked_dead(now)

                newly_dead.append(
                    peer_id
                )

        return newly_dead

    def get_known_peers(
        self,
    ) -> list[PeerInfo]:

        return list(
            self._peers.values()
        )

    def get_alive_peers(
        self,
    ) -> list[PeerInfo]:

        return [
            peer
            for peer
            in self._peers.values()
            if peer.status
            is PeerStatus.ALIVE
        ]

    def get_partial_view(
        self,
        rng: random.Random | None = None,
    ) -> list[PeerInfo]:

        alive = self.get_alive_peers()

        if (
            len(alive)
            <= self.partial_view_size
        ):
            return alive

        rng = (
            rng
            if rng is not None
            else random.Random()
        )

        return rng.sample(
            alive,
            self.partial_view_size,
        )

    def merge(
        self,
        incoming: list[PeerInfo],
    ) -> None:

        for incoming_peer in incoming:

            if (
                incoming_peer.peer_id
                == self.self_id
            ):
                continue

            local = self._peers.get(
                incoming_peer.peer_id
            )

            if (
                local is None
                or
                incoming_peer.last_seen
                > local.last_seen
            ):

                self._peers[
                    incoming_peer.peer_id
                ] = incoming_peer

    def time_since_last_seen(
        self,
        peer_id: str,
        now: float,
    ) -> float | None:

        peer = self._peers.get(
            peer_id
        )

        if peer is None:
            return None

        return (
            now
            - peer.last_seen
        )

    def metrics(
        self,
    ) -> MembershipMetrics:

        alive_count = sum(
            1
            for peer
            in self._peers.values()
            if peer.status
            is PeerStatus.ALIVE
        )

        return MembershipMetrics(
            known_peers=len(
                self._peers
            ),
            alive_peers=alive_count,
            dead_peers=(
                len(self._peers)
                - alive_count
            ),
            partial_view_size_limit=(
                self.partial_view_size
            ),
        )