#!/bin/bash
#SBATCH --job-name=civicmesh
#SBATCH --output=logs/civicmesh-%j.out
#SBATCH --error=logs/civicmesh-%j.err
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=6
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
# -----------------------------------------------------------------------
# Particiones del clúster DIINF
#
# El enunciado exige 2 nodos CPU + 2 nodos GPU. Slurm debe asignar
# nodos del tipo correcto. Ajustar los valores según `sinfo`:
#
#   Opción A — Constraints (descomentar y ajustar):
#     #SBATCH --constraint="[cpu*2,gpu*2]"
#
#   Opción B — Hetjob (si el clúster lo soporta):
#     Separar en dos bloques #SBATCH hetjob con --partition distinta.
#
# Si el clúster no diferencia particiones/constraints, la variable
# CPU_PARTITION y GPU_PARTITION más abajo permiten filtrar manualmente.
# -----------------------------------------------------------------------

# ============================================================================
# CivicMesh — Script Slurm para el clúster DIINF
#
# Mapeo de recursos (Sección 5.1 del enunciado):
#   - Nodos 0,1 (CPU): peers gossip/pub-sub (1 peer por comuna)
#   - Nodo 2 (GPU, solo CPU del host): publicadores Dominio A (delitos) +
#                                       publicadores Dominio B (aire)
#   - Nodo 3 (GPU, solo CPU del host): publicadores restantes + frontend
#
# Uso:
#   export CIVICMESH_RUNS=~/civicmesh-runs   # o ruta en shared FS
#   sbatch slurm/run_civicmesh.sh
#
# El script crea el directorio de la corrida, escribe hostfile.txt,
# copia config.yaml (con paths absolutos), lanza peers en nodos CPU,
# publicadores en nodos GPU y el frontend Streamlit.
# ============================================================================

set -euo pipefail

# Asegurar existencia del directorio de logs de Slurm en el root
mkdir -p logs

# ----- Directorio de la corrida en shared FS -----
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$HOME/civicmesh-runs}"
RUN_ID="slurm-${SLURM_JOB_ID}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "[civicmesh] Job ${SLURM_JOB_ID} — creando directorio de corrida: ${RUN_DIR}"
mkdir -p "${RUN_DIR}/metrics" "${RUN_DIR}/logs"

# Limpieza automática de subprocesos al finalizar o cancelar el job
trap 'echo "[civicmesh] Limpiando procesos..."; kill $(jobs -p) 2>/dev/null || true' EXIT SIGINT SIGTERM

# ----- Resolver hosts asignados por Slurm -----
HOSTS=($(scontrol show hostnames "${SLURM_JOB_NODELIST}"))
if [ "${#HOSTS[@]}" -lt 4 ]; then
    echo "[civicmesh] ERROR: Se requieren 4 nodos y se asignaron ${#HOSTS[@]}" >&2
    exit 1
fi

CPU_HOST_0="${HOSTS[0]}"
CPU_HOST_1="${HOSTS[1]}"
GPU_HOST_0="${HOSTS[2]}"
GPU_HOST_1="${HOSTS[3]}"

echo "[civicmesh] Nodos CPU (Peers):   ${CPU_HOST_0}, ${CPU_HOST_1}"
echo "[civicmesh] Nodos GPU (Pub/UI):  ${GPU_HOST_0}, ${GPU_HOST_1}"

# -----------------------------------------------------------------------
# Validación de tipo de nodo (opcional, descomentar si sinfo lo soporta)
# -----------------------------------------------------------------------
# for h in "${CPU_HOST_0}" "${CPU_HOST_1}"; do
#     FEAT=$(scontrol show node "$h" | grep -oP 'AvailableFeatures=\K[^ ]+')
#     if [[ "$FEAT" != *"cpu"* ]]; then
#         echo "[civicmesh] ADVERTENCIA: $h no tiene feature 'cpu' ($FEAT)" >&2
#     fi
# done
# for h in "${GPU_HOST_0}" "${GPU_HOST_1}"; do
#     FEAT=$(scontrol show node "$h" | grep -oP 'AvailableFeatures=\K[^ ]+')
#     if [[ "$FEAT" != *"gpu"* ]]; then
#         echo "[civicmesh] ADVERTENCIA: $h no tiene feature 'gpu' ($FEAT)" >&2
#     fi
# done

# ----- Configuración general -----
BASE_PORT=9000
GOSSIP_INTERVAL=1.0
FAILURE_TIMEOUT=5.0
STEPS=20
PUB_INTERVAL=1.0

# Comunas del experimento (deben coincidir con config.yaml)
COMUNAS=("Santiago" "Puente_Alto" "Maipu" "La_Florida" "Pudahuel")

