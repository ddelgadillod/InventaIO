"""
La huella del código del agente y los cambios entre dos versiones (INV-72, trazabilidad en MLflow).

- **Huella del código:** resume el código que decide las llamadas, la guarda de argumentos, el verificador y el
  análisis de ventas (`nlp_agent/agente` y `nlp_agent/herramientas`). Usa los ids de blob de git de cada archivo
  `.py`. Por eso da lo mismo desde el árbol de trabajo (al correr) que desde un commit (para las corridas viejas). Dos
  corridas con el mismo código tienen la misma huella aunque salgan de commits distintos.
- **Cambios:** los commits que tocaron el código, el prompt o el catálogo del agente entre dos commits, con los PR y
  las historias que nombran. Sale de git: nada se escribe a mano.

Sin git (la imagen del agente, un clon sin historia) devuelve None o una lista vacía, sin fallar.
"""
import hashlib
import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CODIGO_AGENTE = ("nlp_agent/agente", "nlp_agent/herramientas")
# Lo que cambia el comportamiento del agente: su código y sus prompts (el catálogo está en herramientas/)
CARPETAS_CAMBIOS = (*CODIGO_AGENTE, "nlp_agent/prompts")
HISTORIA = re.compile(r"\bINV-\d+\b")
PR = re.compile(r"(?:Merge pull request #|\(#)(\d+)")
MAX_COMMITS = 40                      # en la nota de una versión; el resto se cuenta


def _git(*args: str, raiz: Path = RAIZ, entrada: str | None = None) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, timeout=60, input=entrada)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _huella(pares: list[tuple[str, str]]) -> str:
    texto = "\n".join(f"{ruta} {blob}" for ruta, blob in sorted(pares))
    return hashlib.sha256(texto.encode()).hexdigest()[:12]


def huella_codigo(commit: str | None = None, raiz: Path = RAIZ, carpetas: tuple[str, ...] = CODIGO_AGENTE) -> str | None:
    """Sin commit: los `.py` que git sigue, con el contenido que tienen ahora. Con commit: los de ese commit."""
    if commit:
        salida = _git("ls-tree", "-r", commit, "--", *carpetas, raiz=raiz)
        if salida is None:
            return None
        pares = []
        for linea in salida.splitlines():
            info, ruta = linea.split("\t", 1)
            _, tipo, blob = info.split()
            if tipo == "blob" and ruta.endswith(".py"):
                pares.append((ruta, blob))
    else:
        listado = _git("ls-files", "--", *carpetas, raiz=raiz)
        if listado is None:
            return None
        rutas = [r for r in listado.splitlines() if r.endswith(".py") and (raiz / r).is_file()]
        blobs = _git("hash-object", "--stdin-paths", raiz=raiz, entrada="".join(f"{r}\n" for r in rutas)) if rutas else ""
        if blobs is None:
            return None
        pares = list(zip(rutas, blobs.split(), strict=True))
    return _huella(pares) if pares else None


def historias_de(*textos: str) -> list[str]:
    """Las historias de Jira que nombran los textos («INV-72»), ordenadas por número."""
    return sorted({h for t in textos for h in HISTORIA.findall(t or "")}, key=lambda h: int(h.split("-")[1]))


def prs_de(*textos: str) -> list[int]:
    return sorted({int(n) for t in textos for n in PR.findall(t or "")})


def cambios(desde: str | None, hasta: str, raiz: Path = RAIZ, carpetas: tuple[str, ...] = CARPETAS_CAMBIOS) -> dict:
    """Lo que cambió en el agente de `desde` a `hasta`: commits (sin los merges), PR integrados y historias.
    Sin `desde`, o si es el mismo commit, no hay rango: la lista queda vacía."""
    vacio = {"commits": [], "prs": [], "historias": [], "total": 0}
    if not desde or not hasta or desde == hasta:
        return vacio
    rango = f"{desde}..{hasta}"
    salida = _git("log", "--no-merges", "--format=%h%x1f%ad%x1f%s", "--date=short", rango, "--", *carpetas, raiz=raiz)
    if salida is None:
        return vacio
    commits = [dict(zip(("commit", "fecha", "asunto"), linea.split("\x1f", 2), strict=True))
               for linea in salida.splitlines() if linea.count("\x1f") == 2]
    # Los merges del rango que tocaron el agente traen el número del PR y la rama (que nombra la historia). Con
    # --first-parent cada merge se compara con la rama a la que entró; sin eso, git lo oculta al filtrar por carpeta
    merges = _git("log", "--first-parent", "--merges", "--format=%s", rango, "--", *carpetas, raiz=raiz) or ""
    textos = [c["asunto"] for c in commits] + merges.splitlines()
    return {"commits": commits, "prs": prs_de(*textos), "historias": historias_de(*textos), "total": len(commits)}


def nota_cambios(c: dict, desde: str | None, hasta: str) -> list[str]:
    """Las líneas en markdown de los cambios, para la nota de una versión."""
    if not desde:
        return ["**Cambios:** es la primera versión medida."]
    if not c["total"]:
        return [f"**Cambios:** ningún commit del agente entre `{desde[:7]}` y `{hasta[:7]}`; cambia la configuración."]
    lineas = [f"**Cambios desde `{desde[:7]}` hasta `{hasta[:7]}`:** {c['total']} commits del código o del prompt"
              + (f"; PR {', '.join(f'#{n}' for n in c['prs'])}" if c["prs"] else "")
              + (f"; historias {', '.join(c['historias'])}" if c["historias"] else "") + ".", ""]
    lineas += [f"- `{x['commit']}` {x['fecha']} {x['asunto']}" for x in c["commits"][:MAX_COMMITS]]
    if c["total"] > MAX_COMMITS:
        lineas.append(f"- … y {c['total'] - MAX_COMMITS} más (`git log {desde[:7]}..{hasta[:7]}`).")
    return lineas
