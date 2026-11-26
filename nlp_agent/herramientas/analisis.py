"""
El análisis de ventas de `historial_ventas` (INV-72, recibido de INV-82: decisiones 3 y 4 de docs/INV-82-requerimientos.md).

La herramienta pide a GET /api/reportes/ventas/analisis una o dos dimensiones con filtros fijos; aquí se arman, sin modelo:

- las `conclusiones` que lee el modelo: el total, la fila con más y con menos venta (y unidades, si se pueden sumar), el
  margen, la variación entre años y, con dos dimensiones, el máximo de cada valor de la otra. El modelo empieza su
  respuesta por ellas y no saca conclusiones de filas sueltas (hallazgo H5);
- la tabla con las filas en el orden pedido y la gráfica con todas las filas devueltas: dos dimensiones con el tiempo en
  barras agrupadas (o líneas si son meses), una serie en el tiempo en barras o líneas y una dimensión que no es tiempo en
  barras horizontales;
- las etiquetas con el periodo en palabras («Ventas por sucursal y año · septiembre de 2024 a 2026», hallazgo H7).

Un periodo con ventas en menos del 90 % de sus días (2026 hasta septiembre, 2022 sin noviembre ni diciembre, febrero de
2023 con un solo día) es parcial: se marca en la tabla y queda fuera de los extremos y de las variaciones, con una nota.
"""
from calendar import monthrange
from datetime import date

from herramientas.base import Columna, grafico, tabla, tarjeta
from herramientas.formato import texto_cantidad, texto_numero

DIMENSIONES = ("anio", "trimestre", "mes", "sucursal", "categoria", "producto")
TIEMPO = ("anio", "trimestre", "mes")
NOMBRE = {"anio": "año", "trimestre": "trimestre", "mes": "mes", "sucursal": "sucursal", "categoria": "categoría",
          "producto": "producto"}
TITULO = {d: n.capitalize() for d, n in NOMBRE.items()}
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre")
MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MAX_FILAS_TABLA = 24            # dos años de meses: la tabla del chat; la gráfica lleva todas las filas devueltas
MAX_FILAS_MODELO = 24
MAX_SERIES = 6                  # una gráfica con más series no se lee: pasa a barras horizontales
MAX_NOMBRES_GRUPO = 5
# Las ventas sin terminal: cuentan en los totales, pero no son una sucursal que compita en los extremos ni en las variaciones
SIN_SUCURSAL = "SIN_SUCURSAL"
UMBRAL_COMPLETO = 0.9           # días con ventas sobre los días del periodo


def pesos(valor: float) -> str:
    return f"$ {texto_numero(valor)}"


def porcentaje(valor: float | None) -> str:
    return "—" if valor is None else f"{texto_numero(valor, 1)} %"


def variacion(valor: float | None) -> str:
    return "—" if valor is None else f"{'+' if valor >= 0 else '−'}{texto_numero(abs(valor), 1)} %"


def participacion(parte: float, total: float) -> str:
    return porcentaje(100 * parte / total) if total else "—"


def cantidad_texto(valor: float, kg: bool | None) -> str:
    """Con la unidad, si se sabe (un producto o un grupo); si no, solo el número."""
    return texto_numero(valor) if kg is None else texto_cantidad(valor, kg)


def texto_valor(dimension: str, valor: str) -> str:
    """«2025-09» → «sep 2025»; «2025-T3» → «T3 2025»; lo demás, igual."""
    if dimension == "mes" and len(valor) == 7:
        return f"{MESES_CORTOS[int(valor[5:]) - 1]} {valor[:4]}"
    if dimension == "trimestre" and "-T" in valor:
        return f"{valor[5:]} {valor[:4]}"
    if dimension == "sucursal" and valor == SIN_SUCURSAL:
        return "Sin sucursal"
    return valor


