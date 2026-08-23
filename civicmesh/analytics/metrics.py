def calculate_convergence(values, tolerance=0.0):
    """
    Calcula la diferencia entre los valores observados por varios peers.

    Una diferencia igual a 0 indica convergencia perfecta.
    Si se define una tolerancia, los peers se consideran convergentes
    cuando la diferencia es menor o igual a ella.
    """

    if not values:
        return {
            "peer_count": 0,
            "min_value": None,
            "max_value": None,
            "spread": None,
            "converged": False,
        }

    min_value = min(values)
    max_value = max(values)
    spread = max_value - min_value

    return {
        "peer_count": len(values),
        "min_value": min_value,
        "max_value": max_value,
        "spread": spread,
        "converged": spread <= tolerance,
    }


def calculate_perception_gap(objective_values, subjective_values, domain):
    """
    Calcula la brecha entre percepción y realidad.

    En aire, ambos valores tienen la misma unidad y se comparan directamente.

    En delitos, los conteos objetivos se normalizan entre 0 y 1
    dividiendo por el máximo observado, para poder compararlos con
    el índice de inseguridad.
    """

    if len(objective_values) != len(subjective_values):
        raise ValueError(
            "objective_values y subjective_values deben tener el mismo tamaño"
        )

    if not objective_values:
        return {
            "gaps": [],
            "mean_gap": None,
            "mean_absolute_gap": None,
        }

    if domain == "air":
        comparable_objective = objective_values

    elif domain == "crime":
        max_value = max(objective_values)

        if max_value == 0:
            comparable_objective = [0.0 for _ in objective_values]
        else:
            comparable_objective = [
                value / max_value for value in objective_values
            ]

    else:
        raise ValueError("domain debe ser 'crime' o 'air'")

    gaps = [
        subjective - objective
        for objective, subjective in zip(
            comparable_objective,
            subjective_values,
        )
    ]

    mean_gap = sum(gaps) / len(gaps)

    mean_absolute_gap = (
        sum(abs(gap) for gap in gaps) / len(gaps)
    )

    return {
        "gaps": gaps,
        "mean_gap": mean_gap,
        "mean_absolute_gap": mean_absolute_gap,
    }

def calculate_peer_availability(alive_peers, dead_peers):
    """
    Calcula la proporción de peers que permanecen vivos.
    """

    if alive_peers < 0 or dead_peers < 0:
        raise ValueError("La cantidad de peers no puede ser negativa")

    total_peers = alive_peers + dead_peers

    if total_peers == 0:
        return {
            "total_peers": 0,
            "availability": None,
        }

    availability = alive_peers / total_peers

    return {
        "total_peers": total_peers,
        "availability": availability,
    }

def calculate_propagation_stats(hop_counts, dropped_messages=0):
    """
    Calcula estadísticas simples de propagación de mensajes.
    """

    if dropped_messages < 0:
        raise ValueError("dropped_messages no puede ser negativo")

    if any(hop < 0 for hop in hop_counts):
        raise ValueError("hop_count no puede ser negativo")

    if not hop_counts:
        return {
            "received_messages": 0,
            "dropped_messages": dropped_messages,
            "average_hops": None,
            "max_hops": None,
        }

    return {
        "received_messages": len(hop_counts),
        "dropped_messages": dropped_messages,
        "average_hops": sum(hop_counts) / len(hop_counts),
        "max_hops": max(hop_counts),
    }