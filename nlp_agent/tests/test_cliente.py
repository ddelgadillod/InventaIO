"""ClienteOllama contra el Ollama simulado: forma de las llamadas, respuestas y errores."""
import httpx
import pytest

from llm.cliente import ClienteOllama, ErrorLLM
from tests.conftest import fin_ollama, linea

MENSAJES = [{"role": "user", "content": "hola"}]
HERRAMIENTA = {
    "type": "function",
    "function": {
        "name": "buscar_producto",
        "description": "Busca productos por nombre o código",
        "parameters": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]},
    },
}


async def test_version_y_modelos(cliente, ollama):
    assert await cliente.version() == "0.40.5"
    assert await cliente.modelo_disponible("qwen3:8b")
    assert not await cliente.modelo_disponible("qwen3:14b")


async def test_modelo_sin_tag_es_latest(cliente, ollama):
    ollama.modelos = ["mistral:latest"]
    assert await cliente.modelo_disponible("mistral")


async def test_forma_de_la_llamada_con_herramientas(cliente, ollama):
    """Contrato con la API nativa de Ollama (criterios 3 y 5; W11)."""
    await cliente.chat(MENSAJES, herramientas=[HERRAMIENTA], opciones={"num_gpu": 0})
    p = ollama.peticiones[-1]
    assert (p.method, p.url.path) == ("POST", "/api/chat")
    cuerpo = ollama.cuerpo()
    assert cuerpo["model"] == "qwen3:8b" and cuerpo["stream"] is False
    assert cuerpo["think"] is False and cuerpo["keep_alive"] == "30m"
    assert cuerpo["options"] == {"num_ctx": 8192, "temperature": 0.0, "top_p": 1.0, "seed": 42, "num_gpu": 0}
    assert cuerpo["tools"] == [HERRAMIENTA] and cuerpo["messages"] == MENSAJES


async def test_sin_herramientas_no_envia_tools(cliente, ollama):
    await cliente.chat(MENSAJES)
    assert "tools" not in ollama.cuerpo()


async def test_llamadas_a_herramientas_y_argumentos_como_texto(cliente, ollama):
    ollama.respuesta = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "buscar_producto", "arguments": {"texto": "arroz"}}},
        {"function": {"name": "consultar_inventario", "arguments": '{"sucursal": "GLORIETA"}'}},
        {"function": {"name": "listar_sucursales", "arguments": ""}},
    ]}, **fin_ollama()}
    r = await cliente.chat(MENSAJES, herramientas=[HERRAMIENTA])
    assert [(ll.nombre, ll.argumentos) for ll in r.llamadas] == [
        ("buscar_producto", {"texto": "arroz"}),
        ("consultar_inventario", {"sucursal": "GLORIETA"}),
        ("listar_sucursales", {}),
    ]


@pytest.mark.parametrize("argumentos", ["{no es json", "[1, 2]"])
async def test_argumentos_invalidos(cliente, ollama, argumentos):
    ollama.respuesta = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "buscar_producto", "arguments": argumentos}}]}, **fin_ollama()}
    # No corta la respuesta: vuelve al modelo para que lo corrija (INV-32, criterio 13)
    r = await cliente.chat(MENSAJES)
    assert r.llamadas[0].argumentos == {} and "no son" in r.llamadas[0].error


async def test_respuesta_quita_razonamiento_y_trae_metricas(cliente, ollama):
    ollama.respuesta = {"message": {"role": "assistant", "content": "<think>sumo</think> Son 12 cajas. "}, **fin_ollama()}
    r = await cliente.chat(MENSAJES)
    assert r.texto == "Son 12 cajas." and r.razonamiento_filtrado
    m = r.metricas
    assert (m.tokens_prompt, m.tokens_respuesta) == (40, 12)
    assert (m.ms_carga, m.ms_prompt, m.ms_respuesta, m.ms_total) == (2.0, 30.0, 240.0, 280.0)


@pytest.mark.parametrize("status,codigo", [
    (404, "modelo_no_descargado"), (400, "solicitud_invalida"), (500, "llm_no_disponible"),
])
async def test_errores_http(cliente, ollama, status, codigo):
    ollama.status = status
    for llamada in (lambda: cliente.chat(MENSAJES), cliente.version):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == codigo


async def test_detalle_del_error_de_ollama(cliente, ollama):
    ollama.status, ollama.cuerpo_error = 400, '{"error":"\\"llama3.1:8b\\" does not support thinking"}'
    with pytest.raises(ErrorLLM) as e:
        await cliente.chat(MENSAJES)
    assert "does not support thinking" in e.value.mensaje


async def test_error_sin_json(cliente, ollama):
    ollama.status, ollama.cuerpo_error = 404, "no encontrado"
    with pytest.raises(ErrorLLM) as e:
        await cliente.version()
    assert e.value.mensaje == "no encontrado"


async def test_ollama_caido(cliente, ollama):
    ollama.caido = True
    for llamada in (lambda: cliente.chat(MENSAJES), cliente.version, lambda: _consumir(cliente)):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == "llm_no_disponible"


@pytest.mark.parametrize("excepcion", [httpx.ReadTimeout, httpx.ConnectTimeout])
async def test_tiempo_agotado(ajustes, excepcion):
    def lento(request):
        raise excepcion("sin respuesta", request=request)
    c = ClienteOllama(ajustes, transport=httpx.MockTransport(lento))
    for llamada in (lambda: c.chat(MENSAJES), c.version, lambda: _consumir(c)):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == "tiempo_agotado"
    await c.cerrar()


async def _consumir(cliente):
    return [f async for f in cliente.chat_stream(MENSAJES)]


async def test_stream_fragmentos_y_fin(cliente, ollama):
    fragmentos = await _consumir(cliente)
    assert [f.texto for f in fragmentos if not f.fin] == ["¡Hola", "! ¿En qué", " te ayudo?"]
    assert fragmentos[-1].fin and fragmentos[-1].metricas.tokens_respuesta == 12
    assert ollama.cuerpo()["stream"] is True and "tools" not in ollama.cuerpo()


async def test_stream_filtra_razonamiento_y_libera_lo_pendiente(cliente, ollama):
    ollama.fragmentos = ["<think>", "pienso</think>Hay", " 5 <"]
    textos = [f.texto for f in await _consumir(cliente) if not f.fin]
    assert "".join(textos) == "Hay 5 <"


async def test_stream_con_lineas_en_blanco(cliente, ollama):
    ollama.lineas_stream = [b"\n", linea({"done": False, "message": {"content": "Hola"}}), linea(fin_ollama())]
    assert [f.texto for f in await _consumir(cliente)] == ["Hola", ""]


@pytest.mark.parametrize("lineas,mensaje", [
    ([linea({"error": "sin memoria"})], "sin memoria"),
    ([b"esto no es json\n"], "no es JSON"),
    ([linea({"done": False, "message": {"content": "Hola"}})], "sin `done`"),
])
async def test_stream_invalido(cliente, ollama, lineas, mensaje):
    ollama.lineas_stream = lineas
    with pytest.raises(ErrorLLM) as e:
        await _consumir(cliente)
    assert e.value.codigo == "respuesta_invalida" and mensaje in e.value.mensaje


async def test_stream_modelo_no_descargado(cliente, ollama):
    ollama.status = 404
    with pytest.raises(ErrorLLM) as e:
        await _consumir(cliente)
    assert e.value.codigo == "modelo_no_descargado"
