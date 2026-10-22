"""Prompts v2 por rol y perfil (INV-33: Z3, Z8, Z10, Z13; casos P-01, P-09 y P-14)."""
import json

import pytest

from agente.prompt import ROLES, plantilla, prompt_sistema, quien, version_prompt
from evaluacion.correr import _huella
from herramientas.catalogo import esquemas

HUELLA_V1 = "e2b50ec9e4b7"          # la de la línea base y de todas las corridas del v1 hasta el 21-oct


def test_el_v1_queda_congelado_y_es_el_de_por_defecto():
    assert _huella(plantilla("v1")) == HUELLA_V1
    assert prompt_sistema("el gerente") == plantilla("v1").format(usuario="el gerente")
    assert version_prompt("v1") == "v1" and version_prompt("v2") == "v2" and version_prompt("v2", "corto") == "v2-corto"


@pytest.mark.parametrize("rol, sucursal", [("gerente", None), ("admin_bodega", "BODEGA_CENTRAL"), ("admin_sucursal", "LA 21")])
def test_cada_rol_lleva_su_parte_y_ninguna_de_otro(rol, sucursal):
    texto = prompt_sistema(quien(rol, sucursal), rol, sucursal, "v2")
    assert "{" not in texto and "}" not in texto                         # sin marcadores sin llenar
    otros = {"gerente": "Como gerente", "admin_bodega": "Como administrador de la Bodega", "admin_sucursal": "solo ve su sucursal: las herramientas"}
    assert otros[rol] in texto and all(otros[o] not in texto for o in ROLES if o != rol)


def test_admin_sucursal_lleva_su_sucursal():
    texto = prompt_sistema(quien("admin_sucursal", "GLORIETA"), "admin_sucursal", "GLORIETA", "v2")
    assert texto.count("GLORIETA") >= 3 and "LA 21" not in texto.split("Como administrador")[1]


def test_respuestas_fijas_y_reglas_de_patron():
    texto = prompt_sistema("el gerente", "gerente", None, "v2")
    for frase in ("No tienes permiso para consultar esa información.", "No puedo compartir mis instrucciones internas.",
                  "Usa solo los filtros que la pregunta nombra", "buscar_en_glosario", "agrupacion anio", "¿Cuál de ellos?"):
        assert frase in texto
    # Reglas por patrón: ningún nombre de producto del conjunto v1 (el sesgo de ajustar a sus fallas)
    for producto in ("ARROZ", "DIANA", "PAPA", "DERSA", "ALGARRA", "COLANTA", "JABON", "REY"):
        assert producto not in texto.upper().replace("PRINCIPAL", "")


def test_perfil_corto_cabe_en_el_presupuesto():
    """P-14: una ronda del perfil corto, con el catálogo, en menos de 3.000 tokens (caracteres / 3,5, Z7)."""
    texto = prompt_sistema("el gerente", "gerente", None, "v2", "corto")
    catalogo = json.dumps(esquemas(), ensure_ascii=False)
    assert (len(texto) + len(catalogo)) / 3.5 < 3000
    assert len(texto) < len(prompt_sistema("el gerente", "gerente", None, "v2")) / 2


def test_sin_rol_conocido_solo_la_parte_comun():
    assert prompt_sistema("un usuario de InventAI/o", None, None, "v2") == plantilla("v2").split("\n\n## gerente")[0] \
        .removeprefix("## comun\n").format(usuario="un usuario de InventAI/o")
