#!/bin/bash
# ============================================================================
# CivicMesh — Experimento de partición de red / caída de peers
#
# Uso (mientras el job principal está corriendo):
#
#   # Matar peers de un nodo CPU (simula caída de nodo completo)
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> cpu1
#
#   # Matar un peer específico
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> peer peer-3
#
# Requiere acceso SSH a los nodos del job.
# Evidenciar el efecto en métricas y frontend para el informe.
# ============================================================================

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Uso: $0 <SLURM_JOB_ID> <modo> [args...]"
    echo ""
    echo "Modos:"
    echo "  cpu1          Matar todos los peers del segundo nodo CPU"
    echo "  cpu0          Matar todos los peers del primer nodo CPU"
    echo "  peer <ID>     Matar un peer específico (e.g., peer-3)"
    echo "  step <STEP>   Cancelar un step de srun con scancel"
    exit 1
fi

JOB_ID="$1"
MODE="$2"

# Resolver nodos asignados al job
HOSTS=($(scontrol show hostnames "$(squeue -j "${JOB_ID}" -o '%N' --noheader)"))
if [ "${#HOSTS[@]}" -lt 4 ]; then
    echo "ERROR: No se encontraron 4 nodos para el job ${JOB_ID}" >&2
    exit 1
fi

CPU_HOST_0="${HOSTS[0]}"
CPU_HOST_1="${HOSTS[1]}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

case "${MODE}" in
    cpu0)
        echo "[kill_partition] Matando peers en ${CPU_HOST_0}..."
        echo "[kill_partition] Timestamp: ${TIMESTAMP}"
        ssh "${CPU_HOST_0}" "pkill -f 'run_peer' || true"
        echo "[kill_partition] Peers en ${CPU_HOST_0} eliminados."
        echo "[kill_partition] Comunas afectadas: Santiago, Maipu, Pudahuel"
        ;;

    cpu1)
        echo "[kill_partition] Matando peers en ${CPU_HOST_1}..."
        echo "[kill_partition] Timestamp: ${TIMESTAMP}"
        ssh "${CPU_HOST_1}" "pkill -f 'run_peer' || true"
        echo "[kill_partition] Peers en ${CPU_HOST_1} eliminados."
        echo "[kill_partition] Comunas afectadas: Puente_Alto, La_Florida"
        ;;

    peer)
        if [ "$#" -lt 3 ]; then
            echo "ERROR: Falta el ID del peer (e.g., peer-3)" >&2
            exit 1
        fi
        PEER_ID="$3"
        echo "[kill_partition] Matando ${PEER_ID}..."
        echo "[kill_partition] Timestamp: ${TIMESTAMP}"
        # Buscar en ambos nodos CPU
        ssh "${CPU_HOST_0}" "pkill -f '${PEER_ID}' 2>/dev/null || true"
        ssh "${CPU_HOST_1}" "pkill -f '${PEER_ID}' 2>/dev/null || true"
        echo "[kill_partition] ${PEER_ID} eliminado."
        ;;

    step)
        if [ "$#" -lt 3 ]; then
            echo "Listando steps del job ${JOB_ID}:"
            squeue -s -j "${JOB_ID}"
            echo ""
            echo "Uso: $0 ${JOB_ID} step <STEP_ID>"
            exit 0
        fi
        STEP_ID="$3"
        echo "[kill_partition] Cancelando step ${STEP_ID}..."
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
echo "  - Métricas:  \$CIVICMESH_RUNS/slurm-${JOB_ID}/metrics/"
echo "  - Logs:      \$CIVICMESH_RUNS/slurm-${JOB_ID}/logs/"
echo "  - Frontend:  http://${HOSTS[3]}:8501"
