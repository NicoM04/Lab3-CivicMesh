"""Modelos de datos para Pub/Sub."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Message:
    """Mensaje que se propaga por la red."""
    topic: str
    channel: str
    payload: dict
    ttl: int
    priority: int
    origin: str
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    hop_count: int = 0
    # No usamos field(default_factory=set) como estado interno directamente,
    # sino para instanciación inicial.
    seen_by: set[str] = field(default_factory=set)


@dataclass
class Subscription:
    """Suscripción local a un tópico."""
    topic: str
    channels: set[str]
    include_neighbors: bool = False
