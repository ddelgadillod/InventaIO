"""Holdout-2 de INV-33: congelado (sha256 del conjunto y del preregistro), válido contra el catálogo, sin pesos, y la
traducción de los traslados en las dos direcciones (la línea base usa sucursal y dirección)."""
import hashlib
import re

from evaluacion.conjunto import (
    DIRECTORIO,
    Esperado,
    cargar,
    coincide,
    errores_contra_catalogo,
    herramientas,
)
from evaluacion.privacidad import tiene_pesos

H = cargar(version="holdout-2")
CARPETA = DIRECTORIO / "holdout-2"


def _registrado(fila: str) -> str:
    return re.search(rf"{fila} \| `([0-9a-f]{{64}})`", (CARPETA / "LEEME.md").read_text(encoding="utf-8")).group(1)


def test_congelado_con_su_preregistro():
    assert hashlib.sha256((CARPETA / "preguntas.json").read_bytes()).hexdigest() == _registrado("sha256 del archivo")
    preregistro = (CARPETA / "PREREGISTRO.md").read_text(encoding="utf-8")
    assert "ANTES de abrir" in preregistro and "Adenda 2" in preregistro and "4e6bca4" in preregistro


def test_cobertura_y_catalogo():
    assert len(H.preguntas) == 15 and len({p.id for p in H.preguntas}) == 15
    assert {p.bloque for p in H.preguntas} == set("ABCDEF") and {p.rol for p in H.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert errores_contra_catalogo(H, herramientas(version="holdout-2")) == [] and all(p.nota for p in H.preguntas)
    assert not tiene_pesos((CARPETA / "preguntas.json").read_text(encoding="utf-8"))
    assert H.por_id("h2-07").turnos_previos[-1].texto.startswith("En LA 21 se vendieron 1.960")


def test_traslados_en_las_dos_direcciones():
    nuevo = Esperado(herramienta="recomendar_traslados", argumentos={"destino": "GLORIETA"}, opcionales={"categoria": "*"})
    assert coincide(nuevo, "recomendar_traslados", {"sucursal": "GLORIETA", "direccion": "hacia", "categoria": "Aseo hogar"})
    assert not coincide(nuevo, "recomendar_traslados", {"sucursal": "GLORIETA", "direccion": "desde"})
    assert not coincide(nuevo, "recomendar_traslados", {"sucursal": "GLORIETA"})             # sin dirección eran las dos
