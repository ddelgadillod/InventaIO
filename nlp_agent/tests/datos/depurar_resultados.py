"""
INV-72 — Copias depuradas de resultados del modo real para las pruebas del CI.

Los resultados del modo real traen respuestas de Vera y resultados de herramientas con datos del negocio, así que
viven en evidencias/resultados-agente/ (privado, fuera del repositorio). Las pruebas del registro en MLflow necesitan
algunos: la línea meta (modelo, huellas, git), las calificaciones, los tiempos, los tokens y qué herramienta se llamó.
Esta copia los conserva y quita lo demás: el texto de la respuesta y su borrador, los resultados de las herramientas
y los valores de los argumentos. Las métricas que se calculan con ella son las mismas que con el original.

    cd nlp_agent
    python tests/datos/depurar_resultados.py ../evidencias/resultados-agente 2026-10-21_local/qwen3_8b_gpu_real.jsonl
"""
import json
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent / "resultados"
OMITIDA = "[respuesta omitida: el original está en evidencias/resultados-agente]"


def depurar(corrida: dict) -> dict:
    llamadas = [{**llamada, "argumentos": {k: "[omitido]" for k in (llamada.get("argumentos") or {})}}
                for llamada in corrida.get("llamadas") or []]
    salida = {**corrida, "texto": OMITIDA if corrida.get("texto") else corrida.get("texto"), "resultados": [],
              "llamadas": llamadas}
    if isinstance(corrida.get("verificacion"), dict) and corrida["verificacion"].get("borrador"):
        salida["verificacion"] = {**corrida["verificacion"], "borrador": OMITIDA}     # el borrador también es texto
    return salida


def copiar(origen: Path, relativa: str, destino: Path = DESTINO) -> Path:
    lineas = (origen / relativa).read_text(encoding="utf-8").splitlines()
    salida = destino / relativa
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join([lineas[0], *(json.dumps(depurar(json.loads(linea)), ensure_ascii=False)
                                             for linea in lineas[1:] if linea.strip())]) + "\n", encoding="utf-8")
    return salida


if __name__ == "__main__":
    origen = Path(sys.argv[1])
    for relativa in sys.argv[2:]:
        print(copiar(origen, relativa))
