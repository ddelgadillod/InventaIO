"""Glosario de INV-31 (negocio, y pronóstico y modelos): corpus al día, BM25 determinista, hit@3, «no tengo esa información»,
la herramienta y las cifras del glosario frente al código."""
import json
import re
import sys
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
    assert len(fragmentos) >= 60 and {f["parte"] for f in fragmentos} == {"Negocio", "Pronóstico y modelos"}
    assert all(f["id"] and f["titulo"] and f["fuente"].startswith("Glosario · ") and f["parte"] in ("Negocio", "Pronóstico y modelos") and f["tambien"]
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
    assert len(aciertos) >= 60 and sum(aciertos) / len(aciertos) >= 0.8
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
    assert "cita la fuente" in r["indicacion"] and r["fragmentos"][0]["fuente"].startswith("Glosario · Negocio · ")
    assert len(r["fragmentos"]) <= 3 and h.etiqueta(h.validar({"consulta": "rojo"})) == "Glosario · rojo"
    nada = (await h.ejecutar(None, h.validar({"consulta": "política de devoluciones de clientes"}))).para_modelo
    assert nada["resultado"] == "sin_resultados" and "no la inventes" in nada["indicacion"]


def _numero(patron: str, texto: str) -> str:
    m = re.search(patron, texto)
    assert m, patron
    return m.group(1)


def _seccion(titulo: str) -> str:
    """El texto de una sección `##` del glosario: cada regla se compara en su sección, no en todo el documento
    (la frase «menos de 3 días» aparece en el semáforo y en las alertas; un cambio en una no debe esconderse)."""
    m = re.search(rf"^## {re.escape(titulo)}\n(.*?)(?=^#{{1,2}} |\Z)", GLOSARIO, re.MULTILINE | re.DOTALL)
    assert m, titulo
    return m.group(1)


def _numeros(patron: str, titulo: str) -> list[float]:
    m = re.search(patron, _seccion(titulo))
    assert m, (titulo, patron)
    return [float(x) for x in m.groups()]


def test_las_cifras_del_glosario_son_las_del_codigo():
    """Cada cifra de una regla del glosario se lee en su sección y se compara con la constante del código."""
    inventario = (RAIZ / "api" / "schemas" / "inventario.py").read_text(encoding="utf-8")
    ok, bajo = (float(_numero(rf"{c} = ([\d.]+)", inventario)) for c in ("SEMAFORO_OK_MIN", "SEMAFORO_BAJO_MIN"))
    assert _numeros(r"\*\*Verde \(OK\):\*\* alcanza para (\d+) días o más", "Semáforo de inventario") == [ok]
    assert _numeros(r"\*\*Amarillo \(bajo\):\*\* alcanza para (\d+) días o más, pero menos de (\d+)",
                    "Semáforo de inventario") == [bajo, ok]
    assert _numeros(r"\*\*Rojo \(crítico\):\*\* alcanza para menos de (\d+) días", "Semáforo de inventario") == [bajo]
    assert _numeros(r"\*\*Stock crítico \(crítica\):\*\* menos de (\d+) días", "Alertas de reglas") == [bajo]
    assert _numeros(r"\*\*Stock bajo \(alta\):\*\* de (\d+) a (\d+) días", "Alertas de reglas") == [bajo, ok]

    config = (RAIZ / "etl_real" / "config.py").read_text(encoding="utf-8")
    minimo, reorden, maximo = (float(_numero(rf'"{c}": (\d+)', config))
                               for c in ("dias_stock_minimo", "dias_punto_reorden", "dias_stock_maximo"))
    seccion = "Stock mínimo, máximo y punto de reorden"
    assert _numeros(r"\*\*Mínimo:\*\* (\d+) días", seccion) == [minimo]
    assert _numeros(r"\*\*Punto de reorden:\*\* (\d+) días", seccion) == [reorden]
    assert _numeros(r"\*\*Máximo:\*\* (\d+) días", seccion) == [maximo]

    compras = json.loads((RAIZ / "ml_service" / "compras" / "politicas_inv21.json").read_text(encoding="utf-8"))
    assert _numeros(r"los días (\d+) y (\d+) de cada mes", "Calendario de pedidos") == compras["calendario_pedidos"]["quincenal"]["dias_mes"]
    assert re.search(r"Semanal, cada (\w+)", _seccion("Calendario de pedidos")).group(1) == compras["calendario_pedidos"]["semanal"]["dias_semana"][0]
    assert _numeros(r"llega (\d+) días hábiles después", "Calendario de pedidos") == [compras["lead_time_dias"]]
    assert _numeros(r"llega (\d+) días hábiles después de hacerlo", "Tiempo de entrega") == [compras["lead_time_dias"]]
    urgencia = [compras["urgencia"]["urgente_dias"], compras["urgencia"]["alta_dias"]]
    assert _numeros(r"\*\*Urgente:\*\* se agota en (\d+) días hábiles o menos\.\n- \*\*Alta:\*\* se agota en (\d+)",
                    "Compras sugeridas y su urgencia") == urgencia

    traslados = json.loads((RAIZ / "ml_service" / "transferencias" / "politicas_inv22.json").read_text(encoding="utf-8"))
    llegada = traslados["traslado"]["dias_habiles_si_no_hay_dias_fijos"]
    assert _numeros(r"\*\*Cantidad mínima:\*\* (\d+) unidades", "Traslados sugeridos") == [traslados["cantidades"]["minimo"]]
    assert _numeros(r"\*\*Llegada:\*\* (\d+) días hábiles", "Traslados sugeridos") == [llegada]
    assert _numeros(r"como en las compras \((\d+) y (\d+) días", "Traslados sugeridos") == \
        [traslados["urgencia"]["urgente_dias"], traslados["urgencia"]["alta_dias"]]
    assert _numeros(r"\*\*Traslado:\*\* llega en (\d+) días hábiles", "Tiempo de entrega") == [llegada]
    assert _numeros(r"lo recibe (\d+) días hábiles más tarde", "Tiempo de entrega") == [llegada]
    margen = traslados["stock_maximo"]
    assert _numeros(r"\((\d+) % sobre el límite alto del pronóstico, frente al (\d+) %", "Producto perecedero y de frío") == \
        [margen["margen_perecedero"] * 100, margen["margen_no_perecedero"] * 100]
    perdida = traslados["cantidades"]["descuento_kilos"]
    assert _numeros(r"se descuenta un (\d+) %", "Productos que se venden por kilo") == [round(perdida * 100)]
    assert _numeros(r"se cuenta el (\d+) %", "Sobrante de la bodega") == [round((1 - perdida) * 100)]
    assert _numeros(r"se queda con (\d+) unidades", "Unidades de exhibición") == [margen["unidades_exhibicion"]]

    modelo = json.loads((RAIZ / "models" / "nivel1_parametros_features.json").read_text(encoding="utf-8"))
    for titulo in ("Pronóstico de demanda", "Producto sin pronóstico"):
        assert _numeros(r"al menos (\d+) días con venta", titulo) == [modelo["min_frecuencia_as_of"]]


@pytest.mark.parametrize("titulo,original,cambiado", [
    ("Semáforo de inventario", "alcanza para menos de 3 días", "alcanza para menos de 4 días"),
    ("Alertas de reglas", "menos de 3 días de cobertura", "menos de 4 días de cobertura"),
    ("Calendario de pedidos", "los días 2 y 16", "los días 2 y 15"),
])
def test_la_comparacion_detecta_un_cambio_en_una_sola_seccion(titulo, original, cambiado, monkeypatch):
    """La prueba de fuego que hizo el usuario: cambiar una regla en una sección tiene que hacer fallar la comparación."""
    assert original in _seccion(titulo)
    seccion = _seccion(titulo)
    monkeypatch.setattr(sys.modules[__name__], "GLOSARIO", GLOSARIO.replace(seccion, seccion.replace(original, cambiado)))
    with pytest.raises(AssertionError):
        test_las_cifras_del_glosario_son_las_del_codigo()
