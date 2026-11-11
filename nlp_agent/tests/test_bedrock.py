"""INV-67: ClienteBedrock contra el Bedrock simulado (forma, firma, streaming, errores y reintentos), su
configuración, el proveedor del agente y el arnés con `--proveedor bedrock`. Ninguna llama a AWS."""
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.config import MODELOS_BEDROCK, VERSION, Settings, get_settings
from evaluacion import correr as correr_mod
from evaluacion.arnes import correr_pregunta
from llm.bedrock import CadenaAWS, ClienteBedrock, a_chat_completions, costo_usd
from llm.cliente import ClienteOllama, ErrorLLM
from llm.proveedor import crear_cliente
from main import crear_app
from tests.bedrock_falso import (
    CREDENCIALES,
    CREDENCIALES_TEMPORALES,
    BedrockFalso,
    evento,
)
from tests.test_arnes import CATALOGO, C
from tests.test_cliente import HERRAMIENTA

MENSAJES = [{"role": "system", "content": "sistema"}, {"role": "user", "content": "hola"}]
URL = "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1/chat/completions"
MODELO = "qwen.qwen3-32b-v1:0"


@pytest.fixture
def ajustes_bedrock() -> Settings:
    return Settings(LLM_PROVEEDOR="bedrock")


@pytest.fixture
def bedrock() -> BedrockFalso:
    return BedrockFalso()


def _cliente(ajustes, bedrock, credenciales=CREDENCIALES) -> ClienteBedrock:
    c = ClienteBedrock(ajustes, transport=httpx.MockTransport(bedrock), credenciales=lambda: credenciales)
    c.esperas = []

    async def dormir(s):
        c.esperas.append(s)
    c._dormir = dormir
    return c


@pytest.fixture
def cliente_bedrock(ajustes_bedrock, bedrock) -> ClienteBedrock:
    return _cliente(ajustes_bedrock, bedrock)


async def _consumir(cliente, **kw):
    return [f async for f in cliente.chat_stream(MENSAJES, **kw)]


# --- Configuración y proveedor (P11, P12) ---

def test_configuracion_por_defecto_sigue_en_ollama():
    s = Settings()
    assert (s.LLM_PROVEEDOR, s.LLM_MODELO, s.BEDROCK_REGION, s.BEDROCK_ENDPOINT) == ("ollama", "qwen3:8b", "us-east-1", "runtime")


def test_bedrock_cambia_el_modelo_solo_si_no_se_dio(monkeypatch):
    assert Settings(LLM_PROVEEDOR="bedrock").LLM_MODELO == MODELO == MODELOS_BEDROCK["runtime"]
    assert Settings(LLM_PROVEEDOR="bedrock", BEDROCK_ENDPOINT="mantle").LLM_MODELO == "qwen.qwen3-32b"
    assert Settings(LLM_PROVEEDOR="bedrock", LLM_MODELO="qwen.qwen3-235b-a22b-2507").LLM_MODELO == "qwen.qwen3-235b-a22b-2507"
    monkeypatch.setenv("LLM_PROVEEDOR", "bedrock")
    assert Settings().LLM_MODELO == MODELO
    monkeypatch.setenv("LLM_MODELO", "otro.modelo")
    assert Settings().LLM_MODELO == "otro.modelo"
    monkeypatch.setenv("BEDROCK_CUERPO_EXTRA", '{"reasoning_effort": "none"}')
    assert Settings().BEDROCK_CUERPO_EXTRA == {"reasoning_effort": "none"}


def test_proveedor_desconocido():
    with pytest.raises(ValidationError):
        Settings(LLM_PROVEEDOR="openai")
    with pytest.raises(ValidationError):
        Settings(BEDROCK_ENDPOINT="otro")


def test_crear_cliente_segun_el_proveedor():
    assert isinstance(crear_cliente(Settings()), ClienteOllama)
    assert isinstance(crear_cliente(Settings(LLM_PROVEEDOR="bedrock")), ClienteBedrock)