def sin_anio(dimension: str, valor: str) -> str:
    """INV-72 (inv82-b-02): el mes o el trimestre sin su año, para comparar el mismo periodo entre años («2025-T1» → «T1»,
    «2025-09» → «septiembre»); lo demás, igual."""
    if dimension == "mes" and len(valor) == 7:
        return MESES[int(valor[5:]) - 1]
    if dimension == "trimestre" and "-T" in valor:
        return valor[5:]
    return texto_valor(dimension, valor)


def de_sucursales(filas: list[dict]) -> list[dict]:
    """Las filas sin las ventas sin terminal (si queda alguna); con ellas, si no."""
    return [f for f in filas if f["dimensiones"].get("sucursal") != SIN_SUCURSAL] or filas


def dias_del_periodo(dimension: str, valor: str, meses: list[int] | None = None) -> int:
    """Los días del calendario de un año (o de sus `meses`, si se filtró por mes), un trimestre o un mes."""
    anio = int(valor[:4])
    if dimension == "mes":
        return monthrange(anio, int(valor[5:7]))[1]
    if dimension == "trimestre":
        t = int(valor[-1])
        return sum(monthrange(anio, m)[1] for m in range(3 * t - 2, 3 * t + 1))
    return sum(monthrange(anio, m)[1] for m in (meses or range(1, 13)))


def parcial(fila: dict, dims: list[str], meses: list[int] | None = None) -> bool:
    """Si el periodo más fino de la fila tuvo ventas en menos del 90 % de sus días. Sin tiempo, nunca."""
    tiempo = next((d for d in ("mes", "trimestre", "anio") if d in dims), None)
    if tiempo is None or "dias_con_ventas" not in fila:
        return False
    return fila["dias_con_ventas"] < UMBRAL_COMPLETO * dias_del_periodo(tiempo, fila["dimensiones"][tiempo], meses)


def nombre_periodo(fila: dict, dims: list[str]) -> str:
    """El periodo de una fila parcial: «2026», «feb 2023»."""
    tiempo = next(d for d in ("mes", "trimestre", "anio") if d in dims)
    return texto_valor(tiempo, fila["dimensiones"][tiempo])


def nombre_fila(fila: dict, dims: list[str]) -> str:
    partes = []
    for d in dims:
        valor = fila["dimensiones"][d]
        partes.append(fila.get("producto_nombre") or valor if d == "producto" else texto_valor(d, valor))
    return " · ".join(partes)


def _lista(textos: list[str]) -> str:
    return textos[0] if len(textos) == 1 else f"{', '.join(textos[:-1])} y {textos[-1]}"


def periodo_en_palabras(meses: list[int] | None, anios: list[int] | None, desde: str, hasta: str) -> str:
    """«septiembre de 2024 a 2026», «2024 a 2026», «sep 2025» o «ene 2022 a sep 2026»."""
    if anios:
        rango = str(anios[0]) if len(anios) == 1 else f"{anios[0]} a {anios[-1]}"
        if meses:
            return f"{_lista([MESES[m - 1] for m in meses])} de {rango}"
        return rango
    a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
    if meses:
        return f"{_lista([MESES[m - 1] for m in meses])}, {a.year} a {b.year}"
    inicio, fin = f"{MESES_CORTOS[a.month - 1]} {a.year}", f"{MESES_CORTOS[b.month - 1]} {b.year}"
    return inicio if inicio == fin else f"{inicio} a {fin}"


def titulo(dims: list[str], periodo: str, *filtros: str | None) -> str:
    por = " y ".join(NOMBRE[d] for d in dims)
    return " · ".join([f"Ventas por {por}", periodo, *[f for f in filtros if f]])


