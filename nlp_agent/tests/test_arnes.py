"""Arnés, reporte y ejecutables del spike con un modelo simulado (sin Ollama)."""
import json

import httpx
import pytest

from evaluacion import correr as correr_mod
from evaluacion import reporte, smoke
from evaluacion.arnes import correr_pregunta, prompt_sistema
from evaluacion.conjunto import cargar, herramientas
from herramientas.catalogo import esquemas
from llm.cliente import (
    ErrorLLM,
    FragmentoLLM,
    LlamadaHerramienta,
    Metricas,
    RespuestaLLM,
)

C = cargar()
CATALOGO = herramientas()


class LLMGuion:
    """Responde en orden lo que dice el guion, en streaming como Ollama 0.40.5 (las llamadas en
    un fragmento propio y sin texto), y guarda los mensajes que recibió."""
    def __init__(self, guion):
        self.guion = list(guion)
        self.recibidos = []

    async def chat_stream(self, mensajes, opciones=None, herramientas=None):
        self.recibidos.append((json.loads(json.dumps(mensajes)), herramientas, opciones))
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        if paso.llamadas:
            yield FragmentoLLM(llamadas=paso.llamadas)
        if paso.texto:
            yield FragmentoLLM(texto=paso.texto)
        yield FragmentoLLM(fin=True, metricas=paso.metricas)


def respuesta(texto="", llamadas=(), tokens=1200):
    return RespuestaLLM(texto=texto, llamadas=[LlamadaHerramienta(n, a, id=f"c{i}") for i, (n, a) in enumerate(llamadas)],
                        metricas=Metricas(tokens_prompt=tokens, tokens_respuesta=20, ms_total=900.0))


def test_prompt_por_rol():
    assert "administrador de la sucursal LA 21" in prompt_sistema(C.por_id("v0-03"), "2025-12-31")
    assert "gerente" in prompt_sistema(C.por_id("v0-01"), "2025-12-31") and "2025-12-31" in prompt_sistema(C.por_id("v0-01"), "2025-12-31")


async def test_dos_rondas_con_resultado_sintetico():
    llm = LLMGuion([respuesta(llamadas=[("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"})], tokens=1150),
                    respuesta("En GLORIETA hay 420 unidades.", tokens=1260)])
    c = await correr_pregunta(llm, C.por_id("v0-01"), CATALOGO, C.fecha_datos, corrida=2, opciones={"num_gpu": 0})
    assert (c.rondas, c.corrida, c.tokens_prompt_max, c.tokens_respuesta) == (2, 2, 1260, 40)
    assert c.calificacion["acierto"] and c.llamadas[0]["herramienta"] == "consultar_inventario"
    mensajes = llm.recibidos[1][0]
    assert mensajes[2]["tool_calls"][0] == {"id": "c0", "function": {"name": "consultar_inventario",
                                                                    "arguments": {"sucursal": "GLORIETA", "producto": "huevos"}}}
    assert mensajes[3]["role"] == "tool" and "420 unidades" in mensajes[3]["content"]
    assert llm.recibidos[0][2] == {"num_gpu": 0}


async def test_herramienta_desconocida_y_limite_de_rondas():
    llamadas = [("inventada", {})]
    llm = LLMGuion([respuesta(llamadas=llamadas)] * 3 + [respuesta("No pude.")])
    c = await correr_pregunta(llm, C.por_id("v0-01"), CATALOGO, C.fecha_datos)
    # 3 rondas con herramientas y una última sin ellas, que obliga a responder
    assert c.rondas == 4 and c.texto == "No pude." and llm.recibidos[-1][1] is None
    assert "No existe la herramienta" in llm.recibidos[1][0][-1]["content"]
    assert not c.calificacion["herramienta"]


async def test_error_del_modelo():
    c = await correr_pregunta(LLMGuion([ErrorLLM("tiempo_agotado", "lento")]), C.por_id("v0-15"), CATALOGO, C.fecha_datos)
    assert c.error == "tiempo_agotado" and not c.calificacion["acierto"]


def _corrida(id_, tipo, acierto, ms=1000, tokens=1200, **cal):
    base = {k: True for k in ("herramienta", "fidelidad", "hechos", "prohibido", "aclaracion", "rechazo", "sin_error")}
    return {"id": id_, "tipo": tipo, "error": None, "razonamiento_filtrado": False, "ms_total": ms,
            "tokens_prompt_max": tokens, "calificacion": {**base, **cal, "acierto": acierto}}


def _archivo(ruta, modelo, corridas, modo="gpu"):
    meta = {"meta": True, "modelo": modelo, "modo": modo, "entorno": "local", "corridas": 3, "razonamiento": False}
    ruta.write_text("\n".join(json.dumps(x) for x in [meta, *corridas]) + "\n")
    return ruta


