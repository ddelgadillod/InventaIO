"""
Parte `docs/GLOSARIO-NEGOCIO.md` en fragmentos y escribe `conocimiento/corpus.json` (INV-31, G3).

    cd nlp_agent
    python -m conocimiento.construir              # reescribe el corpus
    python -m conocimiento.construir --verificar  # falla si el corpus no corresponde al documento

El documento es la fuente legible; el JSON es lo que va en la imagen del agente,
que se construye con el contexto `nlp_agent/` y no ve `docs/` (K3). Cada sección
`##` es un fragmento con id, título, fuente y texto sin marcas de Markdown. La
salida es determinista: el mismo documento da el mismo archivo (criterio 8).
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DOCUMENTO = RAIZ / "docs" / "GLOSARIO-NEGOCIO.md"
CORPUS = Path(__file__).resolve().parent / "corpus.json"


def slug(titulo: str) -> str:
    texto = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def _limpio(markdown: str) -> str:
    """Sin negritas ni código, con viñetas como líneas; el modelo lee texto plano."""
    texto = re.sub(r"\*\*(.+?)\*\*", r"\1", markdown)
    texto = re.sub(r"`([^`]+)`", r"\1", texto)
    texto = re.sub(r"^\s*-\s+", "- ", texto, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def fragmentos(markdown: str) -> list[dict]:
    secciones = re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]
    salida = []
    for seccion in secciones:
        titulo, _, cuerpo = seccion.partition("\n")
        titulo = titulo.strip()
        fuente = re.search(r"\*\*Fuente\.\*\*\s*(.+)", cuerpo)
        tambien = re.search(r"\*\*También se dice\.\*\*\s*(.+)", cuerpo)
        salida.append({
            "id": slug(titulo),
            "titulo": titulo,
            "fuente": f"Glosario de negocio · {titulo}" + (f" ({_limpio(fuente.group(1)).rstrip('.')})" if fuente else ""),
            "tambien": _limpio(tambien.group(1)).rstrip(".") if tambien else "",
            "texto": _limpio(cuerpo),
        })
    ids = [f["id"] for f in salida]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Títulos repetidos en el glosario: {sorted(i for i in ids if ids.count(i) > 1)}")
    return salida


def corpus(markdown: str) -> dict:
    return {
        "fuente": "docs/GLOSARIO-NEGOCIO.md",
        "huella": hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:12],
        "fragmentos": fragmentos(markdown),
    }


def serializar(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1) + "\n"


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--verificar", action="store_true", help="no escribe: falla si el corpus está desactualizado")
    args = a.parse_args(argv)
    esperado = serializar(corpus(DOCUMENTO.read_text(encoding="utf-8")))
    if args.verificar:
        if not CORPUS.is_file() or CORPUS.read_text(encoding="utf-8") != esperado:
            print("conocimiento/corpus.json no corresponde a docs/GLOSARIO-NEGOCIO.md: corre python -m conocimiento.construir")
            return 1
        print("Corpus al día")
        return 0
    CORPUS.write_text(esperado, encoding="utf-8")
    print(f"{len(json.loads(esperado)['fragmentos'])} fragmentos en {CORPUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
