#!/bin/bash
# ============================================================================
# CivicMesh — Experimento de partición de red / caída de peers
# Clúster Xi DIINF (USACH)
#
# Uso (desde la consola del clúster, mientras el job corre):
#   bash slurm/kill_partition.sh <SLURM_JOB_ID> cpu1
# ============================================================================

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Uso: $0 <SLURM_JOB_ID> <modo> [args...]"
    echo ""
    echo "Modos:"
    echo "  cpu1          Matar los peers del segundo nodo CPU (xicpu03: Puente_Alto, La_Florida)"
    echo "  cpu0          Matar los peers del primer nodo CPU (xicpu02: Santiago, Maipu, Pudahuel)"
    echo "  step [ID]     Listar steps activos o cancelar uno específico"
    exit 1
fi

JOB_ID="$1"
MODE="$2"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TARGET_NODE=""

case "${MODE}" in
    cpu1)
        TARGET_NODE="xicpu03"
        echo "[kill_partition] ${TIMESTAMP} — Simulando partición / caída en ${TARGET_NODE}..."
        echo "[kill_partition] Comunas afectadas: Puente_Alto, La_Florida (peer-4, peer-5)"
        ;;

    cpu0)
        TARGET_NODE="xicpu02"
        echo "[kill_partition] ${TIMESTAMP} — Simulando partición / caída en ${TARGET_NODE}..."
        echo "[kill_partition] Comunas afectadas: Santiago, Maipu, Pudahuel (peer-1, peer-2, peer-3)"
        ;;

    step)
        if [ "$#" -lt 3 ]; then
            echo "Steps activos del job ${JOB_ID}:"
            squeue -s -j "${JOB_ID}"
            echo ""
            echo "Para cancelar: $0 ${JOB_ID} step <STEP_ID>"
            exit 0
        fi
        STEP_ID="$3"
        echo "[kill_partition] ${TIMESTAMP} — Cancelando step ${STEP_ID}..."
        scancel --signal=KILL "${STEP_ID}"
        echo "[kill_partition] Step ${STEP_ID} cancelado exitosamente."
        exit 0
        ;;

    *)
        echo "ERROR: Modo desconocido '${MODE}'. Use: cpu1, cpu0, o step." >&2
        exit 1
        ;;
esac

# Obtener los steps de Slurm que están corriendo en el nodo objetivo
STEPS=($(squeue -s -j "${JOB_ID}" --noheader -o "%i %N" 2>/dev/null | grep "${TARGET_NODE}" | awk '{print $1}' || true))

if [ "${#STEPS[@]}" -eq 0 ]; then
    echo "[kill_partition] AVISO: No se encontraron steps individuales en ${TARGET_NODE}."
    echo "[kill_partition] Cancelando directamente por nodo en Slurm..."
    scancel --nodelist="${TARGET_NODE}" --signal=KILL "${JOB_ID}" 2>/dev/null || true
else
    echo "[kill_partition] Cancelando ${#STEPS[@]} step(s) de Slurm en ${TARGET_NODE}: ${STEPS[*]}..."
    for STEP in "${STEPS[@]}"; do
        scancel --signal=KILL "${STEP}" 2>/dev/null || true
    done
fi

echo "[kill_partition] ¡Peers en ${TARGET_NODE} eliminados exitosamente!"
echo ""
echo "[kill_partition] Efecto inmediato en la malla:"
echo "  - Los peers restantes detectarán timeout de fallo en ~5 segundos (failure_timeout)."
echo "  - alive_peers disminuirá en las métricas y dead_peers aumentará."
echo "  - Verifica en: civicmesh-runs/slurm-${JOB_ID}/metrics/"
