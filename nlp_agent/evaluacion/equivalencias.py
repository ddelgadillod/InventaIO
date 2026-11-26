"""
Equivalencias declaradas de INV-40 (decisión del usuario del 18-nov) para calificar los conjuntos escritos antes de
las herramientas nuevas: el v1 y los holdouts esperan las herramientas de entonces.

1. `ficha_producto` vale donde se esperaba `consultar_inventario` o `pronosticar_demanda` de un producto: la ficha
   trae el stock y el pronóstico de ese producto.
2. `periodo` vale en `historial_ventas` donde se aceptaba `dias` o `agrupacion` («ventas del mes pasado»).
3. En una pregunta de abstención, consultar solo `buscar_en_glosario` y abstenerse, o responder con la guía de uso,
   cuenta como abstención («Dame información sobre el asistente»).
4. INV-72 (formulario del 26-nov): en `historial_ventas`, `por` con un periodo (mes, trimestre o año) vale donde se
   esperaba `agrupacion` con ese periodo: desde INV-72 los dos dan el mismo análisis por periodo.

Solo cambian la herramienta y, con ella, el acierto; los demás criterios quedan como los calificó el arnés. Se
reportan las dos cifras, la estricta y con equivalencias (docs/INV-40-requerimientos.md, §11).

    python -m evaluacion.comparar --base <base>.jsonl --nuevo <nuevo>.jsonl --equivalencias
"""
import copy

from evaluacion.calificacion import se_abstiene
from evaluacion.conjunto import Esperado, Pregunta, cargar, coincide

OTROS = ("fidelidad", "hechos", "prohibido", "aclaracion", "rechazo", "sin_error", "abstiene", "cita")
POR_PERIODO = ("mes", "trimestre", "anio")


def esperados(pregunta: Pregunta) -> list[Esperado]:
    salida = list(pregunta.esperado)
    for e in pregunta.esperado:
        if e.herramienta in ("consultar_inventario", "pronosticar_demanda") and "producto" in {**e.argumentos, **e.opcionales}:
            salida.append(Esperado(herramienta="ficha_producto",
                                   argumentos={k: v for k, v in e.argumentos.items() if k == "producto"}))
        if e.herramienta == "historial_ventas" and {"dias", "agrupacion"} & set(e.opcionales):
            salida.append(Esperado(herramienta="historial_ventas", argumentos=e.argumentos,
                                   opcionales={**e.opcionales, "periodo": "*"}))
        if e.herramienta == "historial_ventas" and e.argumentos.get("agrupacion") in POR_PERIODO:
            argumentos = {k: v for k, v in e.argumentos.items() if k != "agrupacion"} | {"por": e.argumentos["agrupacion"]}
            salida.append(Esperado(herramienta="historial_ventas", argumentos=argumentos,
                                   opcionales={**e.opcionales, "agrupacion": "*"}))
    return salida


def elige(pregunta: Pregunta, llamadas: list[tuple[str, dict]], texto: str) -> bool:
    if pregunta.sin_respuesta:
        return True
    if pregunta.abstencion:
        return not llamadas or ({n for n, _ in llamadas} == {"buscar_en_glosario"}
                                and (se_abstiene(texto) or "guía de uso" in texto.lower()))
    return any(coincide(e, n, a) for e in esperados(pregunta) for n, a in llamadas) or (
        pregunta.abstencion_valida and not llamadas)


def version_de(meta: dict) -> str:
    """«v1 (real, 61 preguntas)» → «v1»."""
    return meta["conjunto"].split(" ")[0]


def recalificar(archivo: dict) -> dict:
    """Una copia del archivo de resultados (`reporte.leer`) con la herramienta y el acierto con equivalencias."""
    preguntas = {p.id: p for p in cargar("local", version_de(archivo["meta"])).preguntas}
    salida = copy.deepcopy(archivo)
    for c in salida["corridas"]:
        cal = c["calificacion"]
        primera = [(x["herramienta"], x["argumentos"]) for x in c["llamadas"] if x.get("ronda", 1) == 1]
        herramienta = elige(preguntas[c["id"]], primera, c["texto"])
        cal["herramienta"] = herramienta
        if cal.get("herramienta_ejecutada") is not None:
            cal["herramienta_ejecutada"] = herramienta
        cal["acierto"] = herramienta and all(cal.get(k, True) for k in OTROS)
    return salida
