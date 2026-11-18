"""
Búsqueda léxica BM25 sobre el glosario (INV-31, criterio 2 y G4). Sin dependencias ni embeddings:
la GPU es del modelo y el corpus es pequeño.

Las palabras se normalizan igual en el corpus y en la consulta: minúsculas, sin acentos, sin palabras
vacías, sin la «s» final y cortadas a 6 letras (un recorte de prefijo, que en español junta
«alerta»/«alertas», «prioriza»/«priorización» y «sucursal»/«sucursales»). El título y la línea
«También se dice» pesan más, porque traen las palabras con que la gente pregunta. Es determinista:
a igual puntaje, gana el id menor (criterio 8).

INV-40 (decisión 6, propuesta externa adoptada desde el inicio): la sección de la guía también pesa, y para
responder se exige un umbral doble: el puntaje BM25 del mejor fragmento y la cobertura de la consulta ponderada
por IDF (una palabra rara que falta pesa más que una común, y una que el corpus no tiene, más que todas). Quitar
sufijos del español se midió y quedó apagado (QUITAR_SUFIJOS). Los umbrales y el peso de la guía se calibraron
con el glosario (consultas_hit3.json) y los conjuntos de desarrollo guia-dev y abstencion-dev, nunca con los
de aceptación.
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
# Quien pregunta es gente del negocio: si un término de negocio y uno técnico compiten por la misma palabra
# («cobertura»: días de cobertura frente a cobertura empírica), va primero el de negocio
# La guía (INV-40) va un poco por debajo del glosario: sin eso se llevaba consultas del glosario («calendario de
# pedidos», «qué modelo usa el pronóstico»). Calibrado en la rejilla del 18-nov (docs/INV-40-requerimientos.md)
PESO_PARTE = {"Pronóstico y modelos": 0.8, "Guía de uso": 0.8}
PESO_SECCION = 2
# Medido el 18-nov: con el recorte a 6 letras, quitar sufijos no junta nada que el recorte no junte y separa
# palabras («valida» de «validación»); el glosario bajaba de 60 a 59 aciertos. Queda apagado
QUITAR_SUFIJOS = False
SUFIJOS_GEMINI = ("aciones", "iciones", "amiento", "imiento", "acion", "icion", "mente", "ando", "iendo", "encia", "ente",
           "bles", "ble")
VACIAS = frozenset("""
a al algo algun alguna algunas alguno algunos ante antes asi aun cada como con contra cual cuales cuando de del desde
donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estan estas este esto estos fue ha hay la las
le les lo los mas me mi mis mucho muy nada ni no nos o otra otro para pero poco por porque que quien se ser si sin
sobre solo son su sus tambien te tiene tienen todo todos tu tus un una uno unos usted y ya yo
dame dime explica explicame significa significan significado quiere quieren decir refieres refiere puedes puede favor
funciona funcionan hace hacen hacer trata tratas tratan maneja manejan pasa pasan decide sea salen sale debo debe
utiliza utilizas usa usas queda quedan calcula calculan calcular
""".split())
# Fracción de los términos de la consulta que debe tener el mejor fragmento para responder (G5). Desde INV-40 es
# la fracción de la masa IDF de la consulta, y además el mejor fragmento necesita un puntaje BM25 mínimo
UMBRAL_COBERTURA = 0.45
UMBRAL_PUNTAJE = 1.65


def palabras(texto: str) -> list[str]:
    normal = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    salida = []
    for p in re.findall(r"[a-z0-9]+", normal):
        if p in VACIAS or (len(p) < 2 and not p.isdigit()):
            continue
        if QUITAR_SUFIJOS:
            for sufijo in SUFIJOS_GEMINI:
                if len(p) > len(sufijo) + 3 and p.endswith(sufijo):
                    p = p[:-len(sufijo)]
                    break
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        salida.append(p[:LARGO])
    return salida


def _sin_numero(seccion: str) -> str:
    """«Parte II · 12.7 Recomendaciones» → «Recomendaciones»: el número no es una palabra que alguien pregunte."""
    return re.sub(r"^.*?\d+(?:\.\d+)*\s*", "", seccion)


@dataclass(frozen=True)
class Encontrado:
    fragmento: dict
    puntaje: float


class Indice:
    def __init__(self, fragmentos: list[dict]):
        self.fragmentos = fragmentos
        self._docs = [Counter(palabras(f["titulo"]) * PESO_TITULO + palabras(f.get("tambien", "")) * PESO_TAMBIEN
                              + palabras(_sin_numero(f.get("seccion", ""))) * PESO_SECCION + palabras(f["texto"]))
                      for f in fragmentos]
        self._largo = [sum(d.values()) for d in self._docs]
        self._promedio = sum(self._largo) / len(self._largo) if self._largo else 0.0
        df = Counter(p for d in self._docs for p in d)
        n = len(fragmentos)
        self._idf = {p: math.log((n - c + 0.5) / (c + 0.5) + 1) for p, c in df.items()}
        self._idf_ausente = math.log((n + 0.5) / 0.5 + 1)        # una palabra que el corpus no tiene

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
        """Qué fracción de la masa IDF de las palabras de la consulta aparece en el fragmento (INV-40)."""
        terminos = set(palabras(consulta))
        i = next(n for n, f in enumerate(self.fragmentos) if f["id"] == fragmento_id)
        pesos = {p: self._idf.get(p, self._idf_ausente) for p in terminos}
        total = sum(pesos.values())
        return sum(w for p, w in pesos.items() if p in self._docs[i]) / total if total else 0.0

    def responde(self, consulta: str, k: int = 3, umbral_cobertura: float = UMBRAL_COBERTURA,
                 umbral_puntaje: float = UMBRAL_PUNTAJE) -> list[Encontrado]:
        """Los k mejores si el primero cubre la consulta y tiene puntaje suficiente (G5, INV-40); si no, ninguno:
        «no tengo esa información»."""
        encontrados = self.buscar(consulta, k)
        if not encontrados or encontrados[0].puntaje < umbral_puntaje or \
                self.cobertura(consulta, encontrados[0].fragmento["id"]) < umbral_cobertura:
            return []
        return encontrados

    def buscar(self, consulta: str, k: int = 3) -> list[Encontrado]:
        terminos = palabras(consulta)
        if not terminos:
            return []
        puntajes = [(self.puntaje(terminos, i) * PESO_PARTE.get(f.get("parte", ""), 1.0), f["id"], i)
                     for i, f in enumerate(self.fragmentos)]
        mejores = sorted((x for x in puntajes if x[0] > 0), key=lambda x: (-x[0], x[1]))[:k]
        return [Encontrado(self.fragmentos[i], round(s, 4)) for s, _, i in mejores]
