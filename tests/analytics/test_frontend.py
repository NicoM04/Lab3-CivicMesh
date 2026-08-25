"""Tests unitarios para el módulo de frontend de Analítica."""

import unittest
from pathlib import Path


class TestFrontendModule(unittest.TestCase):
    def test_frontend_file_exists(self) -> None:
        frontend_path = Path("civicmesh/analytics/frontend.py")
        self.assertTrue(frontend_path.is_file(), "frontend.py debe existir en civicmesh/analytics/")

    def test_frontend_contains_expected_components(self) -> None:
        content = Path("civicmesh/analytics/frontend.py").read_text(encoding="utf-8")
        self.assertIn("CivicMesh Analytics", content)
        self.assertIn("calculate_convergence", content)
        self.assertIn("calculate_perception_gap", content)
        self.assertIn("calculate_peer_availability", content)
        self.assertIn("calculate_propagation_stats", content)


if __name__ == "__main__":
    unittest.main()
