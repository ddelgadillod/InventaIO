"""INV-40: los conjuntos nuevos (casos de la historia, guía y abstención) y los criterios de calificación que
agregan: abstenerse y citar la sección de la guía (decisión 7 de docs/INV-40-requerimientos.md)."""
import pytest

from evaluacion.calificacion import calificar, cita_seccion, se_abstiene
from evaluacion.conjunto import cargar, errores_contra_catalogo
from evaluacion.correr import CONJUNTOS_INV40
from herramientas.catalogo import esquemas


@pytest.mark.parametrize("version", CONJUNTOS_INV40)
def test_validan_contra_el_catalogo(version):
    assert errores_contra_catalogo(cargar("local", version), esquemas()) == []


def test_tamanos_de_la_ficha():
    """Criterios 3, 5 y 7: un caso por hallazgo, al menos 30 de la guía y 15 de abstención, con los tres roles."""
    inv40, guia, abst = cargar("local", "inv40"), cargar("local", "guia"), cargar("local", "abstencion")
    notas = " ".join(p.nota or "" for p in inv40.preguntas)
    assert all(h in notas for h in ("H12", "H13", "H14", "H15", "INV-77"))
    assert len(guia.preguntas) >= 30 and all(p.seccion_esperada for p in guia.preguntas)
    assert len(abst.preguntas) >= 15 and all(p.sin_respuesta and p.rechazo for p in abst.preguntas)
    for c in (inv40, guia, abst):
        assert {p.rol for p in c.preguntas} == {"gerente", "admin_bodega", "admin_sucursal"}
    assert {e.herramienta for p in inv40.preguntas for e in p.esperado} >= {"productos_mas_vendidos", "historial_ventas",
                                                                             "recomendar_traslados", "listar_alertas"}


def test_desarrollo_y_aceptacion_no_se_mezclan():
    for a, d in (("guia", "guia-dev"), ("abstencion", "abstencion-dev")):
        aceptacion = {p.pregunta for p in cargar("local", a).preguntas}
        assert not aceptacion & {p.pregunta for p in cargar("local", d).preguntas}


@pytest.mark.parametrize(("texto", "esperado"), [
    ("No tengo esa información en el sistema.", True),
    ("Eso está fuera de lo que puedo consultar: inventario, ventas…", True),
    ("No hay datos para esa pregunta en el sistema.", True),
    ("El dólar está a 4.000 pesos.", False),
])
def test_se_abstiene(texto, esperado):
    assert se_abstiene(texto) is esperado


@pytest.mark.parametrize(("texto", "esperado"), [
    ("Se exporta con el botón «Exportar CSV» (Guía de uso, 12.7 Recomendaciones).", True),
    ("Ver la sección 12.7.", True),
    ("Ver la sección 12.70.", False),
    ("Ver la sección 112.7.", False),
    ("Con el botón «Exportar CSV».", False),
])
def test_cita_seccion(texto, esperado):
    assert cita_seccion(texto, ["12.7"]) is esperado


def test_calificar_abstencion_y_cita():
    abst = cargar("local", "abstencion").por_id("abs-01")
    bien = calificar(abst, [("buscar_en_glosario", {"consulta": "dólar"})], True, [{"resultado": "sin_resultados"}],
                     "No tengo esa información: no está en los datos del sistema.")
    mal = calificar(abst, [], False, [], "El dólar está estable esta semana.")
    assert bien.acierto and bien.herramienta and not mal.acierto and not mal.abstiene
    guia = cargar("local", "guia").por_id("guia-24")
    llamada = [("buscar_en_glosario", {"consulta": "descargar compras excel"})]
    # La herramienta trae la sección en la fuente: así el número citado tiene respaldo para el verificador
    encontrado = [{"resultado": "encontrado", "fragmentos": [{"fuente": "Guía de uso, Parte II, 12.7 Recomendaciones"}]}]
    cita = calificar(guia, llamada, True, encontrado, "Con «Exportar CSV» (Guía de uso, 12.7).")
    sin = calificar(guia, llamada, True, encontrado, "Con el botón «Exportar CSV».")
    assert cita.acierto and not sin.acierto and not sin.cita
