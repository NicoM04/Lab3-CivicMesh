#!/bin/bash
#SBATCH --job-name=civicmesh
#SBATCH --partition=batch
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=6
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --output=civicmesh-%j.out
#SBATCH --error=civicmesh-%j.err

# ============================================================================
# CivicMesh — Script Slurm para el clúster Xi DIINF (USACH)
#
# Clúster Xi:
#   Partición "batch" → xicpu[02-03]  (2× AMD EPYC 7513, 64 threads, 256GB)
#   Partición "GPU"   → xigpu[01-02]  (1× AMD EPYC 7443P, 48 threads, 128GB)
#   Shared FS: /home/xi/<user>  (NFS, visible en todos los nodos)
#   Login:     xi.diinf.usach.cl
#   Slurm:     22.05.2 (soporta --overlap)
#   Python:    3.10.6
#
# Estrategia de despliegue:
#   Este script se lanza con sbatch en la partición "batch" (2 nodos CPU).
#   Los peers gossip/pub-sub corren en xicpu02 y xicpu03.
#   Los publicadores y el frontend se lanzan en la partición "GPU" usando
#   srun -p GPU (solo CPU del host, sin CUDA). Slurm permite lanzar steps
#   en particiones distintas a la del job principal.
#
# Mapeo (Sección 5.1 del enunciado):
#   - xicpu02, xicpu03 (batch): peers gossip/pub-sub (1 peer por comuna)
#   - xigpu01 (GPU, solo CPU):  publicadores Dominio A + Dominio B
#   - xigpu02 (GPU, solo CPU):  frontend Streamlit
#
# Uso:
#   export CIVICMESH_RUNS=~/civicmesh-runs
#   mkdir -p logs
#   sbatch slurm/run_civicmesh.sh
#
# Acceso al frontend (desde tu máquina local, con VPN activa):
#   ssh -L 8501:xigpu02:8501 <usuario>@xi.diinf.usach.cl
#   Abrir http://localhost:8501
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

# ----- Resolver nodos CPU asignados por Slurm (partición batch) -----
CPU_HOSTS=($(scontrol show hostnames "${SLURM_JOB_NODELIST}"))
if [ "${#CPU_HOSTS[@]}" -lt 2 ]; then
    echo "[civicmesh] ERROR: Se requieren 2 nodos batch y se asignaron ${#CPU_HOSTS[@]}" >&2
    exit 1
fi

CPU_HOST_0="${CPU_HOSTS[0]}"   # Esperado: xicpu02
CPU_HOST_1="${CPU_HOSTS[1]}"   # Esperado: xicpu03

# Nodos GPU fijos (partición "GPU" del clúster Xi)
# Se lanzan vía srun -p GPU; no requieren estar en la asignación del job.
GPU_HOST_0="xigpu01"
GPU_HOST_1="xigpu02"

echo "[civicmesh] Nodos CPU (batch):  ${CPU_HOST_0}, ${CPU_HOST_1}"
echo "[civicmesh] Nodos GPU (GPU):    ${GPU_HOST_0}, ${GPU_HOST_1}"

# Verificar disponibilidad de los nodos GPU
echo "[civicmesh] Verificando estado de nodos GPU..."
GPU_STATE=$(sinfo -p GPU --noheader -o "%T" 2>/dev/null || echo "unknown")
if [[ "${GPU_STATE}" == *"down"* ]] || [[ "${GPU_STATE}" == *"drain"* ]]; then
    echo "[civicmesh] ADVERTENCIA: Partición GPU reporta estado '${GPU_STATE}'." >&2
    echo "[civicmesh] Los publicadores y frontend se ejecutarán en los nodos batch como fallback." >&2
    GPU_HOST_0="${CPU_HOST_0}"
    GPU_HOST_1="${CPU_HOST_1}"
    GPU_PARTITION=""
else
    GPU_PARTITION="-p GPU"
fi

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
# Documenta host:port:comuna de cada peer. Los peers descubren la malla
# vía gossip (JOIN al seed); el hostfile sirve de referencia para el
# frontend y para debugging.
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
# Funciones auxiliares de lanzamiento
# =====================================================================

# Lanzar proceso en un nodo de la partición batch (ya asignado al job)
launch_on_batch() {
    local NODE="$1"
    local LOG_FILE="$2"
    local CMD="$3"
    srun --nodes=1 --ntasks=1 --overlap --nodelist="${NODE}" \
        bash -c "${CMD}" \
        > "${LOG_FILE}" 2>&1 &
}

# Lanzar proceso en un nodo GPU (partición GPU, cross-partition step)
# Si GPU no está disponible, cae al nodo batch de fallback.
launch_on_gpu() {
    local NODE="$1"
    local LOG_FILE="$2"
    local CMD="$3"
    if [ -n "${GPU_PARTITION}" ]; then
        # Cross-partition step: lanzar en partición GPU desde job batch
        srun ${GPU_PARTITION} --nodes=1 --ntasks=1 --nodelist="${NODE}" \
            bash -c "${CMD}" \
            > "${LOG_FILE}" 2>&1 &
    else
        # Fallback: correr en nodo batch
        srun --nodes=1 --ntasks=1 --overlap --nodelist="${NODE}" \
            bash -c "${CMD}" \
            > "${LOG_FILE}" 2>&1 &
    fi
}

