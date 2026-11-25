"""InventAI/o — Resume un reporte JSON de OWASP ZAP por riesgo (INV-41, docs/INV-41-requerimientos.md, sección 4.5).
Uso: python3 pruebas/seguridad/resumen_zap.py evidencias/inv41/zap-….json
Imprime cada alerta con su riesgo, su identificador de regla, cuántas veces apareció y hasta tres URL, de la más grave
a la menos grave. Sale con 1 si hay alguna alerta alta, que el criterio 5 no admite abierta."""
import json
import sys
from collections import defaultdict

ORDEN = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
NOMBRE = {"High": "Alta", "Medium": "Media", "Low": "Baja", "Informational": "Informativa"}


def main(ruta: str) -> int:
    with open(ruta, encoding="utf-8") as f:
        reporte = json.load(f)
    alertas = defaultdict(lambda: {"veces": 0, "urls": []})
    for sitio in reporte.get("site", []):
        for a in sitio.get("alerts", []):
            riesgo = a["riskdesc"].split(" ")[0]
            clave = (riesgo, a["pluginid"], a["name"])
            for inst in a.get("instances", []):
                alertas[clave]["veces"] += 1
                if len(alertas[clave]["urls"]) < 3:
                    alertas[clave]["urls"].append(f'{inst.get("method", "")} {inst.get("uri", "")}'.strip())
    if not alertas:
        print("Sin alertas")
        return 0
    conteo = defaultdict(int)
    for (riesgo, regla, nombre), datos in sorted(alertas.items(), key=lambda x: (ORDEN.get(x[0][0], 9), x[0][2])):
        conteo[riesgo] += 1
        print(f"[{NOMBRE.get(riesgo, riesgo)}] {nombre} (regla {regla}): {datos['veces']} veces")
        for url in datos["urls"]:
            print(f"    {url}")
    print()
    print(", ".join(f"{NOMBRE.get(r, r)}: {conteo[r]}" for r in sorted(conteo, key=lambda r: ORDEN.get(r, 9))))
    return 1 if conteo.get("High") else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: resumen_zap.py REPORTE.json")
    sys.exit(main(sys.argv[1]))
