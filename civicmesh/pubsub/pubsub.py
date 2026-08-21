"""Lógica principal de Publish/Subscribe."""

from typing import Any, Callable, Optional
from civicmesh.pubsub.models import Message, Subscription
from civicmesh.pubsub.topology import COMUNA_ADYACENCIA
from civicmesh.pubsub.config import CHANNEL_CONFIG
from civicmesh.gossip.peer import PeerInfo


class PubSub:
    def __init__(self, peer_id: str, gossip_layer: Any, config: dict = None):
        self.peer_id = peer_id
        self.gossip_layer = gossip_layer
        self.config = config or CHANNEL_CONFIG
        
        self.subscriptions: dict[str, Subscription] = {}
        self.seen_ids: set[str] = set()
        self.callbacks: list[Callable[[Message], None]] = []

    def subscribe(self, topic: str, channels: set[str], include_neighbors: bool = False) -> None:
        self.subscriptions[topic] = Subscription(
            topic=topic,
            channels=channels,
            include_neighbors=include_neighbors
        )

    def unsubscribe(self, topic: str) -> None:
        if topic in self.subscriptions:
            del self.subscriptions[topic]

    def publish(self, topic: str, channel: str, payload: dict, priority: Optional[int] = None) -> Message:
        if channel not in self.config:
            raise ValueError(f"Canal desconocido: {channel}")
            
        cfg = self.config[channel]
        msg = Message(
            topic=topic,
            channel=channel,
            payload=payload,
            ttl=cfg["ttl"],
            priority=priority if priority is not None else cfg["priority"],
            origin=self.peer_id
        )
        msg.seen_by.add(self.peer_id)
        self.seen_ids.add(msg.msg_id)
        
        # Enviar a la malla
        local_view = self.gossip_layer.get_known_peers() if self.gossip_layer else []
        self._forward_message(msg, local_view)
        return msg

    def on_message(self, callback: Callable[[Message], None]) -> None:
        self.callbacks.append(callback)

    def _get_interested_peers(self, topic: str, local_view: list[PeerInfo]) -> list[PeerInfo]:
        interested_peers = []
        for p in local_view:
            if topic in p.subscribed_topics:
                interested_peers.append(p)
                continue
                
            # Revisar si es vecino de algún tópico al que está suscrito
            for subscribed_topic in p.subscribed_topics:
                if topic in COMUNA_ADYACENCIA.get(subscribed_topic, []):
                    interested_peers.append(p)
                    break
        return interested_peers

    def should_forward(self, msg: Message, topic: str, local_view: list[PeerInfo]) -> bool:
        # 1. TTL agotado
        if msg.ttl <= 0:
            return False
            
        # 2. Ya lo vi (deduplicación)
        if msg.msg_id in self.seen_ids:
            return False
            
        # 3. Interés geográfico
        interested_peers = self._get_interested_peers(topic, local_view)
        if not interested_peers:
            return False
            
        return True

    def select_forward_targets(self, msg: Message, interested_peers: list[PeerInfo]) -> list[PeerInfo]:
        if msg.channel not in self.config:
            return []
            
        fanout = self.config[msg.channel].get("fanout", 1)
        
        # Filtrar peers que ya vieron el msg
        valid_peers = [p for p in interested_peers if p.peer_id not in msg.seen_by]
        
        # Ordenar para priorizar (ej. peers activos más recientemente)
        valid_peers.sort(key=lambda p: p.last_seen, reverse=True)
        
        return valid_peers[:fanout]

    def _is_local_interested(self, msg: Message) -> bool:
        if msg.topic in self.subscriptions:
            sub = self.subscriptions[msg.topic]
            if msg.channel in sub.channels:
                return True
                
        # Revisar si estamos suscritos a un vecino con include_neighbors=True
        for sub_topic, sub in self.subscriptions.items():
            if sub.include_neighbors and msg.channel in sub.channels:
                if msg.topic in COMUNA_ADYACENCIA.get(sub_topic, []):
                    return True
        return False

    def handle_incoming(self, msg: Message, from_peer: str) -> None:
        # Deduplica
        if msg.msg_id in self.seen_ids:
            return
            
        self.seen_ids.add(msg.msg_id)
        msg.seen_by.add(self.peer_id)
        
        # Interés local
        if self._is_local_interested(msg):
            for cb in self.callbacks:
                cb(msg)
                
        # Decide reenvío
        local_view = self.gossip_layer.get_known_peers() if self.gossip_layer else []
        if self.should_forward(msg, msg.topic, local_view):
            msg.ttl -= 1
            msg.hop_count += 1
            self._forward_message(msg, local_view)

    def _forward_message(self, msg: Message, local_view: list[PeerInfo]) -> None:
        interested = self._get_interested_peers(msg.topic, local_view)
        targets = self.select_forward_targets(msg, interested)
        
        for target in targets:
            # Aquí es el punto de extensión para la capa de red
            # target representa a quién debe enviarse el msg
            pass
