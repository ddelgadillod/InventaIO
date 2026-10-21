"""
Búsqueda léxica BM25 sobre el glosario (INV-31, criterio 2 y G4). Sin dependencias ni embeddings:
la GPU es del modelo y el corpus es pequeño.

Las palabras se normalizan igual en el corpus y en la consulta: minúsculas, sin acentos, sin palabras
vacías, sin la «s» final y cortadas a 6 letras (un recorte de prefijo, que en español junta
«alerta»/«alertas», «prioriza»/«priorización» y «sucursal»/«sucursales»). El título y la línea
«También se dice» pesan más, porque traen las palabras con que la gente pregunta. Es determinista:
a igual puntaje, gana el id menor (criterio 8).
"""
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "corpus.json"
K1, B = 1.5, 0.75
LARGO = 6
PESO_TITULO, PESO_TAMBIEN = 3, 2
VACIAS = frozenset("""
a al algo algun alguna algunas alguno algunos ante antes asi aun cada como con contra cual cuales cuando de del desde
donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estan estas este esto estos fue ha hay la las
le les lo los mas me mi mis mucho muy nada ni no nos o otra otro para pero poco por porque que quien se ser si sin
sobre solo son su sus tambien te tiene tienen todo todos tu tus un una uno unos usted y ya yo
dame dime explica explicame significa significan significado quiere quieren decir refieres refiere puedes puede favor
funciona funcionan hace hacen hacer trata tratas tratan maneja manejan pasa pasan decide sea salen sale debo debe
utiliza utilizas usa usas queda quedan
""".split())
# Fracción de los términos de la consulta que debe tener el mejor fragmento para responder (G5).
# Calibrada con conocimiento/consultas_hit3.json: las de dentro tienen 0,67 o más; las de fuera, 0,5 o menos.
UMBRAL_COBERTURA = 0.6


def palabras(texto: str) -> list[str]:
    normal = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    salida = []
    for p in re.findall(r"[a-z0-9]+", normal):
        if p in VACIAS or (len(p) < 2 and not p.isdigit()):
            continue
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        salida.append(p[:LARGO])
    return salida


@dataclass(frozen=True)
class Encontrado:
    fragmento: dict
    puntaje: float


class Indice:
    def __init__(self, fragmentos: list[dict]):
        self.fragmentos = fragmentos
        self._docs = [Counter(palabras(f["titulo"]) * PESO_TITULO + palabras(f.get("tambien", "")) * PESO_TAMBIEN
                              + palabras(f["texto"])) for f in fragmentos]
        self._largo = [sum(d.values()) for d in self._docs]
        self._promedio = sum(self._largo) / len(self._largo) if self._largo else 0.0
        df = Counter(p for d in self._docs for p in d)
        n = len(fragmentos)
        self._idf = {p: math.log((n - c + 0.5) / (c + 0.5) + 1) for p, c in df.items()}

    @classmethod
    def desde_archivo(cls, ruta: Path = CORPUS) -> "Indice":
        return cls(json.loads(ruta.read_text(encoding="utf-8"))["fragmentos"])

    def puntaje(self, consulta: list[str], i: int) -> float:
        doc, largo, total = self._docs[i], self._largo[i], 0.0
        for p in set(consulta):
            f = doc.get(p, 0)
            if f:
                total += self._idf[p] * f * (K1 + 1) / (f + K1 * (1 - B + B * largo / self._promedio))
        return total

    def cobertura(self, consulta: str, fragmento_id: str) -> float:
        """Qué fracción de las palabras de la consulta aparece en el fragmento."""
        terminos = set(palabras(consulta))
        i = next(n for n, f in enumerate(self.fragmentos) if f["id"] == fragmento_id)
        return sum(1 for p in terminos if p in self._docs[i]) / len(terminos) if terminos else 0.0

    def responde(self, consulta: str, k: int = 3) -> list[Encontrado]:
        """Los k mejores si el primero cubre la consulta (G5); si no, ninguno: «no tengo esa información»."""
        encontrados = self.buscar(consulta, k)
        if not encontrados or self.cobertura(consulta, encontrados[0].fragmento["id"]) < UMBRAL_COBERTURA:
            return []
        return encontrados

    def buscar(self, consulta: str, k: int = 3) -> list[Encontrado]:
        terminos = palabras(consulta)
        if not terminos:
            return []
        puntajes = [(self.puntaje(terminos, i), f["id"], i) for i, f in enumerate(self.fragmentos)]
        mejores = sorted((x for x in puntajes if x[0] > 0), key=lambda x: (-x[0], x[1]))[:k]
        return [Encontrado(self.fragmentos[i], round(s, 4)) for s, _, i in mejores]
