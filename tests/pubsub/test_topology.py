"""Tests unitarios para topología geográfica y normalización de tópicos."""

import unittest

from civicmesh.pubsub.topology import COMUNA_ADYACENCIA, normalize_topic


class TestTopicNormalization(unittest.TestCase):
    def test_normalize_simple_names(self) -> None:
        self.assertEqual(normalize_topic("Santiago"), "santiago")
        self.assertEqual(normalize_topic("  Providencia  "), "providencia")
        self.assertEqual(normalize_topic("las_condes"), "las_condes")

    def test_normalize_accents_and_diacritics(self) -> None:
        self.assertEqual(normalize_topic("Ñuñoa"), "nunoa")
        self.assertEqual(normalize_topic("Estación Central"), "estacion_central")
        self.assertEqual(normalize_topic("Maipú"), "maipu")
        self.assertEqual(normalize_topic("Peñalolén"), "penalolen")
        self.assertEqual(normalize_topic("San Joaquín"), "san_joaquin")
        self.assertEqual(normalize_topic("Conchalí"), "conchali")

    def test_normalize_spaces_and_special_characters(self) -> None:
        self.assertEqual(normalize_topic("Puente Alto"), "puente_alto")
        self.assertEqual(normalize_topic("Pedro Aguirre Cerda"), "pedro_aguirre_cerda")
        self.assertEqual(normalize_topic("La Florida"), "la_florida")
        self.assertEqual(normalize_topic("Lo Barnechea!"), "lo_barnechea")
        self.assertEqual(normalize_topic("Comuna-123"), "comuna_123")


class TestComunaAdyacencia(unittest.TestCase):
    def test_adyacencia_contains_expected_comunas(self) -> None:
        self.assertIn("santiago", COMUNA_ADYACENCIA)
        self.assertIn("providencia", COMUNA_ADYACENCIA)
        self.assertIn("nunoa", COMUNA_ADYACENCIA)
        self.assertIn("las_condes", COMUNA_ADYACENCIA)
        self.assertIn("puente_alto", COMUNA_ADYACENCIA)
        self.assertIn("maipu", COMUNA_ADYACENCIA)

    def test_all_comunas_are_normalized_keys(self) -> None:
        for comuna in COMUNA_ADYACENCIA:
            self.assertEqual(comuna, normalize_topic(comuna))
            for vecino in COMUNA_ADYACENCIA[comuna]:
                self.assertEqual(vecino, normalize_topic(vecino))

    def test_santiago_neighbors(self) -> None:
        vecinos_santiago = COMUNA_ADYACENCIA["santiago"]
        self.assertIn("providencia", vecinos_santiago)
        self.assertIn("estacion_central", vecinos_santiago)
        self.assertIn("recoleta", vecinos_santiago)


if __name__ == "__main__":
    unittest.main()
