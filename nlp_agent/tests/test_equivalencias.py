"""INV-40: las equivalencias declaradas para calificar el v1 y los holdouts con las herramientas nuevas."""
from evaluacion import equivalencias
from evaluacion.conjunto import cargar

V1 = {p.id: p for p in cargar("local", "v1").preguntas}


def _corrida(id_, llamadas, texto="", **cal):
    base = {k: True for k in ("herramienta", "fidelidad", "hechos", "prohibido", "aclaracion", "rechazo", "sin_error",
                              "abstiene", "cita", "acierto")}
    return {"id": id_, "llamadas": [{"ronda": 1, "herramienta": n, "argumentos": a} for n, a in llamadas], "texto": texto,
            "calificacion": {**base, "herramienta_ejecutada": None, **cal}}


def test_ficha_periodo_y_guia_valen():
    archivo = {"meta": {"conjunto": "v1 (real, 61 preguntas)"}, "corridas": [
        _corrida("v1-02", [("ficha_producto", {"producto": "P1234"})], herramienta=False, acierto=False),
        _corrida("v1-55", [("historial_ventas", {"periodo": "mes pasado", "sucursal": "PRINCIPAL"})], herramienta=False),
        _corrida("v1-53", [("buscar_en_glosario", {"consulta": "asistente"})], "Según la Guía de uso, 16.1 …", herramienta=False),
        _corrida("v1-51", [("consultar_inventario", {})], "Hay 12.", herramienta=False),          # abstención que consulta datos
        _corrida("v1-02", [("ficha_producto", {"producto": "P1234"})], herramienta=False, hechos=False),
    ]}
    c = equivalencias.recalificar(archivo)["corridas"]
    assert [x["calificacion"]["herramienta"] for x in c] == [True, True, True, False, True]
    assert [x["calificacion"]["acierto"] for x in c] == [True, True, True, False, False]   # los demás criterios mandan
    assert archivo["corridas"][0]["calificacion"]["herramienta"] is False                  # el original no cambia


def test_sin_las_herramientas_nuevas_nada_cambia():
    p = V1["v1-02"]
    assert len(equivalencias.esperados(p)) > len(p.esperado)
    assert equivalencias.elige(p, [("buscar_producto", {"texto": "P1234"})], "") == \
        any(e.herramienta == "buscar_producto" for e in p.esperado)
    assert equivalencias.version_de({"conjunto": "holdout-2 (real, 15 preguntas)"}) == "holdout-2"
