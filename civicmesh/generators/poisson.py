"""Generador estocástico de eventos discretos para el Dominio A: Delitos (Rol 3: Líder de Datos).

Modela la ocurrencia de delitos por comuna c y tipo de delito k según un proceso
de Poisson homogéneo discreto:
    X_{c,k}(t) ~ Poisson(λ_{c,k} * Δt)

Garantiza reproducibilidad determinista a partir del parámetro seed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from civicmesh.generators.config_loader import get_rng

# Tasas referenciales por defecto (eventos / unidad de tiempo Δt)
DEFAULT_LAMBDAS: dict[str, dict[str, float]] = {
    "Santiago": {"robo": 0.5, "hurto": 1.2, "asalto": 0.3},
    "Puente_Alto": {"robo": 0.8, "hurto": 1.5, "asalto": 0.4},
    "Maipu": {"robo": 0.4, "hurto": 0.9, "asalto": 0.2},
    "La_Florida": {"robo": 0.6, "hurto": 1.1, "asalto": 0.35},
    "Pudahuel": {"robo": 0.7, "hurto": 1.3, "asalto": 0.5},
}


class CrimeGenerator:
    """Generador de delitos basado en distribución de Poisson por comuna y tipo.

    Attributes:
        seed: Semilla inicial para reproducibilidad.
        delta_t: Intervalo de tiempo en cada paso de simulación.
        lambdas: Diccionario de tasas {comuna: {tipo_delito: tasa_lambda}}.
    """

    def __init__(
        self,
        seed: int = 42,
        lambdas: dict[str, dict[str, float]] | None = None,
        delta_t: float = 1.0,
    ) -> None:
        """Inicializa el generador de delitos.

        Args:
            seed: Semilla global entera.
            lambdas: Diccionario de tasas por comuna y tipo. Si es None, usa DEFAULT_LAMBDAS.
            delta_t: Tamaño del paso temporal Δt (por defecto 1.0).
        """
        self.seed = int(seed)
        self.delta_t = float(delta_t)
        self.lambdas = lambdas if lambdas is not None else DEFAULT_LAMBDAS
        self._rngs: dict[str, np.random.Generator] = {}
        self._init_rngs()

    def _init_rngs(self) -> None:
        """Inicializa los generadores de números pseudo-aleatorios por comuna."""
        self._rngs.clear()
        for comuna in self.lambdas:
            self._rngs[comuna] = get_rng(self.seed, comuna, extra="crime_poisson")

    def reset(self) -> None:
        """Reinicia los generadores RNG al estado inicial para reproducir la misma secuencia."""
        self._init_rngs()

    def generate(self, comuna: str, t: float = 0.0) -> dict[str, int]:
        """Genera el conteo de delitos por tipo en un instante t para la comuna indicada.

        Aplica X_{c,k}(t) ~ Poisson(λ_{c,k} * Δt).

        Args:
            comuna: Nombre de la comuna.
            t: Instante temporal (paso o timestamp lógico).

        Returns:
            Diccionario {tipo_delito: conteo_entero}.
        """
        if comuna not in self.lambdas:
            raise KeyError(f"Comuna '{comuna}' no configurada en las tasas de delitos.")

        if comuna not in self._rngs:
            self._rngs[comuna] = get_rng(self.seed, comuna, extra="crime_poisson")

        rng = self._rngs[comuna]
        comuna_lambdas = self.lambdas[comuna]
        counts: dict[str, int] = {}

        for crime_type, lam in comuna_lambdas.items():
            expected = lam * self.delta_t
            # np.random.Generator.poisson devuelve un entero o array de enteros
            counts[crime_type] = int(rng.poisson(lam=expected))

        return counts

    def generate_event(self, comuna: str, t: float = 0.0) -> dict[str, Any]:
        """Genera la estructura de un evento objetivo completo para publicación en pub/sub.

        Args:
            comuna: Nombre de la comuna.
            t: Instante o paso de simulación.

        Returns:
            Diccionario con la carga del evento:
                - comuna: str
                - t: float
                - counts: dict[str, int]
                - total: int (R_c(t) = suma de todos los delitos en t)
        """
        counts = self.generate(comuna, t)
        total = sum(counts.values())
        return {
            "comuna": comuna,
            "t": t,
            "counts": counts,
            "total": total,
        }

    def get_comunas(self) -> list[str]:
        """Retorna la lista de comunas configuradas."""
        return list(self.lambdas.keys())

    def get_crime_types(self, comuna: str) -> list[str]:
        """Retorna la lista de tipos de delitos configurados para una comuna."""
        if comuna not in self.lambdas:
            raise KeyError(f"Comuna '{comuna}' no configurada.")
        return list(self.lambdas[comuna].keys())