def test_ready_con_bedrock_no_llama_al_modelo(monkeypatch, bedrock, core):
    monkeypatch.setenv("LLM_PROVEEDOR", "bedrock")
    get_settings.cache_clear()
    try:
        with TestClient(crear_app(_cliente(get_settings(), bedrock), core)) as api:
            r = api.get("/ready")
        assert r.status_code == 200 and bedrock.peticiones == []
        assert r.json() == {"status": "listo", "modelo": MODELO, "version_ollama": "bedrock runtime us-east-1",
                            "version": VERSION}
        with TestClient(crear_app(_cliente(get_settings(), bedrock, credenciales=None), core)) as api:
            r = api.get("/ready")
        assert r.status_code == 503 and r.json()["motivo"] == "ollama_no_alcanzable"
    finally:
        get_settings.cache_clear()


# --- Forma de la petición y firma (P1, P8) ---

async def test_chat_forma_y_metricas(cliente_bedrock, bedrock):
    bedrock.guion = ["Hola, ¿en qué te ayudo?"]
    r = await cliente_bedrock.chat(MENSAJES, herramientas=[HERRAMIENTA], opciones={"num_gpu": 0})
    p = bedrock.peticiones[-1]
    assert (p.method, str(p.url)) == ("POST", URL)
    assert bedrock.cuerpo() == {"model": MODELO, "messages": MENSAJES, "stream": False, "temperature": 0.0,
                                "top_p": 1.0, "max_tokens": 2048, "tools": [HERRAMIENTA]}
    assert r.texto == "Hola, ¿en qué te ayudo?" and r.llamadas == []
    assert (r.metricas.tokens_prompt, r.metricas.tokens_respuesta) == (1200, 80) and r.metricas.ms_total >= 0


async def test_cuerpo_extra_y_sin_herramientas(ajustes_bedrock, bedrock):
    ajustes_bedrock.BEDROCK_CUERPO_EXTRA = {"reasoning_effort": "none"}
    await _cliente(ajustes_bedrock, bedrock).chat(MENSAJES)
    assert "tools" not in bedrock.cuerpo() and bedrock.cuerpo()["reasoning_effort"] == "none"


async def test_firma_sigv4(cliente_bedrock, bedrock):
    await cliente_bedrock.chat(MENSAJES)
    h = bedrock.peticiones[-1].headers
    fecha = datetime.now(UTC).strftime("%Y%m%d")
    assert h["authorization"].startswith(f"AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/{fecha}/us-east-1/bedrock/aws4_request")
    assert "host" in h["authorization"] and "x-amz-date" in h and "x-amz-security-token" not in h
    assert "secreto-de-prueba" not in str(h)


async def test_firma_con_credenciales_temporales_y_mantle(bedrock):
    s = Settings(LLM_PROVEEDOR="bedrock", BEDROCK_ENDPOINT="mantle", BEDROCK_REGION="sa-east-1")
    await _cliente(s, bedrock, CREDENCIALES_TEMPORALES).chat(MENSAJES)
    p = bedrock.peticiones[-1]
    assert str(p.url) == "https://bedrock-mantle.sa-east-1.api.aws/v1/chat/completions"
    assert "/sa-east-1/bedrock-mantle/aws4_request" in p.headers["authorization"]
    assert p.headers["x-amz-security-token"] == "token-de-sesion"


async def test_sin_credenciales_no_sale_a_la_red(ajustes_bedrock, bedrock):
    c = _cliente(ajustes_bedrock, bedrock, credenciales=None)
    assert not await c.modelo_disponible(MODELO)
    for llamada in (c.version, lambda: c.chat(MENSAJES), lambda: _consumir(c)):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == "llm_no_disponible" and "credenciales" in e.value.mensaje
    assert bedrock.peticiones == []


def test_cadena_aws_con_un_perfil_que_no_existe(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "perfil-que-no-existe")
    assert CadenaAWS()() is None


