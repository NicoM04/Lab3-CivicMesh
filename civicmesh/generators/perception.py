"""Modelos matemáticos de generación subjetiva / percepción ciudadana (Rol 3: Líder de Datos).

Implementa las fórmulas del canal subjetivo especificadas en la Sección 4.3 del enunciado:
- Agregación de rumores recibidos por gossip (P_hat_gossip).
- Memoria local EMA (M_c).
- Dominio A: Sensación de inseguridad mediante función logística sigma(Z_c(t)) in [0, 1].
- Dominio B: Percepción de calidad del aire con memoria de picos, sesgo gamma y arrastre delta.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from civicmesh.generators.config_loader import get_rng


def aggregate_gossip(rumors: list[float] | None) -> float:
    """Calcula la agregación P_hat_gossip(t) sobre el conjunto de rumores recibidos.

    Fórmula:
        P_hat_gossip(t) = (1 / |Q|) * ∑ p  si Q != ∅
                          0                si Q = ∅

    Args:
        rumors: Lista de valores subjetivos recibidos desde el paso anterior.

    Returns:
        Promedio de rumores o 0.0 si la lista está vacía o es None.
    """
    if not rumors:
        return 0.0
    return float(sum(rumors) / len(rumors))


def sigmoid(z: float) -> float:
    """Función logística estándar sigma(z) = 1 / (1 + exp(-z)).

    Incluye acotamiento para evitar desbordamiento numérico (overflow).
    """
    if z < -40.0:
        return 0.0
    if z > 40.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


class PerceptionModelA:
    """Modelo de percepción subjetiva para el Dominio A (Sensación de Inseguridad).

    Ecuaciones:
        (1) M_c(t) = α * M_c(t - Δt) + (1 - α) * R_c(t)
        (2) Z_c(t) = β_0 + β_1 * M_c(t) + β_2 * P_hat_gossip(t) + ε_c(t)
        (3) P_c(t) = σ(Z_c(t))

        donde ε_c(t) ~ N(0, σ_ε^2)

    Condiciones iniciales:
        M_c(0) = 0.0, P_hat_gossip(0) = 0.0
    """

    def __init__(
        self,
        comuna: str = "",
        alpha: float = 0.8,
        beta_0: float = -1.0,
        beta_1: float = 0.4,
        beta_2: float = 0.8,
        sigma_epsilon: float = 0.1,
        seed: int = 42,
        rng: np.random.Generator | None = None,
    ) -> None:
        """Inicializa el modelo de percepción del Dominio A.

        Args:
            comuna: Identificador de la comuna (para el RNG determinista).
            alpha: Factor de persistencia EMA (típico 0.8).
            beta_0: Intercepto de la regresión logística (típico -1.0).
            beta_1: Ponderación de la memoria local de delitos (típico 0.4).
            beta_2: Ponderación de los rumores recibidos por gossip (típico 0.8).
            sigma_epsilon: Desviación estándar del ruido gaussiano ε (típico 0.1).
            seed: Semilla entera para reproducibilidad.
            rng: Generador RNG opcional preexistente.
        """
        self.comuna = comuna
        self.alpha = float(alpha)
        self.beta_0 = float(beta_0)
        self.beta_1 = float(beta_1)
        self.beta_2 = float(beta_2)
        self.sigma_epsilon = float(sigma_epsilon)
        self.seed = int(seed)

        self._rng = rng if rng is not None else get_rng(self.seed, comuna, extra="percep_a")
        self.m_c: float = 0.0
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Reinicia el estado de memoria interna y el generador RNG."""
        self.m_c = 0.0
        self.history.clear()
        self._rng = get_rng(self.seed, self.comuna, extra="percep_a")

    def update(self, r_c: float, gossip_rumors: list[float] | None = None) -> float:
        """Calcula y actualiza la percepción de inseguridad para el paso actual.

        Args:
            r_c: Ground truth local (total de delitos en el paso t: R_c(t)).
            gossip_rumors: Rumores subjetivos recibidos de otros peers/publicadores.

        Returns:
            Índice de percepción P_c(t) en el rango [0.0, 1.0].
        """
        # Ecuación (1): Memoria local EMA
        self.m_c = self.alpha * self.m_c + (1.0 - self.alpha) * float(r_c)

        # Agregación de rumores
        p_hat = aggregate_gossip(gossip_rumors)

        # Ruido gaussiano determinista
        noise = float(self._rng.normal(0.0, self.sigma_epsilon)) if self.sigma_epsilon > 0.0 else 0.0

        # Ecuación (2): Puntuación latente Z_c(t)
        z_c = self.beta_0 + self.beta_1 * self.m_c + self.beta_2 * p_hat + noise

        # Ecuación (3): Percepción logística P_c(t)
        p_c = sigmoid(z_c)

        self.history.append({
            "r_c": float(r_c),
            "m_c": self.m_c,
            "p_hat_gossip": p_hat,
            "noise": noise,
            "z_c": z_c,
            "p_c": p_c,
        })

        return p_c


