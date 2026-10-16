#!/bin/bash
# ============================================================
# InventAI/o — Descarga idempotente de los modelos del agente (INV-30, criterio 10)
# Baja solo los que falten, de a uno, y muestra el digest de cada uno para
# anotarlo en docs/NLP-AGENT.md. Sirve para los dos modos de N6:
#   bash scripts/descargar_modelos_llm.sh                  # Ollama nativo en WSL
#   OLLAMA_CMD="docker compose exec -T ollama ollama" \
#     bash scripts/descargar_modelos_llm.sh                # contenedor del perfil llm
# Modelos: los argumentos, o LLM_MODELO (por defecto qwen3:8b). Revisar antes el
# espacio libre en C: (df -h /mnt/c): cada modelo de 8B ocupa unos 5 GB.
# ============================================================
set -euo pipefail

OLLAMA_CMD="${OLLAMA_CMD:-$HOME/.local/ollama/bin/ollama}"
read -r -a CMD <<< "$OLLAMA_CMD"
MODELOS=("$@")
[ ${#MODELOS[@]} -gt 0 ] || MODELOS=("${LLM_MODELO:-qwen3:8b}")

con_tag() { [[ "$1" == *:* ]] && echo "$1" || echo "$1:latest"; }

instalados=$("${CMD[@]}" list | awk 'NR > 1 {print $1}')
for m in "${MODELOS[@]}"; do
  m=$(con_tag "$m")
  if grep -qxF "$m" <<< "$instalados"; then
    echo "Ya está: $m"
  else
    echo "Descargando $m…"
    "${CMD[@]}" pull "$m"
  fi
done
echo
"${CMD[@]}" list
