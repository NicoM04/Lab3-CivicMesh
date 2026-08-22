"""Tests unitarios para CrimeGenerator (Dominio A - Delitos)."""

import math
import unittest

from civicmesh.generators.poisson import DEFAULT_LAMBDAS, CrimeGenerator


class TestCrimeGenerator(unittest.TestCase):
    """Pruebas para el generador estocástico de Poisson."""

    def test_reproducibility_with_same_seed(self) -> None:
        """Criterio de aceptación: misma semilla produce exactamente los mismos eventos."""
        gen1 = CrimeGenerator(seed=42)
        gen2 = CrimeGenerator(seed=42)

        for t in range(20):
            event1 = gen1.generate_event("Santiago", t=float(t))
            event2 = gen2.generate_event("Santiago", t=float(t))
            self.assertEqual(event1, event2)

    def test_different_seeds_produce_different_events(self) -> None:
        """Semillas diferentes producen secuencias distintas."""
        gen1 = CrimeGenerator(seed=42)
        gen2 = CrimeGenerator(seed=999)

        events1 = [gen1.generate_event("Santiago", t=float(t)) for t in range(20)]
        events2 = [gen2.generate_event("Santiago", t=float(t)) for t in range(20)]

        self.assertNotEqual(events1, events2)

    def test_event_structure_and_total(self) -> None:
        """Verifica la estructura del payload del evento y que total == R_c(t)."""
        gen = CrimeGenerator(seed=42)
        event = gen.generate_event("Puente_Alto", t=1.0)

        self.assertEqual(event["comuna"], "Puente_Alto")
        self.assertEqual(event["t"], 1.0)
        self.assertIn("counts", event)
        self.assertIn("total", event)

        counts = event["counts"]
        self.assertEqual(event["total"], sum(counts.values()))
        self.assertIn("robo", counts)
        self.assertIn("hurto", counts)
        self.assertIn("asalto", counts)
        for count in counts.values():
            self.assertGreaterEqual(count, 0)
            self.assertIsInstance(count, int)

    def test_all_comunas_supported(self) -> None:
        """Verifica que el generador funcione para todas las comunas por defecto."""
        gen = CrimeGenerator(seed=42)
        comunas = gen.get_comunas()
        self.assertIn("Santiago", comunas)
        self.assertIn("Puente_Alto", comunas)
        self.assertIn("Maipu", comunas)
        self.assertIn("La_Florida", comunas)
        self.assertIn("Pudahuel", comunas)

        for comuna in comunas:
            counts = gen.generate(comuna, t=0.0)
            self.assertIsInstance(counts, dict)
            self.assertEqual(set(counts.keys()), {"robo", "hurto", "asalto"})

    def test_unknown_comuna_raises_error(self) -> None:
        """Verifica que solicitar una comuna no configurada lance KeyError."""
        gen = CrimeGenerator(seed=42)
        with self.assertRaises(KeyError):
            gen.generate("ComunaInexistente", t=0.0)

    def test_reset_restores_initial_sequence(self) -> None:
        """Verifica que reset() reinicie la secuencia determinista."""
        gen = CrimeGenerator(seed=42)
        seq1 = [gen.generate_event("Santiago", t=float(t)) for t in range(10)]

        gen.reset()
        seq2 = [gen.generate_event("Santiago", t=float(t)) for t in range(10)]

        self.assertEqual(seq1, seq2)

    def test_poisson_mean_convergence(self) -> None:
        """Verifica estadísticamente que la media empírica converja a λ * Δt."""
        lambdas = {"TestCity": {"robo": 2.0}}
        delta_t = 1.5
        expected_mean = 2.0 * 1.5  # 3.0
        n_samples = 5000

        gen = CrimeGenerator(seed=123, lambdas=lambdas, delta_t=delta_t)
        samples = [gen.generate("TestCity", t=float(i))["robo"] for i in range(n_samples)]

        sample_mean = sum(samples) / n_samples
        # Para Poisson, Var(X) = λ * Δt = 3.0. Std error = sqrt(3.0 / 5000) ≈ 0.024
        std_error = math.sqrt(expected_mean / n_samples)
        self.assertAlmostEqual(sample_mean, expected_mean, delta=3.5 * std_error)


if __name__ == "__main__":
    unittest.main()
