"""Integración pequeña de Gossip con 3 peers en memoria (sin sockets).

No es el escenario multi-proceso completo que exige el laboratorio (ese
requiere transporte real, ver docs/gossip.md#preparación-para-integración-multi-peer):
aquí los tres ``Node`` viven en el mismo proceso y el "envío" de un mensaje
es simplemente invocar ``handle_gossip_message`` en el destinatario con el
payload construido por el emisor. Esto alcanza para demostrar, de forma
rápida y determinista, que la lógica de dominio (JOIN, descubrimiento
transitivo, convergencia y propagación de fallos) funciona de punta a
punta entre varios peers antes de que exista transporte real.
"""

import unittest

from civicmesh.gossip.node import Node
from civicmesh.gossip.peer import PeerInfo


def make_peer(peer_id: str, port: int = 9000) -> PeerInfo:
    return PeerInfo(peer_id=peer_id, host="127.0.0.1", port=port)


def deliver(sender: Node, receiver: Node, now: float) -> None:
    """Simula el envío de un mensaje de gossip de ``sender`` a
    ``receiver`` a esa hora local, sin transporte real."""
    payload = sender.gossip.build_payload(now)
    receiver.handle_gossip_message(payload, now=now)


def join(newcomer: Node, seed: Node, now: float) -> None:
    """Simula un handshake de JOIN completo entre dos nodos en memoria."""
    newcomer.join(seed.self_info, now=now)
    response = seed.handle_join_request(newcomer.self_info, now=now)
    newcomer.handle_join_response(response, now=now)


def mutual_gossip(node_x: Node, node_y: Node, now: float) -> None:
    """Intercambio de gossip en ambos sentidos, a la misma hora local."""
    deliver(node_x, node_y, now)
    deliver(node_y, node_x, now)


class ThreePeerMeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node_a = Node(self_info=make_peer("A", 9001), partial_view_size=5, fanout=2)
        self.node_b = Node(self_info=make_peer("B", 9002), partial_view_size=5, fanout=2)
        self.node_c = Node(self_info=make_peer("C", 9003), partial_view_size=5, fanout=2)

    def test_join_then_gossip_converges_to_full_mutual_knowledge(self) -> None:
        # C se une usando B como seed; A se une usando B como seed.
        join(self.node_c, self.node_b, now=0.0)
        join(self.node_a, self.node_b, now=0.0)

        # En este punto C todavía no conoce a A (nunca hablaron entre sí).
        self.assertNotIn("A", [p.peer_id for p in self.node_c.get_known_peers()])

        # B le hace gossip a C: C debería descubrir a A transitivamente,
        # sin haber tenido nunca contacto directo con A.
        deliver(self.node_b, self.node_c, now=1.0)

        known_by_c = {p.peer_id for p in self.node_c.get_known_peers()}
        self.assertEqual(known_by_c, {"A", "B"})

        # Vista "eventualmente estable": los tres se conocen entre sí.
        self.assertEqual({p.peer_id for p in self.node_a.get_known_peers()}, {"B", "C"})
        self.assertEqual({p.peer_id for p in self.node_b.get_known_peers()}, {"A", "C"})
        self.assertEqual({p.peer_id for p in self.node_c.get_known_peers()}, {"A", "B"})

    def test_partial_views_never_include_self_and_have_no_duplicates(self) -> None:
        join(self.node_c, self.node_b, now=0.0)
        join(self.node_a, self.node_b, now=0.0)
        deliver(self.node_b, self.node_c, now=1.0)
        deliver(self.node_c, self.node_a, now=2.0)

        for node in (self.node_a, self.node_b, self.node_c):
            view_ids = [p.peer_id for p in node.get_partial_view()]
            self.assertNotIn(node.self_info.peer_id, view_ids)
            self.assertEqual(len(view_ids), len(set(view_ids)))

    def test_one_peer_failing_does_not_strand_the_others(self) -> None:
        join(self.node_c, self.node_b, now=0.0)
        join(self.node_a, self.node_b, now=0.0)
        deliver(self.node_b, self.node_c, now=1.0)

        # A deja de emitir señales a partir de aquí (nunca más se lo
        # "toca"). B y C, en cambio, siguen intercambiando gossip y se
        # mantienen frescos mutuamente hasta justo antes de la detección.
        mutual_gossip(self.node_b, self.node_c, now=99.0)

        newly_dead = self.node_b.detect_failed_peers(now=100.0, timeout_seconds=10.0)
        self.assertEqual(newly_dead, ["A"])

        # A ya no es candidato de gossip para B...
        self.assertNotIn("A", [p.peer_id for p in self.node_b.gossip.select_gossip_targets()])
        # ...pero B y C siguen siendo destinos válidos entre sí.
        self.assertIn("C", [p.peer_id for p in self.node_b.gossip.select_gossip_targets()])

        # El veredicto de B se propaga a C vía gossip (last-writer-wins).
        deliver(self.node_b, self.node_c, now=101.0)
        alive_for_c = {p.peer_id for p in self.node_c.get_alive_peers()}
        self.assertEqual(alive_for_c, {"B"})

        # La malla no se destruye: B y C se siguen viendo vivos entre sí.
        self.assertIn("C", [p.peer_id for p in self.node_b.get_alive_peers()])
        self.assertIn("B", [p.peer_id for p in self.node_c.get_alive_peers()])


if __name__ == "__main__":
    unittest.main()
