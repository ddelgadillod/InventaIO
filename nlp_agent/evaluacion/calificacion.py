"""
Calificación de una corrida del spike (INV-30 §4.4; INV-31, criterio 11).

Funciones puras: reciben la pregunta, las llamadas que hizo el modelo, los
resultados que recibió y el texto final, y dicen qué acertó. El diseño (pass^k,
diferencias pareadas, abstención) sigue la §5.1 del documento de Sprint 6.

Fidelidad de cifras (INV-33, criterio 4): la regla es la del verificador del
agente, `agente/fidelidad.py` (Z12): lo que se mide es lo que el agente revisa.
Es una heurística: lo que marca se revisa a mano.
"""
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from agente.fidelidad import UMBRAL_CONTEO, cifras_no_respaldadas, numeros
from evaluacion.conjunto import Pregunta, coincide


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


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
    con_hechos: bool = True,
) -> Calificacion:
    """`contexto`: lo que el modelo sabía antes de las herramientas (prompt de sistema y sucursales).
    `con_hechos=False` con el Core API real: los hechos clave del v0 son sintéticos (INV-32, T17)."""
    referencia = f"{pregunta.pregunta}\n{contexto}"
    if pregunta.abstencion:
        herramienta = not hubo_llamadas
    else:
        herramienta = any(coincide(e, n, a) for e in pregunta.esperado for n, a in primera_ronda) or (
            pregunta.abstencion_valida and not hubo_llamadas
        )
    fuera = cifras_no_respaldadas(texto, referencia, resultados)
    hechos = (not con_hechos) or all(_menciona(texto, h) for h in pregunta.hechos_clave) and (
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

    from evaluacion.arnes import contexto_de, contexto_modelo
    from evaluacion.conjunto import cargar, herramientas, resultado_para

    ruta = Path(ruta)
    lineas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = lineas[0]
    version = meta["conjunto"].split()[0]          # «v1 (colab, 61 preguntas)»
    if "(real" in meta["conjunto"]:
        return _recalificar_real(lineas, ruta, version)
    variante = "colab" if "(colab" in meta["conjunto"] else "local"
    conjunto, catalogo = cargar(variante, version), herramientas(variante, version)
    nombres = {h["function"]["name"] for h in catalogo}
    cambios = 0
    for c in lineas[1:]:
        p = conjunto.por_id(c["id"])
        resultados = [
            resultado_para(p, ll["herramienta"], ll["argumentos"], conjunto.fecha_datos) if ll["herramienta"] in nombres
            else {"error": {"status": 404}} for ll in c["llamadas"]
        ]
        primera = [(ll["herramienta"], ll["argumentos"]) for ll in c["llamadas"] if ll["ronda"] == 1]
        # El v0 se corrió con el prompt del spike; desde el v1, con el del agente
        contexto = (contexto_modelo(p, conjunto.fecha_datos, catalogo) if version == "v0"
                    else contexto_de(_prompt_agente(p, meta), catalogo))
        nueva = calificar(p, primera, bool(c["llamadas"]), resultados, c["texto"], c["error"], contexto).como_dict()
        cambios += nueva != c["calificacion"]
        c["calificacion"] = nueva
    ruta.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas), encoding="utf-8")
    return cambios


def _prompt_agente(p, meta: dict | None = None) -> str:
    """El prompt con que corrió la pregunta: el de `meta.version_prompt` (v1, v2 o v2-corto; v1 si no lo dice)."""
    from agente.prompt import prompt_sistema, quien
    version, _, perfil = (meta or {}).get("version_prompt", "v1").partition("-")
    return prompt_sistema(quien(p.rol, p.sucursal_usuario), p.rol, p.sucursal_usuario, version, perfil or "completo")


def _recalificar_real(lineas: list[dict], ruta, version: str = "v0") -> int:
    """Corridas contra el Core API real (INV-32, T17): los resultados vienen en cada línea. Los hechos
    se califican solo si la pregunta trae los reales (v1)."""
    from evaluacion.arnes import contexto_de
    from evaluacion.conjunto import cargar, para_modo_real
    from herramientas.catalogo import esquemas

    conjunto, catalogo, cambios = cargar(version=version), esquemas(), 0
    for c in lineas[1:]:
        p = conjunto.por_id(c["id"])
        real = para_modo_real(p)
        primera = [(ll["herramienta"], ll["argumentos"]) for ll in c["llamadas"] if ll["ronda"] == 1]
        contexto = contexto_de(_prompt_agente(p, lineas[0]), catalogo)
        nueva = calificar(real or p, primera, bool(c["llamadas"]), c.get("resultados") or [], c["texto"], c["error"],
                          contexto, con_hechos=real is not None).como_dict()
        cambios += nueva != c["calificacion"]
        c["calificacion"] = nueva
    ruta.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas), encoding="utf-8")
    return cambios
