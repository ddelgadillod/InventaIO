"""
InventAI/o — Búsqueda de productos tolerante a errores de escritura (INV-72, recibido de INV-82: decisión 5 y T4).

Solo se usa cuando la búsqueda normal no encuentra nada y quien llama lo pide (`tolerante=true` en /api/consulta/productos):
cada palabra de la búsqueda que no está en el vocabulario del catálogo se cambia por la más parecida, si el parecido es de al
menos PARECIDO_MINIMO (difflib). Entre las que empatan en parecido gana la que empieza con la misma letra y, después, la que
aparece en más productos («arrox» es «arroz» y no «tarro»). El vocabulario son las palabras de los nombres y las familias de
dw.dim_producto, con cuántos productos las usan, en memoria; se rehace cuando cambia la versión de los datos de la caché de lecturas.
"""
import difflib
import re
import unicodedata
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.cache_lecturas import get_cache_lecturas

PARECIDO_MINIMO = 0.8
LARGO_MINIMO = 3          # las palabras más cortas (g, kl, x) no se corrigen
PALABRA = re.compile(r"[^\W\d_]+")
SQL_NOMBRES = text("SELECT nombre, familia FROM dw.dim_producto")

CANDIDATAS = 10
_vocabulario: tuple[str, Counter] | None = None   # (versión de los datos, palabra → cuántos productos la usan)


def normalizar(palabra: str) -> str:
    """En minúsculas y sin tildes: «Azúcar» y «AZUCAR» son la misma palabra."""
    descompuesta = unicodedata.normalize("NFKD", palabra.lower())
    return "".join(c for c in descompuesta if not unicodedata.combining(c))


def palabras_de(texto: str | None) -> set[str]:
    return {normalizar(p) for p in PALABRA.findall(texto or "") if len(p) >= LARGO_MINIMO}


def contar_palabras(productos) -> Counter:
    """palabra → en cuántos productos aparece, a partir de filas (nombre, familia)."""
    cuenta: Counter = Counter()
    for nombre, familia in productos:
        cuenta.update(palabras_de(nombre) | palabras_de(familia))
    return cuenta


def mas_parecida(clave: str, vocabulario: Counter) -> str | None:
    candidatas = difflib.get_close_matches(clave, vocabulario, n=CANDIDATAS, cutoff=PARECIDO_MINIMO)
    if not candidatas:
        return None
    return max(candidatas, key=lambda c: (round(difflib.SequenceMatcher(None, clave, c).ratio(), 6),
                                          c[0] == clave[0], vocabulario[c], c))


def corregir(busqueda: str, vocabulario: Counter) -> str | None:
    """La búsqueda con cada palabra desconocida cambiada por la más parecida del vocabulario, o None si nada cambió."""
    cambio = False

    def reemplazo(m: re.Match) -> str:
        nonlocal cambio
        palabra = m.group(0)
        clave = normalizar(palabra)
        if len(clave) < LARGO_MINIMO or clave in vocabulario:
            return palabra
        parecida = mas_parecida(clave, vocabulario)
        if parecida is None:
            return palabra
        cambio = True
        return parecida

    corregida = PALABRA.sub(reemplazo, busqueda)
    return corregida if cambio else None


def vocabulario(db: Session) -> Counter:
    """Las palabras del catálogo para la versión actual de los datos."""
    global _vocabulario
    version = get_cache_lecturas().version(db)
    if _vocabulario is None or _vocabulario[0] != version:
        _vocabulario = (version, contar_palabras(db.execute(SQL_NOMBRES).fetchall()))
    return _vocabulario[1]
