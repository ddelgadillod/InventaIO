"""
Filtro del razonamiento que se cuela en el texto (INV-32, criterio 13).

Con `think: false` Ollama separa el razonamiento en `message.thinking`, pero hay
reportes de Qwen3 que lo dejan en el texto entre <think> y </think>. Nada de eso
llega al usuario. Las etiquetas pueden venir partidas entre fragmentos del
stream, así que el filtro guarda lo que podría ser el comienzo de una etiqueta.
"""

ABRE = "<think>"
CIERRA = "</think>"


def _prefijo_pendiente(texto: str, etiqueta: str) -> int:
    """Largo del final de `texto` que coincide con el comienzo de `etiqueta`."""
    for n in range(min(len(texto), len(etiqueta) - 1), 0, -1):
        if etiqueta.startswith(texto[-n:]):
            return n
    return 0


class FiltroRazonamiento:
    def __init__(self) -> None:
        self._pendiente = ""
        self._dentro = False
        self.hubo_razonamiento = False

    def filtrar(self, fragmento: str) -> str:
        texto = self._pendiente + fragmento
        self._pendiente = ""
        salida = []
        while texto:
            etiqueta = CIERRA if self._dentro else ABRE
            i = texto.find(etiqueta)
            if i >= 0:
                if not self._dentro:
                    salida.append(texto[:i])
                    self.hubo_razonamiento = True
                self._dentro = not self._dentro
                texto = texto[i + len(etiqueta):]
                continue
            n = _prefijo_pendiente(texto, etiqueta)
            if not self._dentro:
                salida.append(texto[: len(texto) - n])
            self._pendiente = texto[len(texto) - n:] if n else ""
            break
        return "".join(salida)

    def cerrar(self) -> str:
        """Lo que quedó guardado al terminar: texto normal si no era una etiqueta."""
        resto, self._pendiente = self._pendiente, ""
        return "" if self._dentro else resto
