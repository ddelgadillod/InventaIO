"""De qué código sale cada corrida o prueba (INV-33, decisión M4): commit, rama y si había cambios sin commit.
Los resultados que se están escribiendo no cuentan como cambios."""
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EXCLUIR = ":(exclude)nlp_agent/evaluacion/resultados"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git() -> dict:
    """{"commit", "rama", "sucio"}; vacío fuera de un repositorio."""
    commit = _git("rev-parse", "HEAD")
    if not commit:
        return {}
    return {"commit": commit, "rama": _git("branch", "--show-current") or "(sin rama)",
            "sucio": bool(_git("status", "--porcelain", "--", ".", EXCLUIR))}


def etiquetas(procedencia: dict | None) -> dict:
    """Las etiquetas estándar de MLflow para la procedencia (se ven en la cabecera del run)."""
    if not procedencia:
        return {}
    return {"mlflow.source.git.commit": procedencia["commit"], "mlflow.source.git.branch": procedencia["rama"],
            "git_sucio": "sí" if procedencia.get("sucio") else "no",
            **({"git_nota": procedencia["nota"]} if procedencia.get("nota") else {})}
