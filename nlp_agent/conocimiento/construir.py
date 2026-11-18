"""
Parte `docs/GLOSARIO.md` y `docs/GUIA-USO.md` en fragmentos y escribe `conocimiento/corpus.json` (INV-31, G3;
INV-40, decisión 5).

    cd nlp_agent
    python -m conocimiento.construir              # reescribe el corpus
    python -m conocimiento.construir --verificar  # falla si el corpus no corresponde al documento

El documento es la fuente legible; el JSON es lo que va en la imagen del agente,
que se construye con el contexto `nlp_agent/` y no ve `docs/` (K3). Cada sección
`##` es un fragmento con id, título, parte (los encabezados `#`: «Parte I ·
Negocio», «Parte II · Pronóstico y modelos»), fuente y texto sin marcas de
Markdown. La salida es determinista: el mismo documento da el mismo archivo
(criterio 8).

INV-40 suma la guía de uso: cada `##` de `docs/GUIA-USO.md` es un fragmento con la parte «Guía de uso», su
sección de la guía en PDF (la que Vera cita) y su fecha. La fuente junta las dos, así el número de la sección
que cite la respuesta tiene respaldo en lo que trajo la herramienta.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DOCUMENTO = RAIZ / "docs" / "GLOSARIO.md"
GUIA = RAIZ / "docs" / "GUIA-USO.md"
PARTE_GUIA = "Guía de uso"
METADATOS_GUIA = re.compile(r"^\*\*(Sección|Fecha|También se dice)\.\*\*\s*(.+)$", re.MULTILINE)
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


def _secciones(markdown: str):
    """(parte, título, cuerpo) de cada `##`; la parte es el último encabezado `#` antes de la sección."""
    parte, titulo, cuerpo = "", None, []
    for linea in markdown.splitlines():
        if linea.startswith("# "):
            if titulo:
                yield parte, titulo, "\n".join(cuerpo)
                titulo, cuerpo = None, []
            parte = linea[2:].strip().split(" · ", 1)[-1]
        elif linea.startswith("## "):
            if titulo:
                yield parte, titulo, "\n".join(cuerpo)
            titulo, cuerpo = linea[3:].strip(), []
        elif titulo:
            cuerpo.append(linea)
    if titulo:
        yield parte, titulo, "\n".join(cuerpo)


def fragmentos(markdown: str) -> list[dict]:
    salida = []
    for parte, titulo, cuerpo in _secciones(markdown):
        fuente = re.search(r"\*\*Fuente\.\*\*\s*(.+)", cuerpo)
        tambien = re.search(r"\*\*También se dice\.\*\*\s*(.+)", cuerpo)
        salida.append({
            "id": slug(titulo),
            "titulo": titulo,
            "parte": parte,
            "fuente": f"Glosario · {parte + ' · ' if parte else ''}{titulo}"
                      + (f" ({_limpio(fuente.group(1)).rstrip('.')})" if fuente else ""),
            "tambien": _limpio(tambien.group(1)).rstrip(".") if tambien else "",
            "texto": _limpio(cuerpo),
        })
    ids = [f["id"] for f in salida]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Títulos repetidos en el glosario: {sorted(i for i in ids if ids.count(i) > 1)}")
    return salida


def fragmentos_guia(markdown: str) -> list[dict]:
    """Los de la guía de uso: título, sección, fecha y sinónimos; el texto, sin esas tres líneas."""
    salida = []
    for _, titulo, cuerpo in _secciones(markdown):
        datos = {k: v.strip() for k, v in METADATOS_GUIA.findall(cuerpo)}
        if "Sección" not in datos or "Fecha" not in datos:
            raise ValueError(f"La guía necesita «Sección» y «Fecha» en «{titulo}»")
        salida.append({
            "id": f"guia_{slug(titulo)}",
            "titulo": titulo,
            "parte": PARTE_GUIA,
            "seccion": datos["Sección"].rstrip("."),
            "fecha": datos["Fecha"].rstrip("."),
            "fuente": f"Guía de uso · {datos['Sección'].rstrip('.')} ({datos['Fecha'].rstrip('.')})",
            "tambien": _limpio(datos.get("También se dice", "")).rstrip("."),
            "texto": _limpio(METADATOS_GUIA.sub("", cuerpo)),
        })
    ids = [f["id"] for f in salida]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Títulos repetidos en la guía: {sorted(i for i in ids if ids.count(i) > 1)}")
    return salida


def corpus(markdown: str, guia: str | None = None) -> dict:
    """El glosario y, desde INV-40, la guía de uso. La huella cubre los dos documentos."""
    textos = markdown + (guia or "")
    return {
        "fuente": "docs/GLOSARIO.md" + (" y docs/GUIA-USO.md" if guia else ""),
        "huella": hashlib.sha256(textos.encode("utf-8")).hexdigest()[:12],
        "fragmentos": fragmentos(markdown) + (fragmentos_guia(guia) if guia else []),
    }


def serializar(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1) + "\n"


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--verificar", action="store_true", help="no escribe: falla si el corpus está desactualizado")
    args = a.parse_args(argv)
    esperado = serializar(corpus(DOCUMENTO.read_text(encoding="utf-8"), GUIA.read_text(encoding="utf-8")))
    if args.verificar:
        if not CORPUS.is_file() or CORPUS.read_text(encoding="utf-8") != esperado:
            print("conocimiento/corpus.json no corresponde a docs/GLOSARIO.md y docs/GUIA-USO.md: "
                  "corre python -m conocimiento.construir")
            return 1
        print("Corpus al día")
        return 0
    CORPUS.write_text(esperado, encoding="utf-8")
    print(f"{len(json.loads(esperado)['fragmentos'])} fragmentos en {CORPUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