def test_cadena_aws_con_variables(monkeypatch):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secreto-de-prueba")
    cadena = CadenaAWS()
    assert cadena().access_key == "AKIDEXAMPLE" and cadena().secret_key == "secreto-de-prueba"


async def test_version_uso_y_costo(cliente_bedrock, bedrock, ajustes_bedrock):
    assert await cliente_bedrock.version() == "bedrock runtime us-east-1"
    assert await cliente_bedrock.modelo_disponible(MODELO)
    await cliente_bedrock.chat(MENSAJES)
    await _consumir(cliente_bedrock)
    assert cliente_bedrock.uso == {"tokens_entrada": 2400, "tokens_salida": 160, "peticiones": 2}
    assert costo_usd(ajustes_bedrock, 1_000_000, 1_000_000) == pytest.approx(0.75)
    assert costo_usd(ajustes_bedrock, 2400, 160) == pytest.approx(0.000456)


# --- Llamadas a herramientas y traducción de mensajes (P2, P3) ---

async def test_chat_con_llamadas(cliente_bedrock, bedrock):
    bedrock.mensaje = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_a", "type": "function", "function": {"name": "buscar_producto", "arguments": '{"texto": "arroz"}'}},
        {"id": "call_b", "type": "function", "function": {"name": "listar_sucursales", "arguments": {}}},
        {"id": "call_c", "type": "function", "function": {"name": "consultar_inventario", "arguments": "{sucursal"}},
    ]}
    r = await cliente_bedrock.chat(MENSAJES, herramientas=[HERRAMIENTA])
    assert [(ll.id, ll.nombre, ll.argumentos, ll.error is None) for ll in r.llamadas] == [
        ("call_a", "buscar_producto", {"texto": "arroz"}, True),
        ("call_b", "listar_sucursales", {}, True),
        ("call_c", "consultar_inventario", {}, False),     # vuelve al modelo como error, igual que con Ollama
    ]


def test_traduccion_de_mensajes():
    ollama = [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "¿cuánto arroz hay?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "buscar_producto", "arguments": {"texto": "arroz"}}},
            {"id": "call_x", "function": {"name": "listar_sucursales", "arguments": "{}"}}]},
        {"role": "tool", "tool_name": "listar_sucursales", "content": '{"filas": []}'},
        {"role": "tool", "tool_name": "buscar_producto", "content": '{"filas": [1]}'},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "consultar_inventario", "arguments": {}}}]},
        {"role": "tool", "tool_name": "otra", "content": "{}"},
        {"role": "assistant", "content": "Hay 3 unidades."},
    ]
    salida = a_chat_completions(ollama)
    assert salida[2] == {"role": "assistant", "content": "", "tool_calls": [
        {"id": "llamada-1", "type": "function", "function": {"name": "buscar_producto", "arguments": '{"texto": "arroz"}'}},
        {"id": "call_x", "type": "function", "function": {"name": "listar_sucursales", "arguments": "{}"}}]}
    # Cada resultado con el id de su llamada, por nombre; si el nombre no está, la primera pendiente
    assert [(m["tool_call_id"], m["content"]) for m in salida if m["role"] == "tool"] == [
        ("call_x", '{"filas": []}'), ("llamada-1", '{"filas": [1]}'), ("llamada-3", "{}")]
    assert all("tool_name" not in m for m in salida) and salida[-1] == {"role": "assistant", "content": "Hay 3 unidades."}


def test_resultado_sin_llamada():
    with pytest.raises(ErrorLLM) as e:
        a_chat_completions([{"role": "user", "content": "x"}, {"role": "tool", "tool_name": "x", "content": "{}"}])
    assert e.value.codigo == "solicitud_invalida"


