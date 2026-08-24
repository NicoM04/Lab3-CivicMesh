"""Runtime mínimo que integra Gossip, Pub/Sub, TCP y métricas."""

from __future__ import annotations

import threading
import time

from pathlib import Path
from typing import Any, Callable

from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.node import Node
from civicmesh.gossip.peer import PeerInfo, PeerStatus
from civicmesh.network import TCPTransport
from civicmesh.pubsub.pubsub import PubSub
from civicmesh.pubsub.models import Message


class PeerRuntime:
    """Peer ejecutable de CivicMesh."""

    def __init__(
        self,
        peer_id: str,
        host: str,
        port: int,
        *,
        partial_view_size: int = 10,
        gossip_fanout: int = 2,
        gossip_interval: float = 1.0,
        failure_timeout: float = 5.0,
        pubsub_config: dict | None = None,
        metrics_dir: str | Path | None = None,
        simulate_first_send_failure: bool = False,
    ) -> None:

        self.peer_id = peer_id

        self.gossip_interval = float(
            gossip_interval
        )

        self.failure_timeout = float(
            failure_timeout
        )

        self.metrics_dir = (
            Path(metrics_dir)
            if metrics_dir is not None
            else None
        )

        self.node = Node(
            self_info=PeerInfo(
                peer_id=peer_id,
                host=host,
                port=int(port),
            ),
            partial_view_size=(
                partial_view_size
            ),
            fanout=gossip_fanout,
        )

        self.transport = TCPTransport(
            host,
            int(port),
            peer_id=peer_id,
            simulate_first_send_failure=(
                simulate_first_send_failure
            ),
        )

        self.pubsub = PubSub(
            peer_id=peer_id,
            gossip_layer=self.node,
            config=pubsub_config,
            transport=self.transport,
        )

        self.pubsub.on_message(
            self._on_local_message
        )

        self.pubsub.on_event(
            self._on_pubsub_event
        )

        self._maintenance_thread: (
            threading.Thread | None
        ) = None

        self._stop_event = (
            threading.Event()
        )

        self._message_callbacks: list[
            Callable[
                [Message],
                None,
            ]
        ] = []

    @property
    def self_info(
        self,
    ) -> PeerInfo:

        return self.node.self_info

    def start(self) -> None:

        self.transport.start(
            self._handle_envelope
        )

        self._stop_event.clear()

        self._maintenance_thread = (
            threading.Thread(
                target=(
                    self._maintenance_loop
                ),
                name=(
                    "civicmesh-maintenance-"
                    f"{self.peer_id}"
                ),
                daemon=True,
            )
        )

        self._maintenance_thread.start()

    def stop(self) -> None:

        self._stop_event.set()

        if (
            self._maintenance_thread
            is not None
        ):

            self._maintenance_thread.join(
                timeout=1.0
            )

        self.transport.stop()

    def join(
        self,
        seed: PeerInfo,
    ) -> None:
        """JOIN real contra un seed."""

        now = time.time()

        self.node.join(
            seed,
            now=now,
        )

        payload = (
            self.transport.request_join(
                seed,
                self.node.self_info,
            )
        )

        self.node.handle_join_response(
            payload,
            now=time.time(),
        )

    def subscribe(
        self,
        topic: str,
        channels: set[str],
        include_neighbors: bool = False,
    ) -> None:

        self.pubsub.subscribe(
            topic,
            channels,
            include_neighbors=(
                include_neighbors
            ),
        )

    def publish(
        self,
        topic: str,
        channel: str,
        payload: dict,
        priority: int | None = None,
    ) -> Message:

        return self.pubsub.publish(
            topic,
            channel,
            payload,
            priority=priority,
        )

    def on_message(
        self,
        callback: Callable[
            [Message],
            None,
        ],
    ) -> None:

        self._message_callbacks.append(
            callback
        )

    def get_topic_state(
        self,
    ) -> dict[
        str,
        dict[
            str,
            dict[str, Any],
        ],
    ]:

        return (
            self.pubsub
            .get_topic_state()
        )

    def _handle_envelope(
        self,
        envelope: dict[str, Any],
    ) -> dict[str, Any] | None:

        message_type = envelope.get(
            "type"
        )

        now = time.time()

        if message_type == "join_request":

            new_peer = PeerInfo.from_dict(
                envelope["peer"]
            )

            payload = (
                self.node
                .handle_join_request(
                    new_peer,
                    now=now,
                )
            )

            return {
                "type": "join_response",
                "payload":
                    payload.to_dict(),
            }

        if message_type == "gossip":

            payload = (
                GossipPayload.from_dict(
                    envelope["payload"]
                )
            )

            self.node.handle_gossip_message(
                payload,
                now=now,
            )

            return None

        if message_type == "pubsub":

            msg = Message.from_dict(
                envelope["message"]
            )

            from_peer = str(
                envelope.get(
                    "from_peer",
                    msg.origin,
                )
            )

            self.node.membership.touch(
                from_peer,
                now=now,
            )

            self.pubsub.handle_incoming(
                msg,
                from_peer=from_peer,
            )

            return None

        raise ValueError(
            "Tipo de mensaje de red "
            f"desconocido: {message_type}"
        )

    def _maintenance_loop(
        self,
    ) -> None:

        while not self._stop_event.wait(
            self.gossip_interval
        ):

            now = time.time()

            self.node.detect_failed_peers(
                now,
                self.failure_timeout,
            )

            self.node.gossip.run_round(
                now,
                transport=self.transport,
            )

            self._write_network_metric(
                now
            )

    def _write_metric(
        self,
        metric: dict[str, Any],
    ) -> None:

        if self.metrics_dir is None:
            return

        # Utilizamos exactamente el almacenamiento
        # JSONL creado en tu Rol 4.
        from civicmesh.analytics import (
            write_metric,
        )

        write_metric(
            self.metrics_dir,
            self.peer_id,
            metric,
        )

    def _write_network_metric(
        self,
        now: float,
    ) -> None:

        gossip = (
            self.node
            .get_gossip_metrics()
        )

        # Para las métricas de red consideramos
        # únicamente los peers de la malla.
        # Los publicadores quedan fuera del cálculo.
        known_mesh_peers = [
            peer
            for peer
            in self.node.get_known_peers()
            if not peer.peer_id.startswith(
                "publisher-"
            )
        ]

        alive_peers = sum(
            1
            for peer
            in known_mesh_peers
            if peer.status
            is PeerStatus.ALIVE
        )

        dead_peers = sum(
            1
            for peer
            in known_mesh_peers
            if peer.status
            is PeerStatus.DEAD
        )

        # Membership no incluye al propio peer.
        if not self.peer_id.startswith(
            "publisher-"
        ):
            alive_peers += 1

        self._write_metric(
            {
                "record_type":
                    "network_state",

                "peer_id":
                    self.peer_id,

                "timestamp":
                    now,

                "sim_time":
                    now,

                "known_peers":
                    alive_peers
                    + dead_peers,

                "alive_peers":
                    alive_peers,

                "dead_peers":
                    dead_peers,

                "gossip_rounds":
                    gossip.rounds_run,

                "gossip_messages_sent":
                    gossip.messages_sent,

                "gossip_messages_received":
                    gossip.messages_received,
            }
        )

    def _on_local_message(
        self,
        msg: Message,
    ) -> None:

        payload = msg.payload

        if (
            "value" in payload
            and
            "domain" in payload
        ):

            self._write_metric(
                {
                    "record_type":
                        "topic_state",

                    "peer_id":
                        self.peer_id,

                    "timestamp":
                        time.time(),

                    "sim_time":
                        payload.get(
                            "t",
                            0,
                        ),

                    "domain":
                        payload["domain"],

                    "topic":
                        msg.topic,

                    "channel":
                        msg.channel,

                    "metric":
                        payload.get(
                            "metric"
                        ),

                    "value":
                        payload["value"],

                    "unit":
                        payload.get(
                            "unit"
                        ),
                }
            )

        for callback in (
            self._message_callbacks
        ):

            callback(msg)

    def _on_pubsub_event(
        self,
        event: str,
        msg: Message,
        extra: dict[str, Any],
    ) -> None:

        payload = msg.payload

        record = {
            "record_type":
                "message_event",

            "peer_id":
                self.peer_id,

            "timestamp":
                time.time(),

            "sim_time":
                payload.get(
                    "t",
                    0,
                ),

            "domain":
                payload.get(
                    "domain"
                ),

            "topic":
                msg.topic,

            "channel":
                msg.channel,

            "event":
                event,

            "msg_id":
                msg.msg_id,

            "origin":
                msg.origin,

            "hop_count":
                msg.hop_count,

            "ttl":
                msg.ttl,

            "priority":
                msg.priority,
        }

        record.update(extra)

        self._write_metric(
            record
        )