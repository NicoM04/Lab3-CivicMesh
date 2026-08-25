#!/bin/bash
#SBATCH --job-name=civicmesh
#SBATCH --output=logs/civicmesh-%j.out
#SBATCH --error=logs/civicmesh-%j.err
#SBATCH --nodes=4
#SBATCH --ntasks=4
#SBATCH --time=00:30:00

# ============================================================================
# CivicMesh — Script Slurm para el clúster DIINF
#
# Mapeo de recursos (Sección 5.1 del enunciado):
#   - Nodos 0,1 (CPU): peers gossip/pub-sub (2 peers por nodo = 4 peers)
#   - Nodo 2 (GPU, solo CPU): publicador Dominio A (delitos) + publicador Dominio B (aire)
#   - Nodo 3 (GPU, solo CPU): frontend Streamlit
#
# Uso:
#   export CIVICMESH_RUNS=~/civicmesh-runs   # o ruta en shared FS
#   sbatch slurm/run_civicmesh.sh
#
# El script crea automáticamente el directorio de la corrida, escribe el
# hostfile.txt, copia config.yaml y dataset, lanza peers, publicadores y
# frontend, y espera a que finalicen los publicadores antes de limpiar.
# ============================================================================

set -euo pipefail

# ----- Directorio de la corrida en shared FS -----
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$HOME/civicmesh-runs}"
RUN_ID="slurm-${SLURM_JOB_ID}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "[civicmesh] Job ${SLURM_JOB_ID} — creando directorio de corrida: ${RUN_DIR}"
mkdir -p "${RUN_DIR}/metrics" "${RUN_DIR}/logs"

# ----- Resolver hosts asignados por Slurm -----
HOSTS=($(scontrol show hostnames "${SLURM_JOB_NODELIST}"))
CPU_HOST_0="${HOSTS[0]}"
CPU_HOST_1="${HOSTS[1]}"
GPU_HOST_0="${HOSTS[2]}"
GPU_HOST_1="${HOSTS[3]}"

echo "[civicmesh] Nodos CPU: ${CPU_HOST_0}, ${CPU_HOST_1}"
echo "[civicmesh] Nodos GPU: ${GPU_HOST_0}, ${GPU_HOST_1}"

# ----- Configuración de peers -----
BASE_PORT=9000
PEERS_PER_CPU_HOST=2
GOSSIP_INTERVAL=1.0
FAILURE_TIMEOUT=5.0
STEPS=20
PUB_INTERVAL=1.0
TOPIC="Santiago"

# ----- Copiar config y dataset al directorio de la corrida -----
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp "${REPO_DIR}/config.yaml" "${RUN_DIR}/config.yaml"
if [ -d "${REPO_DIR}/datasets" ]; then
    cp -r "${REPO_DIR}/datasets" "${RUN_DIR}/datasets"
fi

# ----- Generar hostfile.txt -----
HOSTFILE="${RUN_DIR}/hostfile.txt"
> "${HOSTFILE}"

PEER_INDEX=0
for CPU_HOST in "${CPU_HOST_0}" "${CPU_HOST_1}"; do
    for i in $(seq 0 $((PEERS_PER_CPU_HOST - 1))); do
        PEER_INDEX=$((PEER_INDEX + 1))
        PORT=$((BASE_PORT + PEER_INDEX))
        echo "peer-${PEER_INDEX} ${CPU_HOST} ${PORT}" >> "${HOSTFILE}"
    done
done

echo "[civicmesh] hostfile.txt generado:"
cat "${HOSTFILE}"

# ----- Seed peer (primer peer para JOIN) -----
SEED_ID="peer-1"
SEED_HOST="${CPU_HOST_0}"
SEED_PORT=$((BASE_PORT + 1))

