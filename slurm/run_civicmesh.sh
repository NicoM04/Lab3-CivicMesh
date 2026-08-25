#!/bin/bash
#SBATCH --job-name=civicmesh
#SBATCH --partition=batch
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=6
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --output=civicmesh-%j.out
#SBATCH --error=civicmesh-%j.err
#SBATCH hetjob
#SBATCH --job-name=civicmesh-gpu
#SBATCH --partition=GPU
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=6
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00

# ============================================================================
# CivicMesh — Script Slurm para el clúster Xi DIINF (USACH)
#
# Mapeo según Sección 5.1 del enunciado:
#   - 2 hosts CPU (partición batch: xicpu02, xicpu03): Peers gossip/pub-sub
#   - 2 hosts GPU (partición GPU: xigpu01, xigpu02):  Publicadores + Frontend
#     (usando solo la CPU del host, sin CUDA)
#   - Shared FS (/home/ceph/...): hostfile.txt, config.yaml, datasets, metrics, logs
# ============================================================================

set -euo pipefail

# ----- Directorio del repositorio y de la corrida -----
REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${REPO_DIR}"

CIVICMESH_RUNS="${CIVICMESH_RUNS:-${REPO_DIR}/civicmesh-runs}"
RUN_ID="slurm-${SLURM_JOB_ID}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "[civicmesh] Job ${SLURM_JOB_ID} — creando directorio de corrida: ${RUN_DIR}"
mkdir -p "${RUN_DIR}/metrics" "${RUN_DIR}/logs"

# Mover logs de SLURM a la carpeta de la corrida para no ensuciar la raíz
mv "${REPO_DIR}/civicmesh-${SLURM_JOB_ID}.out" "${RUN_DIR}/" 2>/dev/null || true
mv "${REPO_DIR}/civicmesh-${SLURM_JOB_ID}.err" "${RUN_DIR}/" 2>/dev/null || true

# Limpieza automática de subprocesos y resguardo de logs al finalizar o cancelar el job
cleanup() {
    echo "[civicmesh] Limpiando procesos..."
    kill $(jobs -p) 2>/dev/null || true
    mv "${REPO_DIR}/civicmesh-${SLURM_JOB_ID}.out" "${RUN_DIR}/" 2>/dev/null || true
    mv "${REPO_DIR}/civicmesh-${SLURM_JOB_ID}.err" "${RUN_DIR}/" 2>/dev/null || true
}
trap cleanup EXIT SIGINT SIGTERM

export PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}"

# ----- Detectar o crear entorno virtual automáticamente -----
if [ ! -f "${REPO_DIR}/.venv/bin/python3" ]; then
    echo "[civicmesh] Entorno virtual no encontrado. Creando ${REPO_DIR}/.venv..."
    python3 -m venv "${REPO_DIR}/.venv" 2>/dev/null || true
    if [ -f "${REPO_DIR}/.venv/bin/pip" ]; then
        echo "[civicmesh] Instalando dependencias (streamlit, pandas, civicmesh)..."
        "${REPO_DIR}/.venv/bin/pip" install --upgrade pip 2>/dev/null || true
        "${REPO_DIR}/.venv/bin/pip" install -e "${REPO_DIR}[test]" streamlit pandas 2>/dev/null || {
            echo "[civicmesh] AVISO: pip install falló en el nodo de cómputo (posible falta de internet en este nodo)." >&2
            echo "[civicmesh] Si falta Streamlit, ejecuta 'bash slurm/setup_env.sh' desde el nodo login." >&2
        }
    fi
fi

if [ -f "${REPO_DIR}/.venv/bin/python3" ]; then
    PYTHON_BIN="${REPO_DIR}/.venv/bin/python3"
    export PATH="${REPO_DIR}/.venv/bin:${PATH}"
    echo "[civicmesh] Usando entorno virtual: ${REPO_DIR}/.venv"
elif [ -d "${HOME}/.venv" ] && [ -f "${HOME}/.venv/bin/python3" ]; then
    PYTHON_BIN="${HOME}/.venv/bin/python3"
    export PATH="${HOME}/.venv/bin:${PATH}"
    echo "[civicmesh] Usando entorno virtual de HOME: ${HOME}/.venv"
else
    PYTHON_BIN="python3"
    echo "[civicmesh] Usando Python del sistema: $(which python3)"
fi

# ----- Resolver nodos CPU (partición batch) y GPU (partición GPU) -----
CPU_NODELIST="${SLURM_JOB_NODELIST_HET_GROUP_0:-${SLURM_JOB_NODELIST:-}}"
CPU_HOSTS=($(scontrol show hostnames "${CPU_NODELIST}"))

if [ "${#CPU_HOSTS[@]}" -ge 2 ]; then
    CPU_HOST_0="${CPU_HOSTS[0]}"   # Esperado: xicpu02
    CPU_HOST_1="${CPU_HOSTS[1]}"   # Esperado: xicpu03