def test_reporte_metricas_y_diferencias(tmp_path):
    bueno = [_corrida(f"q{i}", "herramienta", True, ms=1000 * (i + 1)) for i in range(10) for _ in range(3)]
    malo = [_corrida(f"q{i}", "herramienta", i < 3, herramienta=i < 5) for i in range(10) for _ in range(3)]
    malo.append(_corrida("v0-19", "adversarial", False, rechazo=False))
    a = _archivo(tmp_path / "a.jsonl", "bueno", bueno)
    b = _archivo(tmp_path / "b.jsonl", "malo", malo)
    r = reporte.resumen(reporte.leer([b])[0]["corridas"])
    assert (r["preguntas"], r["fugas"]) == (11, 1) and r["pass3"] == pytest.approx(3 / 11)
    assert r["herramienta"] == pytest.approx(16 / 31)
    texto = reporte.main([str(a), str(b)])
    assert "| bueno | gpu | local | 10 × 3 | 100 % | 100 % |" in texto
    assert "| gpu | local | bueno | malo | 10 | +70.0 pts |" in texto and "| sí |" in texto


def test_diferencia_que_no_separa():
    a = {f"q{i}": [i % 2 == 0] * 3 for i in range(20)}
    b = {f"q{i}": [i % 2 == 1] * 3 for i in range(20)}
    d = reporte.diferencia_pareada(a, b)
    assert d["diferencia"] == 0 and d["ic95"][0] < 0 < d["ic95"][1]
    assert reporte.diferencia_pareada({}, {}) == {"preguntas": 0, "diferencia": 0.0, "ic95": (0.0, 0.0)}


def test_correr_escribe_meta_y_corridas(tmp_path, ollama):
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--preguntas", "v0-15,v0-17", "--corridas", "2", "--modo", "cpu",
                              "--base-url", "http://ollama-falso:11434", "--salida", str(tmp_path)],
                             transport=httpx.MockTransport(ollama))
    lineas = [json.loads(x) for x in salida.read_text().splitlines()]
    meta = lineas[0]
    assert meta["modelo_info"]["digest"] == "500a1f067a9f" and meta["memoria"] == {"total_gb": 6.19, "vram_gb": 6.19}
    assert meta["conjunto"] == "v0 (local, 2 preguntas)" and meta["modo"] == "cpu" and salida.name == "qwen3_8b_cpu.jsonl"
    assert [x["id"] for x in lineas[1:]] == ["v0-15", "v0-17", "v0-15", "v0-17"]
    assert all(json.loads(p.content).get("options", {}).get("num_gpu") == 0
               for p in ollama.peticiones if p.url.path == "/api/chat")


def test_correr_sin_el_modelo(tmp_path, ollama):
    with pytest.raises(SystemExit, match="no está descargado"):
        correr_mod.main(["--modelo", "qwen3:14b", "--preguntas", "v0-15", "--corridas", "1",
                         "--base-url", "http://ollama-falso:11434", "--salida", str(tmp_path)],
                        transport=httpx.MockTransport(ollama))


def test_smoke_mide_y_guarda(tmp_path, ollama):
    r = smoke.main(["--modelo", "qwen3:8b", "--razonamiento", "--base-url", "http://ollama-falso:11434", "--salida", str(tmp_path)],
                   transport=httpx.MockTransport(ollama))
    assert r["razonamiento"] and len(r["mediciones"]) == 5 and r["memoria_gb"] == 6.19
    assert r["generacion_tok_s"] == 50.0 and r["primer_token_s"] is not None
    assert ollama.peticiones[0].url.path == "/api/generate"           # descarga el modelo antes: carga en frío
    chats = [json.loads(p.content) for p in ollama.peticiones if p.url.path == "/api/chat"]
    assert all(c["think"] is True and c["messages"][3]["role"] == "tool" for c in chats)
    assert list(tmp_path.rglob("smoke_qwen3_8b_gpu_razonamiento.json"))


def test_correr_contra_el_core_api_real(tmp_path, ollama, core_api, monkeypatch):
    """T17: herramientas del catálogo v1, usuario de prueba por rol, prompt del agente y sin hechos clave."""
    from evaluacion import calificacion

    def ruteo(request):
        return ollama(request) if request.url.host == "ollama-falso" else core_api(request)
    monkeypatch.setenv("INVENTAIO_CLAVE_PRUEBA", "clave-de-prueba")
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--preguntas", "v0-01,v0-03", "--corridas", "1",
                              "--base-url", "http://ollama-falso:11434", "--core-api", "http://core-falso:8000",
                              "--salida", str(tmp_path)], transport=httpx.MockTransport(ruteo))
    lineas = [json.loads(x) for x in salida.read_text().splitlines()]
    assert salida.name == "qwen3_8b_gpu_real.jsonl" and lineas[0]["conjunto"] == "v0 (real, 2 preguntas)"
    assert lineas[0]["core_api"] == "http://core-falso:8000"
    assert all(x["calificacion"]["hechos"] and x["resultados"] == [] for x in lineas[1:])
    logins = [json.loads(p.content)["email"] for p in core_api.peticiones if p.url.path == "/api/auth/login"]
    assert logins == ["gerente@inventaio.co", "admin.norte@inventaio.co"]          # v0-03 es del admin de LA 21
    chats = [json.loads(p.content) for p in ollama.peticiones if p.url.path == "/api/chat" and json.loads(p.content).get("tools")]
    # esquemas(): el catálogo del agente; CATALOGO, en este archivo, es el del spike
    assert all(len(c["tools"]) == len(esquemas()) and "fecha_dato" in c["messages"][0]["content"] for c in chats)
    assert calificacion.recalificar_archivo(salida) == 0


