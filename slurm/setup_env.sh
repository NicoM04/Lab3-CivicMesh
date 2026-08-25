#!/bin/bash
#SBATCH --job-name=setup-civicmesh
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:10:00
#SBATCH --output=setup-civicmesh-%j.out
#SBATCH --error=setup-civicmesh-%j.err

# ============================================================================
# CivicMesh — Script de instalación del entorno virtual (.venv) en Slurm
#
# Uso:
#   sbatch slurm/setup_env.sh
#   o directamente en el nodo login:
#   bash slurm/setup_env.sh
# ============================================================================

set -euo pipefail

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${REPO_DIR}"

echo "[setup] Creando entorno virtual en ${REPO_DIR}/.venv..."
python3 -m venv "${REPO_DIR}/.venv"

echo "[setup] Actualizando pip..."
"${REPO_DIR}/.venv/bin/pip" install --upgrade pip

echo "[setup] Instalando dependencias (civicmesh, streamlit, pandas, pytest)..."
"${REPO_DIR}/.venv/bin/pip" install -e "${REPO_DIR}[test]" streamlit pandas

echo ""
echo "[setup] Verificando instalación..."
"${REPO_DIR}/.venv/bin/python3" -c "import streamlit, pandas, civicmesh; print('-> OK: Streamlit', streamlit.__version__, '| Pandas', pandas.__version__, '| CivicMesh listo')"

echo ""
echo "[setup] ¡Entorno virtual listo y compartido en: ${REPO_DIR}/.venv!"
