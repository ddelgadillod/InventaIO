"""
INV-82 — Los montos del reporte del punto de venta en una sola base (docs/INV-82-requerimientos.md, D1, D2 y H10 a H14).

Venta sin IVA (D1). El reporte trae, por fila, la venta, el costo, el IVA y la utilidad. Unos archivos registran la venta con
IVA (utilidad = venta − costo − IVA) y otros sin IVA (utilidad = venta − costo): ene-abr 2022 y nov-2022 a dic-2025 con IVA;
may-oct 2022 y 2026 sin IVA. Cada archivo es de un solo tipo, y la utilidad de sus filas con IVA dice cuál: no se supone nada.
Un archivo que no cumple una de las dos reglas en al menos el 99 % de esas filas detiene el ETL.

Costos imposibles (D2). Una línea con venta y con un costo de más de 3 veces su venta viene así del punto de venta (por
ejemplo, el costo de una caja en una venta por unidad). Su costo pasa a ser su venta por la razón costo/venta mediana del
mismo producto en sus líneas válidas; sin ellas, la de su categoría, y sin categoría, la de toda la bodega. Las líneas con
venta 0 (obsequios) no se tocan.
"""
import csv
from array import array
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

CON_IVA, SIN_IVA = "con_iva", "sin_iva"
TOLERANCIA = 1.0              # pesos: el reporte redondea la utilidad
MINIMO_REGLA = 0.99           # fracción de las filas con IVA de un archivo que debe cumplir su regla
IVA_MINIMO = 1.0              # con menos de un peso de IVA, las dos reglas coinciden y la fila no decide
FACTOR_COSTO_IMPOSIBLE = 3.0


class ErrorMontos(ValueError):
    """Un archivo del reporte no se puede clasificar: el ETL se detiene en lugar de mezclar bases."""


def numero(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def regla_de_fila(fila: dict) -> str | None:
    """CON_IVA o SIN_IVA según la utilidad de la fila; None si la fila no tiene IVA o no cumple ninguna."""
    v, c, i, u = (numero(fila.get(k)) for k in ("valor_venta", "costo", "valor_iva", "utilidad"))
    if abs(i) < IVA_MINIMO:
        return None
    if abs(v - c - i - u) < TOLERANCIA:
        return CON_IVA
    if abs(v - c - u) < TOLERANCIA:
        return SIN_IVA
    return None


@dataclass
class _Cuenta:
    con: int = 0
    sin: int = 0
    total: int = 0


def clasificar_archivos(filas: Iterable[dict]) -> dict[str, str]:
    """El tipo de cada `archivo_origen`. Un archivo sin filas con IVA es SIN_IVA: no hay nada que restar."""
    cuentas: dict[str, _Cuenta] = defaultdict(_Cuenta)
    for fila in filas:
        archivo = fila.get("archivo_origen") or ""
        cuenta = cuentas[archivo]
        if abs(numero(fila.get("valor_iva"))) < IVA_MINIMO:
            continue
        cuenta.total += 1
        regla = regla_de_fila(fila)
        cuenta.con += regla == CON_IVA
        cuenta.sin += regla == SIN_IVA
    tipos = {}
    for archivo, c in cuentas.items():
        if c.total == 0:
            tipos[archivo] = SIN_IVA
        elif c.con >= MINIMO_REGLA * c.total:
            tipos[archivo] = CON_IVA
        elif c.sin >= MINIMO_REGLA * c.total:
            tipos[archivo] = SIN_IVA
        else:
            raise ErrorMontos(f"El archivo «{archivo}» no tiene una sola base de venta: de {c.total} filas con IVA, {c.con} "
                              f"cumplen utilidad = venta − costo − IVA y {c.sin}, utilidad = venta − costo. Revisar su parser")
    return tipos


def clasificar_csv(ruta: Path) -> dict[str, str]:
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return clasificar_archivos(csv.DictReader(f))


def venta_sin_iva(fila: dict, tipos: dict[str, str]) -> float:
    """La venta de la fila sin IVA, en valor absoluto (las devoluciones vienen en negativo)."""
    venta = abs(numero(fila.get("valor_venta")))
    if tipos.get(fila.get("archivo_origen") or "") == CON_IVA:
        venta -= abs(numero(fila.get("valor_iva")))
    return round(venta, 2)


def costo_imposible(venta: float, costo: float) -> bool:
    return venta > 0 and costo > FACTOR_COSTO_IMPOSIBLE * venta


@dataclass
class Razones:
    """Las razones costo/venta de las líneas válidas, por producto, por categoría y de toda la bodega."""
    categoria_de: dict[str, str] = field(default_factory=dict)
    por_producto: dict[str, array] = field(default_factory=lambda: defaultdict(lambda: array("d")))
    por_categoria: dict[str, array] = field(default_factory=lambda: defaultdict(lambda: array("d")))
    todas: array = field(default_factory=lambda: array("d"))
    _medianas: dict = field(default_factory=dict)

    def agregar(self, codigo: str, venta: float, costo: float) -> None:
        if venta <= 0 or costo_imposible(venta, costo):
            return
        r = costo / venta
        self.por_producto[codigo].append(r)
        if categoria := self.categoria_de.get(codigo):
            self.por_categoria[categoria].append(r)
        self.todas.append(r)

    def _mediana(self, clave, valores: array) -> float | None:
        if clave not in self._medianas:
            self._medianas[clave] = median(valores) if valores else None
        return self._medianas[clave]

    def razon(self, codigo: str) -> tuple[float, str]:
        """La razón de referencia de un producto y de dónde salió: producto, categoría o bodega."""
        if codigo in self.por_producto and (r := self._mediana(("p", codigo), self.por_producto[codigo])) is not None:
            return r, "producto"
        categoria = self.categoria_de.get(codigo)
        if categoria in self.por_categoria and (r := self._mediana(("c", categoria), self.por_categoria[categoria])) is not None:
            return r, "categoria"
        r = self._mediana(("b",), self.todas)
        if r is None:
            raise ErrorMontos("No hay ninguna línea con costo válido para imputar")
        return r, "bodega"


def cargar_categorias(ruta: Path) -> dict[str, str]:
    """codigo_item → categoria de un dim_producto.csv, o vacío si no existe."""
    if not ruta.is_file():
        return {}
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return {r["codigo_item"]: r.get("categoria") or "" for r in csv.DictReader(f)}
