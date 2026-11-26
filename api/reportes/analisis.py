"""
InventAI/o — Análisis de ventas (INV-72, recibido de INV-82: decisión 3 y T3 de docs/INV-82-requerimientos.md).

GET /api/reportes/ventas/analisis agrupa las ventas por una o dos dimensiones de una lista fija, con filtros fijos. Vera elige
las dimensiones y los filtros; el SQL se arma aquí, con los valores como parámetros: el modelo no escribe SQL (decisión 30).
Aquí van las piezas sin base de datos (validación, SQL y armado de la respuesta), para probarlas sin Postgres.
"""
from datetime import date

from fastapi import HTTPException, status

# Expresión de cada dimensión sobre dim_tiempo (t), dim_sucursal (s) y dim_producto (p). Su texto da el orden natural
DIMENSIONES = {
    "anio": "TO_CHAR(t.fecha, 'YYYY')",
    "trimestre": "TO_CHAR(t.fecha, 'YYYY') || '-T' || TO_CHAR(t.fecha, 'Q')",
    "mes": "TO_CHAR(t.fecha, 'YYYY-MM')",
    "sucursal": "s.nombre",
    "categoria": "p.categoria",
    "producto": "p.codigo_item",
}
DIMENSIONES_TIEMPO = ("anio", "trimestre", "mes")
# Cómo se ordena por cada medida, sobre la consulta agrupada (g)
ORDENES = {
    "valor": "g.valor",
    "cantidad": "g.cantidad",
    "margen": "(g.valor - g.costo)",
    "margen_pct": "(g.valor - g.costo) / NULLIF(g.valor, 0)",
}
NATURAL = "natural"
MAX_DIMENSIONES = 2
MAX_PRODUCTOS = 50
MAX_LIMITE = 200


def _error(mensaje: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, mensaje)


def _partir(valores: list[str] | None) -> list[str]:
    """Acepta el parámetro repetido (?a=1&a=2) o separado por comas (?a=1,2)."""
    return [v.strip() for valor in (valores or []) for v in valor.split(",") if v.strip()]


def normalizar_dimensiones(pedidas: list[str]) -> list[str]:
    dimensiones = [d.lower() for d in _partir(pedidas)]
    validas = ", ".join(DIMENSIONES)
    if not 1 <= len(dimensiones) <= MAX_DIMENSIONES:
        raise _error(f"Pide una o dos dimensiones de: {validas}")
    if fuera := [d for d in dimensiones if d not in DIMENSIONES]:
        raise _error(f"Dimensión no válida: {', '.join(fuera)}. Válidas: {validas}")
    if len(set(dimensiones)) != len(dimensiones):
        raise _error("Una dimensión no se puede repetir")
    return dimensiones


def normalizar_enteros(valores: list[str] | None, nombre: str, minimo: int, maximo: int) -> list[int] | None:
    """Los meses (1 a 12) o los años, sin repetidos y en orden; None si no se pidió ninguno."""
    textos = _partir(valores)
    if not textos:
        return None
    try:
        numeros = sorted({int(t) for t in textos})
    except ValueError:
        raise _error(f"{nombre}: solo números enteros") from None
    if numeros[0] < minimo or numeros[-1] > maximo:
        raise _error(f"{nombre}: de {minimo} a {maximo}")
    return numeros


def normalizar_productos(valores: list[str] | None) -> list[str] | None:
    """Los códigos de un grupo de productos, sin repetidos y en el orden pedido; hasta MAX_PRODUCTOS."""
    codigos = list(dict.fromkeys(_partir(valores)))
    if len(codigos) > MAX_PRODUCTOS:
        raise _error(f"productos: hasta {MAX_PRODUCTOS} códigos por consulta")
    return codigos or None


def normalizar_orden(orden: str, ascendente: bool | None) -> tuple[str, bool]:
    """(orden, ascendente). Por defecto, el orden natural va de menor a mayor y una medida, de mayor a menor."""
    orden = orden.lower()
    if orden != NATURAL and orden not in ORDENES:
        raise _error(f"orden no válido: {orden}. Válidos: {NATURAL}, {', '.join(ORDENES)}")
    if ascendente is None:
        ascendente = orden == NATURAL
    return orden, ascendente


