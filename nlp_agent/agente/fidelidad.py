"""
Verificador de la respuesta del agente (INV-33, criterio 4; decisiones Z4 y Z12).

Un solo verificador para el agente y el arnés: el calificador (`evaluacion/calificacion.py`) lo importa, así que
lo que se mide es lo que el agente revisa antes de responder. Tres reglas:

- **Cifras (Z4a):** cada número de la respuesta debe estar en la pregunta, en el contexto que tuvo el modelo
  (la fecha de la foto, el horizonte de 15 días hábiles, «LA 21») o en los resultados que recibió, o ser la
  suma de una columna de esos resultados. Se aceptan los dos formatos de miles (3.366 y 3,366; 1.250,5) y se
  ignoran los números de 0 a 10, que suelen ser conteos u ordinales. Costos conocidos: una cifra inventada que
  coincida con el contexto no se detecta, y una redonda como «2.000» también se lee como 2,0 (formato en-US), así
  que la respalda cualquier 2 de los resultados.
- **El total (Z4b, C4 e I8):** si un resultado trae `total` mayor que lo que mostró, la respuesta debe decir el
  total («147 productos críticos; estos son los 10 primeros»).
- **La fecha (Z2):** si la respuesta usa datos, debe decir su fecha. No pide reintento: el bucle agrega el cierre
  fijo («Datos al 31 de diciembre de 2025.»).

Las dos primeras piden un reintento con lo que hay que corregir (`Verificacion.correccion`).

INV-33 (P3, 23-oct) agrega una cuarta, que el bucle usa solo con la mejora `sin_datos` y el calificador como
marca (no entra en el acierto): **sin datos con contenido**. Si las herramientas no trajeron nada (el glosario sin
resultados, un producto que no existe, una lista vacía) y la respuesta no lo dice, sino que afirma contenido, es
texto inventado sin cifras (h-08 del holdout: el verificador de cifras no lo ve).
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

NUMERO = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])")
UMBRAL_CONTEO = 10
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def lecturas(cifra: str) -> set[float]:
    """Los valores posibles de una cifra escrita: 1.250 (es-CO) o 1,250 (en-US), 2,1 o 2.1."""
    valores = set()
    for miles, decimal in ((".", ","), (",", ".")):
        partes = cifra.split(decimal)
        if len(partes) > 2:
            continue
        entero = partes[0]
        if miles in entero and not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(miles)}\d{{3}})+", entero):
            continue
        try:
            valores.add(float(entero.replace(miles, "") + ("." + partes[1] if len(partes) == 2 else "")))
        except ValueError:
            pass
    return valores


def numeros(texto: str) -> list[set[float]]:
    """Cada cifra del texto, con sus lecturas posibles."""
    return [lecturas(m.group()) for m in NUMERO.finditer(texto)]


def listas_de_filas(valor: Any):
    if isinstance(valor, list) and valor and all(isinstance(x, dict) for x in valor):
        yield valor
    if isinstance(valor, dict):
        for v in valor.values():
            yield from listas_de_filas(v)


def _sumas(filas: list[dict], columnas: dict[str, float]) -> None:
    for fila in filas:
        for clave, valor in fila.items():
            leidos = numeros(str(valor))
            if len(leidos) == 1 and len(leidos[0]) == 1:
                columnas[clave] = columnas.get(clave, 0) + next(iter(leidos[0]))


def permitidos(contexto: str, resultados: list[Any]) -> set[float]:
    """Las cifras que la respuesta puede usar: las del contexto (por partes, como las fechas) y las de los
    resultados, con las sumas por columna de cada lista de filas y entre resultados (una llamada por sucursal)."""
    salida = set().union(*numeros(contexto)) if numeros(contexto) else set()
    salida |= {float(x) for x in re.findall(r"\d+", contexto)}
    entre: dict[str, float] = {}
    for r in resultados:
        for filas in listas_de_filas(r):
            _sumas(filas, entre)
            columnas: dict[str, float] = {}
            _sumas(filas, columnas)
            salida |= {round(v, 2) for v in columnas.values()}
        for leidas in numeros(json.dumps(r, ensure_ascii=False)):
            salida |= leidas
        salida |= {float(x) for clave in _claves(r) for x in re.findall(r"\d+", clave)}
    return salida | {round(v, 2) for v in entre.values()}


def _claves(valor: Any):
    """Los nombres de los campos: «ventas_30d» respalda «los últimos 30 días» (falso positivo del 22-oct)."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield str(k)
            yield from _claves(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _claves(v)


def cifras_no_respaldadas(texto: str, contexto: str, resultados: list[Any]) -> list[str]:
    """`contexto`: la pregunta más lo que el modelo sabía antes de las herramientas (prompt de sistema)."""
    validas = permitidos(contexto, resultados)
    return [m.group() for m in NUMERO.finditer(texto)
            if not all(v <= UMBRAL_CONTEO for v in lecturas(m.group())) and not lecturas(m.group()) & validas]


def totales_omitidos(texto: str, resultados: list[Any]) -> list[int]:
    """Los `total` de resultados recortados (total > lo mostrado) que la respuesta no dice."""
    dichas = set().union(*numeros(texto)) if numeros(texto) else set()
    faltan = []
    for r in resultados:
        if not isinstance(r, dict) or not isinstance(r.get("total"), int):
            continue
        mostrado = r.get("mostrando", len(r["filas"]) if isinstance(r.get("filas"), list) else r["total"])
        if r["total"] > mostrado and float(r["total"]) not in dichas:
            faltan.append(r["total"])
    return faltan


def fecha_de(resultados: list[Any]) -> str | None:
    """La fecha de los datos que leyó el modelo (`fecha_dato`), si la hay."""
    return next((r["fecha_dato"] for r in resultados if isinstance(r, dict) and r.get("fecha_dato")), None)


def escrita(fecha: str) -> str:
    d = date.fromisoformat(fecha)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def dice_la_fecha(texto: str, fecha: str) -> bool:
    """«31 de diciembre de 2025», «31 de diciembre», «2025-12-31» o «31/12/2025»."""
    d = date.fromisoformat(fecha)
    t = texto.lower()
    return (f"{d.day} de {MESES[d.month - 1]}" in t or fecha in t
            or re.search(rf"\b0?{d.day}[/-]0?{d.month}[/-]{d.year}\b", t) is not None)


VACIOS = ("sin_resultados", "no_encontrado")
NIEGA = ("no hay", "no tengo", "no encontr", "no tiene", "no aparece", "no existe", "sin datos", "no dispongo", "no cuento",
         "no se encontr", "no esta disponible", "no puedo", "no contiene", "no figura", "no registra", "ninguno", "ninguna")


def vacio(resultado: Any) -> bool:
    """Una herramienta que respondió sin datos: el glosario sin resultados, un producto que no existe, una lista vacía."""
    if not isinstance(resultado, dict) or "error" in resultado:
        return False
    return resultado.get("resultado") in VACIOS or (resultado.get("total") == 0 and not resultado.get("filas"))


def sin_datos_con_contenido(texto: str, resultados: list[Any]) -> bool:
    """Todas las herramientas respondieron sin datos y la respuesta no lo dice: afirma algo."""
    if not resultados or not all(vacio(r) for r in resultados) or not texto.strip():
        return False
    t = re.sub(r"[^0-9a-z]+", " ", unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower())
    return not any(n in f" {t} " for n in NIEGA)


@dataclass
class Verificacion:
    cifras_sin_respaldo: list[str] = field(default_factory=list)
    sin_consultar: bool = False                # dio cifras sin haber consultado ninguna herramienta
    totales_omitidos: list[int] = field(default_factory=list)
    fecha: str | None = None                  # la de los datos, si la respuesta no la dice (Z2: cierre fijo)
    sin_datos_con_contenido: bool = False     # P3: solo si se pidió revisarlo

    @property
    def ok(self) -> bool:
        """Sin cifras sin respaldo, totales omitidos ni contenido sin datos; la fecha no pide reintento."""
        return not self.cifras_sin_respaldo and not self.totales_omitidos and not self.sin_datos_con_contenido

    def correccion(self) -> str:
        """Lo que se le pide al modelo en el reintento (Z4)."""
        partes = []
        if self.cifras_sin_respaldo and self.sin_consultar:
            partes.append(f"diste cifras ({', '.join(self.cifras_sin_respaldo)}) sin consultar ninguna herramienta; "
                          "consulta la herramienta que corresponda y usa solo sus cifras")
        elif self.cifras_sin_respaldo:
            partes.append(f"estas cifras no están en los datos consultados: {', '.join(self.cifras_sin_respaldo)}; "
                          "usa solo las cifras de los resultados")
        if self.totales_omitidos:
            partes.append(f"di el total de los resultados ({', '.join(str(t) for t in self.totales_omitidos)}) y que "
                          "muestras solo una parte")
        if self.sin_datos_con_contenido:
            partes.append("las herramientas no trajeron información sobre eso: dilo en una frase, sin inventar nada, y "
                          "ofrece lo que sí puedes consultar")
        return "Corrige tu respuesta: " + "; ".join(partes) + "." if partes else ""

    def cierre(self) -> str:
        """El cierre fijo con la fecha de los datos (Z2), si hace falta."""
        return f"Datos al {escrita(self.fecha)}." if self.fecha else ""


def verificar(texto: str, contexto: str, resultados: list[Any], sin_datos: bool = False) -> Verificacion:
    """`sin_datos` (P3): revisar también el contenido afirmado cuando las herramientas no trajeron nada."""
    fecha = fecha_de(resultados)
    return Verificacion(cifras_sin_respaldo=cifras_no_respaldadas(texto, contexto, resultados), sin_consultar=not resultados,
                        totales_omitidos=totales_omitidos(texto, resultados),
                        fecha=fecha if fecha and not dice_la_fecha(texto, fecha) else None,
                        sin_datos_con_contenido=sin_datos and sin_datos_con_contenido(texto, resultados))


INICIO_RESPALDO = "No pude redactar una respuesta verificada; estos son los datos consultados:"
SIN_DATOS = "No hay datos para esa pregunta en el sistema."
MAX_TABLAS_RESPALDO, MAX_FILAS_RESPALDO = 3, 5


def respaldo(datos: list[dict], fecha: str | None) -> str:
    """La respuesta de respaldo (Z9): solo con las tablas que devolvieron las herramientas (`Resultado.data`), con
    su total, las primeras filas con sus unidades y la fecha. Sin datos (cifras inventadas sin consultar), lo dice."""
    if not datos:
        return SIN_DATOS
    partes = [INICIO_RESPALDO]
    for d in datos[:MAX_TABLAS_RESPALDO]:
        filas = d.get("filas") or []
        total = d.get("total", len(filas))
        partes.append(f"\n**{d.get('titulo', 'Datos')}** ({total} en total" +
                      (f"; se muestran {min(len(filas), MAX_FILAS_RESPALDO)})" if total > MAX_FILAS_RESPALDO else ")") + ":")
        for fila in filas[:MAX_FILAS_RESPALDO]:
            partes.append("- " + ", ".join(f"{c['titulo']}: {fila.get(c['clave'])}" for c in d.get("columnas", [])
                                           if fila.get(c["clave"]) not in (None, "")))
    if fecha:
        partes.append(f"\nDatos al {escrita(fecha)}.")
    return "\n".join(partes)
