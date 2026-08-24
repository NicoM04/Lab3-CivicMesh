"""Módulo de Replay de datos reales de calidad del aire para el Dominio B (Rol 3: Líder de Datos).

Lee y reproduce series temporales reales de PM2.5 / PM10 (Open-Meteo / SINCA)
cacheadas en el repositorio, proporcionando valores deterministas por paso de simulación.
Incluye soporte para interpolación espacial mediante IDW (Inverse Distance Weighting).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def calculate_distance(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """Calcula la distancia euclidiana entre dos pares de coordenadas (lat, lon).

    Args:
        coord1: Tupla (latitud, longitud).
        coord2: Tupla (latitud, longitud).

    Returns:
        Distancia en grados (o unidades consistentes de distancia).
    """
    return math.hypot(coord1[0] - coord2[0], coord1[1] - coord2[1])


def idw_extrapolate(
    target_coord: tuple[float, float],
    stations: dict[str, dict[str, Any]],
    p: float = 2.0,
    metric_key: str = "pm2_5",
) -> float:
    """Calcula el valor extrapolado/interpolado en una coordenada mediante IDW (Inverse Distance Weighting).

    Fórmula:
        v_c(t) = (∑ w_s * v_s(t)) / (∑ w_s), donde w_s = 1 / d(c, s)^p

    Si la distancia es 0 (la estación coincide con la coordenada objetivo), retorna el valor exacto de dicha estación.

    Args:
        target_coord: Tupla (lat, lon) del punto o comuna objetivo.
        stations: Diccionario de estaciones {"Estacion1": {"lat": float, "lon": float, "pm2_5": float, ...}}.
        p: Potencia de ponderación (por defecto 2.0).
        metric_key: Clave del valor numérico a interpolar (por defecto 'pm2_5').

    Returns:
        Valor interpolado como float.

    Raises:
        ValueError: Si stations está vacío o no contiene valores válidos.
    """
    if not stations:
        raise ValueError("El diccionario de estaciones no puede estar vacío para IDW.")

    total_weight = 0.0
    weighted_sum = 0.0

    for name, data in stations.items():
        coord = (float(data["lat"]), float(data["lon"]))
        val = float(data[metric_key])

        dist = calculate_distance(target_coord, coord)
        if dist == 0.0:
            return val

        weight = 1.0 / (dist**p)
        weighted_sum += weight * val
        total_weight += weight

    if total_weight == 0.0:
        raise ValueError("No fue posible calcular ponderaciones IDW válidas.")

    return weighted_sum / total_weight


class AirQualityReplay:
    """Publicador de replay para series temporales reales de calidad del aire (Dominio B).

    Attributes:
        dataset_path: Ruta al archivo JSON cacheado.
        comunas: Lista de comunas cargadas.
    """

    def __init__(
        self,
        dataset_path: str | Path = "datasets/dataset_aire.json",
        comunas: list[str] | None = None,
    ) -> None:
        """Inicializa el reproductor de calidad del aire.

        Args:
            dataset_path: Ruta al archivo JSON con las series de calidad de aire.
            comunas: Filtro opcional de comunas a cargar. Si es None, carga todas las disponibles.
        """
        self.dataset_path = Path(dataset_path)
        self.data: dict[str, list[dict[str, Any]]] = {}
        self._load_dataset(comunas)

    def _load_dataset(self, filter_comunas: list[str] | None = None) -> None:
        """Carga y procesa las series temporales desde el archivo JSON."""
        if not self.dataset_path.is_file():
            raise FileNotFoundError(f"Archivo de dataset no encontrado: {self.dataset_path.resolve()}")

        with open(self.dataset_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, dict):
            raise ValueError("El formato del dataset debe ser un objeto JSON con comunas como claves.")

        for comuna, series in raw_data.items():
            if filter_comunas is not None and comuna not in filter_comunas:
                continue

            times = series.get("time", [])
            pm2_5_list = series.get("pm2_5", [])
            pm10_list = series.get("pm10", [None] * len(times))

            if len(pm10_list) < len(times):
                pm10_list = pm10_list + [None] * (len(times) - len(pm10_list))

            records: list[dict[str, Any]] = []
            last_valid_pm25 = 20.0
            last_valid_pm10 = 40.0

            for i in range(len(times)):
                t_str = times[i]
                raw_pm25 = pm2_5_list[i] if i < len(pm2_5_list) else None
                raw_pm10 = pm10_list[i] if i < len(pm10_list) else None

                # Forward-fill / imputación básica para valores faltantes (null)
                if raw_pm25 is not None:
                    pm25_val = float(raw_pm25)
                    last_valid_pm25 = pm25_val
                else:
                    pm25_val = last_valid_pm25

                if raw_pm10 is not None:
                    pm10_val = float(raw_pm10)
                    last_valid_pm10 = pm10_val
                else:
                    pm10_val = last_valid_pm10

                records.append({
                    "timestamp": t_str,
                    "pm2_5": pm25_val,
                    "pm10": pm10_val,
                })

            self.data[comuna] = records

    def get_comunas(self) -> list[str]:
        """Retorna la lista de comunas cargadas en el dataset."""
        return list(self.data.keys())

    def get_series_length(self, comuna: str) -> int:
        """Retorna la cantidad de muestras temporales disponibles para una comuna."""
        if comuna not in self.data:
            raise KeyError(f"Comuna '{comuna}' no encontrada en el dataset cargado.")
        return len(self.data[comuna])

    def get_value(self, comuna: str, step: int) -> dict[str, Any]:
        """Obtiene la medición en el paso de simulación indicado.

        Si step excede el tamaño de la serie, aplica aritmética modular (wrap-around)
        para permitir simulaciones continuas indeterminadas.

        Args:
            comuna: Nombre de la comuna.
            step: Índice entero del paso de simulación (reloj lógico).

        Returns:
            Diccionario con las claves:
                - comuna: str
                - t: int (step)
                - pm2_5: float
                - pm10: float | None
                - timestamp: str
        """
        if comuna not in self.data:
            raise KeyError(f"Comuna '{comuna}' no encontrada en el dataset.")

        series = self.data[comuna]
        if not series:
            raise ValueError(f"La comuna '{comuna}' no tiene datos registrados.")

        idx = step % len(series)
        record = series[idx]

        return {
            "comuna": comuna,
            "t": step,
            "pm2_5": record["pm2_5"],
            "pm10": record["pm10"],
            "timestamp": record["timestamp"],
        }

    def get_value_by_time(self, comuna: str, timestamp: str) -> dict[str, Any]:
        """Busca una muestra por coincidencia exacta de timestamp ISO (ej: '2023-06-01T14:00').

        Args:
            comuna: Nombre de la comuna.
            timestamp: Cadena de timestamp ISO.

        Returns:
            Diccionario con los datos correspondientes.

        Raises:
            KeyError: Si no se encuentra la comuna o el timestamp.
        """
        if comuna not in self.data:
            raise KeyError(f"Comuna '{comuna}' no encontrada en el dataset.")

        for idx, record in enumerate(self.data[comuna]):
            if record["timestamp"] == timestamp:
                return {
                    "comuna": comuna,
                    "t": idx,
                    "pm2_5": record["pm2_5"],
                    "pm10": record["pm10"],
                    "timestamp": record["timestamp"],
                }

        raise KeyError(f"Timestamp '{timestamp}' no encontrado para la comuna '{comuna}'.")
