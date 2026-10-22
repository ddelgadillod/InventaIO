"""
InventAI/o — Reenvío de los eventos del agente (INV-36, X10)
Separa los eventos por la línea vacía y los reenvía sin cambios, byte a byte,
incluidos los comentarios (`: ping`, X5-c). Solo los lee para saber cuál fue el
último y tomar las cifras de `done` para el registro, nunca el texto (Ley 1581).
"""
import json

SEPARADOR = b"\n\n"


def evento(nombre: str, datos: dict) -> bytes:
    return f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n".encode()


class Reenvio:
    def __init__(self):
        self._pendiente = b""
        self.eventos = 0
        self.ultimo: str | None = None
        self.done: dict = {}
        self.codigo_error: str | None = None

    def recibir(self, fragmento: bytes) -> list[bytes]:
        """Los eventos completos que ya se pueden reenviar."""
        self._pendiente += fragmento
        listos = []
        while SEPARADOR in self._pendiente:
            bloque, self._pendiente = self._pendiente.split(SEPARADOR, 1)
            self._leer(bloque)
            listos.append(bloque + SEPARADOR)
        return listos

    def resto(self) -> bytes:
        resto, self._pendiente = self._pendiente, b""
        return resto

    def _leer(self, bloque: bytes) -> None:
        nombre, datos = None, None
        for linea in bloque.decode("utf-8", "replace").splitlines():
            if linea.startswith("event: "):
                nombre = linea[7:].strip()
            elif linea.startswith("data: "):
                datos = linea[6:]
        if nombre is None:
            return                                   # comentario: «: ping»
        self.eventos += 1
        self.ultimo = nombre
        if nombre in ("done", "error") and datos:
            try:
                cuerpo = json.loads(datos)
            except ValueError:
                return
            if nombre == "done":
                self.done = cuerpo
            else:
                self.codigo_error = cuerpo.get("codigo")
