"""Holdout de INV-33: congelado (sha256), válido contra el catálogo, sin pesos, y los turnos previos (h-06)
llegan al modelo y cuentan como contexto para la fidelidad."""
import hashlib
import re

import pytest
from pydantic import ValidationError

from evaluacion import correr as correr_mod
from evaluacion.arnes import correr_pregunta
from evaluacion.calificacion import calificar
from evaluacion.conjunto import (
    DIRECTORIO,
    Pregunta,
    cargar,
    errores_contra_catalogo,
    herramientas,
)
from evaluacion.privacidad import tiene_pesos
from tests.test_arnes import LLMGuion, respuesta

H = cargar(version="holdout")
ARCHIVO = DIRECTORIO / "holdout" / "preguntas.json"


def test_congelado():
    """Regla 1 del LEEME: el archivo no cambia después de medir."""
    leeme = (DIRECTORIO / "holdout" / "LEEME.md").read_text(encoding="utf-8")
    registrado = re.search(r"sha256 del archivo \| `([0-9a-f]{64})`", leeme).group(1)
    assert hashlib.sha256(ARCHIVO.read_bytes()).hexdigest() == registrado


def test_cobertura_y_catalogo():
    assert len(H.preguntas) == 15 and len({p.id for p in H.preguntas}) == 15
    assert {p.rol for p in H.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert {p.bloque for p in H.preguntas} == set("ABCDEF")
    assert not any(p.pendiente for p in H.preguntas)
    assert errores_contra_catalogo(H, herramientas(version="holdout")) == []
    # Solo datos reales: cada pregunta con herramientas trae sus hechos reales o se revisa a mano (nota)
    assert all(p.nota for p in H.preguntas)


def test_sin_pesos():
    assert not tiene_pesos(ARCHIVO.read_text(encoding="utf-8"))


def test_turnos_previos():
    p = H.por_id("h-06")
    assert [m["role"] for m in p.mensajes()] == ["user", "assistant", "user"]
    assert p.mensajes()[-1]["content"] == p.pregunta
    with pytest.raises(ValidationError, match="terminan con el agente"):
        Pregunta(**{**p.model_dump(), "turnos_previos": [{"rol": "usuario", "texto": "hola"}]})


async def test_los_turnos_previos_llegan_al_modelo():
    p = H.por_id("h-06")
    llm = LLMGuion([respuesta(llamadas=[("consultar_inventario", {"producto": "cerveza aguila", "sucursal": "PRINCIPAL"})]),
                    respuesta("En PRINCIPAL hay 264 y 68 unidades, frente a 96 y 8 en LA 21.")])

    class Ejecutor:
        catalogo = herramientas(version="holdout")

        def preparar(self, nombre, argumentos):
            from agente.bucle import Preparada
            return Preparada(nombre, argumentos, params=argumentos, etiqueta=nombre)

        async def ejecutar(self, preparada):
            from herramientas.base import Resultado
            return Resultado(para_modelo={"fecha_dato": "2025-12-31", "filas": [{"stock": "264 unidades"}, {"stock": "68 unidades"}]})

    c = await correr_pregunta(llm, p, Ejecutor.catalogo, H.fecha_datos, ejecutor=Ejecutor(), prompt="sistema")
    enviados = llm.recibidos[0][0]
    assert [m["role"] for m in enviados] == ["system", "user", "assistant", "user"]
    assert "96 unidades" in enviados[2]["content"]
    # 96 y 8 vienen del turno anterior del agente: no son cifras sin respaldo
    assert c.calificacion["fidelidad"] and c.calificacion["acierto"]


def test_el_turno_previo_es_contexto_de_la_fidelidad():
    p = H.por_id("h-06")
    sin_turnos = p.model_copy(update={"turnos_previos": []})
    texto = "En LA 21 había 96."
    assert calificar(p, [], False, [], texto).fidelidad
    assert not calificar(sin_turnos, [], False, [], texto).fidelidad


def test_solo_contra_el_core_api():
    with pytest.raises(SystemExit, match="--core-api"):
        correr_mod.main(["--modelo", "qwen3:8b", "--conjunto", "holdout", "--corridas", "1"])