# =====================================================================
# FASE 1: Lanzar peers en nodos CPU (partición batch)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 1: Lanzando peers en partición batch ==="

PEER_INDEX=0

# --- Peers en CPU_HOST_0 (xicpu02) ---
for COMUNA in "${CPU0_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && python3 scripts/run_peer.py \
        --peer-id ${PEER_ID} \
        --host ${CPU_HOST_0} \
        --port ${PORT} \
        --topic ${COMUNA} \
        --include-neighbors \
        --config ${RUN_DIR}/config.yaml \
        --gossip-interval ${GOSSIP_INTERVAL} \
        --failure-timeout ${FAILURE_TIMEOUT} \
        --metrics-dir ${RUN_DIR}/metrics"

    if [ "${PEER_ID}" != "${SEED_ID}" ]; then
        PEER_CMD="${PEER_CMD} --seed-id ${SEED_ID} --seed-host ${SEED_HOST} --seed-port ${SEED_PORT}"
    fi

    echo "[civicmesh]   ${PEER_ID} → ${CPU_HOST_0}:${PORT} (${COMUNA})"
    launch_on_batch "${CPU_HOST_0}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# --- Peers en CPU_HOST_1 (xicpu03) ---
for COMUNA in "${CPU1_COMUNAS[@]}"; do
    PEER_INDEX=$((PEER_INDEX + 1))
    PEER_ID="peer-${PEER_INDEX}"
    PORT=$((BASE_PORT + PEER_INDEX))

    PEER_CMD="cd ${REPO_DIR} && python3 scripts/run_peer.py \
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
    launch_on_batch "${CPU_HOST_1}" "${RUN_DIR}/logs/${PEER_ID}.out" "${PEER_CMD}"
done

# Dar tiempo a los peers para arrancar y hacer JOIN gossip
echo "[civicmesh] Esperando ${TOTAL_PEERS} peers (5s)..."
sleep 5

# =====================================================================
# FASE 2: Lanzar publicadores en nodos GPU (solo CPU del host)
# =====================================================================
echo ""
echo "[civicmesh] === FASE 2: Lanzando publicadores en partición GPU ==="

PUB_PIDS=()
PUB_PORT=9100

# --- Publicadores Dominio A (delitos) en xigpu01 ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-crime-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_0}:${PUB_PORT}"
    launch_on_gpu "${GPU_HOST_0}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && python3 scripts/run_publisher.py \
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

# --- Publicadores Dominio B (calidad del aire) en xigpu01 ---
for COMUNA in "${COMUNAS[@]}"; do
    PUB_ID="publisher-air-${COMUNA}"

    echo "[civicmesh]   ${PUB_ID} → ${GPU_HOST_0}:${PUB_PORT}"
    launch_on_gpu "${GPU_HOST_0}" "${RUN_DIR}/logs/${PUB_ID}.out" \
        "cd ${REPO_DIR} && python3 scripts/run_publisher.py \
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
# FASE 3: Lanzar frontend Streamlit en xigpu02
# =====================================================================
echo ""
echo "[civicmesh] === FASE 3: Lanzando frontend en partición GPU ==="

FRONTEND_PORT=8501
echo "[civicmesh] Frontend Streamlit → ${GPU_HOST_1}:${FRONTEND_PORT}"
echo "[civicmesh] Para acceso remoto (con VPN activa):"
echo "[civicmesh]   ssh -L ${FRONTEND_PORT}:${GPU_HOST_1}:${FRONTEND_PORT} <usuario>@xi.diinf.usach.cl"
echo "[civicmesh]   Abrir http://localhost:${FRONTEND_PORT}"

launch_on_gpu "${GPU_HOST_1}" "${RUN_DIR}/logs/frontend.out" \
    "cd ${REPO_DIR} && \
     export CIVICMESH_METRICS_DIR='${RUN_DIR}/metrics' && \
     python3 -m streamlit run civicmesh/analytics/frontend.py \
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
echo "[civicmesh] Hostfile: ${HOSTFILE}"

# =====================================================================
# EXPERIMENTO DE FALLO / PARTICIÓN (Sección 5.3, paso 7)
#
# Mientras el job está activo y el frontend corre, ejecutar manualmente
# desde otra sesión SSH en xi.diinf.usach.cl:
#
#   # Opción 1: matar todos los peers de xicpu03
#   ssh xicpu03 "pkill -f run_peer"
#
#   # Opción 2: cancelar un step específico
#   squeue -s -j <JOB_ID>
#   scancel --signal=KILL <STEP_ID>
#
#   # Opción 3: usar el script auxiliar
#   bash slurm/kill_partition.sh <JOB_ID> cpu1
#
# Observar el efecto en:
#   - ${RUN_DIR}/metrics/   (convergencia, drops, hops)
#   - Frontend Streamlit    (brecha percepción–realidad)
#   - ${RUN_DIR}/logs/      (timeouts de gossip, peers perdidos)
# =====================================================================

# Dejar el frontend corriendo hasta que Slurm cancele el job o expire --time
wait "${FRONTEND_PID}" 2>/dev/null || true

echo "[civicmesh] Job ${SLURM_JOB_ID} finalizado."
