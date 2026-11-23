"""INV-78: los tiempos de espera encadenados de una pregunta a Vera.

Navegador → Nginx (135 s) → Core API, chat (120 s en total) → agente → Core API → servicio de predicción (120 s).
La primera consulta de compras tras un despliegue tarda hasta ~52 s en el servicio de predicción. Con 60 s por
llamada, el agente cortaba antes que todos los demás y Vera respondía «hubo un problema».
"""
from core.config import Settings

FRIO_COMPRAS_S = 52          # lo más lento medido en frío en el servicio de predicción (INV-78, 18-nov)
CHAT_TIMEOUT_S = 120         # api/core/config.py: el tiempo total de un flujo del chat
MARGEN_MODELO_S = 15         # lo mínimo que debe quedar para las rondas del modelo dentro del chat


def test_el_agente_espera_las_recomendaciones_en_frio():
    s = Settings(_env_file=None)
    assert s.CORE_API_TIMEOUT_S >= FRIO_COMPRAS_S + 30, "el agente cortaría las compras en frío (INV-78)"


def test_la_espera_del_agente_cabe_en_el_tiempo_del_chat():
    s = Settings(_env_file=None)
    assert s.CORE_API_TIMEOUT_S + MARGEN_MODELO_S <= CHAT_TIMEOUT_S
    assert s.CORE_API_TIMEOUT_S < s.LLM_TIMEOUT_S