async def test_la_pregunta_completa_con_el_bucle(cliente_bedrock, bedrock):
    """El bucle del agente sin cambios: la llamada en stream, el resultado con su tool_call_id y la respuesta."""
    p = C.por_id("v0-01")
    bedrock.guion = [[("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"})], "En GLORIETA hay 420 unidades."]
    c = await correr_pregunta(cliente_bedrock, p, CATALOGO, C.fecha_datos)
    assert c.error is None and c.llamadas[0]["herramienta"] == "consultar_inventario"
    segunda = bedrock.cuerpo(1)["messages"]
    assert segunda[-2]["tool_calls"][0]["id"] == "call_0" and segunda[-1]["role"] == "tool"
    assert segunda[-1]["tool_call_id"] == "call_0" and "tool_name" not in segunda[-1]
    assert "420" in c.texto and c.tokens_prompt_max == 1200


# --- Streaming (P4, P5) ---

async def test_stream_texto_y_metricas(cliente_bedrock, bedrock):
    bedrock.guion = ["Hola, ¿en qué te ayudo?"]
    fragmentos = await _consumir(cliente_bedrock, herramientas=[HERRAMIENTA])
    assert bedrock.cuerpo()["stream"] is True and bedrock.cuerpo()["stream_options"] == {"include_usage": True}
    assert "".join(f.texto for f in fragmentos) == "Hola, ¿en qué te ayudo?"
    fin = fragmentos[-1]
    assert fin.fin and fin.metricas.tokens_prompt == 1200 and fin.metricas.tokens_respuesta == 80
    assert fin.metricas.ms_total >= fin.metricas.ms_prompt >= 0 and not fin.razonamiento_filtrado


async def test_stream_filtra_el_razonamiento(cliente_bedrock, bedrock):
    bedrock.eventos = [evento({"choices": [{"index": 0, "delta": {"reasoning_content": "pienso…"}}]}),
                       evento({"choices": [{"index": 0, "delta": {"content": "<think>dudo</thi"}}]}),
                       evento({"choices": [{"index": 0, "delta": {"content": "nk>Listo"}, "finish_reason": "stop"}]}),
                       ": comentario\n\n", evento("[DONE]")]
    fragmentos = await _consumir(cliente_bedrock)
    assert "".join(f.texto for f in fragmentos) == "Listo" and fragmentos[-1].razonamiento_filtrado
    # Sin evento de uso: métricas en cero, sin fallar
    assert fragmentos[-1].metricas.tokens_prompt == 0


async def test_stream_razonamiento_en_su_campo(cliente_bedrock, bedrock):
    bedrock.eventos = [evento({"choices": [{"index": 0, "delta": {"reasoning": "pienso"}}]}),
                       evento({"choices": [{"index": 0, "delta": {"content": "Listo"}, "finish_reason": "stop"}]})]
    fragmentos = await _consumir(cliente_bedrock)        # sin [DONE]: basta el finish_reason
    assert fragmentos[-1].razonamiento_filtrado and fragmentos[0].texto == "Listo"


async def test_stream_con_llamadas_por_partes(cliente_bedrock, bedrock):
    bedrock.guion = [[("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"}), ("listar_sucursales", {})]]
    fragmentos = await _consumir(cliente_bedrock, herramientas=[HERRAMIENTA])
    con_llamadas = [f for f in fragmentos if f.llamadas]
    assert len(con_llamadas) == 1 and fragmentos[-2] is con_llamadas[0] and fragmentos[-1].fin
    assert [(ll.id, ll.nombre, ll.argumentos) for ll in con_llamadas[0].llamadas] == [
        ("call_0", "consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"}), ("call_1", "listar_sucursales", {})]
    assert not any(f.texto for f in fragmentos)


async def test_stream_razonar_se_ignora(cliente_bedrock, bedrock):
    """P7 de INV-33 pasa `razonar`; en Bedrock va por BEDROCK_CUERPO_EXTRA (B14)."""
    await _consumir(cliente_bedrock, razonar=True)
    assert "razonar" not in bedrock.cuerpo() and "think" not in bedrock.cuerpo()


# --- Errores y reintentos (P6, P7) ---

