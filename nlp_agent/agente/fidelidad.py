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

INV-40 (decisión 4) agrega tres reglas que también piden reintento, y activa la de «sin datos con contenido»:

- **Etiquetas sin consultar (hallazgo H12):** la respuesta trae etiquetas como «<reporte> ventas </reporte>» y no
  hubo ninguna consulta.
- **«No hay» sin consultar (INV-77):** la respuesta niega que haya datos («no hay traslados», «no existen…») sin
  haber consultado ninguna herramienta. Las frases fijas de permiso, alcance e instrucciones no cuentan.
- **Cita inventada (ronda de ajuste del 18-nov):** la respuesta nombra una sección de la guía («sección 8.3»,
  «Guía de uso, 12.7») que no vino en los fragmentos consultados, o sin haber consultado la guía.
- **«La mayoría» sobre una muestra (hallazgo H14):** la respuesta dice «la mayoría», «casi todos» o «más de la
  mitad» y lo único que vio fue una lista parcial (`total` mayor que `mostrando`) sin un resumen global.

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


def permitidos(contexto: str, resultados: list[Any], porcentajes: bool = True) -> set[float]:
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
    salida |= {round(v, 2) for v in entre.values()}
    # C5 (24-oct): un cuantil 0,89 se dice «89 %» (h2-08: el respaldo reemplazaba una buena respuesta del glosario)
    return salida | ({round(v * 100, 2) for v in salida if 0 < v < 1} if porcentajes else set())