else
    CPU_HOST_0="${CPU_HOSTS[0]:-xicpu02}"
    CPU_HOST_1="${CPU_HOSTS[1]:-xicpu03}"
fi

if [ -n "${SLURM_JOB_NODELIST_HET_GROUP_1:-}" ]; then
    GPU_HOSTS=($(scontrol show hostnames "${SLURM_JOB_NODELIST_HET_GROUP_1}"))
    GPU_HOST_0="${GPU_HOSTS[0]:-xigpu01}"   # Publicadores
    GPU_HOST_1="${GPU_HOSTS[1]:-xigpu02}"   # Frontend
    HET_CPU="--het-group=0"
    HET_GPU="--het-group=1"
    echo "[civicmesh] Modo: 4 nodos (2 CPU batch + 2 GPU)"
else
    GPU_HOST_0="${CPU_HOST_0}"
    GPU_HOST_1="${CPU_HOST_1}"
    HET_CPU=""
    HET_GPU=""
    echo "[civicmesh] Modo: 2 nodos batch (fallback)"
fi

echo "[civicmesh] Nodos CPU (Peers):        ${CPU_HOST_0} (1-3), ${CPU_HOST_1} (4-5)"
echo "[civicmesh] Nodo GPU (Publicadores):  ${GPU_HOST_0}"
echo "[civicmesh] Nodo GPU (Frontend):      ${GPU_HOST_1}"

# ----- Configuración general -----
BASE_PORT=9000
GOSSIP_INTERVAL=1.0
FAILURE_TIMEOUT=5.0
STEPS=20
PUB_INTERVAL=1.0

# Comunas del experimento (deben coincidir con config.yaml)
COMUNAS=("Santiago" "Puente_Alto" "Maipu" "La_Florida" "Pudahuel")

# Distribución de comunas por nodo CPU (peers)
#   xicpu02 ← Santiago, Maipu, Pudahuel    (3 peers)
#   xicpu03 ← Puente_Alto, La_Florida      (2 peers)
CPU0_COMUNAS=("Santiago" "Maipu" "Pudahuel")
CPU1_COMUNAS=("Puente_Alto" "La_Florida")

# ----- Copiar config y dataset al directorio de la corrida -----
cp "${REPO_DIR}/config.yaml" "${RUN_DIR}/config.yaml"

if [ -d "${REPO_DIR}/datasets" ]; then
    cp -r "${REPO_DIR}/datasets" "${RUN_DIR}/datasets"
fi

# Reescribir dataset_path para usar ruta absoluta en NFS
sed -i "s|dataset_path:.*|dataset_path: \"${RUN_DIR}/datasets/dataset_aire.json\"|" \
    "${RUN_DIR}/config.yaml"

echo "[civicmesh] config.yaml copiado y dataset_path actualizado a ruta absoluta"

# ----- Generar hostfile.txt -----
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
# Funciones de lanzamiento de procesos
# =====================================================================
launch_on_cpu() {
    local NODE="$1"
    local LOG_FILE="$2"
    local CMD="$3"
    srun ${HET_CPU} --nodes=1 --ntasks=1 --overlap --nodelist="${NODE}" \
        bash -c "export PATH='${PATH}'; export PYTHONPATH='${REPO_DIR}'; ${CMD}" \
        > "${LOG_FILE}" 2>&1 &
}

launch_on_gpu() {
    local NODE="$1"
    local LOG_FILE="$2"
    local CMD="$3"
    srun ${HET_GPU} --nodes=1 --ntasks=1 --overlap --nodelist="${NODE}" \
        bash -c "export PATH='${PATH}'; export PYTHONPATH='${REPO_DIR}'; ${CMD}" \
        > "${LOG_FILE}" 2>&1 &
}

# =====================================================================
# FASE 1: Lanzar peers en nodos CPU (partición batch)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 1: Lanzando peers en partición batch ==="

# --- Seed peer en CPU_HOST_0 (xicpu02) ---
PEER_INDEX=1
PEER_ID="peer-1"
PORT=$((BASE_PORT + 1))
COMUNA="${CPU0_COMUNAS[0]}"

PEER_CMD="cd ${REPO_DIR} && ${PYTHON_BIN} scripts/run_peer.py \
    --peer-id ${PEER_ID} \
    --host ${CPU_HOST_0} \
    --port ${PORT} \
    --topic ${COMUNA} \
    --include-neighbors \
    --config ${RUN_DIR}/config.yaml \
    --gossip-interval ${GOSSIP_INTERVAL} \
    --failure-timeout ${FAILURE_TIMEOUT} \
    --metrics-dir ${RUN_DIR}/metrics"

echo "[civicmesh]   ${PEER_ID} (SEED) → ${CPU_HOST_0}:${PORT} (${COMUNA})"
launch_on_cpu "${CPU_HOST_0}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"

