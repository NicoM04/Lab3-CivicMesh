"""Lógica principal de Publish/Subscribe."""

from __future__ import annotations

from typing import Any, Callable, Optional

from civicmesh.gossip.peer import PeerInfo
from civicmesh.pubsub.config import CHANNEL_CONFIG
from civicmesh.pubsub.models import Message, Subscription
from civicmesh.pubsub.topology import (
    COMUNA_ADYACENCIA,
    normalize_topic,
)


class PubSub:
    def __init__(
        self,
        peer_id: str,
        gossip_layer: Any,
        config: dict | None = None,
        transport: Any | None = None,
    ) -> None:

        self.peer_id = peer_id
        self.gossip_layer = gossip_layer
        self.config = config or CHANNEL_CONFIG
        self.transport = transport

        self.subscriptions: dict[str, Subscription] = {}
        self.seen_ids: set[str] = set()

        self.callbacks: list[
            Callable[[Message], None]
        ] = []

        self.event_callbacks: list[
            Callable[
                [str, Message, dict[str, Any]],
                None,
            ]
        ] = []

        # Último mensaje conocido por tópico × canal.
        self.topic_state: dict[
            tuple[str, str],
            Message,
        ] = {}

    def _local_view(self) -> list[PeerInfo]:

        if not self.gossip_layer:
            return []

        get_alive = getattr(
            self.gossip_layer,
            "get_alive_peers",
            None,
        )

        if callable(get_alive):
            alive = get_alive()

            if isinstance(alive, (list, tuple)):
                return list(alive)

        get_known = getattr(
            self.gossip_layer,
            "get_known_peers",
            None,
        )

        if callable(get_known):
            known = get_known()

            if isinstance(known, (list, tuple)):
                return list(known)

        return []

    def _sync_subscriptions(self) -> None:
        """Informa a Gossip los tópicos locales."""

        if (
            self.gossip_layer
            and hasattr(
                self.gossip_layer,
                "update_subscribed_topics",
            )
        ):
            self.gossip_layer.update_subscribed_topics(
                set(self.subscriptions)
            )

    def subscribe(
        self,
        topic: str,
        channels: set[str],
        include_neighbors: bool = False,
    ) -> None:

        normalized = normalize_topic(topic)

        self.subscriptions[normalized] = Subscription(
            topic=normalized,
            channels=set(channels),
            include_neighbors=include_neighbors,
        )

        self._sync_subscriptions()

    def unsubscribe(self, topic: str) -> None:

        normalized = normalize_topic(topic)

        self.subscriptions.pop(
            normalized,
            None,
        )

        self._sync_subscriptions()

    def publish(
        self,
        topic: str,
        channel: str,
        payload: dict,
        priority: Optional[int] = None,
    ) -> Message:

        if channel not in self.config:
            raise ValueError(
                f"Canal desconocido: {channel}"
            )

        normalized_topic = normalize_topic(topic)

        cfg = self.config[channel]

        msg = Message(
            topic=normalized_topic,
            channel=channel,
            payload=payload,
            ttl=cfg["ttl"],
            priority=(
                priority
                if priority is not None
                else cfg["priority"]
            ),
            origin=self.peer_id,
        )

        msg.seen_by.add(self.peer_id)
        self.seen_ids.add(msg.msg_id)

        self._emit_event(
            "published",
            msg,
            {},
        )

        self._deliver_local(msg)

        self._forward_message(
            msg,
            self._local_view(),
        )

        return msg

    def on_message(
        self,
        callback: Callable[[Message], None],
    ) -> None:

        self.callbacks.append(callback)

    def on_event(
        self,
        callback: Callable[
            [str, Message, dict[str, Any]],
            None,
        ],
    ) -> None:

        self.event_callbacks.append(callback)

    def _emit_event(
        self,
        event: str,
        msg: Message,
        extra: dict[str, Any],
    ) -> None:

        for callback in self.event_callbacks:
            callback(
                event,
                msg,
                extra,
            )

    def _get_interested_peers(
        self,
        topic: str,
        local_view: list[PeerInfo],
    ) -> list[PeerInfo]:

        normalized_topic = normalize_topic(topic)

        interested_peers: list[PeerInfo] = []

        for peer in local_view:

            peer_topics = {
                normalize_topic(value)
                for value
                in peer.subscribed_topics
            }

            if normalized_topic in peer_topics:

                interested_peers.append(peer)

                continue

            for subscribed_topic in peer_topics:

                if (
                    normalized_topic
                    in COMUNA_ADYACENCIA.get(
                        subscribed_topic,
                        [],
                    )
                ):
                    interested_peers.append(peer)

                    break

        return interested_peers

    def should_forward(
        self,
        msg: Message,
        topic: str,
        local_view: list[PeerInfo],
    ) -> bool:

        if msg.ttl <= 0:
            return False

        if msg.msg_id in self.seen_ids:
            return False

        interested_peers = (
            self._get_interested_peers(
                topic,
                local_view,
            )
        )

        if not interested_peers:
            return False

        return bool(
            self.select_forward_targets(
                msg,
                interested_peers,
            )
        )

    def select_forward_targets(
        self,
        msg: Message,
        interested_peers: list[PeerInfo],
    ) -> list[PeerInfo]:

        if msg.channel not in self.config:
            return []

        fanout = self.config[
            msg.channel
        ].get(
            "fanout",
            1,
        )

        valid_peers = [
            peer
            for peer in interested_peers
            if (
                peer.peer_id
                not in msg.seen_by
                and peer.peer_id
                != self.peer_id
            )
        ]

        valid_peers.sort(
            key=lambda peer: peer.last_seen,
            reverse=True,
        )

        return valid_peers[:fanout]

    def _is_local_interested(
        self,
        msg: Message,
    ) -> bool:

        if msg.topic in self.subscriptions:

            subscription = self.subscriptions[
                msg.topic
            ]

            if msg.channel in subscription.channels:
                return True

        for (
            sub_topic,
            subscription,
        ) in self.subscriptions.items():

            if (
                subscription.include_neighbors
                and msg.channel
                in subscription.channels
            ):

                if (
                    msg.topic
                    in COMUNA_ADYACENCIA.get(
                        sub_topic,
                        [],
                    )
                ):
                    return True

        return False

    def _deliver_local(
        self,
        msg: Message,
    ) -> None:

        if not self._is_local_interested(msg):
            return

        # Guardamos una copia para que un reenvío
        # posterior no modifique el estado observado.
        snapshot = Message.from_dict(
            msg.to_dict()
        )

        self.topic_state[
            (
                msg.topic,
                msg.channel,
            )
        ] = snapshot

        for callback in self.callbacks:
            callback(snapshot)

    def get_topic_state(
        self,
    ) -> dict[
        str,
        dict[
            str,
            dict[str, Any],
        ],
    ]:

        result = {}

        for (
            topic,
            channel,
        ), msg in self.topic_state.items():

            result.setdefault(
                topic,
                {},
            )[channel] = msg.to_dict()

        return result

    def handle_incoming(
        self,
        msg: Message,
        from_peer: str,
    ) -> None:

        if msg.msg_id in self.seen_ids:

            self._emit_event(
                "dropped",
                msg,
                {
                    "from_peer": from_peer,
                    "drop_reason": "duplicate",
                },
            )

            return

        local_view = self._local_view()

        forward = self.should_forward(
            msg,
            msg.topic,
            local_view,
        )

        self.seen_ids.add(
            msg.msg_id
        )

        msg.seen_by.add(
            self.peer_id
        )

        self._emit_event(
            "received",
            msg,
            {
                "from_peer": from_peer,
            },
        )

        self._deliver_local(msg)

        if forward:

            msg.ttl -= 1
            msg.hop_count += 1

            self._forward_message(
                msg,
                local_view,
            )

        elif msg.ttl <= 0:

            self._emit_event(
                "dropped",
                msg,
                {
                    "from_peer": from_peer,
                    "drop_reason":
                        "ttl_exhausted",
                },
            )

    def _forward_message(
        self,
        msg: Message,
        local_view: list[PeerInfo],
    ) -> None:

        interested = (
            self._get_interested_peers(
                msg.topic,
                local_view,
            )
        )

        targets = (
            self.select_forward_targets(
                msg,
                interested,
            )
        )

        for target in targets:

            if self.transport is None:
                continue

            sent = bool(
                self.transport.send_pubsub(
                    target,
                    msg,
                )
            )

            if sent:

                self._emit_event(
                    "forwarded",
                    msg,
                    {
                        "target_peer":
                            target.peer_id,
                    },
                )

            else:

                self._emit_event(
                    "dropped",
                    msg,
                    {
                        "target_peer":
                            target.peer_id,
                        "drop_reason":
                            "network_send_failed",
                    },
                )