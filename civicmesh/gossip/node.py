"""Punto de integración de la capa Gossip."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from civicmesh.gossip.config import GossipConfig
from civicmesh.gossip.gossip import GossipService
from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.metrics import (
    GossipMetrics,
    MembershipMetrics,
)
from civicmesh.gossip.peer import PeerInfo


class Node:
    """Representa un peer de CivicMesh."""

    def __init__(
        self,
        self_info: PeerInfo,
        partial_view_size: int,
        fanout: int,
    ) -> None:

        self.self_info = self_info

        self.membership = MembershipTable(
            self_id=self_info.peer_id,
            partial_view_size=partial_view_size,
        )

        self.gossip = GossipService(
            membership=self.membership,
            fanout=fanout,
            self_info=self_info,
        )

    @classmethod
    def from_config(
        cls,
        self_info: PeerInfo,
        config: GossipConfig,
    ) -> "Node":

        return cls(
            self_info=self_info,
            partial_view_size=(
                config.partial_view_size
            ),
            fanout=config.fanout,
        )

    def join(
        self,
        seeds: PeerInfo | Iterable[PeerInfo],
        now: float,
    ) -> None:

        seed_list = (
            [seeds]
            if isinstance(
                seeds,
                PeerInfo,
            )
            else list(seeds)
        )

        if not seed_list:
            raise ValueError(
                "join requiere al menos un peer seed"
            )

        for seed in seed_list:

            if (
                seed.peer_id
                == self.self_info.peer_id
            ):
                raise ValueError(
                    "un peer no puede usarse "
                    "a sí mismo como seed"
                )

        for seed in seed_list:

            self.membership.register_peer(
                seed,
                now,
            )

    def handle_join_request(
        self,
        new_peer: PeerInfo,
        now: float,
    ) -> GossipPayload:

        self.membership.register_peer(
            new_peer,
            now,
        )

        return self.gossip.build_payload(
            now
        )

    def handle_join_response(
        self,
        payload: GossipPayload,
        now: float,
    ) -> None:

        self.gossip.merge_incoming(
            payload,
            now=now,
        )

    def handle_gossip_message(
        self,
        payload: GossipPayload,
        now: float,
    ) -> None:

        self.gossip.merge_incoming(
            payload,
            now=now,
        )

    def detect_failed_peers(
        self,
        now: float,
        timeout_seconds: float,
    ) -> list[str]:

        return (
            self.membership.detect_timeouts(
                now,
                timeout_seconds,
            )
        )

    def update_subscribed_topics(
        self,
        topics: set[str],
    ) -> None:
        """Actualiza los tópicos anunciados por este peer."""

        self.self_info = replace(
            self.self_info,
            subscribed_topics=frozenset(
                topics
            ),
        )

        self.gossip.self_info = (
            self.self_info
        )

    def get_known_peers(
        self,
    ) -> list[PeerInfo]:

        return (
            self.membership
            .get_known_peers()
        )

    def get_alive_peers(
        self,
    ) -> list[PeerInfo]:

        return (
            self.membership
            .get_alive_peers()
        )

    def get_partial_view(
        self,
    ) -> list[PeerInfo]:

        return (
            self.membership
            .get_partial_view()
        )

    def get_membership_metrics(
        self,
    ) -> MembershipMetrics:

        return self.membership.metrics()

    def get_gossip_metrics(
        self,
    ) -> GossipMetrics:

        return self.gossip.metrics()