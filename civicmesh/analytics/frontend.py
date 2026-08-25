import os
import sys
import pandas as pd
import streamlit as st

from civicmesh.analytics import (
    read_metrics,
    calculate_convergence,
    calculate_perception_gap,
    calculate_peer_availability,
    calculate_propagation_stats,
)


st.set_page_config(
    page_title="CivicMesh Analytics",
    layout="wide",
)

st.title("CivicMesh - Analítica")

default_metrics_dir = os.environ.get("CIVICMESH_METRICS_DIR", "")
if not default_metrics_dir:
    for idx, arg in enumerate(sys.argv):
        if arg == "--metrics-dir" and idx + 1 < len(sys.argv):
            default_metrics_dir = sys.argv[idx + 1]
            break
if not default_metrics_dir:
    default_metrics_dir = "runs/demo/metrics"

metrics_dir = st.sidebar.text_input(
    "Directorio de métricas",
    default_metrics_dir,
)


tolerance = st.sidebar.number_input(
    "Tolerancia de convergencia",
    min_value=0.0,
    value=0.0,
    step=0.1,
)

records = read_metrics(metrics_dir)

if not records:
    st.warning(
        f"No se encontraron métricas en: {metrics_dir}"
    )
    st.stop()

df = pd.DataFrame(records)

required_columns = {
    "peer_id",
    "domain",
    "topic",
    "channel",
    "sim_time",
    "value",
}

if not required_columns.issubset(df.columns):
    st.error(
        "Las métricas no contienen los campos necesarios "
        "para el frontend."
    )
    st.stop()

# Si existe record_type, usamos solamente los estados de tópico.
if "record_type" in df.columns:
    topic_df = df[df["record_type"] == "topic_state"].copy()
else:
    topic_df = df.copy()

topic_df = topic_df.dropna(
    subset=[
        "peer_id",
        "domain",
        "topic",
        "channel",
        "sim_time",
        "value",
    ]
)

if topic_df.empty:
    st.warning("No existen métricas de estado de tópico.")
    st.stop()


# ---------------------------------------------------------
# Filtros
# ---------------------------------------------------------

domains = sorted(topic_df["domain"].unique())

domain = st.sidebar.selectbox(
    "Dominio",
    domains,
)

domain_df = topic_df[
    topic_df["domain"] == domain
]

topics = sorted(domain_df["topic"].unique())

topic = st.sidebar.selectbox(
    "Tópico",
    topics,
)

filtered = domain_df[
    domain_df["topic"] == topic
].copy()


# ---------------------------------------------------------
# Estado tópico × canal
# ---------------------------------------------------------

st.header("Estado por tópico y canal")

latest_time = filtered["sim_time"].max()

latest = filtered[
    filtered["sim_time"] == latest_time
]

objective_latest = latest[
    latest["channel"] == "objetivo"
]["value"]

subjective_latest = latest[
    latest["channel"] == "subjetivo"
]["value"]

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Paso de simulación",
        latest_time,
    )

with col2:
    if not objective_latest.empty:
        st.metric(
            "Canal objetivo",
            f"{objective_latest.mean():.2f}",
        )
    else:
        st.metric("Canal objetivo", "Sin datos")

with col3:
    if not subjective_latest.empty:
        st.metric(
            "Canal subjetivo",
            f"{subjective_latest.mean():.2f}",
        )
    else:
        st.metric("Canal subjetivo", "Sin datos")


# ---------------------------------------------------------
# Convergencia
# ---------------------------------------------------------

st.header("Convergencia entre peers")

if not objective_latest.empty:

    convergence = calculate_convergence(
        objective_latest.tolist(),
        tolerance=tolerance,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Peers considerados",
            convergence["peer_count"],
        )

    with col2:
        st.metric(
            "Diferencia máxima",
            f"{convergence['spread']:.2f}",
        )

    with col3:
        status = (
            "Sí"
            if convergence["converged"]
            else "No"
        )

        st.metric(
            "¿Convergente?",
            status,
        )

else:
    st.info(
        "No hay valores objetivos para calcular convergencia."
    )


# Evolución temporal de la convergencia

objective_history = filtered[
    filtered["channel"] == "objetivo"
]

convergence_history = []

for sim_time, group in objective_history.groupby("sim_time"):

    result = calculate_convergence(
        group["value"].tolist(),
        tolerance=tolerance,
    )

    convergence_history.append(
        {
            "sim_time": sim_time,
            "Diferencia entre peers": result["spread"],
        }
    )



# ---------------------------------------------------------
# Convergencia temporal
# ---------------------------------------------------------

objective_history = filtered[
    filtered["channel"] == "objetivo"
]

convergence_history = []

for sim_time, group in objective_history.groupby("sim_time"):

    result = calculate_convergence(
        group["value"].tolist(),
        tolerance=tolerance,
    )

    convergence_history.append(
        {
            "sim_time": sim_time,
            "Diferencia entre peers": result["spread"],
            "Peers con dato": result["peer_count"],
        }
    )


if convergence_history:

    convergence_df = pd.DataFrame(
        convergence_history
    ).set_index("sim_time")

    st.subheader(
        "Convergencia del canal objetivo"
    )

    st.line_chart(
        convergence_df[
            ["Diferencia entre peers"]
        ]
    )

    st.subheader(
        "Peers participantes en la convergencia"
    )

    st.line_chart(
        convergence_df[
            ["Peers con dato"]
        ]
    )

