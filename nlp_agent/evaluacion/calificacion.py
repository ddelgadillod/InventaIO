"""
Calificación de una corrida del spike (INV-30 §4.4; INV-31, criterio 11).

Funciones puras: reciben la pregunta, las llamadas que hizo el modelo, los
resultados que recibió y el texto final, y dicen qué acertó. El diseño (pass^k,
diferencias pareadas, abstención) sigue la §5.1 del documento de Sprint 6.

Fidelidad de cifras (INV-33, criterio 4): cada número de la respuesta debe
estar en la pregunta, en el contexto que le dimos al modelo (la fecha de la
foto, el horizonte de 15 días hábiles, los nombres de las sucursales como «LA
21») o en los resultados que recibió, o ser la suma de una columna de esos
resultados. Costo conocido: una cifra inventada que coincida con el contexto
(«15 sucursales») no se detecta. Se aceptan los dos formatos de miles (1.250 y
1,250) y se ignoran los números de 0 a 10, que suelen ser conteos u ordinales
(«los 3 productos»). Es una heurística: lo que marca se revisa a mano.
"""
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from evaluacion.conjunto import Pregunta, coincide

NUMERO = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])")
UMBRAL_CONTEO = 10


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


def _lecturas(cifra: str) -> set[float]:
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
    return [_lecturas(m.group()) for m in NUMERO.finditer(texto)]


def _permitidos(pregunta: str, resultados: list[Any]) -> set[float]:
    permitidos = set().union(*numeros(pregunta)) if numeros(pregunta) else set()
    # Las fechas del contexto se leen por partes (2025-12-31 → 2025, 12 y 31)
    permitidos |= {float(x) for x in re.findall(r"\d+", pregunta)}
    for r in resultados:
        texto = json.dumps(r, ensure_ascii=False)
        for lecturas in numeros(texto):
            permitidos |= lecturas
        # Sumas por columna de cada lista de filas (el total de varias sucursales)
        for filas in _listas_de_filas(r):
            columnas: dict[str, float] = {}
            for fila in filas:
                for clave, valor in fila.items():
                    leidos = numeros(str(valor))
                    if len(leidos) == 1 and len(leidos[0]) == 1:
                        columnas[clave] = columnas.get(clave, 0) + next(iter(leidos[0]))
            permitidos |= {round(v, 2) for v in columnas.values()}
    return permitidos


def _listas_de_filas(valor: Any):
    if isinstance(valor, list) and valor and all(isinstance(x, dict) for x in valor):
        yield valor
    if isinstance(valor, dict):
        for v in valor.values():
            yield from _listas_de_filas(v)


def cifras_no_respaldadas(texto: str, pregunta: str, resultados: list[Any]) -> list[str]:
    """`pregunta` incluye el contexto del modelo: la pregunta más el prompt de sistema."""
    permitidos = _permitidos(pregunta, resultados)
    fuera = []
    for m in NUMERO.finditer(texto):
        lecturas = _lecturas(m.group())
        if all(v <= UMBRAL_CONTEO for v in lecturas):
            continue
        if not lecturas & permitidos:
            fuera.append(m.group())
    return fuera


def _menciona(texto: str, hecho: str) -> bool:
    if re.fullmatch(r"\d+", hecho):
        return any(float(hecho) in lecturas for lecturas in numeros(texto))
    return _normal(hecho) in _normal(texto)


@dataclass
class Calificacion:
    herramienta: bool            # la primera ronda eligió bien (o se abstuvo cuando correspondía)
    fidelidad: bool              # ninguna cifra sin respaldo
    hechos: bool                 # hechos_clave y hechos_alguno
    prohibido: bool              # no dijo nada de lo prohibido
    aclaracion: bool             # pidió aclaración, si se esperaba
    rechazo: bool                # se negó sin dar cifras, si se esperaba
    sin_error: bool              # el modelo no falló (argumentos inválidos, tiempo agotado…)
    cifras_sin_respaldo: list[str] = field(default_factory=list)

    @property
    def acierto(self) -> bool:
        return all((self.herramienta, self.fidelidad, self.hechos, self.prohibido, self.aclaracion, self.rechazo, self.sin_error))

    def como_dict(self) -> dict:
        return {**asdict(self), "acierto": self.acierto}


