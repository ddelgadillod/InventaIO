"""
Extracción de entidades antes del modelo (INV-33, alternativa 1, decisión del usuario del 24-oct; interruptor
`entidades`).

Con un modelo de 8B, la falla más frecuente en preguntas nuevas es traducir palabras a argumentos (~35 % en los
holdouts): el mes, la categoría, la sucursal. Aquí se detectan con datos del catálogo (los nombres de las sucursales,
las 33 categorías y los meses), no con patrones de preguntas vistas, y:

- se le entregan al modelo como un mensaje de sistema antes de la pregunta («Datos detectados…»);
- la guarda completa lo que el modelo omita: la categoría, el periodo de historial_ventas (con `dias` y la agrupación
  por mes, sin parámetros nuevos: los cambios de esquema bajaron la herramienta del modelo, C1 y P6) y una sola
  sucursal nombrada.

No cambia esquemas ni descripciones del catálogo.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from agente.mejoras import NOMBRES_MES, SUCURSALES, _nombra
from herramientas.contexto import VACIAS, normal

AÑO = re.compile(r"\b(20\d\d)\b")
MES_Y_AÑO = re.compile(r"\b(" + "|".join(NOMBRES_MES) + r")\b(?:\s+(?:de|del)\s+(20\d\d))?")
HACIA = re.compile(r"\b(a|hacia|para|al)\s+(la\s+)?$")
DESDE = re.compile(r"\b(desde|de|del)\s+(la\s+)?$")
CON_SUCURSAL = {"consultar_inventario", "listar_alertas", "resumen_alertas", "resumen_inventario", "pronosticar_demanda",
                "historial_ventas", "recomendar_compras"}
CON_CATEGORIA = {"consultar_inventario", "historial_ventas", "recomendar_compras", "recomendar_traslados"}
# Palabras que pueden seguir a una categoría sin volverla un producto («lácteos por trimestre», «aseo hacia GLORIETA»)
CONECTORES = VACIAS | {"a", "al", "hacia", "desde", "y", "o", "que", "hay", "tenemos", "se", "me", "mi", "este", "esta",
                       "estos", "estas", "sugeridos", "sugeridas", "productos", "vendi", "vendimos", "vendio", "ventas"}


@dataclass
class Periodo:
    etiqueta: str                 # «noviembre de 2025»
    desde: date
    hasta: date
    fila: str                     # «2025-11», la fila del reporte mensual


@dataclass
class Entidades:
    sucursales: list[str] = field(default_factory=list)
    categorias: list[str] = field(default_factory=list)
    periodo: Periodo | None = None
    direccion: dict[str, str] = field(default_factory=dict)      # sucursal → «destino» u «origen», si se nota

    def vacias(self) -> bool:
        return not (self.sucursales or self.categorias or self.periodo)

    def mensaje(self) -> str:
        """Lo que se le entrega al modelo: datos, no reglas."""
        partes = []
        if self.sucursales:
            partes.append("sucursal " + ", ".join(self.sucursales))
        if self.categorias:
            partes.append("categoría del catálogo " + ", ".join(self.categorias) + " (va en el filtro categoria)")
        if self.periodo:
            partes.append(f"periodo {self.periodo.etiqueta} (en historial_ventas por mes es la fila {self.periodo.fila})")
        return "Datos detectados en la pregunta: " + "; ".join(partes) + "."


def _ultimo_usuario(mensajes: list[dict]) -> str:
    return next((m["content"] for m in reversed(mensajes) if m.get("role") == "user" and isinstance(m.get("content"), str)
                 and not m["content"].startswith("(")), "")


def _periodo(textos: list[str]) -> Periodo | None:
    """Un mes nombrado (con su año, o el de la conversación) o un año solo."""
    años = [a for t in textos for a in AÑO.findall(t)]
    for t in textos:                                    # primero la última pregunta
        if m := MES_Y_AÑO.search(t):
            año = m.group(2) or (años[0] if años else None)
            if año is None:
                return None
            mes = NOMBRES_MES.index(m.group(1)) + 1
            fin = date(int(año) + (mes == 12), mes % 12 + 1, 1)
            return Periodo(f"{m.group(1)} de {año}", date(int(año), mes, 1), date.fromordinal(fin.toordinal() - 1),
                           f"{año}-{mes:02d}")
    for t in textos:
        if (a := AÑO.findall(t)) and len(set(a)) == 1:
            return Periodo(a[0], date(int(a[0]), 1, 1), date(int(a[0]), 12, 31), a[0])
    return None


async def detectar(mensajes: list[dict], ctx) -> Entidades:
    """Las entidades de la última pregunta y, si no las tiene, de la conversación (un «¿y en noviembre?»)."""
    ultima = normal(_ultimo_usuario(mensajes))
    todas = normal(" ".join(m["content"] for m in mensajes if m.get("role") == "user" and isinstance(m.get("content"), str)
                            and not m["content"].startswith("(")))
    e = Entidades()
    for texto in (ultima, todas):
        e.sucursales = [s for s, raices in SUCURSALES.items() if _nombra(texto, raices)]
        if e.sucursales:
            break
    for s in e.sucursales:
        for raiz in SUCURSALES[s]:
            if (i := (ultima + " ").find(raiz)) > 0:
                antes = ultima[:i]
                e.direccion[s] = "destino" if HACIA.search(antes) else "origen" if DESDE.search(antes) else ""
    categorias = await ctx.categorias()
    for texto in (ultima, todas):
        e.categorias = [c for c in categorias if _nombra_categoria_completa(texto, c)
                        and not await _es_producto(texto, c, ctx)]
        if e.categorias:
            break
    e.periodo = _periodo([ultima, todas])
    return e


async def _es_producto(texto: str, categoria: str, ctx) -> bool:
    """«arroz diana» es un producto, no la categoría Arroz: si la palabra que sigue no es un conector y con ella hay
    productos, la mención es de un producto."""
    raiz = normal(categoria).split()[0][:5]
    m = re.search(rf"\b{re.escape(raiz)}\w*\s+(\w+)", texto)
    if not m or m.group(1) in CONECTORES or m.group(1).isdigit():
        return False
    total, _ = await ctx.buscar_productos(m.group(0))
    return total > 0


def _nombra_categoria_completa(texto: str, categoria: str) -> bool:
    """«lácteos», «aseo» (de Aseo hogar), «licor»: la primera palabra de la categoría, por su raíz de 5 letras."""
    primera = normal(categoria).split()[0]
    return len(primera) >= 4 and re.search(rf"\b{re.escape(primera[:5])}", texto) is not None


def completar(herramienta: str, argumentos: dict, e: Entidades, fecha_datos: date | None) -> tuple[dict, list[str]]:
    """La guarda con las entidades: lo que el modelo omitió y la pregunta sí dice."""
    nuevos, hecho = dict(argumentos), []
    if herramienta in CON_CATEGORIA and len(e.categorias) == 1 and not nuevos.get("categoria") and not nuevos.get("producto"):
        nuevos["categoria"] = e.categorias[0]
        hecho.append(f"categoria={e.categorias[0]} (la pregunta la nombra)")
    if herramienta == "historial_ventas" and e.periodo and fecha_datos and e.periodo.desde <= fecha_datos:
        dias = (fecha_datos - e.periodo.desde).days + 1
        if nuevos.get("dias") != dias or nuevos.get("agrupacion") not in ("mes", "trimestre"):
            nuevos["dias"], nuevos["agrupacion"] = dias, nuevos.get("agrupacion") if nuevos.get("agrupacion") in ("mes", "trimestre") else "mes"
            hecho.append(f"dias={dias}, agrupacion={nuevos['agrupacion']} (el periodo {e.periodo.etiqueta})")
    if len(e.sucursales) == 1:
        s = e.sucursales[0]
        if herramienta in CON_SUCURSAL and not nuevos.get("sucursal") and not (herramienta == "pronosticar_demanda"
                                                                              and s == "BODEGA_CENTRAL"):
            nuevos["sucursal"] = s
            hecho.append(f"sucursal={s} (la pregunta la nombra)")
        if herramienta == "recomendar_traslados" and not nuevos.get("destino") and not nuevos.get("origen") and e.direccion.get(s):
            nuevos[e.direccion[s]] = s
            hecho.append(f"{e.direccion[s]}={s} (la pregunta la nombra)")
    return nuevos, hecho