def _claves(valor: Any):
    """Los nombres de los campos: «ventas_30d» respalda «los últimos 30 días» (falso positivo del 22-oct)."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield str(k)
            yield from _claves(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _claves(v)


def cifras_no_respaldadas(texto: str, contexto: str, resultados: list[Any], porcentajes: bool = True) -> list[str]:
    """`contexto`: la pregunta más lo que el modelo sabía antes de las herramientas (prompt de sistema)."""
    validas = permitidos(contexto, resultados, porcentajes)
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


def _normal(texto: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore")
                           .decode().lower()).split())


def opciones(resultados: list[Any]) -> list[tuple[str, ...]]:
    """INV-33 (P2): las opciones que trajo la herramienta para aclarar: (nombre, código) de los candidatos o de los
    productos encontrados, o (categoría,) de la pista de categorías."""
    salida = []
    for r in resultados:
        if not isinstance(r, dict):
            continue
        for c in r.get("candidatos") or []:
            salida.append((c.get("nombre", ""), c.get("codigo", "")))
        for f in r.get("filas") or []:
            if isinstance(f, dict) and "codigo" in f and "nombre" in f:
                salida.append((f["nombre"], f["codigo"]))
        if r.get("aclarar"):
            salida += [(c,) for c in r.get("categorias") or []]
    return list(dict.fromkeys(salida))


def nombra_opciones(texto: str, resultados: list[Any]) -> bool:
    """Nombra al menos 2 de las opciones (o la única), por su nombre o su código; sin opciones, sí."""
    todas = opciones(resultados)
    if not todas:
        return True
    t = _normal(texto)
    return sum(any(x and _normal(x) in t for x in o) for o in todas) >= min(2, len(todas))


PREGUNTA_CUAL = re.compile(r"\bcual(es)?\b|\belige\b|\bescoge\b")


def aclaracion_sin_opciones(texto: str, resultados: list[Any]) -> bool:
    """Pregunta «¿cuál?» sin nombrar las opciones que trajo la herramienta (v1-08, v1-15, v1-41 el 22-oct)."""
    return "?" in texto and bool(PREGUNTA_CUAL.search(_normal(texto))) and bool(opciones(resultados)) \
        and not nombra_opciones(texto, resultados)


VACIOS = ("sin_resultados", "no_encontrado")
NIEGA = ("no hay", "no tengo", "no encontr", "no tiene", "no aparece", "no existe", "sin datos", "no dispongo", "no cuento",
         "no se encontr", "no esta disponible", "no puedo", "no contiene", "no figura", "no registra", "ninguno", "ninguna")


ETIQUETA = re.compile(r"</?[A-Za-z][\w-]*(?:\s[^<>]*)?>")
NIEGA_DATOS = re.compile(r"\bno (hay|existen?|se (encontr|registr|report)\w*|encontr\w*|tenemos|tienen?|cuentan? con)\b")
FRASES_FIJAS = ("fuera de lo que puedo consultar", "no tienes permiso", "no puedo compartir",
                "no puedo dar informacion de otros usuarios")
CUANTIFICADOR = re.compile(r"\b(la mayoria|la mayor parte|casi todos|casi todas|mas de la mitad|en su mayoria|"
                           r"practicamente todos|practicamente todas)\b")
RESUMEN_GLOBAL = ("global", "por_tipo", "por_urgencia", "por_estado", "suma_por_sucursal")
CITA_SECCION = re.compile(r"(?:secci[oó]n|gu[ií]a de uso|cap[ií]tulo)[^.\n\d]{0,25}?(\d{1,2}\.\d{1,2})(?![\d.,]\d)", re.IGNORECASE)
NO_HAY_DATOS = ("no hay datos", "no tengo esa informacion", "no tengo informacion", "fuera de lo que puedo consultar",
                "no tienes permiso", "no puedo dar informacion")


def cita_inventada(texto: str, resultados: list[Any]) -> bool:
    """La respuesta cita una sección de la guía que no está en las fuentes de los fragmentos que trajo la búsqueda."""
    citadas = set(CITA_SECCION.findall(texto))
    if not citadas:
        return False
    fuentes = " ".join(f.get("fuente", "") for r in resultados if isinstance(r, dict)
                       for f in (r.get("fragmentos") or []) if isinstance(f, dict))
    return any(not re.search(rf"(?<![\d.]){re.escape(s)}(?![\d])", fuentes) for s in citadas)


def niega_datos(texto: str) -> bool:
    """Una respuesta de «no hay datos» o de abstención: no lleva el cierre con la fecha de los datos."""
    t = _normal(texto)
    return any(f in t for f in NO_HAY_DATOS)


def etiquetas_sin_consultar(texto: str, resultados: list[Any]) -> bool:
    """H12: «<reporte> ventas </reporte>» sin llamar ninguna herramienta."""
    return not resultados and bool(ETIQUETA.search(texto))


def niega_sin_consultar(texto: str, resultados: list[Any]) -> bool:
    """INV-77: «no hay traslados» dicho sin haber consultado ninguna herramienta."""
    if resultados:
        return False
    t = _normal(texto)
    return not any(f in t for f in FRASES_FIJAS) and bool(NIEGA_DATOS.search(t))


def cuantificador_sobre_muestra(texto: str, resultados: list[Any]) -> bool:
    """H14: «la mayoría están en inconsistencia» mirando los 10 primeros de una lista más larga, sin un resumen."""
    if not CUANTIFICADOR.search(_normal(texto)):
        return False
    parciales = [r for r in resultados if isinstance(r, dict) and isinstance(r.get("total"), int)
                 and isinstance(r.get("mostrando"), int) and r["total"] > r["mostrando"]]
    con_resumen = any(isinstance(r, dict) and any(k in r for k in RESUMEN_GLOBAL) for r in resultados)
    return bool(parciales) and not con_resumen


def vacio(resultado: Any) -> bool:
    """Una herramienta que respondió sin datos: el glosario sin resultados, un producto que no existe, una lista vacía."""
    if not isinstance(resultado, dict) or "error" in resultado:
        return False
    return resultado.get("resultado") in VACIOS or (resultado.get("total") == 0 and not resultado.get("filas"))


def sin_datos_con_contenido(texto: str, resultados: list[Any]) -> bool:
    """Todas las herramientas respondieron sin datos y la respuesta no lo dice: afirma algo."""
    if not resultados or not all(vacio(r) for r in resultados) or not texto.strip():
        return False
    t = _normal(texto)
    return not any(n in f" {t} " for n in NIEGA)


@dataclass
class Verificacion:
    cifras_sin_respaldo: list[str] = field(default_factory=list)
    sin_consultar: bool = False                # dio cifras sin haber consultado ninguna herramienta
    totales_omitidos: list[int] = field(default_factory=list)
    fecha: str | None = None                  # la de los datos, si la respuesta no la dice (Z2: cierre fijo)
    sin_datos_con_contenido: bool = False     # P3; activa en el agente desde INV-40 (decisión 4)
    etiquetas_sin_consultar: bool = False     # INV-40, H12
    niega_sin_consultar: bool = False         # INV-40, INV-77
    cuantificador_sobre_muestra: bool = False  # INV-40, H14
    cita_inventada: bool = False              # INV-40, ronda de ajuste

    @property
    def ok(self) -> bool:
        """Sin cifras sin respaldo, totales omitidos, contenido sin datos ni las reglas de INV-40; la fecha no pide
        reintento."""
        return not (self.cifras_sin_respaldo or self.totales_omitidos or self.sin_datos_con_contenido
                    or self.etiquetas_sin_consultar or self.niega_sin_consultar or self.cuantificador_sobre_muestra
                    or self.cita_inventada)

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
        if self.etiquetas_sin_consultar:
            partes.append("escribiste etiquetas en lugar de consultar; si la pregunta pide datos, llama la herramienta "
                          "que corresponda y responde en texto normal")
        if self.niega_sin_consultar:
            partes.append("dijiste que no hay datos sin consultar ninguna herramienta; consulta primero y responde con "
                          "lo que traiga")
        if self.cita_inventada:
            partes.append("citaste una sección de la guía que no trajo la búsqueda; consulta buscar_en_glosario y cita solo "
                          "la sección que traiga, o no cites ninguna")
        if self.cuantificador_sobre_muestra:
            partes.append("dijiste «la mayoría» o «casi todos» mirando solo una parte de la lista; di cuántos son de los "
                          "que se muestran y el total, o consulta el resumen")
        return "Corrige tu respuesta: " + "; ".join(partes) + "." if partes else ""

    def cierre(self) -> str:
        """El cierre fijo con la fecha de los datos (Z2), si hace falta."""
        return f"Datos al {escrita(self.fecha)}." if self.fecha else ""


def verificar(texto: str, contexto: str, resultados: list[Any], sin_datos: bool = False,
              porcentajes: bool = True, reglas_inv40: bool = False) -> Verificacion:
    """`sin_datos` (P3): revisar también el contenido afirmado cuando las herramientas no trajeron nada.
    `reglas_inv40`: las tres reglas de INV-40 (el agente las usa siempre; el calificador las marca aparte).
    `porcentajes` (C5): aceptar «89 %» por un 0,89. El calificador lo acepta siempre; el agente, solo con la
    corrección `glosario` (decisión del 24-oct: el agente integrado se comporta como el del 22-oct)."""
    fecha = fecha_de(resultados)
    return Verificacion(cifras_sin_respaldo=cifras_no_respaldadas(texto, contexto, resultados, porcentajes),
                        sin_consultar=not resultados,
                        totales_omitidos=totales_omitidos(texto, resultados),
                        fecha=fecha if fecha and not dice_la_fecha(texto, fecha) and not niega_datos(texto) else None,
                        sin_datos_con_contenido=sin_datos and sin_datos_con_contenido(texto, resultados),
                        etiquetas_sin_consultar=reglas_inv40 and etiquetas_sin_consultar(texto, resultados),
                        niega_sin_consultar=reglas_inv40 and niega_sin_consultar(texto, resultados),
                        cuantificador_sobre_muestra=reglas_inv40 and cuantificador_sobre_muestra(texto, resultados),
                        cita_inventada=reglas_inv40 and cita_inventada(texto, resultados))


INICIO_RESPALDO = "No pude redactar una respuesta verificada; estos son los datos consultados:"
INICIO_GLOSARIO = "Esto dice el glosario del negocio:"
MAX_CARACTERES_GLOSARIO = 700


def respaldo_glosario(resultados: list[Any]) -> str | None:
    """C5 (24-oct): el respaldo de una respuesta del glosario cita el fragmento y su fuente; sin esto decía «No hay
    datos para esa pregunta», aunque el glosario sí había respondido (h2-08)."""
    for r in resultados:
        if isinstance(r, dict) and r.get("resultado") == "encontrado" and r.get("fragmentos"):
            f = r["fragmentos"][0]
            texto = f["texto"].split("\n\nFuente.")[0].split("\n\nTambién se dice.")[0].strip()
            if len(texto) > MAX_CARACTERES_GLOSARIO:
                texto = texto[:MAX_CARACTERES_GLOSARIO].rsplit(" ", 1)[0] + "…"
            return f"{INICIO_GLOSARIO}\n\n**{f['titulo']}.** {texto}\n\nFuente: {f['fuente']}."
    return None
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
