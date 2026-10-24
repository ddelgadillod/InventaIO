"""Recorte del historial (Z7) y sugerencias deterministas (Z6), INV-33."""
from agente.historial import POR_PERFIL, recortar, tokens
from agente.sugerencias import GENERALES, MAX_SUGERENCIAS, sugerencias


def _turno(i, largo=700):
    return [{"role": "user", "content": f"pregunta {i} " + "x" * largo}, {"role": "assistant", "content": "r" * largo}]


def test_cabe_entero():
    h = _turno(1, 10) + [{"role": "user", "content": "¿y en LA 21?"}]
    assert recortar(h, 1500) == (h, 0)


def test_se_quitan_turnos_completos_desde_el_mas_viejo():
    """P-08: 13 mensajes que pasan el presupuesto: se quitan turnos viejos completos y la última pregunta queda."""
    h = [m for i in range(6) for m in _turno(i)] + [{"role": "user", "content": "¿y ahora?"}]
    assert len(h) == 13
    quedan, recortados = recortar(h, POR_PERFIL["completo"])
    assert recortados > 0 and quedan[0]["role"] == "user" and quedan[-1]["content"] == "¿y ahora?"
    assert tokens(quedan) <= 1500 and quedan == h[2 * recortados:]


def test_la_ultima_pregunta_siempre_queda():
    h = _turno(0) + [{"role": "user", "content": "z" * 10_000}]
    quedan, recortados = recortar(h, 500)
    assert recortados == 1 and quedan == [h[-1]]


def test_sugerencias():
    assert sugerencias(["consultar_inventario"]) == ["¿Quieres el pronóstico de demanda de ese producto?",
                                                     "¿Quieres las compras sugeridas?"]
    tres = sugerencias(["consultar_inventario", "listar_alertas", "pronosticar_demanda"])
    assert len(tres) == MAX_SUGERENCIAS and len(set(tres)) == 3
    assert sugerencias([]) == list(GENERALES) and sugerencias(["consultar_inventario"], hubo_error=True) == []
