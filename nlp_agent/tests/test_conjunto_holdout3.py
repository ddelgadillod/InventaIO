"""Holdout-3 de INV-33: congelado (sha256 del conjunto y del preregistro), válido contra el catálogo y sin pesos."""
import hashlib
import re

from evaluacion.conjunto import (
    DIRECTORIO,
    cargar,
    errores_contra_catalogo,
    herramientas,
)
from evaluacion.privacidad import tiene_pesos

H = cargar(version="holdout-3")
CARPETA = DIRECTORIO / "holdout-3"


def _registrado(fila: str) -> str:
    return re.search(rf"{fila} \| `([0-9a-f]{{64}})`", (CARPETA / "LEEME.md").read_text(encoding="utf-8")).group(1)


def test_congelado_con_su_preregistro():
    assert hashlib.sha256((CARPETA / "preguntas.json").read_bytes()).hexdigest() == _registrado("sha256 del archivo")
    preregistro = (CARPETA / "PREREGISTRO.md").read_text(encoding="utf-8")
    assert "ANTES de medir" in preregistro and "Código congelado en 42172fa" in preregistro


def test_cobertura_y_catalogo():
    assert len(H.preguntas) == 15 and len({p.id for p in H.preguntas}) == 15
    assert {p.bloque for p in H.preguntas} == set("ABCDEF") and {p.rol for p in H.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert errores_contra_catalogo(H, herramientas(version="holdout-3")) == [] and all(p.nota for p in H.preguntas)
    assert not tiene_pesos((CARPETA / "preguntas.json").read_text(encoding="utf-8"))
    assert H.por_id("h3-06").turnos_previos[-1].texto == "En PRINCIPAL tienes 66 unidades de Lenteja Su Despensa 460 g."
