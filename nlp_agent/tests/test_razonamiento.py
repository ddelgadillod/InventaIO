"""El razonamiento (<think>…</think>) nunca llega al usuario, aunque venga partido entre fragmentos."""
from llm.razonamiento import FiltroRazonamiento


def _pasar(fragmentos: list[str]) -> tuple[str, FiltroRazonamiento]:
    f = FiltroRazonamiento()
    texto = "".join(f.filtrar(x) for x in fragmentos) + f.cerrar()
    return texto, f


def test_texto_sin_etiquetas_pasa_igual():
    texto, f = _pasar(["Hay 3.366 ", "unidades < 4.000"])
    assert texto == "Hay 3.366 unidades < 4.000"
    assert not f.hubo_razonamiento


def test_quita_el_bloque_completo():
    texto, f = _pasar(["<think>calculo el total</think>Son 12 cajas."])
    assert texto == "Son 12 cajas."
    assert f.hubo_razonamiento


def test_etiquetas_partidas_entre_fragmentos():
    texto, _ = _pasar(["Ho", "<thi", "nk>pienso", " algo</th", "ink>la", " mundo"])
    assert texto == "Hola mundo"


def test_razonamiento_sin_cerrar_se_descarta():
    texto, _ = _pasar(["Respuesta. <think>esto no termina"])
    assert texto == "Respuesta. "


def test_un_menor_que_al_final_no_se_pierde():
    texto, _ = _pasar(["stock <", ""])
    assert texto == "stock <"
