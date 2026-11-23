"""
Pruebas con Bedrock real (marca `bedrock`, INV-67): solo en local, con un perfil de
AWS que pueda invocar el modelo; sin credenciales, se saltan. Nunca en el CI.
Son la sonda técnica del adaptador (texto, llamada en streaming y la segunda ronda
con el resultado) y cuestan menos de un centavo de dólar.
    cd nlp_agent && AWS_PROFILE=inventaio-spike pytest -m bedrock
"""
import json

import pytest

from core.config import Settings
from llm.bedrock import CadenaAWS, ClienteBedrock

pytestmark = pytest.mark.bedrock

INVENTARIO = {"type": "function", "function": {
    "name": "consultar_inventario", "description": "Stock actual de un producto en una sucursal",
    "parameters": {"type": "object", "properties": {"producto": {"type": "string"}, "sucursal": {"type": "string"}},
                   "required": ["producto"]}}}
PREGUNTA = [{"role": "system", "content": "Eres un asistente de inventario. Usa las herramientas para consultar datos."},
            {"role": "user", "content": "¿Cuántos huevos hay en la sucursal GLORIETA?"}]


@pytest.fixture
async def cliente():
    if CadenaAWS()() is None:
        pytest.skip("sin credenciales de AWS (AWS_PROFILE, variables o el rol de la EC2)")
    c = ClienteBedrock(Settings(LLM_PROVEEDOR="bedrock"))
    yield c
    await c.cerrar()


async def test_texto(cliente):
    r = await cliente.chat([{"role": "user", "content": "Responde solo la palabra: listo"}])
    assert "listo" in r.texto.lower() and r.metricas.tokens_prompt > 0 and r.metricas.tokens_respuesta > 0


async def test_llamada_en_streaming_y_segunda_ronda(cliente):
    fragmentos = [f async for f in cliente.chat_stream(list(PREGUNTA), herramientas=[INVENTARIO])]
    llamadas = [ll for f in fragmentos if f.llamadas for ll in f.llamadas]
    assert llamadas and llamadas[0].nombre == "consultar_inventario" and llamadas[0].error is None
    assert "huevo" in json.dumps(llamadas[0].argumentos, ensure_ascii=False).lower()
    assert fragmentos[-1].fin and fragmentos[-1].metricas.tokens_prompt > 0
    # La segunda ronda en el formato del bucle (el de Ollama): el adaptador pone el tool_call_id
    mensajes = [*PREGUNTA,
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": ll.id, "function": {"name": ll.nombre, "arguments": ll.argumentos}} for ll in llamadas]},
                *({"role": "tool", "tool_name": ll.nombre,
                   "content": json.dumps({"fecha_dato": "2025-12-31", "filas": [{"producto": "HUEVO AA X30", "stock": 420}]})}
                  for ll in llamadas)]
    texto = "".join([f.texto async for f in cliente.chat_stream(mensajes, herramientas=[INVENTARIO])])
    assert "420" in texto