def test_correr_real_sin_clave(tmp_path, monkeypatch):
    monkeypatch.delenv("INVENTAIO_CLAVE_PRUEBA", raising=False)
    with pytest.raises(SystemExit, match="INVENTAIO_CLAVE_PRUEBA"):
        correr_mod.main(["--modelo", "qwen3:8b", "--core-api", "http://core-falso:8000", "--salida", str(tmp_path)])
    with pytest.raises(SystemExit, match="solo con la variante local"):
        correr_mod.main(["--modelo", "qwen3:8b", "--core-api", "http://x", "--variante", "colab", "--salida", str(tmp_path)])


def test_el_sintetico_del_v1_valida_los_argumentos_como_el_real():
    from evaluacion.arnes import EjecutorSintetico
    from evaluacion.conjunto import cargar
    from herramientas.catalogo import esquemas
    e = EjecutorSintetico(cargar("local", "v1").preguntas[0], "2025-12-31", esquemas())
    p = e.preparar("recomendar_traslados", {"sucursal": "PRINCIPAL", "orden": "urgencia"})
    assert p.error.status == 422 and "«orden» no existe" in str(p.error)
    assert e.preparar("recomendar_traslados", {"producto": "Jabon Dersa"}).error is None


async def test_con_verificar_guarda_el_borrador_y_el_resultado():
    """INV-33 (Z11): la fidelidad del borrador (la del modelo) y la final, con el reintento."""
    llm = LLMGuion([respuesta(llamadas=[("consultar_inventario", {"sucursal": "GLORIETA", "producto": "huevos"})]),
                    respuesta("En GLORIETA hay 9.999 unidades."), respuesta("En GLORIETA hay 420 unidades.")])
    c = await correr_pregunta(llm, C.por_id("v0-01"), CATALOGO, C.fecha_datos, verificar=True)
    v = c.verificacion
    assert v["resultado"] == "reintento" and not v["borrador_fiel"] and v["borrador"] == "En GLORIETA hay 9.999 unidades."
    assert c.calificacion["fidelidad"] and "9.999" not in c.texto and "420" in c.texto
    assert "verificacion" in c.como_dict()


async def test_sin_verificar_no_hay_verificacion():
    llm = LLMGuion([respuesta("Hola")])
    c = await correr_pregunta(llm, C.por_id("v0-01"), CATALOGO, C.fecha_datos)
    assert c.verificacion is None and "verificacion" not in c.como_dict()


def test_registro_con_verificar(tmp_path):
    from evaluacion import registro_mlflow as rm
    meta = {"meta": True, "modelo": "qwen3:8b", "conjunto": "v1 (local, 2 preguntas)", "verificar": True, "tipo": "sonda",
            "version_prompt": "v2", "corridas": 1}
    cal = {"herramienta": True, "fidelidad": True, "hechos": True, "prohibido": True, "aclaracion": True, "rechazo": True,
           "sin_error": True, "cifras_sin_respaldo": [], "acierto": True}
    lineas = [meta] + [{"id": f"v1-0{i}", "corrida": 1, "rol": "gerente", "tipo": "herramienta", "rondas": 2, "llamadas": [],
                        "texto": "x", "error": None, "ms_total": 1000.0, "ms_modelo": 800.0, "tokens_prompt_max": 1,
                        "tokens_respuesta": 1, "razonamiento_filtrado": False, "calificacion": cal,
                        "verificacion": {"resultado": r, "borrador_fiel": r == "ok", "respaldo": r == "respaldo"}}
                       for i, r in ((1, "ok"), (2, "reintento"))]
    archivo = tmp_path / "x.jsonl"
    archivo.write_text("".join(json.dumps(x) + "\n" for x in lineas), encoding="utf-8")
    run = rm.run_de_archivo(archivo)
    m = run["metricas"]
    assert (m["fidelidad_borrador"], m["tasa_reintento"], m["tasa_respaldo"]) == (0.5, 0.5, 0.0)
    assert m["cumple_meta_fidelidad"] == 0.0                         # la meta se exige al borrador
    assert run["tags"]["verificar"] == "sí" and run["tags"]["version_prompt"] == "v2"
    assert "Fidelidad del borrador" in run["tags"]["mlflow.note.content"]
