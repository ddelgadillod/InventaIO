"""
InventAI/o — Mediciones de rendimiento del modelo de lenguaje (INV-30, criterio 3).
Sin Docker, contra cualquier Ollama (LLM_BASE_URL). Desde la raíz del repositorio:
    python scripts/smoke_llm.py --modelo qwen3:8b [--modo cpu] [--razonamiento]
El código está en nlp_agent/evaluacion/smoke.py; el examen completo, en
nlp_agent/evaluacion/correr.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nlp_agent"))

from evaluacion.smoke import main  # noqa: E402

if __name__ == "__main__":
    main()
