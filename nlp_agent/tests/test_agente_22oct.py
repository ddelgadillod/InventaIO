"""Decisión del 24-oct (holdout-3): el agente que se integra con INV-33 se comporta como el del 22-oct; todo lo nuevo
queda detrás de interruptores apagados (MEJORAS=ninguna). La foto `datos/agente_22oct.json` se tomó del commit f652559
(el esquema, las plantillas del prompt v2 y el prompt de un rol) y estas pruebas fallan si algo la cambia sin interruptor."""
import json
from pathlib import Path

from agente.mejoras import Mejoras
from agente.prompt import plantilla, prompt_sistema, quien
from core.config import Settings
from herramientas.catalogo import esquemas

FOTO = json.loads((Path(__file__).parent / "datos" / "agente_22oct.json").read_text(encoding="utf-8"))


def test_el_esquema_es_el_del_22oct():
    assert esquemas() == FOTO["esquemas"] and esquemas(Mejoras()) == FOTO["esquemas"]


def test_el_prompt_es_el_del_22oct():
    assert plantilla("v2", "completo") == FOTO["plantilla_v2"] and plantilla("v2", "corto") == FOTO["plantilla_v2_corto"]
    assert prompt_sistema(quien("gerente", None), "gerente", None, "v2", "completo") == FOTO["prompt_gerente"]


def test_sin_mejoras_por_defecto():
    assert Mejoras.desde_texto(Settings().MEJORAS) == Mejoras()


def test_con_catalogo_cambia():
    assert esquemas(Mejoras(catalogo=True)) != FOTO["esquemas"]
    assert prompt_sistema(quien("gerente", None), "gerente", None, "v2", "completo", catalogo=True) != FOTO["prompt_gerente"]


def test_los_campos_ocultos_se_rechazan_como_el_22oct(ctx):
    from agente.bucle import EjecutorCoreAPI
    e = EjecutorCoreAPI(ctx)
    p = e.preparar("recomendar_traslados", {"destino": "PRINCIPAL"})
    assert p.error.status == 422 and "«destino» no existe en recomendar_traslados; válidos: sucursal, direccion" in p.error.mensaje
    assert e.preparar("historial_ventas", {"periodo": "2025-11"}).error.status == 422
    assert e.preparar("recomendar_traslados", {"sucursal": "PRINCIPAL", "direccion": "hacia"}).error is None
    ctx.mejoras = Mejoras(catalogo=True, periodo=True)
    con = EjecutorCoreAPI(ctx)
    assert con.preparar("recomendar_traslados", {"destino": "PRINCIPAL"}).error is None
    assert con.preparar("historial_ventas", {"periodo": "2025-11"}).error is None
