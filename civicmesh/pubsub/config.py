"""Configuración de canales para pub/sub."""

from typing import Any

# Por defecto, TTL, prioridad y fanout para cada tipo de canal
CHANNEL_CONFIG: dict[str, dict[str, int]] = {
    "objetivo": {
        "ttl": 5,          # Llega más lejos
        "priority": 10,    # Más prioritario
        "fanout": 3        # Se propaga más rápido
    },
    "subjetivo": {
        "ttl": 3,          # Rumores viven menos
        "priority": 5,     # Menos prioritario
        "fanout": 2        # Menor cobertura por salto
    }
}
