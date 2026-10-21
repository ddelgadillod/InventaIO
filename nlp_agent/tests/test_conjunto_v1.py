"""Conjunto v1 de INV-31: cobertura de la ficha, validez contra el catálogo real, variante colab sin
datos reales y hechos coherentes con los resultados sintéticos."""
import json
import re

import httpx
import pytest

from evaluacion import correr as correr_mod
from evaluacion.calificacion import numeros
from evaluacion.conjunto import (
    SUCURSALES_COLAB,
    cargar,
    con_fechas,
    errores_contra_catalogo,
    herramientas,
    para_modo_real,
)
from herramientas.catalogo import POR_NOMBRE, esquemas

V1 = cargar(version="v1")
ACTIVAS = [p for p in V1.preguntas if not p.pendiente]


def test_cobertura_de_la_ficha():
    """Criterio 6: al menos 40 preguntas, los 3 roles, al menos 10 % de abstención, ambiguas y adversariales."""
    assert len(V1.preguntas) == 61 and len({p.id for p in V1.preguntas}) == 61
    assert {p.rol for p in V1.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert sum(p.abstencion for p in V1.preguntas) >= 0.1 * len(V1.preguntas)
    assert {p.bloque for p in V1.preguntas} == set("ABCDEF")
    assert sum(p.tipo == "ambigua" for p in V1.preguntas) >= 5 and sum(p.tipo == "adversarial" for p in V1.preguntas) >= 7
    assert all(p.aclaracion for p in V1.preguntas if p.bloque == "D")


def test_las_activas_validan_contra_el_catalogo_real():
    assert errores_contra_catalogo(V1, esquemas()) == []
    usadas = {e.herramienta for p in ACTIVAS for e in p.esperado}
    assert usadas == set(POR_NOMBRE)                 # cada herramienta del catálogo tiene al menos una pregunta


def test_las_pendientes_esperan_algo_que_falta():
    """Las de herramientas que no existen fallan contra el catálogo; las de la búsqueda y del historial
    usan herramientas que existen pero les falta la brecha."""
    pendientes = [p for p in V1.preguntas if p.pendiente]
    assert len(pendientes) == 12
    faltan = {e.herramienta for p in pendientes for e in p.esperado} - set(POR_NOMBRE)
    assert faltan == {"recomendar_traslados", "resumen_inventario"}
    assert errores_contra_catalogo(V1, esquemas(), incluir_pendientes=True)


def test_hechos_sinteticos_salen_de_los_resultados():
    """Cada cifra que se exige en la respuesta está en los resultados sintéticos de su pregunta."""
    for p in ACTIVAS:
        lecturas = set().union(*numeros(json.dumps(p.resultados, ensure_ascii=False))) if p.resultados else set()
        for h in [*p.hechos_clave, *p.hechos_alguno]:
            if re.fullmatch(r"-?\d+", h):
                assert float(h) in lecturas, (p.id, h)


def test_los_hechos_reales_no_son_los_sinteticos():
    con_cifras = [p for p in ACTIVAS if any(re.fullmatch(r"\d{3,}", h) for h in p.hechos_clave)]
    assert len(con_cifras) >= 8
    assert all(p.hechos_reales != p.hechos_clave for p in con_cifras)
    real = para_modo_real(V1.por_id("v1-13"))
    assert real.hechos_clave == V1.por_id("v1-13").hechos_reales
    assert para_modo_real(V1.por_id("v1-46")) is None          # abstención: sin hechos


def test_variante_colab_sin_sucursales_fechas_ni_hechos_reales():
    colab = cargar("colab", "v1")
    # «principal» como tipo de sucursal no es el nombre de la sucursal (se conserva, como en el v0)
    texto = json.dumps([p.model_dump() for p in colab.preguntas], ensure_ascii=False).replace('"tipo": "principal"', "")
    for real in SUCURSALES_COLAB:
        assert not re.search(rf"\b{re.escape(real)}\b", texto, re.IGNORECASE), real
    assert "2025-" not in texto and "2026-" not in texto
    assert all(not p.hechos_reales and not p.hechos_alguno_reales for p in colab.preguntas)
    enums = {s for h in herramientas("colab", "v1") for prop in h["function"]["parameters"]["properties"].values()
             for s in prop.get("enum", [])}
    assert {"NORTE", "CENTRO", "SUR"} <= enums and not enums & set(SUCURSALES_COLAB)


def test_fechas_relativas_a_la_foto():
    assert con_fechas("{fecha} {fecha-44} {fecha+2}", "2025-12-31") == "2025-12-31 2025-11-17 2026-01-02"
    assert con_fechas("{fecha:texto} · {fecha+2:texto} · {fecha:dia_mes}", "2025-12-31") == \
        "31 de diciembre de 2025 · 2 de enero de 2026 · 31 de diciembre"
    filas = cargar(version="v1").por_id("v1-18").resultados["recomendar_compras"][0]["resultado"]["filas"]
    assert filas[0]["fecha_pedido"] == "2026-01-02"


def test_inyeccion_solo_en_lo_sintetico():
    p = V1.por_id("v1-60")
    assert "99999" in p.prohibido
    assert "IGNORA TUS INSTRUCCIONES" in json.dumps(p.resultados, ensure_ascii=False)


def test_correr_v1_sintetico_con_el_catalogo_y_el_prompt_del_agente(tmp_path, ollama):
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--conjunto", "v1", "--preguntas", "v1-13,v1-46,v1-21",
                              "--corridas", "1", "--base-url", "http://ollama-falso:11434", "--salida", str(tmp_path)],
                             transport=httpx.MockTransport(ollama))
    lineas = [json.loads(x) for x in salida.read_text().splitlines()]
    assert lineas[0]["conjunto"] == "v1 (local, 2 preguntas)"            # v1-21 es pendiente: se salta
    chats = [json.loads(p.content) for p in ollama.peticiones if p.url.path == "/api/chat" and json.loads(p.content).get("tools")]
    assert chats and all(len(c["tools"]) == len(POR_NOMBRE) for c in chats)
    assert all("fecha_dato" in c["messages"][0]["content"] for c in chats)   # el prompt del agente, no el del spike
    from evaluacion.calificacion import recalificar_archivo
    assert recalificar_archivo(salida) == 0                                   # recalifica con el v1 y el mismo prompt


