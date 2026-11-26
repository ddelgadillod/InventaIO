"""InventAI/o — Resume por escalón la escalera de carga de INV-41 (criterio 6, el límite observado).

Lee el CSV que deja `correr.sh lectura escalera` (k6 con `--out csv=...csv.gz`) e imprime dos tablas en Markdown:
una por minuto y otra por escalón sostenido, con los usuarios virtuales, las peticiones por segundo, el p95 de cada
pantalla, los 5xx y las peticiones sin respuesta. Solo usa la biblioteca estándar:
    python3 pruebas/carga/escalones.py evidencias/inv41/k6-lecturaescalera-AAAAMMDD-HHMM.csv.gz
"""

import csv
import gzip
import sys
from collections import defaultdict
from urllib.parse import parse_qsl

PANTALLAS = ("dashboard", "alertas", "recomendaciones", "login")
# Minuto de inicio y de fin de cada escalón sostenido, y sus usuarios: los de escalera() en inventaio.js
ESCALONES = ((1, 3, 20), (4, 6, 40), (7, 9, 60), (10, 12, 80))


def percentil(valores: list[float], p: float) -> float | None:
    """Interpola entre los dos rangos más cercanos, como k6."""
    if not valores:
        return None
    orden = sorted(valores)
    pos = p * (len(orden) - 1)
    bajo = int(pos)
    alto = min(bajo + 1, len(orden) - 1)
    return orden[bajo] + (orden[alto] - orden[bajo]) * (pos - bajo)


class Tramo:
    """Lo medido en un intervalo de tiempo: un minuto o un escalón."""

    def __init__(self) -> None:
        self.duraciones: dict[str, list[float]] = defaultdict(list)
        self.peticiones = 0
        self.e5xx = 0
        self.sin_respuesta = 0
        self.vus = 0
        self.segundos: set[int] = set()

    def fila(self, etiqueta: str) -> str:
        segundos = max(len(self.segundos), 1)
        celdas = [etiqueta, str(self.vus), f"{self.peticiones / segundos:.1f}"]
        for pantalla in PANTALLAS:
            p95 = percentil(self.duraciones[pantalla], 0.95)
            celdas.append("—" if p95 is None else f"{p95 / 1000:.2f}")
        tasa = 100 * self.e5xx / self.peticiones if self.peticiones else 0
        celdas += [f"{tasa:.2f} %", str(self.sin_respuesta)]
        return "| " + " | ".join(celdas) + " |"


def leer(ruta: str) -> tuple[dict[int, Tramo], int]:
    """Agrupa las mediciones de la navegación y el login por minuto desde que arranca la escalera."""
    filas = []
    with gzip.open(ruta, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["scenario"] in ("navegacion", "login") or r["metric_name"] == "vus":
                filas.append(r)
    escalera = [int(r["timestamp"]) for r in filas if r["scenario"]]
    if not escalera:
        sys.exit("El CSV no trae mediciones de la escalera")
    origen = min(escalera)
    minutos: dict[int, Tramo] = defaultdict(Tramo)
    for r in filas:
        t = int(r["timestamp"]) - origen
        if t < 0:  # la preparación, antes de la escalera
            continue
        tramo = minutos[t // 60]
        nombre, valor = r["metric_name"], float(r["metric_value"])
        if nombre == "vus":
            tramo.vus = max(tramo.vus, int(valor))
            continue
        escenario = dict(parse_qsl(r["extra_tags"])).get("escenario", "")
        if nombre == "http_req_duration" and escenario in PANTALLAS:
            tramo.duraciones[escenario].append(valor)
            tramo.peticiones += 1
            tramo.segundos.add(t)
            tramo.sin_respuesta += r["status"] in ("", "0")
        elif nombre == "errores_5xx":
            tramo.e5xx += int(valor)
    return minutos, origen


def sumar(minutos: dict[int, Tramo], desde: int, hasta: int) -> Tramo:
    total = Tramo()
    for m in range(desde, hasta):
        tramo = minutos.get(m)
        if tramo is None:
            continue
        for pantalla, valores in tramo.duraciones.items():
            total.duraciones[pantalla].extend(valores)
        total.peticiones += tramo.peticiones
        total.e5xx += tramo.e5xx
        total.sin_respuesta += tramo.sin_respuesta
        total.vus = max(total.vus, tramo.vus)
        total.segundos |= tramo.segundos
    return total


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    minutos, _ = leer(sys.argv[1])
    encabezado = (
        "| {} | Usuarios | Peticiones/s | Dashboard p95 (s) | Alertas p95 (s) | Recomendaciones p95 (s) "
        "| Login p95 (s) | 5xx | Sin respuesta |"
    )
    separador = "| --- " * 9 + "|"

    print(
        "Por minuto desde que arranca la escalera (los usuarios son el máximo del minuto)\n"
    )
    print(encabezado.format("Minuto"))
    print(separador)
    for m in sorted(minutos):
        print(minutos[m].fila(str(m)))

    print("\nPor escalón sostenido (sin las rampas)\n")
    print(encabezado.format("Escalón"))
    print(separador)
    for desde, hasta, usuarios in ESCALONES:
        tramo = sumar(minutos, desde, hasta)
        if tramo.peticiones:
            print(tramo.fila(f"{usuarios} (min {desde}–{hasta})"))


if __name__ == "__main__":
    main()
