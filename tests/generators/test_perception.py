"""Tests unitarios para los modelos de percepción subjetiva (PerceptionModelA y PerceptionModelB)."""

import unittest

from civicmesh.generators.perception import (
    PerceptionModelA,
    PerceptionModelB,
    aggregate_gossip,
    sigmoid,
)


class TestAggregateGossip(unittest.TestCase):
    """Pruebas para la función de agregación de rumores."""

    def test_empty_or_none(self) -> None:
        self.assertEqual(aggregate_gossip([]), 0.0)
        self.assertEqual(aggregate_gossip(None), 0.0)

    def test_average_calculation(self) -> None:
        self.assertAlmostEqual(aggregate_gossip([0.2, 0.4, 0.6]), 0.4)
        self.assertAlmostEqual(aggregate_gossip([100.0]), 100.0)



class TestPerceptionModelA(unittest.TestCase):
    """Pruebas para el modelo de percepción del Dominio A (Inseguridad)."""

    def test_initial_conditions(self) -> None:
        model = PerceptionModelA(comuna="Santiago", seed=42)
        self.assertEqual(model.m_c, 0.0)
        self.assertEqual(len(model.history), 0)

    def test_output_range_in_zero_one(self) -> None:
        """Verifica que la salida pertenezca estrictamente al intervalo [0, 1]."""
        model = PerceptionModelA(comuna="Santiago", seed=42)
        # Probamos con valores extremos de delitos y rumores
        for r in [0, 1, 10, 100, 1000]:
            p = model.update(r_c=r, gossip_rumors=[0.9, 1.0])
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_reproducibility_with_seed(self) -> None:
        """Verifica que con la misma semilla se obtenga exactamente la misma secuencia de percepción."""
        m1 = PerceptionModelA(comuna="Santiago", seed=42)
        m2 = PerceptionModelA(comuna="Santiago", seed=42)

        stimuli = [2, 0, 1, 3, 5, 0, 1]
        p_seq1 = [m1.update(r_c=r, gossip_rumors=[0.5]) for r in stimuli]
        p_seq2 = [m2.update(r_c=r, gossip_rumors=[0.5]) for r in stimuli]

        self.assertEqual(p_seq1, p_seq2)

    def test_gossip_amplifies_insecurity(self) -> None:
        """Verifica que la presencia de rumores altos incremente la sensación de inseguridad."""
        # Fijamos sigma_epsilon = 0.0 para evaluar puramente el efecto determinista
        m_no_gossip = PerceptionModelA(comuna="Santiago", sigma_epsilon=0.0, seed=42)
        m_with_gossip = PerceptionModelA(comuna="Santiago", sigma_epsilon=0.0, seed=42)

        p_no = m_no_gossip.update(r_c=2.0, gossip_rumors=[])
        p_with = m_with_gossip.update(r_c=2.0, gossip_rumors=[0.8, 0.9])

        self.assertGreater(p_with, p_no)

    def test_ema_memory_decay(self) -> None:
        """Verifica que tras un pico de delitos, la memoria local M_c decaiga gradualmente."""
        model = PerceptionModelA(comuna="Santiago", alpha=0.8, sigma_epsilon=0.0, seed=42)

        # Paso 1: Pico de 10 delitos -> M_c(1) = 0.8*0 + 0.2*10 = 2.0
        model.update(r_c=10.0)
        self.assertAlmostEqual(model.m_c, 2.0)

        # Paso 2: 0 delitos -> M_c(2) = 0.8*2.0 + 0.2*0 = 1.6
        model.update(r_c=0.0)
        self.assertAlmostEqual(model.m_c, 1.6)

        # Paso 3: 0 delitos -> M_c(3) = 0.8*1.6 + 0.2*0 = 1.28
        model.update(r_c=0.0)
        self.assertAlmostEqual(model.m_c, 1.28)

    def test_reset_restores_state(self) -> None:
        """Verifica que reset() restaure el estado inicial."""
        model = PerceptionModelA(comuna="Santiago", seed=42)
        model.update(r_c=5.0)
        self.assertNotEqual(model.m_c, 0.0)

        model.reset()
        self.assertEqual(model.m_c, 0.0)
        self.assertEqual(len(model.history), 0)


class TestPerceptionModelB(unittest.TestCase):
    """Pruebas para el modelo de percepción del Dominio B (Calidad del Aire)."""

    def test_initial_conditions(self) -> None:
        model = PerceptionModelB(comuna="Santiago", seed=42)
        self.assertEqual(model.m_c, 0.0)
        self.assertEqual(len(model.history), 0)

    def test_reproducibility_with_seed(self) -> None:
        """Verifica que con la misma semilla se obtenga la misma secuencia."""
        m1 = PerceptionModelB(comuna="Santiago", seed=42)
        m2 = PerceptionModelB(comuna="Santiago", seed=42)

        series = [25.0, 30.0, 80.0, 45.0, 20.0]
        p1 = [m1.update(v_c=v, gossip_rumors=[30.0]) for v in series]
        p2 = [m2.update(v_c=v, gossip_rumors=[30.0]) for v in series]

        self.assertEqual(p1, p2)

    def test_peak_memory_retention(self) -> None:
        """Verifica que ante una caída brusca de PM2.5, la memoria mantenga la influencia del pico."""
        # Sin ruido para verificar fórmula analíticamente
        model = PerceptionModelB(comuna="Santiago", alpha=0.8, gamma=0.5, delta=0.0, sigma_epsilon=0.0)

        # Paso 1: Pico agudo de PM2.5 = 100 µg/m³
        # u_c = max(100, 0) = 100
        # M_c(1) = 0.8*0 + 0.2*100 = 20.0
        # P_c(1) = 100 + 0.5*(20 - 100) = 60.0
        p1 = model.update(v_c=100.0)
        self.assertAlmostEqual(model.m_c, 20.0)
        self.assertAlmostEqual(p1, 60.0)

        # Paso 2: El aire se limpia bruscamente a v_c = 10 µg/m³
        # u_c = max(10, 20.0) = 20.0 (estímulo dominado por la memoria del pico anterior!)
        # M_c(2) = 0.8*20.0 + 0.2*20.0 = 20.0
        # P_c(2) = 10 + 0.5*(20 - 10) = 15.0 (percepción > ground truth debido al sesgo γ)
        p2 = model.update(v_c=10.0)
        self.assertAlmostEqual(model.m_c, 20.0)
        self.assertAlmostEqual(p2, 15.0)
        self.assertGreater(p2, 10.0)

    def test_clipping_bounds(self) -> None:
        """Verifica que la percepción esté acotada por [clip_min, clip_max]."""
        model = PerceptionModelB(comuna="Santiago", clip_min=0.0, clip_max=300.0, seed=42)

        p_high = model.update(v_c=1000.0, gossip_rumors=[800.0])
        self.assertLessEqual(p_high, 300.0)

        p_low = model.update(v_c=-50.0, gossip_rumors=[0.0])
        self.assertGreaterEqual(p_low, 0.0)

    def test_gossip_drag(self) -> None:
        """Verifica que los rumores de alta contaminación eleven la percepción percibida."""
        m_clean = PerceptionModelB(comuna="Santiago", sigma_epsilon=0.0, seed=42)
        m_polluted_rumor = PerceptionModelB(comuna="Santiago", sigma_epsilon=0.0, seed=42)

        p_clean = m_clean.update(v_c=30.0, gossip_rumors=[])
        p_drag = m_polluted_rumor.update(v_c=30.0, gossip_rumors=[120.0])

        self.assertGreater(p_drag, p_clean)


if __name__ == "__main__":
    unittest.main()