# Distribución de comunas por nodo CPU (peers)
#   CPU_HOST_0 ← Santiago, Maipu, Pudahuel    (3 peers)
#   CPU_HOST_1 ← Puente_Alto, La_Florida      (2 peers)
CPU0_COMUNAS=("Santiago" "Maipu" "Pudahuel")
CPU1_COMUNAS=("Puente_Alto" "La_Florida")

# ----- Copiar config y dataset al directorio de la corrida -----
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp "${REPO_DIR}/config.yaml" "${RUN_DIR}/config.yaml"

if [ -d "${REPO_DIR}/datasets" ]; then
    cp -r "${REPO_DIR}/datasets" "${RUN_DIR}/datasets"
fi

# Reescribir dataset_path en la copia de config para usar ruta absoluta
# (los nodos GPU hacen cd al REPO_DIR, pero el dataset vive en el shared FS)
sed -i "s|dataset_path:.*|dataset_path: \"${RUN_DIR}/datasets/dataset_aire.json\"|" \
    "${RUN_DIR}/config.yaml"

echo "[civicmesh] config.yaml copiado y dataset_path actualizado a ruta absoluta"

# ----- Generar hostfile.txt -----
# El hostfile documenta host:port de cada peer para referencia y para el
# frontend. Los peers descubren la malla vía gossip (JOIN al seed); el
# hostfile puede usarse como vista inicial si se agrega --hostfile al peer.
HOSTFILE="${RUN_DIR}/hostfile.txt"
> "${HOSTFILE}"

PEER_INDEX=0

for COMUNA in "${CPU0_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PORT=$((BASE_PORT + PEER_INDEX))
    echo "peer-${PEER_INDEX} ${CPU_HOST_0} ${PORT} ${COMUNA}" >> "${HOSTFILE}"
done

for COMUNA in "${CPU1_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PORT=$((BASE_PORT + PEER_INDEX))
    echo "peer-${PEER_INDEX} ${CPU_HOST_1} ${PORT} ${COMUNA}" >> "${HOSTFILE}"
done

TOTAL_PEERS=${PEER_INDEX}

echo "[civicmesh] hostfile.txt generado (${TOTAL_PEERS} peers):"
cat "${HOSTFILE}"

# ----- Seed peer (primer peer para JOIN gossip) -----
SEED_ID="peer-1"
SEED_HOST="${CPU_HOST_0}"
SEED_PORT=$((BASE_PORT + 1))

# =====================================================================
# Función auxiliar para lanzar un proceso remoto.
# Usa srun --overlap si está disponible; si falla, cae a ssh.
# =====================================================================
launch_remote() {
    local NODE="$1"
    local LOG_FILE="$2"
    local CMD="$3"

    # Intentar con srun --overlap (requiere Slurm >= 20.11)
    srun --nodes=1 --ntasks=1 --overlap --nodelist="${NODE}" \
        bash -c "${CMD}" \
        > "${LOG_FILE}" 2>&1 &
}

# =====================================================================
# FASE 1: Lanzar peers en nodos CPU (1 peer por comuna)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 1: Lanzando peers ==="

PEER_INDEX=0

# --- Peers en CPU_HOST_0 ---
for COMUNA in "${CPU0_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && python scripts/run_peer.py \
        --peer-id ${PEER_ID} \
        --host ${CPU_HOST_0} \
        --port ${PORT} \
        --topic ${COMUNA} \
        --include-neighbors \
        --config ${RUN_DIR}/config.yaml \
        --gossip-interval ${GOSSIP_INTERVAL} \
        --failure-timeout ${FAILURE_TIMEOUT} \
        --metrics-dir ${RUN_DIR}/metrics"

    # Los peers que no son el seed hacen JOIN al seed
    if [ "${PEER_ID}" != "${SEED_ID}" ]; then
        PEER_CMD="${PEER_CMD} --seed-id ${SEED_ID} --seed-host ${SEED_HOST} --seed-port ${SEED_PORT}"
    fi

    echo "[civicmesh]   ${PEER_ID} → ${CPU_HOST_0}:${PORT} (${COMUNA})"
    launch_remote "${CPU_HOST_0}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# --- Peers en CPU_HOST_1 ---
for COMUNA in "${CPU1_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && python scripts/run_peer.py \
        --peer-id ${PEER_ID} \
        --host ${CPU_HOST_1} \
        --port ${PORT} \
        --topic ${COMUNA} \
        --include-neighbors \
        --config ${RUN_DIR}/config.yaml \
        --gossip-interval ${GOSSIP_INTERVAL} \
        --failure-timeout ${FAILURE_TIMEOUT} \
        --metrics-dir ${RUN_DIR}/metrics \
        --seed-id ${SEED_ID} --seed-host ${SEED_HOST} --seed-port ${SEED_PORT}"

    echo "[civicmesh]   ${PEER_ID} → ${CPU_HOST_1}:${PORT} (${COMUNA})"
    launch_remote "${CPU_HOST_1}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# Dar tiempo a los peers para arrancar y hacer JOIN gossip