class PerceptionModelB:
    """Modelo de percepción subjetiva para el Dominio B (Calidad del Aire).

    Ecuaciones:
        Estímulo con memoria de pico: u_c(t) = max(v_c(t), M_c(t - Δt))
        (4) M_c(t) = α * M_c(t - Δt) + (1 - α) * u_c(t)
        (5) P_c(t) = v_c(t) + γ * (M_c(t) - v_c(t)) + δ * P_hat_gossip(t) + ε_c(t)

        donde ε_c(t) ~ N(0, σ_ε^2), y se aplica clip al rango físico [clip_min, clip_max].

    Condiciones iniciales:
        M_c(0) = 0.0, P_hat_gossip(0) = 0.0
    """

    def __init__(
        self,
        comuna: str = "",
        alpha: float = 0.85,
        gamma: float = 0.6,
        delta: float = 0.3,
        sigma_epsilon: float = 2.0,
        clip_min: float = 0.0,
        clip_max: float = 500.0,
        seed: int = 42,
        rng: np.random.Generator | None = None,
    ) -> None:
        """Inicializa el modelo de percepción del Dominio B.

        Args:
            comuna: Identificador de la comuna.
            alpha: Factor de persistencia EMA (típico 0.85).
            gamma: Sesgo por memoria de picos retenidos (típico 0.6).
            delta: Arrastre por rumor recibido por gossip (típico 0.3).
            sigma_epsilon: Desviación estándar del ruido gaussiano (típico 2.0).
            clip_min: Límite inferior físico (por defecto 0.0).
            clip_max: Límite superior físico (por defecto 500.0).
            seed: Semilla entera para reproducibilidad.
            rng: Generador RNG opcional preexistente.
        """
        self.comuna = comuna
        self.alpha = float(alpha)
        self.gamma = float(gamma)
        self.delta = float(delta)
        self.sigma_epsilon = float(sigma_epsilon)
        self.clip_min = float(clip_min)
        self.clip_max = float(clip_max)
        self.seed = int(seed)

        self._rng = rng if rng is not None else get_rng(self.seed, comuna, extra="percep_b")
        self.m_c: float = 0.0
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Reinicia el estado interno y el generador RNG."""
        self.m_c = 0.0
        self.history.clear()
        self._rng = get_rng(self.seed, self.comuna, extra="percep_b")

    def update(self, v_c: float, gossip_rumors: list[float] | None = None) -> float:
        """Calcula y actualiza la percepción de calidad del aire para el paso actual.

        Args:
            v_c: Valor medido / replay objetivo (ej. PM2.5 en µg/m³).
            gossip_rumors: Rumores subjetivos recibidos desde el paso anterior.

        Returns:
            Percepción de calidad del aire P_c(t) acotada al rango físico.
        """
        val_v = float(v_c)

        # Estímulo con retención de picos
        u_c = max(val_v, self.m_c)

        # Ecuación (4): Memoria EMA
        self.m_c = self.alpha * self.m_c + (1.0 - self.alpha) * u_c

        # Agregación de rumores
        p_hat = aggregate_gossip(gossip_rumors)

        # Ruido gaussiano
        noise = float(self._rng.normal(0.0, self.sigma_epsilon)) if self.sigma_epsilon > 0.0 else 0.0

        # Ecuación (5): Percepción combinada
        raw_p = val_v + self.gamma * (self.m_c - val_v) + self.delta * p_hat + noise

        # Clip físico
        p_c = max(self.clip_min, min(self.clip_max, raw_p))

        self.history.append({
            "v_c": val_v,
            "u_c": u_c,
            "m_c": self.m_c,
            "p_hat_gossip": p_hat,
            "noise": noise,
            "raw_p": raw_p,
            "p_c": p_c,
        })

        return p_c
