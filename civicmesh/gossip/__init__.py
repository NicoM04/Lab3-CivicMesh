"""Capa de red / Gossip / Membership de CivicMesh (Rol 1).

Exporta el punto de entrada principal (``Node``) y los tipos de dominio
que otras capas pueden necesitar. La interfaz recomendada para consumidores
externos (Pub/Sub) es ``civicmesh.gossip.interfaces.PeerDirectory``.
"""

from civicmesh.gossip.bootstrap import load_hostfile, parse_hostfile, select_seeds
from civicmesh.gossip.config import GossipConfig
from civicmesh.gossip.gossip import GossipService
from civicmesh.gossip.membership import MembershipTable
from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.metrics import GossipMetrics, MembershipMetrics
from civicmesh.gossip.node import Node
from civicmesh.gossip.peer import PeerInfo, PeerStatus

__all__ = [
    "GossipConfig",
    "GossipMetrics",
    "GossipPayload",
    "GossipService",
    "MembershipMetrics",
    "MembershipTable",
    "Node",
    "PeerInfo",
    "PeerStatus",
    "load_hostfile",
    "parse_hostfile",
    "select_seeds",
]
