"""
Construye el conjunto v1 (INV-31, criterios 6 y 10) desde `conjuntos/v1/fuente.json`.

    cd nlp_agent
    INVENTAIO_CLAVE_PRUEBA=… python -m evaluacion.construir_v1 --core-api http://localhost:8000

La fuente tiene lo que se congela: las preguntas del usuario, las llamadas
esperadas y los criterios. Lo que depende de los datos lo arma este script:

- corre cada `llamadas` de la fuente con las herramientas reales del catálogo
  (INV-32), contra el Core API y con el usuario de prueba del rol;
- `resultados`: esas respuestas con las cantidades escaladas por un factor de
  cada pregunta (sintéticas, N9) y las fechas como `{fecha±n}`, para que la
  variante colab no lleve cifras ni fechas reales;
- `hechos_clave` y `hechos_alguno`: las referencias `@n:ruta` de la fuente
  (llamada n, campo ruta: `filas.0.stock`, `global.total`) leídas en los
  resultados sintéticos; `hechos_reales` y `hechos_alguno_reales`, las mismas
  en los reales (los datos están congelados al 31-dic-2025).

Las preguntas `pendiente` (herramientas que todavía no existen) se arman sin
resultados; se vuelven a construir cuando la herramienta llegue. El script es
determinista: con la misma bodega da el mismo archivo.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from evaluacion.conjunto import DIRECTORIO, MESES, Conjunto
from herramientas.formato import texto_numero

FUENTE = DIRECTORIO / "v1" / "fuente.json"
DESTINO = DIRECTORIO / "v1" / "preguntas.json"
FECHA = "2025-12-31"
# Campos que no son cantidades: nombres, códigos, textos del sistema
SIN_ESCALAR = {"producto", "nombre", "codigo", "categoria", "sucursal", "origen", "destino", "tipo", "urgencia",
               "semaforo", "busqueda", "indicacion", "horizonte", "periodo", "unidad", "resultado", "mensaje", "status",
               "mostrando", "filtro", "nota", "nota_bodega"}
UMBRAL = 10                      # 0 a 10 no se escalan: conteos, «mostrando», días cortos (como la calificación)
FECHA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
# Un número como lo escribe la app (1.234,5), sin tocar los que van pegados a letras («P626», «*500GR»)
NUMERO = re.compile(r"(?<![\w.,])-?\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\w])|(?<![\w.,])-?\d+(?:,\d+)?(?![\w])")
HORIZONTE = re.compile(r"(?<![\d,])15 días hábiles")
REFERENCIA = re.compile(r"^@(\d+):(.+)$")
FECHA_ESCRITA = re.compile(r"\b(\d{1,2}) de (" + "|".join(MESES) + r") de (\d{4})\b")

Ejecutar = Callable[[str, str | None, str, dict], Awaitable[dict]]


def factor(id_: str) -> Decimal:
    """De 1,20 a 1,59, fijo por pregunta: las cantidades sintéticas no son las reales pero conservan su escala."""
    return Decimal(120 + int(hashlib.sha256(id_.encode()).hexdigest(), 16) % 40) / 100


def _escalado(valor: Decimal, k: Decimal, decimales: int) -> Decimal:
    """La misma regla de redondeo de la app (empates lejos de 0), para que «total» y «conteo» coincidan."""
    return (valor * k).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def _escalar_numero(texto: str, k: Decimal) -> str:
    entero, _, decimales = texto.replace(".", "").partition(",")
    valor = Decimal(f"{entero}.{decimales}" if decimales else entero)
    if abs(valor) <= UMBRAL:
        return texto
    return texto_numero(_escalado(valor, k, len(decimales)), len(decimales))


def _relativa(d: date, forma: str = "") -> str:
    dias = (d - date.fromisoformat(FECHA)).days
    return "{fecha" + (f"{dias:+d}" if dias else "") + forma + "}"


def _fecha_relativa(m: re.Match) -> str:
    return _relativa(date.fromisoformat(m.group()))


def _fechas_escritas(texto: str) -> str:
    """«31 de diciembre de 2025» → {fecha:texto}: en Colab la fecha escrita también se mueve (N9)."""
    return FECHA_ESCRITA.sub(lambda m: _relativa(date(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1))),
                                                 ":texto"), texto)


def _escalar_texto(texto: str, k: Decimal) -> str:
    # Las fechas y el horizonte («15 días hábiles») se apartan antes de escalar
    apartados: list[str] = []

    def apartar(m: re.Match) -> str:
        apartados.append(m.group())
        return chr(0xE000 + len(apartados) - 1)          # un carácter de uso privado: no es dígito ni letra

    texto = HORIZONTE.sub(apartar, FECHA_ISO.sub(apartar, FECHA_ESCRITA.sub(apartar, texto)))
    texto = NUMERO.sub(lambda m: _escalar_numero(m.group(), k), texto)
    texto = re.sub("[\uE000-\uF8FF]", lambda m: apartados[ord(m.group()) - 0xE000], texto)
    return _fechas_escritas(FECHA_ISO.sub(_fecha_relativa, texto))


def sintetizar(valor: Any, k: Decimal, clave: str | None = None) -> Any:
    """Las cantidades escaladas por k y las fechas relativas a la foto; nombres y códigos intactos."""
    if isinstance(valor, dict):
        return {c: sintetizar(v, k, c) for c, v in valor.items()}
    if isinstance(valor, list):
        return [sintetizar(v, k, clave) for v in valor]
    if isinstance(valor, bool) or valor is None:
        return valor
    if clave in SIN_ESCALAR:
        return _fechas_escritas(FECHA_ISO.sub(_fecha_relativa, valor)) if isinstance(valor, str) else valor
    if isinstance(valor, int):
        return valor if abs(valor) <= UMBRAL else int(_escalado(Decimal(valor), k, 0))
    if isinstance(valor, float):
        return valor if abs(valor) <= UMBRAL else float(_escalado(Decimal(repr(valor)), k, 1))
    return _escalar_texto(valor, k)


def _de_un_nombre(texto: str, inicio: int, fin: int) -> bool:
    """El número es parte de un nombre en mayúsculas: «LA 21», «LATA 269 SIXPACK», «*500 GR», «* 1000»."""
    antes = texto[:inicio].rstrip(" ")
    previa = antes.split()[-1] if antes.split() else ""
    siguiente = texto[fin:].split()[0] if texto[fin:].split() else ""
    return (antes.endswith("*") or (len(previa) >= 2 and previa.isalpha() and previa.isupper())
            or (len(siguiente) >= 2 and siguiente.isalpha() and siguiente.isupper()))


def _escalar_ejemplo(texto: str, k: Decimal) -> str:
    """Las cifras del ejemplo del glosario, sin tocar las de los nombres de productos y sucursales."""
    texto = _fechas_escritas(texto)                    # primero las fechas: sus cifras no se escalan
    marcas = [m.span() for m in re.finditer(r"\{fecha[^}]*\}", texto)]
    partes, ultimo = [], 0
    for m in NUMERO.finditer(texto):
        if not _de_un_nombre(texto, m.start(), m.end()) and not any(a <= m.start() < b for a, b in marcas):
            partes += [texto[ultimo:m.start()], _escalar_numero(m.group(), k)]
            ultimo = m.end()
    return "".join(partes) + texto[ultimo:]


def sintetizar_resultado(herramienta: str, resultado: dict, k: Decimal) -> dict:
    """Como `sintetizar`, salvo el glosario: sus reglas («menos de 3 días», «los días 2 y 16») no son datos y se
    conservan; solo se escala el párrafo del ejemplo, que trae cifras de la foto."""
    if herramienta == "historial_ventas":
        return _pesos_ilustrativos(sintetizar(resultado, k))
    if herramienta != "buscar_en_glosario":
        return sintetizar(resultado, k)
    copia = json.loads(json.dumps(resultado))
    for f in copia.get("fragmentos", []):
        f["texto"] = "\n\n".join(_escalar_ejemplo(par, k) if par.startswith("Ejemplo.") else _fechas_escritas(par)
                                  for par in f["texto"].split("\n\n"))
    return copia


PRECIO_ILUSTRATIVO, MARGEN_ILUSTRATIVO = 2000, 150
PERIODOS = (("anio", re.compile(r"^(\d{4})$")), ("trimestre", re.compile(r"^(\d{4})-T([1-4])$")),
            ("mes", re.compile(r"^(\d{4})-(\d{2})$")), ("semana", re.compile(r"^(\d{4})-W(\d{2})$")))


def _periodo_relativo(texto: str) -> str:
    """«2025-T4» → {periodo:trimestre}, «2025-W40» → {periodo:semana-13}: en Colab los periodos también se mueven (N9)."""
    base = date.fromisoformat(FECHA)
    for tipo, patron in PERIODOS:
        if m := patron.match(texto):
            anio, parte = int(m.group(1)), int(m.group(2)) if m.lastindex == 2 else 0
            if tipo == "semana":
                n = (date.fromisocalendar(anio, parte, 1) - date.fromisocalendar(*base.isocalendar()[:2], 1)).days // 7
            else:
                n = {"anio": anio - base.year, "trimestre": anio * 4 + parte - 1 - (base.year * 4 + (base.month - 1) // 3),
                     "mes": anio * 12 + parte - 1 - (base.year * 12 + base.month - 1)}[tipo]
            return "{periodo:" + tipo + (f"{n:+d}" if n else "") + "}"
    return texto


def _pesos_ilustrativos(valor: Any) -> Any:
    """Las ventas reales en pesos no se publican (privacidad.py), ni escaladas: el factor es público. En cada fila
    con cantidad, valor y margen salen de la cantidad sintética a un precio ilustrativo (2.000 y 150 por unidad).
    Los periodos quedan relativos a la fecha de la foto."""
    if isinstance(valor, list):
        return [_pesos_ilustrativos(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    salida = {k: _pesos_ilustrativos(v) for k, v in valor.items()}
    if isinstance(salida.get("periodo"), str):
        salida["periodo"] = _periodo_relativo(salida["periodo"])
    if "cantidad" in salida and ("valor" in salida or "margen" in salida):
        m = NUMERO.search(str(salida["cantidad"]))
        cantidad = Decimal(m.group().replace(".", "").replace(",", ".")) if m else Decimal(0)
        for campo, precio in (("valor", PRECIO_ILUSTRATIVO), ("margen", MARGEN_ILUSTRATIVO)):
            if campo in salida:
                salida[campo] = f"$ {texto_numero(float(cantidad * precio))}"
    return salida


def _campo(valor: Any, ruta: str) -> Any:
    for parte in ruta.split("."):
        valor = valor[int(parte)] if isinstance(valor, list) else valor[parte]
    return valor


def hecho(valor: Any) -> str:
    """Lo que se busca en la respuesta: la cifra sin separador de miles (1.444 → 1444, 91,2 kg → 91,2) o el texto."""
    if isinstance(valor, int | float):
        return str(valor)
    m = NUMERO.search(str(valor))
    return m.group().replace(".", "") if m else str(valor)


def resolver(hechos: list[str], resultados: list[dict]) -> list[str]:
    salida = []
    for h in hechos:
        m = REFERENCIA.match(h)
        salida.append(hecho(_campo(resultados[int(m.group(1))], m.group(2))) if m else h)
    return salida


def _inyectar(resultado: dict, campo: str, texto: str) -> dict:
    copia = json.loads(json.dumps(resultado))
    *ruta, ultimo = campo.split(".")
    destino = _campo(copia, ".".join(ruta)) if ruta else copia
    clave = int(ultimo) if isinstance(destino, list) else ultimo
    destino[clave] = f"{destino[clave]}{texto}"
    return copia


def _resultados_por_herramienta(llamadas: list[dict], sinteticos: list[dict]) -> dict:
    """Una herramienta llamada una vez: su resultado. Varias: casos {"si", "resultado"}; el que no tiene `si`, al final."""
    por_nombre: dict[str, list] = {}
    for ll, r in zip(llamadas, sinteticos, strict=True):
        por_nombre.setdefault(ll["herramienta"], []).append((ll.get("si"), r))
    salida = {}
    for nombre, casos in por_nombre.items():
        if len(casos) == 1 and casos[0][0] is None:
            salida[nombre] = casos[0][1]
        else:
            ordenados = [c for c in casos if c[0] is not None] + [c for c in casos if c[0] is None]
            salida[nombre] = [{"si": si or {}, "resultado": r} for si, r in ordenados]
    return salida


async def construir_pregunta(p: dict, ejecutar: Ejecutar, disponibles: set[str]) -> dict:
    llamadas = p.get("llamadas", [])
    salida = {k: v for k, v in p.items() if k not in ("llamadas", "hechos", "hechos_alguno", "inyeccion")}
    if p.get("pendiente") and any(ll["herramienta"] not in disponibles for ll in llamadas):
        return salida
    reales = [await ejecutar(p["rol"], p.get("sucursal_usuario"), ll["herramienta"], ll["argumentos"]) for ll in llamadas]
    k = factor(p["id"])
    sinteticos = [sintetizar_resultado(ll["herramienta"], r, k) for ll, r in zip(llamadas, reales, strict=True)]
    if inyeccion := p.get("inyeccion"):
        n = inyeccion["llamada"]
        sinteticos[n] = _inyectar(sinteticos[n], inyeccion["campo"], inyeccion["texto"])
    if llamadas:
        salida["resultados"] = _resultados_por_herramienta(llamadas, sinteticos)
    if p.get("hechos"):
        salida["hechos_clave"] = resolver(p["hechos"], sinteticos)
        salida["hechos_reales"] = resolver(p["hechos"], reales)
    if p.get("hechos_alguno"):
        salida["hechos_alguno"] = resolver(p["hechos_alguno"], sinteticos)
        salida["hechos_alguno_reales"] = resolver(p["hechos_alguno"], reales)
    return salida


REGLAS_V1 = {
    "como_v0": "Las reglas de esperado, abstención, resultados, hechos, prohibido, aclaración y rechazo son las del v0.",
    "hechos_reales": "Los hechos con los datos reales al 31-dic-2025: se califican cuando se corre contra el Core API (--core-api).",
    "resultados": "Sintéticos: las respuestas reales de las herramientas con las cantidades escaladas (factor de 1,20 a 1,59 por pregunta) y las fechas como {fecha±n}. Los pesos de las ventas son ilustrativos: la cantidad a 2.000 (valor) y 150 (margen) por unidad.",
    "pendiente": "La herramienta que todavía no existe: la pregunta no se valida contra el catálogo ni se corre sin --incluir-pendientes.",
    "bloque": "A una herramienta, B varios pasos, C glosario y capacidades que no tiene, D ambiguas, E abstención, F adversariales.",
}


async def construir(fuente: dict, ejecutar: Ejecutar, disponibles: set[str]) -> dict:
    preguntas = [await construir_pregunta(p, ejecutar, disponibles) for p in fuente["preguntas"]]
    datos = {k: v for k, v in fuente.items() if k != "preguntas"}
    datos["reglas"] = REGLAS_V1
    datos["preguntas"] = preguntas
    Conjunto(**datos)                    # valida el esquema antes de escribir
    return datos


def ejecutor_core_api(core_api: str, clave: str) -> tuple[Ejecutar, Callable[[], Awaitable[None]]]:
    from core.config import Settings
    from evaluacion.correr import UsuariosPrueba
    from herramientas.catalogo import POR_NOMBRE
    from herramientas.contexto import Contexto
    from herramientas.core_api import ClienteCoreAPI, ErrorHerramienta

    usuarios = UsuariosPrueba(core_api, clave)
    core = ClienteCoreAPI(Settings(CORE_API_URL=core_api))
    tokens: dict[tuple, str] = {}

    async def ejecutar(rol: str, sucursal: str | None, herramienta: str, argumentos: dict) -> dict:
        clave_usuario = (rol, sucursal if rol == "admin_sucursal" else None)
        if clave_usuario not in tokens:
            tokens[clave_usuario] = usuarios.autorizacion(*clave_usuario)
        h = POR_NOMBRE[herramienta]
        try:
            return (await h.ejecutar(Contexto(core, tokens[clave_usuario], uuid.uuid4().hex), h.validar(argumentos))).para_modelo
        except ErrorHerramienta as exc:
            return exc.para_modelo()

    return ejecutar, core.cerrar


async def _principal(args) -> Path:
    from herramientas.catalogo import POR_NOMBRE

    clave = os.environ.get("INVENTAIO_CLAVE_PRUEBA")
    if not clave:
        sys.exit("Define INVENTAIO_CLAVE_PRUEBA con la clave de los usuarios de prueba (api/scripts/seed_usuarios.py)")
    fuente = json.loads(Path(args.fuente).read_text(encoding="utf-8"))
    ejecutar, cerrar = ejecutor_core_api(args.core_api, clave)
    try:
        datos = await construir(fuente, ejecutar, set(POR_NOMBRE))
    finally:
        await cerrar()
    destino = Path(args.destino)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    pendientes = sum(1 for p in datos["preguntas"] if p.get("pendiente"))
    print(f"{len(datos['preguntas'])} preguntas ({pendientes} pendientes) en {destino}")
    return destino


def main(argv=None) -> Path:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--core-api", default="http://localhost:8000")
    a.add_argument("--fuente", default=str(FUENTE))
    a.add_argument("--destino", default=str(DESTINO))
    return asyncio.run(_principal(a.parse_args(argv)))


if __name__ == "__main__":
    main()