def calificar(
    pregunta: Pregunta,
    primera_ronda: list[tuple[str, dict]],
    hubo_llamadas: bool,
    resultados: list[Any],
    texto: str,
    error: str | None = None,
    contexto: str = "",
) -> Calificacion:
    """`contexto`: lo que el modelo sabía antes de las herramientas (prompt de sistema y sucursales)."""
    referencia = f"{pregunta.pregunta}\n{contexto}"
    if pregunta.abstencion:
        herramienta = not hubo_llamadas
    else:
        herramienta = any(coincide(e, n, a) for e in pregunta.esperado for n, a in primera_ronda) or (
            pregunta.abstencion_valida and not hubo_llamadas
        )
    fuera = cifras_no_respaldadas(texto, referencia, resultados)
    hechos = all(_menciona(texto, h) for h in pregunta.hechos_clave) and (
        not pregunta.hechos_alguno or any(_menciona(texto, h) for h in pregunta.hechos_alguno)
    )
    prohibido = not any(_normal(p) in _normal(texto) for p in pregunta.prohibido)
    aclaracion = (not pregunta.aclaracion) or "?" in texto
    # Rechazo: ninguna cifra de datos (mayor que un conteo) salvo las de la pregunta o códigos de error
    codigos = {float(r["error"]["status"]) for r in resultados if isinstance(r, dict) and "error" in r}
    cifras_pregunta = {float(x) for x in re.findall(r"\d+", referencia)} | (set().union(*numeros(referencia)) if numeros(referencia) else set())
    cifras_datos = [
        lecturas for lecturas in numeros(texto)
        if not all(v <= UMBRAL_CONTEO for v in lecturas) and not lecturas & (cifras_pregunta | codigos)
    ]
    rechazo = (not pregunta.rechazo) or not cifras_datos
    return Calificacion(
        herramienta=herramienta,
        fidelidad=not fuera,
        hechos=hechos,
        prohibido=prohibido,
        aclaracion=aclaracion,
        rechazo=rechazo,
        sin_error=error is None and bool(texto.strip()),
        cifras_sin_respaldo=fuera,
    )


def recalificar_archivo(ruta) -> int:
    """Vuelve a calificar un archivo de resultados con la regla vigente, sin volver a correr el modelo.

    Los resultados que recibió el modelo se reconstruyen con `resultado_para` a partir de las
    llamadas guardadas (es determinista). Devuelve cuántas calificaciones cambiaron."""
    from pathlib import Path

    from evaluacion.arnes import contexto_modelo
    from evaluacion.conjunto import cargar, herramientas, resultado_para

    ruta = Path(ruta)
    lineas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = lineas[0]
    variante = "colab" if "(colab" in meta["conjunto"] else "local"
    conjunto, catalogo = cargar(variante), herramientas(variante)
    nombres = {h["function"]["name"] for h in catalogo}
    cambios = 0
    for c in lineas[1:]:
        p = conjunto.por_id(c["id"])
        resultados = [
            resultado_para(p, ll["herramienta"], ll["argumentos"], conjunto.fecha_datos) if ll["herramienta"] in nombres
            else {"error": {"status": 404}} for ll in c["llamadas"]
        ]
        primera = [(ll["herramienta"], ll["argumentos"]) for ll in c["llamadas"] if ll["ronda"] == 1]
        nueva = calificar(p, primera, bool(c["llamadas"]), resultados, c["texto"], c["error"],
                          contexto_modelo(p, conjunto.fecha_datos, catalogo)).como_dict()
        cambios += nueva != c["calificacion"]
        c["calificacion"] = nueva
    ruta.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas), encoding="utf-8")
    return cambios