# ----- Lanzar peers en nodos CPU -----
PEER_INDEX=0
for CPU_HOST in "${CPU_HOST_0}" "${CPU_HOST_1}"; do
    for i in $(seq 0 $((PEERS_PER_CPU_HOST - 1))); do
        PEER_INDEX=$((PEER_INDEX + 1))
        PEER_ID="peer-${PEER_INDEX}"
        PORT=$((BASE_PORT + PEER_INDEX))

        PEER_CMD="cd ${REPO_DIR} && python scripts/run_peer.py \
            --peer-id ${PEER_ID} \
            --host ${CPU_HOST} \
            --port ${PORT} \
            --topic ${TOPIC} \
            --include-neighbors \
            --config ${RUN_DIR}/config.yaml \
            --gossip-interval ${GOSSIP_INTERVAL} \
            --failure-timeout ${FAILURE_TIMEOUT} \
            --metrics-dir ${RUN_DIR}/metrics"

        # Los peers que no son el seed hacen JOIN al seed
        if [ "${PEER_ID}" != "${SEED_ID}" ]; then
            PEER_CMD="${PEER_CMD} --seed-id ${SEED_ID} --seed-host ${SEED_HOST} --seed-port ${SEED_PORT}"
        fi

        echo "[civicmesh] Lanzando ${PEER_ID} en ${CPU_HOST}:${PORT}"
        srun --nodes=1 --ntasks=1 --nodelist="${CPU_HOST}" \
            bash -c "${PEER_CMD}" \
            > "${RUN_DIR}/logs/${PEER_ID}.out" 2>&1 &
    done
done

# Dar tiempo a los peers para arrancar y hacer JOIN
sleep 3

# ----- Lanzar publicadores en nodo GPU 0 -----
echo "[civicmesh] Lanzando publicador Dominio A (delitos) en ${GPU_HOST_0}"
srun --nodes=1 --ntasks=1 --nodelist="${GPU_HOST_0}" \
    bash -c "cd ${REPO_DIR} && python scripts/run_publisher.py \
        --domain crime \
        --comuna ${TOPIC} \
        --peer-id publisher-a \
        --host ${GPU_HOST_0} \
        --port 9100 \
        --seed-id ${SEED_ID} \
        --seed-host ${SEED_HOST} \
        --seed-port ${SEED_PORT} \
        --config ${RUN_DIR}/config.yaml \
        --steps ${STEPS} \
        --interval ${PUB_INTERVAL} \
        --metrics-dir ${RUN_DIR}/metrics" \
    > "${RUN_DIR}/logs/publisher-a.out" 2>&1 &
PUB_A_PID=$!

echo "[civicmesh] Lanzando publicador Dominio B (calidad del aire) en ${GPU_HOST_0}"
srun --nodes=1 --ntasks=1 --nodelist="${GPU_HOST_0}" \
    bash -c "cd ${REPO_DIR} && python scripts/run_publisher.py \
        --domain air \
        --comuna ${TOPIC} \
        --peer-id publisher-b \
        --host ${GPU_HOST_0} \
        --port 9101 \
        --seed-id ${SEED_ID} \
        --seed-host ${SEED_HOST} \
        --seed-port ${SEED_PORT} \
        --config ${RUN_DIR}/config.yaml \
        --steps ${STEPS} \
        --interval ${PUB_INTERVAL} \
        --metrics-dir ${RUN_DIR}/metrics" \
    > "${RUN_DIR}/logs/publisher-b.out" 2>&1 &
PUB_B_PID=$!

# ----- Lanzar frontend en nodo GPU 1 -----
FRONTEND_PORT=8501
echo "[civicmesh] Lanzando frontend Streamlit en ${GPU_HOST_1}:${FRONTEND_PORT}"
echo "[civicmesh] Acceso: ssh -L ${FRONTEND_PORT}:${GPU_HOST_1}:${FRONTEND_PORT} <usuario>@<login-diinf>"
srun --nodes=1 --ntasks=1 --nodelist="${GPU_HOST_1}" \
    bash -c "cd ${REPO_DIR} && python -m streamlit run civicmesh/analytics/frontend.py \
        --server.port=${FRONTEND_PORT} \
        --server.address=0.0.0.0 \
        -- --metrics-dir ${RUN_DIR}/metrics" \
    > "${RUN_DIR}/logs/frontend.out" 2>&1 &
FRONTEND_PID=$!

# ----- Esperar a que los publicadores terminen -----
echo "[civicmesh] Esperando a que los publicadores terminen (${STEPS} pasos × ${PUB_INTERVAL}s)..."
wait ${PUB_A_PID} ${PUB_B_PID} 2>/dev/null || true

echo "[civicmesh] Publicadores finalizaron. Métricas en: ${RUN_DIR}/metrics/"
echo "[civicmesh] Frontend sigue activo en ${GPU_HOST_1}:${FRONTEND_PORT} hasta que el job expire."

# Dejar el frontend corriendo hasta que Slurm cancele el job
wait ${FRONTEND_PID} 2>/dev/null || true

echo "[civicmesh] Job ${SLURM_JOB_ID} finalizado."
