"""
Arnés del spike (INV-30, criterio 8) y de INV-32 (T11, T17): corre una pregunta
del conjunto contra un modelo con el mismo bucle de herramientas del agente
(`agente.bucle`, hasta 3 rondas) y la califica.

Dos ejecutores:
- sintético (el del spike): las herramientas responden con los resultados
  sintéticos de la pregunta; corre sin Docker contra cualquier Ollama (local o
  Colab, N9);
- real (INV-32): las herramientas del catálogo v1 contra el Core API, con el
  token del usuario de prueba del rol de cada pregunta. Los «hechos clave» del
  v0 son sintéticos y no se califican (T17); los del v1 traen su versión con
  los datos reales (`hechos_reales`, INV-31), que sí se califica.

La latencia del primer token la mide `evaluacion.smoke`.
"""
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agente.bucle import MAX_RONDAS, Ejecutor, Preparada, Resumen, responder
from agente.prompt import quien
from evaluacion.calificacion import calificar
from evaluacion.conjunto import Pregunta, para_modo_real, resultado_para
from evaluacion.privacidad import sin_pesos, tiene_pesos
from herramientas.base import ErrorArgumentos, Resultado
from herramientas.catalogo import POR_NOMBRE, esquemas
from herramientas.core_api import ErrorHerramienta
from llm.cliente import ClienteLLM, ErrorLLM

PROMPT_SPIKE = (Path(__file__).resolve().parent / "prompt_spike.md").read_text(encoding="utf-8")


def prompt_sistema(pregunta: Pregunta, fecha: str) -> str:
    return PROMPT_SPIKE.format(usuario=quien(pregunta.rol, pregunta.sucursal_usuario), fecha=fecha)


def contexto_de(prompt: str, catalogo: list[dict]) -> str:
    """Lo que el modelo sabe sin herramientas: el prompt de sistema y las sucursales del catálogo."""
    sucursales = {s for h in catalogo for nombre, prop in h["function"]["parameters"]["properties"].items()
                  if nombre == "sucursal" for s in prop.get("enum", [])}
    return prompt + "\n" + " ".join(sorted(sucursales))


def contexto_modelo(pregunta: Pregunta, fecha: str, catalogo: list[dict]) -> str:
    return contexto_de(prompt_sistema(pregunta, fecha), catalogo)


class EjecutorSintetico:
    """Las herramientas del spike: responden con los resultados sintéticos de la pregunta."""

    def __init__(self, pregunta: Pregunta, fecha: str, catalogo: list[dict]):
        self.pregunta, self.fecha, self.catalogo = pregunta, fecha, catalogo
        self._nombres = {h["function"]["name"] for h in catalogo}
        self._validar = catalogo == esquemas()          # con el catálogo del agente (v1), los argumentos se validan como en el real

    def preparar(self, nombre, argumentos):
        if nombre not in self._nombres:
            return Preparada(nombre, argumentos, conocida=False, error=ErrorHerramienta(404, f"No existe la herramienta {nombre}"))
        if self._validar:
            try:
                POR_NOMBRE[nombre].validar(argumentos)
            except ErrorArgumentos as exc:
                return Preparada(nombre, argumentos, etiqueta=nombre, error=ErrorHerramienta(422, str(exc)))
        return Preparada(nombre, argumentos, params=argumentos, etiqueta=nombre)

    async def ejecutar(self, preparada):
        return Resultado(para_modelo=resultado_para(self.pregunta, preparada.nombre, preparada.argumentos, self.fecha))


@dataclass
class Corrida:
    id: str
    corrida: int
    rol: str
    tipo: str
    rondas: int = 0
    llamadas: list[dict] = field(default_factory=list)       # {ronda, herramienta, argumentos}
    texto: str = ""
    error: str | None = None
    razonamiento_filtrado: bool = False
    tokens_prompt_max: int = 0                                # el presupuesto de una ronda (INV-32, criterio 12)
    tokens_respuesta: int = 0
    ms_total: float = 0.0
    ms_modelo: float = 0.0
    calificacion: dict = field(default_factory=dict)
    resultados: list | None = None                           # solo con el Core API real

    def como_dict(self) -> dict:
        d = asdict(self)
        if d["resultados"] is None:
            del d["resultados"]
        return d


async def correr_pregunta(
    cliente: ClienteLLM,
    pregunta: Pregunta,
    catalogo: list[dict],
    fecha: str,
    corrida: int = 1,
    opciones: dict | None = None,
    max_rondas: int = MAX_RONDAS,
    ejecutor: Ejecutor | None = None,
    prompt: str | None = None,
) -> Corrida:
    """Sin `ejecutor`, el sintético del spike con su prompt (o `prompt`, el del agente en el v1). Con
    uno real, `prompt` es el del agente y los hechos son los reales, si la pregunta los trae (T17)."""
    real = ejecutor is not None
    ejecutor = ejecutor or EjecutorSintetico(pregunta, fecha, catalogo)
    prompt = prompt or prompt_sistema(pregunta, fecha)
    c = Corrida(id=pregunta.id, corrida=corrida, rol=pregunta.rol, tipo=pregunta.tipo)
    mensajes = [{"role": "system", "content": prompt}, {"role": "user", "content": pregunta.pregunta}]
    r = Resumen()
    inicio = time.monotonic()
    try:
        async for _ in responder(cliente, mensajes, ejecutor, r, opciones, max_rondas):
            pass
    except ErrorLLM as exc:
        c.error = exc.codigo
    c.rondas, c.llamadas, c.texto = r.rondas, r.llamadas, r.texto.strip()
    c.tokens_prompt_max, c.tokens_respuesta, c.ms_modelo = r.tokens_prompt_max, r.tokens_respuesta, r.ms_modelo
    c.razonamiento_filtrado = r.razonamiento_filtrado
    c.ms_total = round((time.monotonic() - inicio) * 1000, 1)
    if real:
        c.resultados = r.resultados      # no se pueden reconstruir: se guardan para recalificar
    primera = [(ll["herramienta"], ll["argumentos"]) for ll in r.llamadas if ll["ronda"] == 1]
    calificada = para_modo_real(pregunta) if real else pregunta
    c.calificacion = calificar(calificada or pregunta, primera, bool(r.llamadas), r.resultados, c.texto, c.error,
                               contexto_de(prompt, ejecutor.catalogo), con_hechos=calificada is not None).como_dict()
    if real and (tiene_pesos(c.resultados) or tiene_pesos(c.texto)):
        # Ventas reales en pesos: no se guardan (privacidad.py); las cifras sin respaldo se cuentan, sin el valor
        c.texto, c.resultados = sin_pesos(c.texto), sin_pesos(c.resultados)
        c.calificacion["cifras_sin_respaldo"] = ["[omitido]"] * len(c.calificacion["cifras_sin_respaldo"])
    return c
