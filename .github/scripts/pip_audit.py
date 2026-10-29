"""
InventAI/o — pip-audit con las excepciones aceptadas (INV-24, D12).

Uso: python .github/scripts/pip_audit.py -r api/requirements.txt [más argumentos de pip-audit]

Lee .github/pip-audit-excepciones.txt, falla si alguna excepción ya venció y
corre pip-audit ignorando solo las vigentes: cualquier otra vulnerabilidad
conocida hace fallar el paso.
"""
import subprocess
import sys
from datetime import date
from pathlib import Path

EXCEPCIONES = Path(__file__).resolve().parent.parent / "pip-audit-excepciones.txt"


def leer_excepciones(ruta: Path = EXCEPCIONES, hoy: date | None = None):
    """Devuelve (vigentes, vencidas), cada una como lista de (id, vence, paquete, motivo)."""
    hoy = hoy or date.today()
    vigentes, vencidas = [], []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        ident, vence, paquete, motivo = linea.split(maxsplit=3)
        destino = vigentes if date.fromisoformat(vence) >= hoy else vencidas
        destino.append((ident, vence, paquete, motivo))
    return vigentes, vencidas


def main(argumentos: list[str]) -> int:
    vigentes, vencidas = leer_excepciones()
    for ident, vence, paquete, _ in vencidas:
        print(f"::error::La excepción {ident} ({paquete}) venció el {vence}: "
              "corregirla, renovarla con un motivo nuevo o quitarla de .github/pip-audit-excepciones.txt")
    if vencidas:
        return 1
    for ident, vence, paquete, _ in vigentes:
        print(f"Excepción aceptada hasta el {vence}: {ident} ({paquete})")
    ignorar = [f"--ignore-vuln={ident}" for ident, *_ in vigentes]
    return subprocess.call(["pip-audit", "--progress-spinner", "off", *ignorar, *argumentos])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
