"""
Arnés del spike (INV-30, criterio 8): corre una pregunta del conjunto contra un
modelo, con hasta 3 rondas de herramientas (INV-32, criterio 6) y los
resultados sintéticos de la pregunta, y la califica.

Corre sin Docker contra cualquier Ollama (local o Colab): solo necesita un
`ClienteLLM`. Las rondas de herramientas van sin streaming, como en el agente;
la latencia del primer token la mide `evaluacion.smoke`.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evaluacion.calificacion import calificar
from evaluacion.conjunto import Pregunta, resultado_para
from llm.cliente import ClienteLLM, ErrorLLM

MAX_RONDAS = 3
PROMPT_SPIKE = (Path(__file__).resolve().parent / "prompt_spike.md").read_text(encoding="utf-8")
USUARIOS = {
    "gerente": "el gerente, que ve todas las sucursales y la Bodega Central",
    "admin_bodega": "el administrador de la Bodega Central",
    "admin_sucursal": "el administrador de la sucursal {sucursal}, que solo ve su sucursal",
}


def prompt_sistema(pregunta: Pregunta, fecha: str) -> str:
    usuario = USUARIOS[pregunta.rol].format(sucursal=pregunta.sucursal_usuario)
    return PROMPT_SPIKE.format(usuario=usuario, fecha=fecha)


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

    def como_dict(self) -> dict:
        return asdict(self)


def _mensaje_asistente(texto: str, llamadas) -> dict:
    return {
        "role": "assistant",
        "content": texto,
        "tool_calls": [
            {**({"id": ll.id} if ll.id else {}), "function": {"name": ll.nombre, "arguments": ll.argumentos}}
            for ll in llamadas
        ],
    }


async def correr_pregunta(
    cliente: ClienteLLM,
    pregunta: Pregunta,
    catalogo: list[dict],
    fecha: str,
    corrida: int = 1,
    opciones: dict | None = None,
    max_rondas: int = MAX_RONDAS,
) -> Corrida:
    c = Corrida(id=pregunta.id, corrida=corrida, rol=pregunta.rol, tipo=pregunta.tipo)
    nombres = {h["function"]["name"] for h in catalogo}
    mensajes = [{"role": "system", "content": prompt_sistema(pregunta, fecha)}, {"role": "user", "content": pregunta.pregunta}]
    primera: list[tuple[str, dict]] = []
    resultados: list[Any] = []
    inicio = time.monotonic()

    def contar(r) -> None:
        c.tokens_prompt_max = max(c.tokens_prompt_max, r.metricas.tokens_prompt)
        c.tokens_respuesta += r.metricas.tokens_respuesta
        c.ms_modelo += r.metricas.ms_total
        c.razonamiento_filtrado |= r.razonamiento_filtrado

    try:
        for ronda in range(1, max_rondas + 1):
            r = await cliente.chat(mensajes, herramientas=catalogo, opciones=opciones)
            contar(r)
            c.rondas = ronda
            if not r.llamadas:
                c.texto = r.texto
                break
            if ronda == 1:
                primera = [(ll.nombre, ll.argumentos) for ll in r.llamadas]
            mensajes.append(_mensaje_asistente(r.texto, r.llamadas))
            for ll in r.llamadas:
                c.llamadas.append({"ronda": ronda, "herramienta": ll.nombre, "argumentos": ll.argumentos})
                if ll.nombre in nombres:
                    resultado = resultado_para(pregunta, ll.nombre, ll.argumentos, fecha)
                else:
                    resultado = {"error": {"status": 404, "mensaje": f"No existe la herramienta {ll.nombre}"}}
                resultados.append(resultado)
                mensajes.append({"role": "tool", "tool_name": ll.nombre, "content": json.dumps(resultado, ensure_ascii=False)})
        else:
            # Se acabaron las rondas: una última llamada sin herramientas obliga a responder
            r = await cliente.chat(mensajes, herramientas=None, opciones=opciones)
            contar(r)
            c.texto = r.texto
    except ErrorLLM as exc:
        c.error = exc.codigo
    c.ms_total = round((time.monotonic() - inicio) * 1000, 1)
    c.calificacion = calificar(pregunta, primera, bool(c.llamadas), resultados, c.texto, c.error).como_dict()
    return c