# ---------------------------------------------------------
# Percepción vs realidad
# ---------------------------------------------------------

st.header("Percepción vs realidad")

series = (
    filtered
    .groupby(["sim_time", "channel"])["value"]
    .mean()
    .unstack()
    .sort_index()
)

if (
    "objetivo" in series.columns
    and "subjetivo" in series.columns
):

    series = series.dropna(
        subset=["objetivo", "subjetivo"]
    )

    objective_values = (
        series["objetivo"].tolist()
    )

    subjective_values = (
        series["subjetivo"].tolist()
    )

    gap = calculate_perception_gap(
        objective_values,
        subjective_values,
        domain,
    )

    st.metric(
        "Brecha absoluta promedio",
        f"{gap['mean_absolute_gap']:.2f}",
    )

    # Para delitos normalizamos el objetivo,
    # porque percepción y realidad tienen escalas distintas.
    if domain == "crime":

        max_value = max(objective_values)

        if max_value == 0:
            comparable_objective = [
                0.0
                for _ in objective_values
            ]
        else:
            comparable_objective = [
                value / max_value
                for value in objective_values
            ]

    else:
        comparable_objective = objective_values

    comparison = pd.DataFrame(
        {
            "Realidad": comparable_objective,
            "Percepción": subjective_values,
        },
        index=series.index,
    )

    comparison.index.name = "sim_time"

    st.subheader("Evolución temporal")

    st.line_chart(comparison)

    gap_chart = pd.DataFrame(
        {
            "Brecha": gap["gaps"],
        },
        index=series.index,
    )

    gap_chart.index.name = "sim_time"

    st.subheader("Brecha percepción-realidad")

    st.line_chart(gap_chart)

else:
    st.info(
        "Se necesitan datos objetivos y subjetivos "
        "para calcular la brecha."
    )

# ---------------------------------------------------------
# Estado de red
# ---------------------------------------------------------

st.header("Estado de red")

if "record_type" in df.columns:

    network_df = df[
        df["record_type"] == "network_state"
    ].copy()

else:
    network_df = pd.DataFrame()


if not network_df.empty:

    network_df = network_df.dropna(
        subset=[
            "sim_time",
            "alive_peers",
            "dead_peers",
        ]
    )

    latest_network_time = (
        network_df["sim_time"].max()
    )

    latest_network = network_df[
        network_df["sim_time"]
        == latest_network_time
    ].iloc[0]

    alive = int(
        latest_network["alive_peers"]
    )

    dead = int(
        latest_network["dead_peers"]
    )

    availability = calculate_peer_availability(
        alive,
        dead,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Peers vivos",
            alive,
        )

    with col2:
        st.metric(
            "Peers muertos",
            dead,
        )

    with col3:
        percentage = (
            availability["availability"] * 100
        )

        st.metric(
            "Disponibilidad",
            f"{percentage:.1f} %",
        )

    # Tomamos un único valor por instante porque
    # varios peers pueden reportar el mismo estado.
    network_series = (
        network_df
        .groupby("sim_time")[
            ["alive_peers", "dead_peers"]
        ]
        .mean()
        .sort_index()
    )

    st.subheader(
        "Evolución de peers"
    )

    st.line_chart(network_series)

    availability_values = []

    for _, row in network_series.iterrows():

        result = calculate_peer_availability(
            row["alive_peers"],
            row["dead_peers"],
        )

        availability_values.append(
            result["availability"] * 100
        )

    availability_chart = pd.DataFrame(
        {
            "Disponibilidad (%)":
                availability_values
        },
        index=network_series.index,
    )

    st.subheader(
        "Disponibilidad de la red"
    )

    st.line_chart(
        availability_chart
    )

else:

    st.info(
        "No existen métricas de estado de red."
    )

# ---------------------------------------------------------
# Propagación Pub/Sub
# ---------------------------------------------------------

st.header("Propagación Pub/Sub")

if "record_type" in df.columns:

    message_df = df[
        df["record_type"] == "message_event"
    ].copy()

else:
    message_df = pd.DataFrame()


if not message_df.empty:

    received_df = message_df[
        message_df["event"] == "received"
    ]

    dropped_df = message_df[
        message_df["event"] == "dropped"
    ]

    hop_counts = (
        received_df["hop_count"]
        .dropna()
        .tolist()
    )

    propagation = calculate_propagation_stats(
        hop_counts=hop_counts,
        dropped_messages=len(dropped_df),
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Mensajes recibidos",
            propagation["received_messages"],
        )

    with col2:
        st.metric(
            "Mensajes descartados",
            propagation["dropped_messages"],
        )

    with col3:
        average = propagation["average_hops"]

        st.metric(
            "Hops promedio",
            (
                f"{average:.2f}"
                if average is not None
                else "Sin datos"
            ),
        )

    with col4:
        maximum = propagation["max_hops"]

        st.metric(
            "Hops máximos",
            (
                maximum
                if maximum is not None
                else "Sin datos"
            ),
        )

else:

    st.info(
        "No existen métricas de propagación Pub/Sub."
    )