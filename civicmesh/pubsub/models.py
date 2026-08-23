"""Modelos de datos para Pub/Sub."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """Mensaje que se propaga por la red."""

    topic: str
    channel: str
    payload: dict[str, Any]
    ttl: int
    priority: int
    origin: str
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    hop_count: int = 0
    seen_by: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Convierte el mensaje a un diccionario serializable en JSON."""
        return {
            "topic": self.topic,
            "channel": self.channel,
            "payload": self.payload,
            "ttl": self.ttl,
            "priority": self.priority,
            "origin": self.origin,
            "msg_id": self.msg_id,
            "timestamp": self.timestamp,
            "hop_count": self.hop_count,
            "seen_by": sorted(self.seen_by),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Message":
        """Reconstruye un Message desde un diccionario JSON."""
        return Message(
            topic=str(data["topic"]),
            channel=str(data["channel"]),
            payload=dict(data.get("payload", {})),
            ttl=int(data["ttl"]),
            priority=int(data["priority"]),
            origin=str(data["origin"]),
            msg_id=str(data["msg_id"]),
            timestamp=float(data["timestamp"]),
            hop_count=int(data.get("hop_count", 0)),
            seen_by=set(data.get("seen_by", [])),
        )


@dataclass
class Subscription:
    """Suscripción local a un tópico."""

    topic: str
    channels: set[str]
    include_neighbors: bool = False