@pytest.mark.parametrize("status,codigo,texto", [
    (400, "solicitud_invalida", "falla simulada"),
    (422, "solicitud_invalida", "falla simulada"),
    (401, "llm_no_disponible", "credenciales o el permiso (401)"),
    (403, "llm_no_disponible", "credenciales o el permiso (403)"),
    (404, "modelo_no_descargado", "falla simulada"),
    (500, "llm_no_disponible", "Bedrock respondió 500"),
])
async def test_errores_http(cliente_bedrock, bedrock, status, codigo, texto):
    for llamada in (lambda: cliente_bedrock.chat(MENSAJES), lambda: _consumir(cliente_bedrock)):
        bedrock.estados = [status]
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == codigo and texto in e.value.mensaje
    assert cliente_bedrock.esperas == []                 # sin reintentos


@pytest.mark.parametrize("cuerpo,detalle", [
    ('{"message": "sin acceso al modelo"}', "sin acceso al modelo"),
    ('{"error": "cadena"}', "cadena"),
    ("no es json", "no es json"),
])
async def test_detalle_del_error(cliente_bedrock, bedrock, cuerpo, detalle):
    bedrock.estados, bedrock.cuerpo_error = [400], cuerpo
    with pytest.raises(ErrorLLM) as e:
        await cliente_bedrock.chat(MENSAJES)
    assert e.value.mensaje == detalle


async def test_reintenta_429_y_503_antes_de_responder(cliente_bedrock, bedrock):
    bedrock.estados = [429, 503]
    r = await cliente_bedrock.chat(MENSAJES)
    assert r.texto == "Listo." and cliente_bedrock.esperas == [1.0, 2.0] and len(bedrock.peticiones) == 3
    # Cada intento se firma de nuevo
    assert all("authorization" in p.headers for p in bedrock.peticiones)


async def test_tras_dos_reintentos_falla(cliente_bedrock, bedrock):
    bedrock.estados = [429, 429, 429]
    with pytest.raises(ErrorLLM) as e:
        await _consumir(cliente_bedrock)
    assert e.value.codigo == "llm_no_disponible" and "429" in e.value.mensaje and len(bedrock.peticiones) == 3


@pytest.mark.parametrize("eventos,mensaje", [
    ([evento({"error": {"message": "throttled"}})], "throttled"),
    (["data: {roto\n\n"], "no es JSON"),
    ([evento({"choices": [{"index": 0, "delta": {"content": "a medias"}}]})], "sin final"),
])
async def test_errores_en_el_stream(cliente_bedrock, bedrock, eventos, mensaje):
    bedrock.eventos = eventos
    with pytest.raises(ErrorLLM) as e:
        await _consumir(cliente_bedrock)
    assert e.value.codigo == "respuesta_invalida" and mensaje in e.value.mensaje


