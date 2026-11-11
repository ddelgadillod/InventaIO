#!/usr/bin/env python3
"""
InventAI/o — Versión única del producto (release v2.1.0).

El archivo VERSION de la raíz es la fuente. Este script la escribe en cada lugar donde la versión se
muestra o se publica: la interfaz (package.json, que leen el login y la barra superior), el Core API y
su OpenAPI versionado, el ML Service, el agente y el README. Con --verificar solo compara y falla si
alguno no coincide; el CI lo corre en cada Pull Request.

    python scripts/version.py 2.1.0        # cambia VERSION y todos los lugares
    python scripts/version.py --verificar  # compara, sin cambiar nada

El package-lock.json se reescribe como lo hace npm (JSON con 2 espacios y salto de línea final), así
que solo cambian sus dos campos de versión.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_VERSION = RAIZ / "VERSION"
SEMVER = re.compile(r"\d+\.\d+\.\d+")

# (archivo, expresión con un grupo para la versión). Cada expresión debe encontrar exactamente un lugar
LUGARES = [
    ("frontend/package.json", r'^  "version": "([^"]+)",$'),
    ("api/main.py", r'^    version="([^"]+)",$'),
    ("api/tests/postman/inventaio-core-api.openapi.yml", r"^  version: (\S+)$"),
    ("ml_service/main.py", r'^    version="([^"]+)",$'),
    ("nlp_agent/core/config.py", r'^VERSION = "([^"]+)"$'),
    ("README.md", r"badge/version-([0-9.]+)-"),
]
LOCK = "frontend/package-lock.json"


def leer_lock() -> dict:
    return json.loads((RAIZ / LOCK).read_text(encoding="utf-8"))


def versiones() -> dict[str, str]:
    """La versión que dice cada lugar, por nombre."""
    encontradas = {}
    for archivo, patron in LUGARES:
        texto = (RAIZ / archivo).read_text(encoding="utf-8")
        hallazgos = re.findall(patron, texto, flags=re.M)
        if len(hallazgos) != 1:
            raise SystemExit(f"{archivo}: se esperaba un lugar con la versión y hay {len(hallazgos)}")
        encontradas[archivo] = hallazgos[0]
    lock = leer_lock()
    encontradas[LOCK] = lock["version"]
    encontradas[f"{LOCK} (paquete raíz)"] = lock["packages"][""]["version"]
    return encontradas


def escribir(version: str) -> None:
    ARCHIVO_VERSION.write_text(version + "\n", encoding="utf-8")
    for archivo, patron in LUGARES:
        ruta = RAIZ / archivo
        texto = ruta.read_text(encoding="utf-8")

        def poner(m: re.Match) -> str:
            return m.group(0).replace(m.group(1), version)

        ruta.write_text(re.sub(patron, poner, texto, count=1, flags=re.M), encoding="utf-8")
    lock = leer_lock()
    lock["version"] = version
    lock["packages"][""]["version"] = version
    (RAIZ / LOCK).write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verificar() -> int:
    esperada = ARCHIVO_VERSION.read_text(encoding="utf-8").strip()
    distintas = {a: v for a, v in versiones().items() if v != esperada}
    if distintas:
        print(f"La versión del producto es {esperada} (VERSION), pero:")
        for archivo, version in distintas.items():
            print(f"  {archivo}: {version}")
        print(f"Corregir con: python scripts/version.py {esperada}")
        return 1
    print(f"Versión {esperada} en los {len(LUGARES) + 2} lugares")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description="Versión única del producto")
    a.add_argument("version", nargs="?", help="versión nueva, X.Y.Z")
    a.add_argument("--verificar", action="store_true", help="solo compara con VERSION")
    args = a.parse_args()
    if args.verificar:
        return verificar()
    if not args.version or not SEMVER.fullmatch(args.version):
        a.error("indicar la versión como X.Y.Z, o --verificar")
    escribir(args.version)
    return verificar()


if __name__ == "__main__":
    sys.exit(main())