def un_anio_antes(d: date) -> date:
    """La misma fecha un año antes; el 29 de febrero pasa al 28."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def un_anio_despues(dimension: str, valor: str) -> str:
    """El valor de una dimensión de tiempo un año después («2025-09» → «2026-09»); las demás no cambian."""
    if dimension not in DIMENSIONES_TIEMPO:
        return valor
    return f"{int(valor[:4]) + 1}{valor[4:]}"


def sql_analisis(dimensiones: list[str], filtros: str, orden_sql: str | None) -> str:
    """La consulta agrupada. Con orden_sql, además los totales de todas las filas (antes del límite) y el límite;
    sin él, solo las filas agrupadas (la del año anterior, para comparar)."""
    columnas = [f"{DIMENSIONES[d]} AS d{i}" for i, d in enumerate(dimensiones)]
    por_kilo = "COALESCE(p.se_vende_por_kilo, false)"
    if "producto" in dimensiones:
        columnas += ["MIN(p.nombre) AS producto_nombre", f"BOOL_OR({por_kilo}) AS producto_por_kilo"]
    union_sucursal = "JOIN dw.dim_sucursal s ON s.id_sucursal = v.id_sucursal" if "sucursal" in dimensiones else ""
    agrupada = f"""
        SELECT {", ".join(columnas)},
               SUM(v.cantidad) AS cantidad, SUM(v.valor_total) AS valor, SUM(v.costo_total) AS costo,
               COUNT(*) AS transacciones, COUNT(DISTINCT v.id_tiempo) AS dias,
               BOOL_OR({por_kilo}) AS hay_kilo, BOOL_OR(NOT {por_kilo}) AS hay_unidad
        FROM dw.fact_ventas v
        JOIN dw.dim_tiempo t ON t.id_tiempo = v.id_tiempo
        JOIN dw.dim_producto p ON p.id_producto = v.id_producto
        {union_sucursal}
        WHERE t.fecha BETWEEN :fi AND :ff AND NOT v.es_devolucion {filtros}
        GROUP BY {", ".join(str(i + 1) for i in range(len(dimensiones)))}"""
    if orden_sql is None:
        return agrupada
    return f"""
        WITH g AS ({agrupada})
        SELECT g.*,
               COUNT(*) OVER () AS filas_totales,
               SUM(g.cantidad) OVER () AS total_cantidad, SUM(g.valor) OVER () AS total_valor,
               SUM(g.costo) OVER () AS total_costo, SUM(g.transacciones) OVER () AS total_transacciones,
               BOOL_OR(g.hay_kilo) OVER () AS total_hay_kilo, BOOL_OR(g.hay_unidad) OVER () AS total_hay_unidad
        FROM g
        ORDER BY {orden_sql}
        LIMIT :limite"""


def orden_sql(dimensiones: list[str], orden: str, ascendente: bool) -> str:
    sentido = "ASC" if ascendente else "DESC"
    naturales = [f"g.d{i}" for i in range(len(dimensiones))]
    if orden == NATURAL:
        return ", ".join(f"{n} {sentido}" for n in naturales)
    # Los empates, en orden natural
    return f"{ORDENES[orden]} {sentido} NULLS LAST, " + ", ".join(naturales)


def medidas(cantidad, valor, costo, transacciones) -> dict:
    cantidad, valor, costo = float(cantidad or 0), float(valor or 0), float(costo or 0)
    margen = valor - costo
    return {"cantidad": cantidad, "valor_total": valor, "costo_total": costo, "margen": margen,
            "margen_pct": round(100 * margen / valor, 2) if valor else None,
            "transacciones": int(transacciones or 0)}


def variacion_pct(actual: float, anterior: float) -> float | None:
    return round(100 * (actual - anterior) / anterior, 2) if anterior else None


def clave_fila(fila, dimensiones: list[str]) -> tuple[str, ...]:
    return tuple(str(getattr(fila, f"d{i}")) for i in range(len(dimensiones)))


def armar_fila(fila, dimensiones: list[str], anteriores: dict | None) -> dict:
    """Una fila de la respuesta. Con `anteriores` (clave ya llevada un año adelante → fila del año anterior), sus medidas
    del año anterior y la variación."""
    resultado = {"dimensiones": dict(zip(dimensiones, clave_fila(fila, dimensiones), strict=True)),
                 **medidas(fila.cantidad, fila.valor, fila.costo, fila.transacciones),
                 "dias_con_ventas": int(fila.dias)}
    if "producto" in dimensiones:
        resultado["producto_nombre"] = fila.producto_nombre
        resultado["unidad"] = "kg" if fila.producto_por_kilo else "unidad"
    if anteriores is not None:
        previa = anteriores.get(clave_fila(fila, dimensiones))
        if previa is not None:
            resultado["anterior"] = medidas(previa.cantidad, previa.valor, previa.costo, previa.transacciones)
            resultado["variacion_valor_pct"] = variacion_pct(resultado["valor_total"], resultado["anterior"]["valor_total"])
            resultado["variacion_cantidad_pct"] = variacion_pct(resultado["cantidad"], resultado["anterior"]["cantidad"])
    return resultado


def indexar_anteriores(filas, dimensiones: list[str]) -> dict:
    """Las filas del año anterior, con su clave llevada un año adelante para cruzarlas con las del periodo pedido."""
    return {tuple(un_anio_despues(d, v) for d, v in zip(dimensiones, clave_fila(f, dimensiones), strict=True)): f
            for f in filas}