echo "[civicmesh] Esperando ${TOTAL_PEERS} peers (5s)..."
sleep 5

# =====================================================================
# FASE 2: Lanzar publicadores en nodos GPU (solo CPU del host)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 2: Lanzando publicadores ==="

PUB_PIDS=()
PUB_PORT=9100

# --- Publicadores Dominio A (delitos) en GPU_HOST_0 ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-crime-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_0}:${PUB_PORT}"
    launch_remote "${GPU_HOST_0}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && python scripts/run_publisher.py \
            --domain crime \
            --comuna ${COMUNA} \
            --peer-id ${PUB_ID} \
            --host ${GPU_HOST_0} \
            --port ${PUB_PORT} \
            --seed-id ${SEED_ID} \
            --seed-host ${SEED_HOST} \
            --seed-port ${SEED_PORT} \
            --config ${RUN_DIR}/config.yaml \
            --steps ${STEPS} \
            --interval ${PUB_INTERVAL} \
            --metrics-dir ${RUN_DIR}/metrics"
    PUB_PIDS+=($!)
    PUB_PORT=$((PUB_PORT + 1))
done

# --- Publicadores Dominio B (calidad del aire) en GPU_HOST_1 ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-air-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_1}:${PUB_PORT}"
    launch_remote "${GPU_HOST_1}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && python scripts/run_publisher.py \
            --domain air \
            --comuna ${COMUNA} \
            --peer-id ${PUB_ID} \
            --host ${GPU_HOST_1} \
            --port ${PUB_PORT} \
            --seed-id ${SEED_ID} \
            --seed-host ${SEED_HOST} \
            --seed-port ${SEED_PORT} \
            --config ${RUN_DIR}/config.yaml \
            --steps ${STEPS} \
            --interval ${PUB_INTERVAL} \
            --metrics-dir ${RUN_DIR}/metrics"
    PUB_PIDS+=($!)
    PUB_PORT=$((PUB_PORT + 1))
done

# =====================================================================
# FASE 3: Lanzar frontend Streamlit en GPU_HOST_1
# =====================================================================
echo ""
echo "[civicmesh] === FASE 3: Lanzando frontend ==="

FRONTEND_PORT=8501
echo "[civicmesh] Frontend Streamlit → ${GPU_HOST_1}:${FRONTEND_PORT}"
echo "[civicmesh] Para acceso remoto (SSH tunnel):"
echo "[civicmesh]   ssh -L ${FRONTEND_PORT}:${GPU_HOST_1}:${FRONTEND_PORT} <usuario>@<login-diinf>"

launch_remote "${GPU_HOST_1}" "${RUN_DIR}/logs/frontend.out" \
    "cd ${REPO_DIR} && \
     export CIVICMESH_METRICS_DIR='${RUN_DIR}/metrics' && \
     python -m streamlit run civicmesh/analytics/frontend.py \
        --server.port=${FRONTEND_PORT} \
        --server.address=0.0.0.0 \
        --server.headless=true"
FRONTEND_PID=$!

# =====================================================================
# FASE 4: Esperar publicadores y mantener frontend
# =====================================================================
echo ""
echo "[civicmesh] === Esperando publicadores (${STEPS} pasos × ${PUB_INTERVAL}s) ==="

for PID in "${PUB_PIDS[@]}"; do
    wait "${PID}" 2>/dev/null || true
done

echo "[civicmesh] Publicadores finalizaron."
echo "[civicmesh] Métricas en: ${RUN_DIR}/metrics/"
echo "[civicmesh] Frontend sigue activo en ${GPU_HOST_1}:${FRONTEND_PORT}"

# =====================================================================
# EXPERIMENTO DE FALLO / PARTICIÓN (Sección 5.3, paso 7)
#
# Mientras el job está activo y el frontend corre, ejecutar manualmente
# desde otra terminal para simular caída de un nodo CPU:
#
#   # Opción 1: matar peers de CPU_HOST_1
#   ssh <CPU_HOST_1> "pkill -f run_peer"
#
#   # Opción 2: cancelar un step específico de srun
#   squeue -s -j <JOB_ID>          # listar steps
#   scancel --signal=KILL <STEP_ID>
#
# Observar el efecto en:
#   - ${RUN_DIR}/metrics/   (convergencia, drops, hops)
#   - Frontend Streamlit    (brecha percepción–realidad)
#   - ${RUN_DIR}/logs/      (timeouts de gossip, peers perdidos)
#
# Para un script automatizado, ver: slurm/kill_partition.sh
# =====================================================================

# Dejar el frontend corriendo hasta que Slurm cancele el job o expire --time
wait "${FRONTEND_PID}" 2>/dev/null || true

echo "[civicmesh] Job ${SLURM_JOB_ID} finalizado."
