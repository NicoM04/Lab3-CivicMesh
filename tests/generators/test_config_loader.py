"""Tests unitarios para config_loader y utilidades de reproducibilidad."""

import unittest
from pathlib import Path

from civicmesh.generators.config_loader import get_rng, load_config


class TestConfigLoader(unittest.TestCase):
    """Pruebas para la carga de configuración y generación de RNG deterministas."""

    def test_load_default_config(self) -> None:
        """Verifica que config.yaml se cargue correctamente con todas las secciones."""
        config = load_config("config.yaml")
        self.assertIsInstance(config, dict)
        self.assertIn("seed", config)
        self.assertIn("comunas", config)
        self.assertIn("dominio_a", config)
        self.assertIn("dominio_b", config)

        self.assertEqual(config["seed"], 42)
        self.assertIn("Santiago", config["comunas"])
        self.assertIn("lambdas", config["dominio_a"])
        self.assertIn("percepcion", config["dominio_a"])
        self.assertIn("dataset_path", config["dominio_b"])
        self.assertIn("percepcion", config["dominio_b"])

    def test_load_nonexistent_config_raises_error(self) -> None:
        """Verifica que un archivo inexistente lance FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_config("nonexistent_path_12345.yaml")

    def test_rng_determinism(self) -> None:
        """Verifica que el mismo seed y comuna produzcan exactamente los mismos números."""
        rng1 = get_rng(42, "Santiago", "poisson")
        rng2 = get_rng(42, "Santiago", "poisson")

        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]

        self.assertEqual(seq1, seq2)

    def test_rng_different_seeds(self) -> None:
        """Verifica que semillas diferentes generen secuencias distintas."""
        rng1 = get_rng(42, "Santiago")
        rng2 = get_rng(999, "Santiago")

        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]

        self.assertNotEqual(seq1, seq2)

    def test_rng_different_comunas(self) -> None:
        """Verifica que distintas comunas tengan secuencias independientes con la misma semilla base."""
        rng1 = get_rng(42, "Santiago")
        rng2 = get_rng(42, "Puente_Alto")

        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]

        self.assertNotEqual(seq1, seq2)

    def test_rng_extra_parameter(self) -> None:
        """Verifica que el parámetro extra modifique el stream de forma determinista."""
        rng1 = get_rng(42, "Santiago", "extra1")
        rng2 = get_rng(42, "Santiago", "extra2")

        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]

        self.assertNotEqual(seq1, seq2)


if __name__ == "__main__":
    unittest.main()
