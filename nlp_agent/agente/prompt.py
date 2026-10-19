"""
Prompt de sistema con herramientas (INV-32, T15).

Es el del spike (`evaluacion/prompt_spike.md`), con el que se midió qwen3:8b,
con un cambio: la fecha de los datos ya no va fija en el prompt sino que la da
cada herramienta en `fecha_dato`. INV-33 escribe los prompts por rol, la
aclaración y los totales.
"""
from pathlib import Path

VERSION_PROMPT = "v1"
PLANTILLA = (Path(__file__).resolve().parent.parent / "prompts" / VERSION_PROMPT / "sistema.md").read_text(encoding="utf-8")
USUARIOS = {
    "gerente": "el gerente, que ve todas las sucursales y la Bodega Central",
    "admin_bodega": "el administrador de la Bodega Central",
    "admin_sucursal": "el administrador de la sucursal {sucursal}, que solo ve su sucursal",
}
DESCONOCIDO = "un usuario de InventAI/o"


def quien(rol: str | None, sucursal: str | None) -> str:
    return USUARIOS.get(rol or "", DESCONOCIDO).format(sucursal=sucursal)


def prompt_sistema(usuario: str) -> str:
    return PLANTILLA.format(usuario=usuario)
