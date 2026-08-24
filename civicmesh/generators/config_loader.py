"""Módulo de configuración y utilidades de reproducibilidad (Líder de Datos).

Carga la configuración de CivicMesh desde archivos YAML y provee
generadores de números pseudo-aleatorios (RNG) deterministas basados en semillas
compuestas para garantizar la reproducibilidad de los experimentos.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """Carga y valida el archivo de configuración YAML de CivicMesh.

    Args:
        config_path: Ruta al archivo YAML.

    Returns:
        Diccionario con la configuración parseada.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el contenido del archivo no es un diccionario válido.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"El archivo {config_path} debe contener un mapeo (diccionario) YAML válido.")

    return data


def get_rng(seed: int, comuna: str = "", extra: str = "") -> np.random.Generator:
    """Genera un RNG determinista de numpy a partir de una semilla compuesta.

    Utiliza un hash SHA-256 sobre (comuna + extra) para generar un desplazamiento
    determinista independiente del valor de PYTHONHASHSEED, garantizando que
    diferentes ejecuciones con la misma semilla produzcan secuencias idénticas.

    Args:
        seed: Semilla entera global.
        comuna: Nombre de la comuna o tópico geográfico.
        extra: Identificador adicional (por ejemplo, tipo de delito o canal).

    Returns:
        Instancia de numpy.random.Generator (PCG64).
    """
    key_str = f"{comuna}::{extra}".encode("utf-8")
    hash_digest = hashlib.sha256(key_str).hexdigest()
    # Tomamos los primeros 8 caracteres hexadecimales (32 bits)
    offset = int(hash_digest[:8], 16)
    combined_seed = (int(seed) + offset) % (2**32)
    return np.random.default_rng(combined_seed)
