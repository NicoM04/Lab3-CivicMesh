"""Tests unitarios para AirQualityReplay e IDW (Dominio B - Calidad del Aire)."""

import json
import tempfile
import unittest
from pathlib import Path

from civicmesh.generators.replay import AirQualityReplay, calculate_distance, idw_extrapolate


class TestAirQualityReplay(unittest.TestCase):
    """Pruebas para el reproductor de datos reales de calidad del aire."""

    def test_load_default_dataset(self) -> None:
        """Verifica que el dataset en datasets/dataset_aire.json se cargue correctamente."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        comunas = replay.get_comunas()

        self.assertIn("Santiago", comunas)
        self.assertIn("Puente_Alto", comunas)
        self.assertIn("Maipu", comunas)
        self.assertIn("La_Florida", comunas)
        self.assertIn("Pudahuel", comunas)

        # Cada comuna debe tener 720 muestras (1 mes horario)
        self.assertEqual(replay.get_series_length("Santiago"), 720)

    def test_get_value_structure(self) -> None:
        """Verifica que get_value retorne todos los campos requeridos."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        sample = replay.get_value("Santiago", step=0)

        self.assertEqual(sample["comuna"], "Santiago")
        self.assertEqual(sample["t"], 0)
        self.assertIn("pm2_5", sample)
        self.assertIn("timestamp", sample)
        self.assertIsInstance(sample["pm2_5"], float)

    def test_deterministic_replay(self) -> None:
        """Verifica que dos instancias lean exactamente los mismos valores para los mismos pasos."""
        replay1 = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        replay2 = AirQualityReplay(dataset_path="datasets/dataset_aire.json")

        for step in range(50):
            val1 = replay1.get_value("Santiago", step=step)
            val2 = replay2.get_value("Santiago", step=step)
            self.assertEqual(val1, val2)

    def test_wraparound_step(self) -> None:
        """Verifica que los pasos mayores a la longitud de la serie hagan wrap-around correcto."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        length = replay.get_series_length("Santiago")

        val_start = replay.get_value("Santiago", step=0)
        val_wrapped = replay.get_value("Santiago", step=length)

        self.assertEqual(val_start["pm2_5"], val_wrapped["pm2_5"])
        self.assertEqual(val_start["timestamp"], val_wrapped["timestamp"])
        self.assertEqual(val_wrapped["t"], length)

    def test_get_value_by_time(self) -> None:
        """Verifica la consulta por timestamp ISO."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        first_record = replay.get_value("Santiago", step=0)
        ts = first_record["timestamp"]

        queried = replay.get_value_by_time("Santiago", ts)
        self.assertEqual(queried["timestamp"], ts)
        self.assertEqual(queried["pm2_5"], first_record["pm2_5"])

    def test_invalid_comuna_or_time_raises(self) -> None:
        """Verifica el manejo de errores en comunas o timestamps inexistentes."""
        replay = AirQualityReplay(dataset_path="datasets/dataset_aire.json")
        with self.assertRaises(KeyError):
            replay.get_value("ComunaInvalida", step=0)

        with self.assertRaises(KeyError):
            replay.get_value_by_time("Santiago", "2099-01-01T00:00")

    def test_custom_dataset_with_null_imputation(self) -> None:
        """Verifica el manejo de valores null / None mediante forward-fill."""
        custom_data = {
            "TestComuna": {
                "time": ["2023-06-01T00:00", "2023-06-01T01:00", "2023-06-01T02:00"],
                "pm2_5": [50.0, None, 30.0],
                "pm10": [100.0, 110.0, None],
            }
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as f:
            json.dump(custom_data, f)
            temp_path = f.name

        try:
            replay = AirQualityReplay(dataset_path=temp_path)
            step0 = replay.get_value("TestComuna", 0)
            step1 = replay.get_value("TestComuna", 1)  # Era None en pm2_5
            step2 = replay.get_value("TestComuna", 2)  # Era None en pm10

            self.assertEqual(step0["pm2_5"], 50.0)
            self.assertEqual(step1["pm2_5"], 50.0)  # Imputado con 50.0
            self.assertEqual(step2["pm2_5"], 30.0)

            self.assertEqual(step0["pm10"], 100.0)
            self.assertEqual(step1["pm10"], 110.0)
            self.assertEqual(step2["pm10"], 110.0)  # Imputado con 110.0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestIDWExtrapolation(unittest.TestCase):
    """Pruebas para la extrapolación espacial mediante IDW."""

    def setUp(self) -> None:
        self.stations = {
            "EstacionA": {"lat": 0.0, "lon": 0.0, "pm2_5": 20.0},
            "EstacionB": {"lat": 2.0, "lon": 0.0, "pm2_5": 40.0},
        }

    def test_idw_exact_point_matches(self) -> None:
        """Si la coordenada objetivo coincide con una estación (distancia 0), devuelve su valor exacto."""
        val = idw_extrapolate((0.0, 0.0), self.stations)
        self.assertEqual(val, 20.0)

        val_b = idw_extrapolate((2.0, 0.0), self.stations)
        self.assertEqual(val_b, 40.0)

    def test_idw_midpoint_symmetry(self) -> None:
        """En el punto medio exacto entre dos estaciones simétricas, el valor es el promedio aritmético."""
        midpoint = (1.0, 0.0)
        val = idw_extrapolate(midpoint, self.stations, p=2.0)
        self.assertAlmostEqual(val, 30.0)

    def test_idw_empty_stations_raises_error(self) -> None:
        """Lanza ValueError si no hay estaciones disponibles."""
        with self.assertRaises(ValueError):
            idw_extrapolate((1.0, 1.0), {})


if __name__ == "__main__":
    unittest.main()
