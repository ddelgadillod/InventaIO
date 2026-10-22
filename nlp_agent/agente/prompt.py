"""
Prompt de sistema (INV-32, T15; INV-33, decisiones Z3, Z8, Z10 y Z13).

- `prompts/v1/sistema.md`: el de INV-32, congelado. Es la línea base del v1 y el que corre por defecto hasta que
  el v2 se mida.
- `prompts/v2/`: una parte común (`comun.md`) y una por rol (`gerente.md`, `admin_bodega.md`, `admin_sucursal.md`),
  o la versión condensada (`corto.md`) con el perfil corto para CPU.

`PROMPT_VERSION` (v1 | v2) y `PERFIL_PROMPT` (completo | corto) se leen del entorno y no de `core/config.py`
mientras INV-36, que cambia ese archivo, no esté en develop. La fecha de los datos no va en el prompt: la da cada
herramienta en `fecha_dato`.
"""
import os
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
VERSION = os.environ.get("PROMPT_VERSION", "v1")
PERFIL = os.environ.get("PERFIL_PROMPT", "completo")
ROLES = ("gerente", "admin_bodega", "admin_sucursal")
USUARIOS = {
    "gerente": "el gerente, que ve todas las sucursales y la Bodega Central",
    "admin_bodega": "el administrador de la Bodega Central",
    "admin_sucursal": "el administrador de la sucursal {sucursal}, que solo ve su sucursal",
}
DESCONOCIDO = "un usuario de InventAI/o"


def _leer(version: str, nombre: str) -> str:
    return (PROMPTS / version / nombre).read_text(encoding="utf-8")


def partes(version: str = VERSION, perfil: str = PERFIL) -> dict[str, str]:
    """Los archivos del prompt: el único del v1; en el v2, la parte común (o la corta) y la de cada rol."""
    if version == "v1":
        return {"sistema": _leer("v1", "sistema.md")}
    if perfil == "corto":
        return {"corto": _leer("v2", "corto.md").strip()}
    return {"comun": _leer("v2", "comun.md").strip(), **{rol: _leer("v2", f"{rol}.md").strip() for rol in ROLES}}


def plantilla(version: str = VERSION, perfil: str = PERFIL) -> str:
    """Todo el prompt en un texto: lo que se registra en MLflow y de donde sale su huella. El del v1 es su archivo."""
    p = partes(version, perfil)
    if version == "v1":
        return p["sistema"]
    return "\n\n".join(f"## {nombre}\n{texto}" for nombre, texto in p.items())


def version_prompt(version: str = VERSION, perfil: str = PERFIL) -> str:
    """Lo que va en `meta.version_prompt`: v1, v2 o v2-corto."""
    return version if version == "v1" or perfil == "completo" else f"{version}-{perfil}"


VERSION_PROMPT = version_prompt()
PLANTILLA = plantilla()


def quien(rol: str | None, sucursal: str | None) -> str:
    return USUARIOS.get(rol or "", DESCONOCIDO).format(sucursal=sucursal)


def prompt_sistema(usuario: str, rol: str | None = None, sucursal: str | None = None, version: str = VERSION,
                   perfil: str = PERFIL) -> str:
    """El prompt del usuario. En el v2, la parte común más la de su rol, si se sabe (el chat de INV-36 todavía
    pasa solo `usuario`); el perfil corto no tiene partes por rol."""
    p = partes(version, perfil)
    if version == "v1":
        return p["sistema"].format(usuario=usuario)
    if perfil == "corto":
        return p["corto"].format(usuario=usuario)
    texto = p["comun"].format(usuario=usuario)
    if rol in ROLES:
        texto += "\n\n" + p[rol].format(sucursal=sucursal or "su sucursal")
    return texto
