from civicmesh.analytics import calculate_convergence
from civicmesh.analytics import calculate_perception_gap
from civicmesh.analytics import calculate_peer_availability
from civicmesh.analytics import calculate_propagation_stats


def test_perfect_convergence():
    result = calculate_convergence([20, 20, 20])

    assert result["peer_count"] == 3
    assert result["spread"] == 0
    assert result["converged"] is True


def test_peers_are_divergent():
    result = calculate_convergence([20, 22, 25])

    assert result["spread"] == 5
    assert result["converged"] is False


def test_convergence_with_tolerance():
    result = calculate_convergence([20, 21, 22], tolerance=2)

    assert result["spread"] == 2
    assert result["converged"] is True


def test_empty_values():
    result = calculate_convergence([])

    assert result["peer_count"] == 0
    assert result["spread"] is None
    assert result["converged"] is False

def test_air_perception_gap():
    result = calculate_perception_gap(
        objective_values=[20, 30],
        subjective_values=[25, 28],
        domain="air",
    )

    assert result["gaps"] == [5, -2]
    assert result["mean_gap"] == 1.5
    assert result["mean_absolute_gap"] == 3.5


def test_crime_perception_gap():
    result = calculate_perception_gap(
        objective_values=[0, 2, 4],
        subjective_values=[0.2, 0.6, 0.9],
        domain="crime",
    )

    assert result["gaps"][0] == 0.2
    assert round(result["gaps"][1], 2) == 0.1
    assert round(result["gaps"][2], 2) == -0.1


def test_perception_gap_empty_values():
    result = calculate_perception_gap(
        objective_values=[],
        subjective_values=[],
        domain="air",
    )

    assert result["gaps"] == []
    assert result["mean_gap"] is None


def test_perception_gap_different_sizes():
    try:
        calculate_perception_gap(
            objective_values=[10, 20],
            subjective_values=[15],
            domain="air",
        )

        assert False

    except ValueError:
        assert True

def test_peer_availability():
    result = calculate_peer_availability(
        alive_peers=3,
        dead_peers=1,
    )

    assert result["total_peers"] == 4
    assert result["availability"] == 0.75


def test_peer_availability_all_alive():
    result = calculate_peer_availability(
        alive_peers=4,
        dead_peers=0,
    )

    assert result["availability"] == 1.0


def test_peer_availability_no_peers():
    result = calculate_peer_availability(
        alive_peers=0,
        dead_peers=0,
    )

    assert result["total_peers"] == 0
    assert result["availability"] is None


def test_peer_availability_negative_values():
    try:
        calculate_peer_availability(
            alive_peers=-1,
            dead_peers=1,
        )

        assert False

    except ValueError:
        assert True

def test_propagation_stats():
    result = calculate_propagation_stats(
        hop_counts=[1, 1, 2, 2],
        dropped_messages=1,
    )

    assert result["received_messages"] == 4
    assert result["dropped_messages"] == 1
    assert result["average_hops"] == 1.5
    assert result["max_hops"] == 2


def test_propagation_without_messages():
    result = calculate_propagation_stats(
        hop_counts=[],
        dropped_messages=0,
    )

    assert result["received_messages"] == 0
    assert result["average_hops"] is None
    assert result["max_hops"] is None