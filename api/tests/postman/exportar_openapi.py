"""
InventAI/o — Exporta el OpenAPI del Core API a YAML para importarlo en Postman (INV-25)
Correr dentro del contenedor, que monta el código en /app:
docker exec inventaio-api python -m tests.postman.exportar_openapi
"""
from pathlib import Path

import yaml

from main import app

SALIDA = Path(__file__).with_name("inventaio-core-api.openapi.yml")
SERVIDOR = "http://localhost:8000"

# Ejemplos con la bodega real (foto al 2025-12-31). Postman los usa para llenar
# los parámetros y los cuerpos al importar; los opcionales quedan desactivados.
EJEMPLOS_PARAMETROS = {
    "id_producto": 171, "id_sucursal": 1, "id_proveedor": 1,       # arroz P3937, PRINCIPAL
    "sucursal_id": 1, "sucursal": "PRINCIPAL", "categoria": "Huevos", "familia": "Huevos",
    "busqueda": "ARROZ", "semaforo": "critico", "tipo": "inconsistencia_inventario", "urgencia": "alta",
    "fecha_inicio": "2025-12-01", "fecha_fin": "2025-12-31",
}
EJEMPLOS_CUERPO = {                       # el login ya trae el suyo en LoginRequest
    "/api/auth/refresh": {"refresh_token": "<refresh_token del login>"},
    "/api/ml/predict": {"producto_id": "P1632", "sucursal_id": "PRINCIPAL", "horizonte": 15},
}


def exportar() -> dict:
    original = app.openapi()
    spec = {"openapi": original["openapi"], "info": original["info"],
            "servers": [{"url": SERVIDOR, "description": "Docker Compose local"}], **original}
    for ruta, operaciones in spec["paths"].items():
        for operacion in operaciones.values():
            for parametro in operacion.get("parameters", []):
                if parametro["name"] in EJEMPLOS_PARAMETROS:
                    parametro["example"] = EJEMPLOS_PARAMETROS[parametro["name"]]
            cuerpo = operacion.get("requestBody", {}).get("content", {}).get("application/json")
            if cuerpo is not None and ruta in EJEMPLOS_CUERPO:
                cuerpo["example"] = EJEMPLOS_CUERPO[ruta]
    return spec


if __name__ == "__main__":
    SALIDA.write_text(yaml.safe_dump(exportar(), allow_unicode=True, sort_keys=False, width=120),
                      encoding="utf-8")
    print(f"OpenAPI exportado a {SALIDA}")