def conclusiones(dims: list[str], d: dict, kg: bool | None, grupo: list[str] | None = None) -> list[str]:
    """Las conclusiones del código sobre todas las filas devueltas (D3): cifras ya formateadas, para que el modelo las
    copie y el verificador las encuentre. Las unidades solo se suman si no mezclan kilos y unidades."""
    total = d["total"]
    todas = de_sucursales(d["filas"])
    parciales = [f for f in todas if parcial(f, dims, d.get("meses"))]
    filas = [f for f in todas if f not in parciales] or todas
    salida = []
    cantidad = None if d["unidades_mixtas"] else (lambda v: cantidad_texto(v, kg))
    partes_total = [f"ventas {pesos(total['valor_total'])}", f"margen {pesos(total['margen'])} "
                    f"({porcentaje(total['margen_pct'])} de las ventas)"]
    if cantidad:
        partes_total.append(cantidad(total["cantidad"]))
    salida.append("Total: " + ", ".join(partes_total) + ".")
    if not filas:
        return salida
    completas = d["filas_totales"] == len(d["filas"])
    extremos = [("valor_total", "venta", pesos)] + ([("cantidad", "unidades", cantidad)] if cantidad else [])
    if len(filas) > 1:
        for clave, que, fmt in extremos:
            mayor = max(filas, key=lambda f, c=clave: f[c])
            texto = (f"Más {que}: {nombre_fila(mayor, dims)}, {fmt(mayor[clave])} "
                     f"({participacion(mayor[clave], total[clave])} del total)")
            if completas:
                menor = min(filas, key=lambda f, c=clave: f[c])
                texto += (f"; menos {que}: {nombre_fila(menor, dims)}, {fmt(menor[clave])} "
                          f"({participacion(menor[clave], total[clave])} del total)")
            salida.append(texto + ".")
        con_margen = [f for f in filas if f.get("margen_pct") is not None]
        if len(con_margen) > 1:
            alto = max(con_margen, key=lambda f: f["margen_pct"])
            bajo = min(con_margen, key=lambda f: f["margen_pct"])
            salida.append(f"Mayor margen: {nombre_fila(alto, dims)} ({porcentaje(alto['margen_pct'])}); menor margen: "
                          f"{nombre_fila(bajo, dims)} ({porcentaje(bajo['margen_pct'])}).")
    if not completas:
        salida.append(f"Hay {texto_numero(d['filas_totales'])} filas en total; las conclusiones son de las "
                      f"{texto_numero(len(d['filas']))} devueltas, en el orden pedido.")
    if len(todas) < len(d["filas"]):
        salida.append("Las ventas sin sucursal asignada (sin terminal) cuentan en el total, no en las comparaciones.")
    if parciales and len(filas) < len(todas):
        nombres = list(dict.fromkeys(nombre_periodo(f, dims) for f in parciales))
        salida.append(f"Periodos con datos parciales, fuera de las comparaciones: {_lista(nombres)}.")
    salida += _variaciones(dims, filas)
    if comparadas := [f for f in d["filas"] if f.get("anterior")]:      # como el total: también sin sucursal
        actual = sum(f["valor_total"] for f in comparadas)
        antes = sum(f["anterior"]["valor_total"] for f in comparadas)
        if antes:
            salida.append(f"Frente al mismo periodo un año antes: ventas {pesos(actual)} contra {pesos(antes)} "
                          f"({variacion(100 * (actual - antes) / antes)}).")
    if grupo:
        nombres = grupo[:MAX_NOMBRES_GRUPO]
        resto = len(grupo) - len(nombres)
        salida.append(f"Se sumaron {len(grupo)} productos: {', '.join(nombres)}" + (f" y {resto} más." if resto else "."))
    return salida


