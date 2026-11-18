"""El agente integrado no cambia sin querer. Decisión del 24-oct (holdout-3): el de INV-33 se comporta como el del
22-oct y todo lo nuevo queda detrás de interruptores apagados (MEJORAS=ninguna); su foto es `datos/agente_22oct.json`.
INV-40 cambia a propósito el esquema y el prompt (decisiones 1 a 4 de docs/INV-40-requerimientos.md); la foto vigente
es `datos/agente_inv40.json`, que se regenera con `python -m tests.test_agente_vigente` cuando un cambio es deliberado."""
import json
import sys
from pathlib import Path

from agente.mejoras import Mejoras
from agente.prompt import plantilla, prompt_sistema, quien
from core.config import Settings
from herramientas.catalogo import esquemas

ARCHIVO = Path(__file__).parent / "datos" / "agente_inv40.json"


def foto() -> dict:
    return {"esquemas": esquemas(), "plantilla_v2": plantilla("v2", "completo"), "plantilla_v2_corto": plantilla("v2", "corto"),
            "prompt_gerente": prompt_sistema(quien("gerente", None), "gerente", None, "v2", "completo")}


FOTO = json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.exists() else {}


def test_el_esquema_es_el_vigente():
    assert esquemas() == FOTO["esquemas"] and esquemas(Mejoras()) == FOTO["esquemas"]


def test_el_prompt_es_el_vigente():
    assert plantilla("v2", "completo") == FOTO["plantilla_v2"] and plantilla("v2", "corto") == FOTO["plantilla_v2_corto"]
    assert prompt_sistema(quien("gerente", None), "gerente", None, "v2", "completo") == FOTO["prompt_gerente"]


def test_sin_mejoras_por_defecto():
    assert Mejoras.desde_texto(Settings().MEJORAS) == Mejoras()


def test_con_catalogo_cambia():
    assert esquemas(Mejoras(catalogo=True)) != FOTO["esquemas"]
    assert prompt_sistema(quien("gerente", None), "gerente", None, "v2", "completo", catalogo=True) != FOTO["prompt_gerente"]


def test_los_campos_ocultos_se_rechazan(ctx):
    """INV-40: en traslados se muestran destino y origen; sucursal y dirección, las del 22-oct, se rechazan si el
    modelo las inventa. El periodo de las ventas se muestra siempre."""
    from agente.bucle import EjecutorCoreAPI
    e = EjecutorCoreAPI(ctx)
    p = e.preparar("recomendar_traslados", {"sucursal": "PRINCIPAL", "direccion": "hacia"})
    assert p.error.status == 422 and "no existen en recomendar_traslados" in p.error.mensaje and "destino" in p.error.mensaje
    assert e.preparar("recomendar_traslados", {"destino": "PRINCIPAL"}).error is None
    assert e.preparar("recomendar_traslados", {"destino": "BODEGA_CENTRAL"}).error.status == 422
    assert e.preparar("historial_ventas", {"periodo": "2025-11"}).error is None


if __name__ == "__main__":                       # regenera la foto vigente tras un cambio deliberado
    ARCHIVO.write_text(json.dumps(foto(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sys.exit(0)