async def test_respuesta_que_no_es_json(ajustes_bedrock):
    c = _cliente(ajustes_bedrock, lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(ErrorLLM) as e:
        await c.chat(MENSAJES)
    assert e.value.codigo == "respuesta_invalida"


async def test_red_caida_y_tiempo_agotado(ajustes_bedrock, bedrock):
    bedrock.caido = True
    c = _cliente(ajustes_bedrock, bedrock)
    for llamada in (lambda: c.chat(MENSAJES), lambda: _consumir(c)):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == "llm_no_disponible"

    def lento(request):
        raise httpx.ReadTimeout("lento", request=request)
    c = _cliente(ajustes_bedrock, lento)
    for llamada in (lambda: c.chat(MENSAJES), lambda: _consumir(c)):
        with pytest.raises(ErrorLLM) as e:
            await llamada()
        assert e.value.codigo == "tiempo_agotado"


async def test_corte_a_mitad_del_stream(ajustes_bedrock):
    class Cortado(httpx.AsyncByteStream):
        def __init__(self, error):
            self.error = error

        async def __aiter__(self):
            yield evento({"choices": [{"index": 0, "delta": {"content": "Hola"}}]}).encode()
            raise self.error

    for error, codigo in ((httpx.ReadTimeout("lento"), "tiempo_agotado"), (httpx.ReadError("cortado"), "llm_no_disponible")):
        c = _cliente(ajustes_bedrock, lambda request, e=error: httpx.Response(200, stream=Cortado(e)))
        with pytest.raises(ErrorLLM) as e:
            await _consumir(c)
        assert e.value.codigo == codigo
    await c.cerrar()


# --- Arnés (P13) ---

def test_correr_con_bedrock(tmp_path, bedrock):
    bedrock.guion = ["listo", [("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"})],
                     "En GLORIETA hay 420 unidades.", "No tengo ese dato."]
    salida = correr_mod.main(["--proveedor", "bedrock", "--preguntas", "v0-01,v0-15", "--corridas", "1",
                              "--salida", str(tmp_path), "--entorno", "nube-us-east-1"],
                             transport=httpx.MockTransport(bedrock), credenciales=lambda: CREDENCIALES)
    lineas = [json.loads(x) for x in salida.read_text().splitlines()]
    meta, corridas = lineas[0], lineas[1:]
    assert salida.name == "qwen.qwen3-32b-v1_0_nube.jsonl" and salida.parent.name.endswith("_nube-us-east-1")
    assert meta["proveedor"] == "bedrock" and meta["llm"] == "bedrock runtime us-east-1" and meta["modo"] == "nube"
    assert meta["precios_usd_millon"] == {"entrada": 0.15, "salida": 0.6} and meta["memoria"] == {}
    assert "ollama" not in meta and "modelo_info" not in meta
    # v0-01: dos rondas; v0-15: una. El calentamiento no cuenta
    assert [(c["id"], c["tokens_entrada"], c["tokens_salida"]) for c in corridas] == [("v0-01", 2400, 160), ("v0-15", 1200, 80)]
    assert corridas[0]["costo_usd"] == pytest.approx(0.000456)
    assert all(p.url.host == "bedrock-runtime.us-east-1.amazonaws.com" for p in bedrock.peticiones)


def test_correr_con_bedrock_se_detiene_en_el_tope(tmp_path, bedrock):
    """Cada petición simulada cuesta US$0,000228: con el calentamiento y una pregunta se pasa de US$0,0004."""
    with pytest.raises(SystemExit, match=r"tope de US\$0\.0004 alcanzado \(US\$0\.0005\).*no se registra en MLflow"):
        correr_mod.main(["--proveedor", "bedrock", "--preguntas", "v0-15,v0-17", "--corridas", "3", "--tope-usd", "0.0004",
                         "--salida", str(tmp_path), "--mlflow"],
                        transport=httpx.MockTransport(bedrock), credenciales=lambda: CREDENCIALES)
    [salida] = tmp_path.rglob("*.jsonl")
    assert len(salida.read_text().splitlines()) == 2              # la meta y la única pregunta que alcanzó
    assert len(bedrock.peticiones) == 2


def test_correr_con_bedrock_informa_el_costo(tmp_path, bedrock, capsys):
    correr_mod.main(["--proveedor", "bedrock", "--preguntas", "v0-15", "--corridas", "1", "--salida", str(tmp_path)],
                    transport=httpx.MockTransport(bedrock), credenciales=lambda: CREDENCIALES)
    assert "Costo estimado de la corrida: US$0.0005 (2 peticiones, 2400 tokens de entrada y 160 de salida)" in capsys.readouterr().out


def test_correr_con_bedrock_valida_los_argumentos(tmp_path):
    with pytest.raises(SystemExit, match="--modo cpu es de Ollama"):
        correr_mod.main(["--proveedor", "bedrock", "--modo", "cpu", "--salida", str(tmp_path)])
    with pytest.raises(SystemExit):
        correr_mod.main(["--salida", str(tmp_path)])            # Ollama sin --modelo