def _variaciones(dims: list[str], filas: list[dict]) -> list[str]:
    """La variación entre años: del primero al último y año contra año; con dos dimensiones, por cada valor de la otra,
    y el mayor de cada valor de la otra."""
    salida = []
    if "anio" in dims:
        otra = next((d for d in dims if d != "anio"), None)
        grupos: dict[str, dict[str, float]] = {}
        for f in filas:
            clave = sin_anio(otra, f["dimensiones"][otra]) if otra else ""
            grupos.setdefault(clave, {})[f["dimensiones"]["anio"]] = f["valor_total"]
        partes = []
        for clave, por_anio in grupos.items():
            anios = sorted(por_anio)
            if len(anios) < 2 or not por_anio[anios[0]]:
                continue
            total = variacion(100 * (por_anio[anios[-1]] - por_anio[anios[0]]) / por_anio[anios[0]])
            nombre = (clave + ": ") if otra else ""
            if otra or len(anios) == 2:
                partes.append(f"{nombre}{total} de {anios[0]} a {anios[-1]}")
            else:
                pasos = [f"{b} frente a {a} {variacion(100 * (por_anio[b] - por_anio[a]) / por_anio[a])}"
                         for a, b in zip(anios, anios[1:], strict=False) if por_anio[a]]
                partes.append(f"{total} de {anios[0]} a {anios[-1]} ({'; '.join(pasos)})")
        if partes:
            salida.append("Variación de las ventas: " + "; ".join(partes) + ".")
    if len(dims) == 2:
        primera, segunda = dims
        mejores = {}
        for f in filas:
            clave = sin_anio(segunda, f["dimensiones"][segunda]) if primera == "anio" else f["dimensiones"][segunda]
            if clave not in mejores or f["valor_total"] > mejores[clave]["valor_total"]:
                mejores[clave] = f
        if len(mejores) > 1:
            nombre = (lambda k: k) if primera == "anio" else (lambda k: texto_valor(segunda, k))
            salida.append(f"Mayor venta de cada {NOMBRE[segunda]}: " + "; ".join(
                f"{nombre(k)}, {texto_valor(primera, f['dimensiones'][primera])} ({pesos(f['valor_total'])})"
                for k, f in mejores.items()) + ".")
    return salida


def grafica(dims: list[str], filas: list[dict], unidad: str = "$") -> dict | None:
    """La gráfica con todas las filas devueltas: la forma sale de las dimensiones (sección 4.6)."""
    if not filas:
        return None
    tiempo = [d for d in dims if d in TIEMPO]
    if len(dims) == 2 and tiempo:
        x, otra = tiempo[0], next(d for d in dims if d != tiempo[0])
        series = list(dict.fromkeys(f["dimensiones"][otra] for f in filas))
        if len(series) <= MAX_SERIES:
            puntos: dict[str, dict] = {}
            for f in filas:
                v = f["dimensiones"][x]
                punto = puntos.setdefault(v, {"periodo": texto_valor(x, v), "_orden": v})
                punto[f"s{series.index(f['dimensiones'][otra])}"] = f["valor_total"]
            datos = [puntos[k] for k in sorted(puntos)]
            etiquetas = [(f"s{i}", (next(f.get("producto_nombre") for f in filas if f["dimensiones"][otra] == s)
                                    if otra == "producto" else texto_valor(otra, s))) for i, s in enumerate(series)]
            return grafico("linea" if x == "mes" and len(datos) > 12 else "barras", "periodo", etiquetas, datos, unidad)
    if len(dims) == 1 and tiempo:
        datos = sorted(({"periodo": texto_valor(dims[0], f["dimensiones"][dims[0]]), "_orden": f["dimensiones"][dims[0]],
                         "valor": f["valor_total"], "margen": f["margen"]} for f in filas), key=lambda p: p["_orden"])
        return grafico("linea" if len(datos) > 12 else "barras", "periodo", [("valor", "Ventas"), ("margen", "Margen")],
                       datos, unidad)
    # Sin tiempo (o con demasiadas series): barras horizontales en el orden pedido
    datos = [{"nombre": nombre_fila(f, dims), "valor": f["valor_total"]} for f in filas]
    return grafico("barras_h", "nombre", [("valor", "Ventas")], datos, unidad)


def con_cantidad(dims: list[str], d: dict) -> bool:
    """La columna de cantidad: si las unidades se pueden sumar, o si cada fila es un producto."""
    return not d["unidades_mixtas"] or "producto" in dims