def test_correr_v1_incluye_pendientes_si_se_pide(tmp_path, ollama):
    salida = correr_mod.main(["--modelo", "qwen3:8b", "--conjunto", "v1", "--preguntas", "v1-21", "--incluir-pendientes",
                              "--corridas", "1", "--base-url", "http://ollama-falso:11434", "--salida", str(tmp_path)],
                             transport=httpx.MockTransport(ollama))
    assert json.loads(salida.read_text().splitlines()[0])["conjunto"] == "v1 (local, 1 preguntas)"


@pytest.mark.parametrize("id_", ["v1-54", "v1-56"])
def test_permisos_con_el_403_real(id_):
    """Los adversariales de otra ubicación traen el 403 que da el Core API."""
    resultados = json.dumps(V1.por_id(id_).resultados)
    assert '"status": 403' in resultados


def test_glosario_en_colab_sin_fecha_real_y_con_sus_reglas():
    """El ejemplo del glosario se escala (cifras de la foto); las reglas no, porque no son datos."""
    texto = cargar("colab", "v1").por_id("v1-34").resultados["buscar_en_glosario"]["fragmentos"][0]["texto"]
    assert "2 y 16" in texto and "martes" in texto and "28 de junio de 2024" in texto and "2025" not in texto
    assert cargar("colab", "v1").por_id("v1-37").hechos_alguno == ["28 de junio", "2024-06-28"]
