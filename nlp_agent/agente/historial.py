"""
Presupuesto del historial (INV-33, criterio 5, decisión Z7). Los tokens se estiman como caracteres / 3,5, más
conservador que los 4,2 medidos en español. Se quitan turnos completos (usuario y agente) desde el más viejo
hasta que el historial cabe; la última pregunta siempre se conserva. Lo recortado va en `done.turnos_recortados`.
"""
CARACTERES_POR_TOKEN = 3.5
POR_PERFIL = {"completo": 1500, "corto": 500}


def tokens(mensajes: list[dict]) -> int:
    return round(sum(len(str(m.get("content") or "")) for m in mensajes) / CARACTERES_POR_TOKEN)


def recortar(historial: list[dict], max_tokens: int) -> tuple[list[dict], int]:
    """El historial que cabe en `max_tokens` y cuántos turnos se quitaron. Un turno empieza en un mensaje del
    usuario; el último (la pregunta actual y lo que siga) nunca se quita."""
    inicios = [i for i, m in enumerate(historial) if m.get("role") == "user"]
    if len(inicios) <= 1:
        return historial, 0
    recortados = 0
    while recortados < len(inicios) - 1 and tokens(historial[inicios[recortados]:]) > max_tokens:
        recortados += 1
    return historial[inicios[recortados]:], recortados
