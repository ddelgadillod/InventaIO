"""Glosario de negocio de INV-31: corpus al día, BM25 determinista, hit@3, «no tengo esa información»,
la herramienta y las cifras del glosario frente al código."""
import json
import re
from pathlib import Path

import pytest

from conocimiento import construir
from conocimiento.bm25 import UMBRAL_COBERTURA, Indice, palabras
from herramientas.catalogo import POR_NOMBRE

RAIZ = Path(__file__).resolve().parents[2]
CONSULTAS = json.loads((Path(construir.__file__).parent / "consultas_hit3.json").read_text(encoding="utf-8"))
INDICE = Indice.desde_archivo()
GLOSARIO = construir.DOCUMENTO.read_text(encoding="utf-8")


def test_corpus_al_dia_con_el_documento():
    """Criterio 8 y G3: el JSON de la imagen es exactamente el que sale del documento."""
    assert construir.main(["--verificar"]) == 0
    assert construir.serializar(construir.corpus(GLOSARIO)) == construir.serializar(construir.corpus(GLOSARIO))


def test_fragmentos_con_id_titulo_y_fuente():
    """Criterio 1."""
    fragmentos = construir.fragmentos(GLOSARIO)
    assert len(fragmentos) >= 15
    assert all(f["id"] and f["titulo"] and f["fuente"].startswith("Glosario de negocio · ") and f["tambien"]
               for f in fragmentos)
    assert all("**" not in f["texto"] and "`" not in f["texto"] for f in fragmentos)
    with pytest.raises(ValueError, match="repetidos"):
        construir.fragmentos("## Semáforo\ntexto\n## Semáforo\notro")


def test_verificar_falla_si_el_corpus_no_corresponde(tmp_path, monkeypatch):
    monkeypatch.setattr(construir, "CORPUS", tmp_path / "corpus.json")
    assert construir.main(["--verificar"]) == 1
    assert construir.main([]) == 0 and construir.main(["--verificar"]) == 0


def test_palabras_normalizadas():
    assert palabras("¿Qué significan las ALERTAS de los Productos perecederos?") == ["alerta", "produc", "perece"]
    assert palabras("días") == palabras("dia")


def test_hit3_y_fuera_del_glosario():
    """Criterio 7 (≥ 0,8) y criterio 4: lo que el glosario no tiene no devuelve nada."""
    aciertos = [x["esperado"] in [e.fragmento["id"] for e in INDICE.responde(x["consulta"])] for x in CONSULTAS["dentro"]]
    assert len(aciertos) >= 30 and sum(aciertos) / len(aciertos) >= 0.8
    assert all(INDICE.responde(x["consulta"]) == [] for x in CONSULTAS["fuera"])
    ids = {f["id"] for f in INDICE.fragmentos}
    assert {x["esperado"] for x in CONSULTAS["dentro"]} <= ids


def test_determinista_y_desempate_por_id():
    a = [(e.fragmento["id"], e.puntaje) for e in INDICE.buscar("alertas")]
    assert a == [(e.fragmento["id"], e.puntaje) for e in Indice.desde_archivo().buscar("alertas")]
    empate = Indice([{"id": "b", "titulo": "x", "texto": "rojo"}, {"id": "a", "titulo": "x", "texto": "rojo"}])
    assert [e.fragmento["id"] for e in empate.buscar("rojo")] == ["a", "b"]
    assert INDICE.buscar("de la el") == [] and 0 < UMBRAL_COBERTURA < 1


async def test_herramienta_con_fuente_y_sin_resultados():
    h = POR_NOMBRE["buscar_en_glosario"]
    r = (await h.ejecutar(None, h.validar({"consulta": "qué es el semáforo rojo"}))).para_modelo
    assert r["resultado"] == "encontrado" and r["fragmentos"][0]["id"] == "semaforo_de_inventario"
    assert "cita la fuente" in r["indicacion"] and r["fragmentos"][0]["fuente"].startswith("Glosario de negocio")
    assert len(r["fragmentos"]) <= 3 and h.etiqueta(h.validar({"consulta": "rojo"})) == "Glosario · rojo"
    nada = (await h.ejecutar(None, h.validar({"consulta": "política de devoluciones de clientes"}))).para_modelo
    assert nada["resultado"] == "sin_resultados" and "no la inventes" in nada["indicacion"]


def _numero(patron: str, texto: str) -> str:
    m = re.search(patron, texto)
    assert m, patron
    return m.group(1)


def test_las_cifras_del_glosario_son_las_del_codigo():
    """Si cambia una regla en el código, el glosario tiene que cambiar con ella."""
    inventario = (RAIZ / "api" / "schemas" / "inventario.py").read_text(encoding="utf-8")
    assert float(_numero(r"SEMAFORO_OK_MIN = ([\d.]+)", inventario)) == 7
    assert float(_numero(r"SEMAFORO_BAJO_MIN = ([\d.]+)", inventario)) == 3
    assert "alcanza para 7 días o más" in GLOSARIO and "menos de 3 días" in GLOSARIO
    compras = json.loads((RAIZ / "ml_service" / "compras" / "politicas_inv21.json").read_text(encoding="utf-8"))
    assert compras["calendario_pedidos"] == {"quincenal": {"dias_mes": [2, 16]}, "semanal": {"dias_semana": ["martes"]}}
    assert compras["lead_time_dias"] == 5 and compras["urgencia"] == {"urgente_dias": 5, "alta_dias": 10}
    assert "días 2 y 16" in GLOSARIO and "cada martes" in GLOSARIO and "5 días hábiles después" in GLOSARIO
    traslados = json.loads((RAIZ / "ml_service" / "transferencias" / "politicas_inv22.json").read_text(encoding="utf-8"))
    assert traslados["cantidades"]["minimo"] == 6 and traslados["traslado"]["dias_habiles_si_no_hay_dias_fijos"] == 2
    assert (traslados["stock_maximo"]["margen_perecedero"], traslados["stock_maximo"]["margen_no_perecedero"]) == (0.25, 0.5)
    assert "6 unidades o kilos" in GLOSARIO and "25 %" in GLOSARIO and "50 %" in GLOSARIO
    config = (RAIZ / "etl_real" / "config.py").read_text(encoding="utf-8")
    assert [_numero(rf'"{c}": (\d+)', config) for c in ("dias_stock_minimo", "dias_punto_reorden", "dias_stock_maximo")] == \
        ["3", "7", "30"]
