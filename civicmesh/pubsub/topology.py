"""Topología geográfica y utilidades de normalización de tópicos."""

from __future__ import annotations

import re
import unicodedata


def normalize_topic(topic: str) -> str:
    """Normaliza nombres de comunas a minúsculas con guiones bajos.

    Ejemplos:
        Santiago -> santiago
        Puente Alto -> puente_alto
        Ñuñoa -> nunoa
    """
    text = unicodedata.normalize("NFKD", str(topic))
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)

    return text.strip("_")


COMUNA_ADYACENCIA: dict[str, list[str]] = {
    "santiago": [
        "providencia",
        "estacion_central",
        "recoleta",
        "independencia",
        "san_miguel",
        "san_joaquin",
        "quinta_normal",
    ],

    "providencia": [
        "santiago",
        "nunoa",
        "las_condes",
        "vitacura",
        "recoleta",
    ],

    "nunoa": [
        "providencia",
        "santiago",
        "macul",
        "san_joaquin",
        "penalolen",
        "la_reina",
    ],

    "las_condes": [
        "providencia",
        "vitacura",
        "la_reina",
        "lo_barnechea",
    ],

    "recoleta": [
        "santiago",
        "providencia",
        "independencia",
        "huechuraba",
        "conchali",
    ],

    "estacion_central": [
        "santiago",
        "quinta_normal",
        "cerrillos",
        "pedro_aguirre_cerda",
        "lo_prado",
        "maipu",
    ],

    "san_miguel": [
        "santiago",
        "san_joaquin",
        "pedro_aguirre_cerda",
        "san_ramon",
        "la_cisterna",
    ],

    "macul": [
        "nunoa",
        "san_joaquin",
        "penalolen",
        "la_florida",
    ],

    "independencia": [
        "santiago",
        "recoleta",
        "conchali",
        "renca",
    ],

    "quinta_normal": [
        "santiago",
        "estacion_central",
        "renca",
        "cerro_navia",
        "lo_prado",
    ],

    "san_joaquin": [
        "santiago",
        "nunoa",
        "macul",
        "san_miguel",
        "la_florida",
    ],

    "vitacura": [
        "las_condes",
        "providencia",
        "huechuraba",
        "lo_barnechea",
    ],

    "la_reina": [
        "nunoa",
        "las_condes",
        "penalolen",
    ],

    "penalolen": [
        "nunoa",
        "macul",
        "la_reina",
        "la_florida",
    ],

    "la_florida": [
        "macul",
        "penalolen",
        "san_joaquin",
        "puente_alto",
    ],

    "puente_alto": [
        "la_florida",
    ],

    "maipu": [
        "pudahuel",
        "estacion_central",
        "cerrillos",
    ],

    "pudahuel": [
        "maipu",
        "lo_prado",
        "cerro_navia",
        "renca",
    ],
}