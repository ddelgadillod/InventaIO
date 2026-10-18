"""
Calificación de una corrida del spike (INV-30 §4.4; INV-31, criterio 11).

Funciones puras: reciben la pregunta, las llamadas que hizo el modelo, los
resultados que recibió y el texto final, y dicen qué acertó. El diseño (pass^k,
diferencias pareadas, abstención) sigue la §5.1 del documento de Sprint 6.

Fidelidad de cifras (INV-33, criterio 4): cada número de la respuesta debe
estar en la pregunta o en los resultados que recibió el modelo, o ser la suma de
una columna de esos resultados. Se aceptan los dos formatos de miles (1.250 y
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
) -> Calificacion:
    if pregunta.abstencion:
        herramienta = not hubo_llamadas
    else:
        herramienta = any(coincide(e, n, a) for e in pregunta.esperado for n, a in primera_ronda) or (
            pregunta.abstencion_valida and not hubo_llamadas
        )
    fuera = cifras_no_respaldadas(texto, pregunta.pregunta, resultados)
    hechos = all(_menciona(texto, h) for h in pregunta.hechos_clave) and (
        not pregunta.hechos_alguno or any(_menciona(texto, h) for h in pregunta.hechos_alguno)
    )
    prohibido = not any(_normal(p) in _normal(texto) for p in pregunta.prohibido)
    aclaracion = (not pregunta.aclaracion) or "?" in texto
    # Rechazo: ninguna cifra de datos (mayor que un conteo) salvo las de la pregunta o códigos de error
    codigos = {float(r["error"]["status"]) for r in resultados if isinstance(r, dict) and "error" in r}
    cifras_pregunta = set().union(*numeros(pregunta.pregunta)) if numeros(pregunta.pregunta) else set()
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
