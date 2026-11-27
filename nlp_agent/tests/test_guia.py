"""INV-40: el corpus de la guía de uso (docs/GUIA-USO.md). Criterio 5: hit@3 de al menos 0,9 en las preguntas
de aceptación; criterio 6 y DoD 5: cada fragmento con sección, fecha y fuente, sin nombres del negocio y con
números que solo son reglas del sistema, comparadas aquí con el código."""
import json
import re
from pathlib import Path

import pytest

from conocimiento import construir
from conocimiento.bm25 import Indice
from evaluacion.conjunto import cargar

RAIZ = Path(__file__).resolve().parents[2]
GUIA = (RAIZ / "docs" / "GUIA-USO.md").read_text(encoding="utf-8")
FRAGMENTOS = construir.fragmentos_guia(GUIA)
INDICE = Indice.desde_archivo()
NUMERO = re.compile(r"(?<![\w.,])\d{1,3}(?:\.\d{3})+(?![\w])|(?<![\w.,])\d+(?:,\d+)?(?![\w])")


def _seccion(fragmento: dict) -> str | None:
    m = re.search(r"(\d+\.\d+)", fragmento.get("seccion", ""))
    return m.group(1) if m else None


def hit3(version: str) -> tuple[int, int]:
    preguntas = cargar("local", version).preguntas
    aciertos = sum(any(_seccion(e.fragmento) in p.seccion_esperada for e in INDICE.responde(p.pregunta))
                   for p in preguntas)
    return aciertos, len(preguntas)


def test_corpus_con_la_guia_y_metadatos():
    corpus = json.loads((RAIZ / "nlp_agent" / "conocimiento" / "corpus.json").read_text(encoding="utf-8"))
    guia = [f for f in corpus["fragmentos"] if f["parte"] == "Guía de uso"]
    assert len(guia) == len(FRAGMENTOS) >= 50
    for f in guia:
        assert f["id"].startswith("guia_") and _seccion(f) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f["fecha"])
        assert _seccion(f) in f["fuente"] and f["fecha"] in f["fuente"] and f["tambien"] and f["texto"]
        assert "Sección." not in f["texto"] and "También se dice." not in f["texto"]


def test_sin_nombres_del_negocio():
    """Ni sucursales, ni personas ni correos de los usuarios de prueba (api/scripts/seed_usuarios.py)."""
    semilla = (RAIZ / "api" / "scripts" / "seed_usuarios.py").read_text(encoding="utf-8")
    sucursales = set(re.findall(r'"admin_sucursal", "([^"]+)"', semilla))
    personas = set(re.findall(r'@inventaio\.co", "([^"]+)"', semilla))
    assert sucursales and personas
    texto = " ".join(f["titulo"] + " " + f["tambien"] + " " + f["texto"] for f in FRAGMENTOS)
    # Las sucursales se escriben en mayúsculas en el sistema («PRINCIPAL»); «pantalla principal» es otra cosa
    for nombre in sucursales:
        assert not re.search(rf"\b{re.escape(nombre)}\b", texto), nombre
    for nombre in personas:
        assert not re.search(rf"\b{re.escape(nombre)}\b", texto, re.IGNORECASE), nombre
    assert "@" not in texto and "admin123" not in texto


def _reglas_del_codigo() -> dict[float, str]:
    """Los únicos números permitidos en la guía, leídos del código: cada uno con la regla de donde sale."""
    leer = lambda ruta: (RAIZ / ruta).read_text(encoding="utf-8")  # noqa: E731
    inventario, etl = leer("api/schemas/inventario.py"), leer("etl_real/config.py")
    compras = json.loads(leer("ml_service/compras/politicas_inv21.json"))
    traslados = json.loads(leer("ml_service/transferencias/politicas_inv22.json"))
    modelo = json.loads(leer("models/nivel1_parametros_features.json"))
    numero = lambda patron, texto: float(re.search(patron, texto, re.MULTILINE).group(1))  # noqa: E731
    reglas = {
        numero(r"SEMAFORO_OK_MIN = ([\d.]+)", inventario): "semáforo: OK desde",
        numero(r"SEMAFORO_BAJO_MIN = ([\d.]+)", inventario): "semáforo: bajo desde",
        numero(r'"dias_stock_maximo": (\d+)', etl): "stock máximo en días",
        float(compras["urgencia"]["urgente_dias"]): "urgente hasta",
        float(compras["urgencia"]["alta_dias"]): "alta hasta",
        float(compras["lead_time_dias"]): "plazo del proveedor",
        float(traslados["traslado"]["dias_habiles_si_no_hay_dias_fijos"]): "llegada del traslado",
        float(modelo["min_frecuencia_as_of"]): "días con venta para tener pronóstico",
        numero(r"new_password: str = Field\(\.\.\., min_length=(\d+)", leer("api/schemas/auth.py")): "largo de la clave",
        numero(r"^MAX_FILAS = (\d+)", leer("nlp_agent/herramientas/base.py")): "filas de Vera",
        numero(r"MAX_CARACTERES_MENSAJE: int = (\d+)", leer("nlp_agent/core/config.py")): "caracteres por mensaje",
        numero(r'^HORIZONTE = "(\d+) días hábiles"', leer("nlp_agent/herramientas/catalogo.py")): "horizonte",
        numero(r"^FACTOR_COSTO_IMPOSIBLE = ([\d.]+)", leer("etl_real/montos.py")): "costo imposible (INV-82)",
    }
    for d in compras["calendario_pedidos"]["quincenal"]["dias_mes"]:
        reglas[float(d)] = "pedido quincenal"
    reglas[numero(r'"dias_stock_minimo": (\d+)', etl)] = "stock mínimo en días"
    reglas[numero(r'"dias_punto_reorden": (\d+)', etl)] = "punto de reorden en días"
    return reglas


def test_los_numeros_de_la_guia_son_reglas_del_codigo():
    reglas = _reglas_del_codigo()
    for f in FRAGMENTOS:
        texto = re.sub(r"^\d+\. ", "", f["texto"], flags=re.MULTILINE)      # sin los números de una lista
        for n in NUMERO.findall(texto):
            assert float(n.replace(".", "").replace(",", ".")) in reglas, (f["titulo"], n)


@pytest.mark.parametrize(("version", "minimo"), [("guia", 0.9), ("guia-dev", 0.9)])
def test_hit3_de_la_guia(version, minimo):
    """Criterio 5. La aceptación (guia) se midió una vez el 18-nov: 31/35 antes de la ronda declarada y 33/35
    después (contaminada: la confirmación limpia es el conjunto guia-holdout del usuario)."""
    aciertos, total = hit3(version)
    assert aciertos / total >= minimo


def test_la_regla_de_numeros_detecta_un_cambio():
    """Si la guía dijera un número que no es una regla del código, la prueba falla."""
    reglas = _reglas_del_codigo()
    assert 4.0 not in reglas and 15.0 in reglas and 2000.0 in reglas


async def test_la_herramienta_trae_la_seccion_de_la_guia(ctx):
    from herramientas.catalogo import POR_NOMBRE
    h = POR_NOMBRE["buscar_en_glosario"]
    r = (await h.ejecutar(ctx, h.validar({"consulta": "cómo descargo las compras en CSV para Excel"}))).para_modelo
    guia = [f for f in r["fragmentos"] if f["id"].startswith("guia_")]
    assert guia and "Guía de uso · Parte II · 12.7" in guia[0]["fuente"] and "sección" in r["indicacion"]
    nada = (await h.ejecutar(ctx, h.validar({"consulta": "precio del dólar hoy"}))).para_modelo
    assert nada["resultado"] == "sin_resultados"