# Esperar a que el seed peer esté completamente escuchando
echo "[civicmesh] Esperando inicialización del seed peer (2s)..."
sleep 2

# --- Resto de peers en CPU_HOST_0 (xicpu02) ---
for COMUNA in "${CPU0_COMUNAS[@]:1}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && ${PYTHON_BIN} scripts/run_peer.py \
        --peer-id ${PEER_ID} \
        --host ${CPU_HOST_0} \
        --port ${PORT} \
        --topic ${COMUNA} \
        --include-neighbors \
        --config ${RUN_DIR}/config.yaml \
        --gossip-interval ${GOSSIP_INTERVAL} \
        --failure-timeout ${FAILURE_TIMEOUT} \
        --metrics-dir ${RUN_DIR}/metrics \
        --seed-id ${SEED_ID} --seed-host ${SEED_HOST} --seed-port ${SEED_PORT}"

    echo "[civicmesh]   ${PEER_ID} → ${CPU_HOST_0}:${PORT} (${COMUNA})"
    launch_on_cpu "${CPU_HOST_0}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# --- Peers en CPU_HOST_1 (xicpu03) ---
for COMUNA in "${CPU1_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && ${PYTHON_BIN} scripts/run_peer.py \
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
    launch_on_cpu "${CPU_HOST_1}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# Dar tiempo a los peers para arrancar y hacer JOIN gossip
echo "[civicmesh] Esperando ${TOTAL_PEERS} peers (3s)..."
sleep 3

# =====================================================================
# FASE 2: Lanzar publicadores en nodo GPU (solo CPU del host)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 2: Lanzando publicadores en ${GPU_HOST_0} ==="

PUB_PIDS=()
PUB_PORT=9100

# --- Publicadores Dominio A (delitos) ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-crime-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_0}:${PUB_PORT}"
    launch_on_gpu "${GPU_HOST_0}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && ${PYTHON_BIN} scripts/run_publisher.py \
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

# --- Publicadores Dominio B (calidad del aire) ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-air-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_0}:${PUB_PORT}"
    launch_on_gpu "${GPU_HOST_0}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && ${PYTHON_BIN} scripts/run_publisher.py \
            --domain air \
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

# =====================================================================
# FASE 3: Lanzar frontend Streamlit en nodo GPU (${GPU_HOST_1})
# =====================================================================
echo ""
echo "[civicmesh] === FASE 3: Lanzando frontend en ${GPU_HOST_1} ==="

FRONTEND_PORT=8501
echo "[civicmesh] Frontend Streamlit → ${GPU_HOST_1}:${FRONTEND_PORT}"
echo "[civicmesh] Para acceso remoto (con VPN activa):"
echo "[civicmesh]   ssh -L ${FRONTEND_PORT}:${GPU_HOST_1}:${FRONTEND_PORT} <usuario>@xi.diinf.usach.cl"
echo "[civicmesh]   Abrir http://localhost:${FRONTEND_PORT}"

launch_on_gpu "${GPU_HOST_1}" "${RUN_DIR}/logs/frontend.out" \
    "cd ${REPO_DIR} && \
     export CIVICMESH_METRICS_DIR='${RUN_DIR}/metrics' && \
     ${PYTHON_BIN} -m streamlit run civicmesh/analytics/frontend.py \
        --server.port=${FRONTEND_PORT} \
        --server.address=0.0.0.0 \
        --server.headless=true"
FRONTEND_PID=$!

# =====================================================================
# FASE 4: Esperar publicadores y mantener la malla activa
# =====================================================================
echo ""
echo "[civicmesh] === Esperando publicadores (${STEPS} pasos × ${PUB_INTERVAL}s) ==="

for PID in "${PUB_PIDS[@]}"; do
    wait "${PID}" 2>/dev/null || true
done

echo "[civicmesh] Publicadores finalizaron con éxito."
echo "[civicmesh] Métricas generadas en: ${RUN_DIR}/metrics/"
echo "[civicmesh] Hostfile: ${HOSTFILE}"

# Verificar si el frontend sigue corriendo
if kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    echo "[civicmesh] Frontend sigue activo en ${GPU_HOST_1}:${FRONTEND_PORT}"
    echo "[civicmesh] El job permanecerá activo hasta agotar --time o ser cancelado con scancel."
    wait "${FRONTEND_PID}" 2>/dev/null || true
else
    echo "[civicmesh] AVISO: Frontend finalizó o no inició en ${GPU_HOST_1} (ver logs/frontend.out)."
    echo "[civicmesh] Para instalar Streamlit en el clúster: pip install --user streamlit"
    echo "[civicmesh] Manteniendo la malla activa por 5 minutos para auditoría de métricas..."
    sleep 300
fi

echo "[civicmesh] Job ${SLURM_JOB_ID} finalizado."
