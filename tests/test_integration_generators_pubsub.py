"""Test de integración entre Generadores (Rol 3) y Capa PubSub/Gossip (Rol 1 y 2).

Verifica el flujo end-to-end obligatorio de la Sección 7.2 del enunciado:
1. Publicación y recepción de eventos generados estocásticamente en Dominio A (Delitos de Poisson).
2. Publicación y recepción de series reproducidas en Dominio B (Replay de Calidad del Aire).
3. Integración de rumores recibidos por pubsub en los modelos de percepción ciudadana (A y B).
4. Verificación de reglas de reenvío (should_forward), decremento de TTL y entrega a vecinos geográficos.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from civicmesh.generators.perception import (
    PerceptionModelA,
    PerceptionModelB,
    aggregate_gossip,
)
from civicmesh.generators.poisson import CrimeGenerator
from civicmesh.generators.replay import AirQualityReplay
from civicmesh.gossip.peer import PeerInfo, PeerStatus
from civicmesh.pubsub.models import Message
from civicmesh.pubsub.pubsub import PubSub


def make_peer(peer_id: str, subscribed_topics: list[str]) -> PeerInfo:
    return PeerInfo(
        peer_id=peer_id,
        host="127.0.0.1",
        port=9000,
        status=PeerStatus.ALIVE,
        last_seen=100.0,
        subscribed_topics=frozenset(subscribed_topics),
    )


class TestMeshGeneratorsIntegration(unittest.TestCase):
    """Pruebas de integración de generadores y modelos de percepción sobre la malla PubSub."""

    def setUp(self) -> None:
        self.mock_gossip_peer1 = Mock()
        self.mock_gossip_peer2 = Mock()

        # Peer 1 ubicado en santiago
        self.pubsub_peer1 = PubSub(peer_id="peer-santiago", gossip_layer=self.mock_gossip_peer1)
        # Peer 2 ubicado en providencia (vecina de santiago)
        self.pubsub_peer2 = PubSub(peer_id="peer-providencia", gossip_layer=self.mock_gossip_peer2)

        # Peer 1 conoce a Peer 2 suscrito a providencia
        self.peer2_info = make_peer("peer-providencia", ["providencia"])
        self.peer1_info = make_peer("peer-santiago", ["santiago"])

        self.mock_gossip_peer1.get_known_peers.return_value = [self.peer2_info]
        self.mock_gossip_peer2.get_known_peers.return_value = [self.peer1_info]

    def test_domain_a_poisson_to_pubsub_and_perception(self) -> None:
        """Dominio A: Delitos generados se publican en canal objetivo y alimentan la percepción."""
        crime_gen = CrimeGenerator(seed=42)
        perception_santiago = PerceptionModelA(comuna="Santiago", seed=42)
        perception_providencia = PerceptionModelA(comuna="Providencia", seed=42)

        received_messages_peer2: list[Message] = []
        self.pubsub_peer2.on_message(lambda msg: received_messages_peer2.append(msg))
        self.pubsub_peer2.subscribe("providencia", {"objetivo", "subjetivo"}, include_neighbors=True)

        # Paso t = 1.0: Peer 1 genera evento objetivo de delitos en Santiago
        crime_event = crime_gen.generate_event("Santiago", t=1.0)
        self.assertEqual(crime_event["comuna"], "Santiago")
        self.assertGreaterEqual(crime_event["total"], 0)

        # Peer 1 publica en canal objetivo
        obj_msg = self.pubsub_peer1.publish(
            topic="santiago",
            channel="objetivo",
            payload=crime_event,
        )
        self.assertEqual(obj_msg.channel, "objetivo")
        self.assertEqual(obj_msg.ttl, 5)

        # Simulación de entrega en la red hacia Peer 2
        self.pubsub_peer2.handle_incoming(obj_msg, from_peer="peer-santiago")

        # Peer 2 debe haber recibido el mensaje objetivo por ser vecina de Santiago
        self.assertEqual(len(received_messages_peer2), 1)
        self.assertEqual(received_messages_peer2[0].payload["comuna"], "Santiago")

        # Peer 1 calcula su percepción local con R_c(t)
        p_c_santiago = perception_santiago.update(r_c=float(crime_event["total"]))
        self.assertGreaterEqual(p_c_santiago, 0.0)
        self.assertLessEqual(p_c_santiago, 1.0)

        # Peer 1 publica la percepción en el canal subjetivo
        subj_msg = self.pubsub_peer1.publish(
            topic="santiago",
            channel="subjetivo",
            payload={"comuna": "Santiago", "t": 1.0, "p_c": p_c_santiago},
        )
        self.pubsub_peer2.handle_incoming(subj_msg, from_peer="peer-santiago")

        # Peer 2 recibe el rumor subjetivo
        self.assertEqual(len(received_messages_peer2), 2)
        received_rumor = received_messages_peer2[1].payload["p_c"]

        # Peer 2 actualiza su percepción en Providencia considerando el rumor recibido por gossip
        p_c_providencia = perception_providencia.update(r_c=1.0, gossip_rumors=[received_rumor])
        self.assertGreaterEqual(p_c_providencia, 0.0)
        self.assertLessEqual(p_c_providencia, 1.0)

    def test_domain_b_replay_to_pubsub_and_peak_perception(self) -> None:
        """Dominio B: Replay de calidad del aire se publica en canal objetivo y modela picos."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        perception_model = PerceptionModelB(comuna="Santiago", seed=42)

        received_messages: list[Message] = []
        self.pubsub_peer2.on_message(lambda msg: received_messages.append(msg))
        self.pubsub_peer2.subscribe("santiago", {"objetivo", "subjetivo"}, include_neighbors=False)

        # Paso t = 0: Muestra base
        sample_0 = replay.get_value("Santiago", step=0)
        msg_0 = self.pubsub_peer1.publish("santiago", "objetivo", sample_0)
        self.pubsub_peer2.handle_incoming(msg_0, from_peer="peer-santiago")

        p_0 = perception_model.update(v_c=sample_0["pm2_5"])
        self.assertGreater(p_0, 0.0)

        # Paso t = 10: Siguiente muestra
        sample_1 = replay.get_value("Santiago", step=10)
        msg_1 = self.pubsub_peer1.publish("santiago", "objetivo", sample_1)
        self.pubsub_peer2.handle_incoming(msg_1, from_peer="peer-santiago")

        p_1 = perception_model.update(v_c=sample_1["pm2_5"])
        self.assertGreater(p_1, 0.0)
        self.assertEqual(len(received_messages), 2)

    def test_forwarding_and_deduplication_integrity(self) -> None:
        """Verifica que mensajes generados decrecen su TTL y no se duplican."""
        msg = self.pubsub_peer1.publish("santiago", "objetivo", {"test": 123})
        initial_ttl = msg.ttl

        # Primera entrega a peer 2 -> should_forward True
        local_view = [self.peer1_info]
        self.assertTrue(self.pubsub_peer2.should_forward(msg, "santiago", local_view))

        self.pubsub_peer2.handle_incoming(msg, from_peer="peer-santiago")
        self.assertEqual(msg.ttl, initial_ttl - 1)
        self.assertEqual(msg.hop_count, 1)

        # Segundo intento de entrega con el mismo mensaje -> deduplicado (no reenvía)
        self.assertFalse(self.pubsub_peer2.should_forward(msg, "santiago", local_view))


if __name__ == "__main__":
    unittest.main()
