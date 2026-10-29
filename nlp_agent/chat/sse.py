"""Formato de los eventos SSE del chat: `event: <nombre>` y `data: <JSON>` (§4.3)."""
import json

EVENTOS = ("meta", "tool", "data", "token", "done", "error")


def evento(nombre: str, datos: dict) -> str:
    if nombre not in EVENTOS:
        raise ValueError(f"evento desconocido: {nombre}")
    return f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n"
