#!/bin/bash
# ============================================================================
# CivicMesh — Experimento de partición de red / caída de peers
# Clúster Xi DIINF (USACH)
#
# Uso (desde otra sesión SSH en xi.diinf.usach.cl, mientras el job corre):
#
#   # Matar todos los peers del segundo nodo CPU (xicpu03)
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> cpu1
#
#   # Matar un peer específico
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> peer peer-3
#
#   # Listar / cancelar steps de srun
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> step
#
# Evidenciar el efecto en métricas y frontend para el informe.
# ============================================================================

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Uso: $0 <SLURM_JOB_ID> <modo> [args...]"
    echo ""
    echo "Modos:"
    echo "  cpu0          Matar todos los peers del primer nodo CPU (xicpu02)"
    echo "  cpu1          Matar todos los peers del segundo nodo CPU (xicpu03)"
    echo "  peer <ID>     Matar un peer específico (e.g., peer-3)"
    echo "  step [ID]     Listar steps o cancelar uno específico"
    exit 1
fi

JOB_ID="$1"
MODE="$2"

# Resolver nodos CPU asignados al job (partición batch)
NODELIST=$(squeue -j "${JOB_ID}" -o '%N' --noheader 2>/dev/null)
if [ -z "${NODELIST}" ]; then
    echo "ERROR: No se encontró el job ${JOB_ID} (¿sigue corriendo?)" >&2
    exit 1
fi

CPU_HOSTS=($(scontrol show hostnames "${NODELIST}"))
CPU_HOST_0="${CPU_HOSTS[0]:-xicpu02}"
CPU_HOST_1="${CPU_HOSTS[1]:-xicpu03}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CIVICMESH_RUNS="${CIVICMESH_RUNS:-${REPO_DIR}/civicmesh-runs}"
RUN_DIR="${CIVICMESH_RUNS}/slurm-${JOB_ID}"

case "${MODE}" in
    cpu0)
        echo "[kill_partition] ${TIMESTAMP} — Matando peers en ${CPU_HOST_0}..."
        echo "[kill_partition] Comunas afectadas: Santiago, Maipu, Pudahuel"
        ssh "${CPU_HOST_0}" "pkill -f 'run_peer' || true"
        echo "[kill_partition] Peers en ${CPU_HOST_0} eliminados."
        ;;

    cpu1)
        echo "[kill_partition] ${TIMESTAMP} — Matando peers en ${CPU_HOST_1}..."
        echo "[kill_partition] Comunas afectadas: Puente_Alto, La_Florida"
        ssh "${CPU_HOST_1}" "pkill -f 'run_peer' || true"
        echo "[kill_partition] Peers en ${CPU_HOST_1} eliminados."
        ;;

    peer)
        if [ "$#" -lt 3 ]; then
            echo "ERROR: Falta el ID del peer (e.g., peer-3)" >&2
            exit 1
        fi
        PEER_ID="$3"
        echo "[kill_partition] ${TIMESTAMP} — Matando ${PEER_ID}..."
        ssh "${CPU_HOST_0}" "pkill -f '${PEER_ID}' 2>/dev/null || true"
        ssh "${CPU_HOST_1}" "pkill -f '${PEER_ID}' 2>/dev/null || true"
        echo "[kill_partition] ${PEER_ID} eliminado."
        ;;

    step)
        if [ "$#" -lt 3 ]; then
            echo "Steps del job ${JOB_ID}:"
            squeue -s -j "${JOB_ID}"
            echo ""
            echo "Para cancelar: $0 ${JOB_ID} step <STEP_ID>"
            exit 0
        fi
        STEP_ID="$3"
        echo "[kill_partition] ${TIMESTAMP} — Cancelando step ${STEP_ID}..."
        scancel --signal=KILL "${STEP_ID}"
        echo "[kill_partition] Step ${STEP_ID} cancelado."
        ;;

    *)
        echo "ERROR: Modo desconocido '${MODE}'" >&2
        exit 1
        ;;
esac

echo ""
echo "[kill_partition] Verificar efecto en:"
echo "  - Métricas:  ${RUN_DIR}/metrics/"
echo "  - Logs:      ${RUN_DIR}/logs/"
echo "  - Frontend:  http://localhost:8501 (vía SSH tunnel a xigpu02)"