def columnas(dims: list[str], unidades: bool, comparar: bool) -> list[Columna]:
    cols = [Columna(f"d_{d}", TITULO[d]) for d in dims]
    if unidades:
        cols.append(Columna("cantidad", "Cantidad", "cantidad"))
    cols += [Columna("valor", "Ventas"), Columna("margen", "Margen"), Columna("margen_pct", "Margen %")]
    if comparar:
        cols += [Columna("valor_anterior", "Ventas un año antes"), Columna("variacion", "Variación")]
    return cols


def fila_texto(f: dict, dims: list[str], unidades: bool, kg: bool | None, comparar: bool,
               meses: list[int] | None = None) -> dict:
    fila = {f"d_{d}": (f.get("producto_nombre") or f["dimensiones"][d]) if d == "producto"
            else texto_valor(d, f["dimensiones"][d]) for d in dims}
    if parcial(f, dims, meses):
        tiempo = next(d for d in ("mes", "trimestre", "anio") if d in dims)
        fila[f"d_{tiempo}"] += " (parcial)"
    if "producto" in dims:
        fila["codigo"] = f["dimensiones"]["producto"]
    if unidades:
        fila["cantidad"] = (texto_cantidad(f["cantidad"], f.get("unidad") == "kg") if "producto" in dims
                            else cantidad_texto(f["cantidad"], kg))
    fila |= {"valor": pesos(f["valor_total"]), "margen": pesos(f["margen"]), "margen_pct": porcentaje(f["margen_pct"])}
    if comparar:
        fila["valor_anterior"] = pesos(f["anterior"]["valor_total"]) if f.get("anterior") else "—"
        fila["variacion"] = variacion(f.get("variacion_valor_pct"))
    return fila


def presentar(dims: list[str], d: dict, periodo: str, filtros: list[str | None], kg: bool | None,
              grupo: list[str] | None) -> tuple[dict, dict | None]:
    """(lo que lee el modelo, el `data` del chat) de una respuesta del análisis. `kg`: si las unidades son kilos, o
    None si no se sabe (sin filtro de producto)."""
    comparar = d["comparar"]
    unidades = con_cantidad(dims, d)
    filas = [fila_texto(f, dims, unidades, kg, comparar, d.get("meses")) for f in d["filas"]]
    cuerpo = None
    if filas:
        total = d["total"]
        tarjetas = [tarjeta("Ventas", pesos(total["valor_total"]), periodo),
                    tarjeta("Margen", pesos(total["margen"]), f"{porcentaje(total['margen_pct'])} de las ventas")]
        if not d["unidades_mixtas"]:
            tarjetas.append(tarjeta("Cantidad", cantidad_texto(total["cantidad"], kg)))
        cuerpo = tabla(titulo(dims, periodo, *filtros), columnas(dims, unidades, comparar), filas[:MAX_FILAS_TABLA],
                       d["filas_totales"], tarjetas=tarjetas, grafico=grafica(dims, d["filas"]))
    para_modelo = {
        "fecha_dato": d["datos_hasta"],
        "historia_desde": d["datos_desde"], "historia_hasta": d["datos_hasta"],
        "periodo_desde": d["periodo_desde"],
        "consulta": {"por": [NOMBRE[x] for x in dims], "periodo": periodo,
                     **({"filtros": [f for f in filtros if f]} if any(filtros) else {}),
                     "orden": d["orden"] + (" de menor a mayor" if d["ascendente"] else " de mayor a menor")
                     if d["orden"] != "natural" else "natural"},
        "conclusiones": conclusiones(dims, d, kg, grupo),
        "total": d["filas_totales"], "mostrando": min(len(filas), MAX_FILAS_MODELO),
        "filas": filas[:MAX_FILAS_MODELO],
    }
    if d["unidades_mixtas"]:
        para_modelo["nota"] = "Las unidades mezclan kilos y unidades de productos distintos: compara las ventas en pesos."
    return para_modelo, cuerpo
