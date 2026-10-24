"""
Contexto de una pregunta (INV-32): el token del usuario, el `request_id` y lo
que se resuelve una sola vez por petición para traducir lo que da el modelo:

- el perfil (`/api/auth/me`): solo el rol y la sucursal; el email y el nombre se
  descartan y no llegan al modelo ni a los registros (C18, Ley 1581);
- las sucursales, con sus ids leídos del Core API (T2, C5);
- las categorías: el filtro del inventario es exacto («arroz» no encuentra
  «Arroz»), así que se traducen al nombre canónico (C19);
- los productos (T2): código exacto, nombre exacto o subcadena. La búsqueda del
  Core API es por subcadena y en orden alfabético («leche» da 110 y el primero
  es «ARROZ CON LECHE…», C4); si la frase completa no aparece («arroz carolina
  500»), se busca la palabra más larga y se exigen todas las demás.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from herramientas.core_api import ClienteCoreAPI, ErrorHerramienta

ROLES_GLOBALES = ("gerente", "admin_bodega")
MAX_CANDIDATOS = 5
POR_PAGINA = 100            # el máximo de page_size en el Core API
MAX_PAGINAS = 3
# Palabras que no ayudan a encontrar un producto: los nombres escriben las
# presentaciones de muchas formas («*500GR», «500 G», «X 500»)
VACIAS = {"de", "del", "la", "las", "el", "los", "en", "con", "por", "para", "x", "g", "gr", "grs", "gramos",
          "und", "unds", "unidad", "unidades", "kg", "kl", "kilo", "kilos", "ml", "lt", "litro", "litros"}


def normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", texto).split())


KILO = "__kilo__"              # C9: «de kilo» es una presentación (1000 g, *KL, KG)
PRESENTACION_X = re.compile(r"^(\d+)x(\d+)$")


def palabras(texto: str, amplia: bool = False) -> list[str]:
    """Las palabras que buscan un producto. Con `amplia` (C9, 24-oct): «3x80» son dos números, como «3*80» en la
    bodega, y «kilo» (o kg, kl) busca la presentación de 1000 g o por kilo."""
    salida = []
    for p in normal(texto).split():
        if amplia and (m := PRESENTACION_X.match(p)):
            salida += [m.group(1), m.group(2)]
        elif amplia and p in ("kilo", "kilos", "kg", "kl"):
            salida.append(KILO)
        elif p not in VACIAS and (len(p) > 1 or p.isdigit()):
            salida.append(p)
    return list(dict.fromkeys(salida))


# INV-33, brecha B1: la bodega escribe muchos nombres abreviados (JAB, GALL, DET, CHOC…). El diccionario
# sale de la bodega y lo valida el usuario (decisión B7); sin el archivo, la búsqueda es la de INV-32
ARCHIVO_ABREVIATURAS = Path(__file__).with_name("abreviaturas.json")


def cargar_abreviaturas(ruta: Path = ARCHIVO_ABREVIATURAS) -> dict[str, tuple[str, ...]]:
    """palabra que escribe el usuario → abreviaturas con que está en la bodega, todo normalizado. Las palabras de
    una entrada separadas por « / » son sinónimos («galleta / galletas», «champú / shampoo»)."""
    if not ruta.is_file():
        return {}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {normal(palabra): tuple(normal(a) for a in abreviaturas)
            for entrada, abreviaturas in datos["abreviaturas"].items() for palabra in entrada.split("/")}


def _sinonimos(ruta: Path = ARCHIVO_ABREVIATURAS) -> dict[str, frozenset[str]]:
    if not ruta.is_file():
        return {}
    entradas = [frozenset(normal(p) for p in e.split("/")) for e in json.loads(ruta.read_text(encoding="utf-8"))["abreviaturas"]]
    return {p: e for e in entradas for p in e}


ABREVIATURAS = cargar_abreviaturas()
SINONIMOS = _sinonimos()


def abreviaturas_de(palabra: str) -> tuple[str, ...]:
    """Las abreviaturas de una palabra, también en plural («galletas» → gall)."""
    for forma in (palabra, palabra[:-1] if palabra.endswith("s") else "", palabra[:-2] if palabra.endswith("es") else ""):
        if forma and forma in ABREVIATURAS:
            return ABREVIATURAS[forma]
    return ()


def aclaracion_abreviatura(texto: str, categorias: list[str]) -> dict | None:
    """Regla del usuario (21-oct): una abreviatura de varias palabras (AC es aceite y acondicionador) es dudosa;
    si los resultados no son todos de la misma categoría, el modelo pregunta antes de responder con cifras."""
    distintas = sorted(set(categorias))
    if len(distintas) < 2:
        return None
    for p in palabras(texto):
        forma = next((f for f in (p, p[:-1], p[:-2]) if f in ABREVIATURAS), p)
        for a in abreviaturas_de(p):
            otras = sorted(w for w, abrevs in ABREVIATURAS.items()
                           if a in abrevs and w != forma and w not in SINONIMOS.get(forma, ()))
            if otras:
                return {"aclarar": True, "categorias": distintas,
                        "indicacion": (f"En la bodega «{a.upper()}» abrevia «{p}» y también {', '.join(f'«{o}»' for o in otras)}: "
                                       "los resultados son de varias categorías. Pregunta al usuario cuál quiere, con "
                                       "estas categorías, antes de responder con cifras.")}
    return None


def _esta(palabra: str, nombre_normal: str) -> bool:
    if palabra == KILO:
        return re.search(r"(?<!\d)1000(?!\d)|\bkl\b|\bkg\b|\bkilo", nombre_normal) is not None
    if palabra.isdigit():                               # «500» está en «*500GR», no en «*5000 GR»
        return re.search(rf"(?<!\d){palabra}(?!\d)", nombre_normal) is not None
    if palabra in nombre_normal:
        return True
    # La abreviatura cuenta solo como palabra completa: «ac» es aceite en «AC DIANA», no en «ACADEMIA»
    return any(re.search(rf"\b{re.escape(a)}\b", nombre_normal) for a in abreviaturas_de(palabra))


def contiene_todas(nombre: str, buscadas: list[str]) -> bool:
    """Cada palabra está en el nombre, como subcadena o con su abreviatura de la bodega; los números, completos."""
    n = normal(nombre)
    return all(_esta(p, n) for p in buscadas)


def requiere_busqueda_por_palabras(texto: str, nombres: list[str], amplia: bool = False) -> bool:
    """La búsqueda por subcadena se queda corta: no encontró nada, la consulta tiene una palabra que la bodega
    abrevia, o lo que encontró no empieza por la primera palabra («PAPA * KL» encuentra RAPI PAPA * KL). Con
    `amplia` (C9), siempre que haya dos palabras o más: «panela grande» también es PANELA REDONDA GRANDE."""
    buscadas = palabras(texto, amplia)
    if not buscadas:
        return False
    if amplia and len(buscadas) >= 2:
        return True
    if not nombres or any(abreviaturas_de(p) for p in buscadas):
        return True
    primera = next((p for p in buscadas if not p.isdigit()), None)
    return primera is not None and not all(normal(n).startswith(primera) for n in nombres)


@dataclass
class Sucursal:
    id: int
    nombre: str
    tipo: str

    @property
    def fisica(self) -> bool:
        return self.tipo != "bodega_central"


@dataclass
class Perfil:
    rol: str
    sucursal: str | None

    @property
    def es_global(self) -> bool:
        return self.rol in ROLES_GLOBALES


@dataclass
class Producto:
    id: int
    codigo: str
    nombre: str
    categoria: str
    unidad: str


@dataclass
class Candidatos:
    """El producto no se pudo resolver a uno solo: el modelo pregunta (criterio 3)."""
    estado: str                     # ambiguo | no_encontrado
    texto: str
    total: int
    candidatos: list[Producto] = field(default_factory=list)

    def para_modelo(self) -> dict:
        if self.estado == "no_encontrado":
            return {"resultado": "no_encontrado", "busqueda": self.texto, "total": 0,
                    "indicacion": "No hay productos con ese nombre: pide otro nombre o el código."}
        return {
            "resultado": "ambiguo", "busqueda": self.texto, "total": self.total,
            "candidatos": [{"codigo": p.codigo, "nombre": p.nombre, "categoria": p.categoria} for p in self.candidatos],
            "indicacion": "Varios productos coinciden: pide al usuario que elija uno y no supongas cuál.",
        }


def _producto(item: dict) -> Producto:
    return Producto(id=item["id_producto"], codigo=item["codigo_item"], nombre=item["nombre"],
                    categoria=item["categoria"], unidad=item.get("unidad", "unidad"))


def _ordenar(productos: list[Producto], texto: str) -> list[Producto]:
    n = normal(texto)
    return sorted(productos, key=lambda p: (normal(p.codigo) != n, normal(p.nombre) != n,
                                            not normal(p.nombre).startswith(n), len(p.nombre), p.nombre))


class Contexto:
    def __init__(self, core: ClienteCoreAPI, autorizacion: str, request_id: str, mejoras=None):
        self.core = core
        self.autorizacion = autorizacion
        self.request_id = request_id
        self.mejoras = mejoras          # agente.mejoras.Mejoras (INV-33, §3g): las correcciones de las herramientas
        self._perfil: Perfil | None = None
        self._sucursales: list[Sucursal] | None = None
        self._categorias: list[str] | None = None
        self._fecha_ventas = None

    def activa(self, nombre: str) -> bool:
        """Si la corrección `nombre` (C1 a C9) está encendida."""
        return bool(self.mejoras is not None and getattr(self.mejoras, nombre, False))

    async def get(self, ruta: str, **params):
        return await self.core.pedir("GET", ruta, self.autorizacion, self.request_id, params=params)

    async def post(self, ruta: str, cuerpo: dict):
        return await self.core.pedir("POST", ruta, self.autorizacion, self.request_id, cuerpo=cuerpo)

    async def paginas(self, ruta: str, **params) -> tuple[int, list[dict]]:
        """Hasta 3 páginas de 100: el total real y las filas leídas."""
        total, items = 0, []
        for pagina in range(1, MAX_PAGINAS + 1):
            d = await self.get(ruta, **params, page=pagina, page_size=POR_PAGINA)
            total = d["total"]
            items += d["items"]
            if len(items) >= total or not d["items"]:
                break
        return total, items

    async def perfil(self) -> Perfil:
        if self._perfil is None:
            d = await self.get("/api/auth/me")
            self._perfil = Perfil(rol=d["rol"], sucursal=d.get("sucursal_nombre"))
        return self._perfil

    async def sucursales(self) -> list[Sucursal]:
        if self._sucursales is None:
            d = await self.get("/api/consulta/sucursales")
            self._sucursales = [Sucursal(s["id_sucursal"], s["nombre"], s["tipo"]) for s in d["items"]]
        return self._sucursales

    async def sucursal(self, nombre: str) -> Sucursal:
        todas = await self.sucursales()
        for s in todas:
            if normal(s.nombre) == normal(nombre):
                return s
        raise ErrorHerramienta(422, f"No existe la sucursal {nombre}. Válidas: {', '.join(s.nombre for s in todas)}")

    async def tiendas_por_rol(self) -> list[str]:
        """Las sucursales físicas de una consulta sin sucursal (T4, T9): las 3 para el
        gerente y el admin_bodega; para el admin_sucursal, la suya."""
        perfil = await self.perfil()
        fisicas = [s.nombre for s in await self.sucursales() if s.fisica]
        if perfil.es_global:
            return fisicas
        if perfil.sucursal in fisicas:
            return [perfil.sucursal]
        raise ErrorHerramienta(403, "El usuario no tiene una sucursal física asignada")

    async def categorias(self) -> list[str]:
        """Las categorías del catálogo, una vez por petición."""
        if self._categorias is None:
            d = await self.get("/api/consulta/categorias")
            self._categorias = [c["categoria"] for c in d["items"]]
        return self._categorias

    async def fecha_ventas(self):
        """La fecha hasta la que hay ventas (INV-33, entidades: el periodo de un mes nombrado se cuenta hasta ella)."""
        if self._fecha_ventas is None:
            from datetime import date
            d = await self.get("/api/reportes/ventas", agrupacion="mes")
            self._fecha_ventas = date.fromisoformat(d["datos_hasta"])
        return self._fecha_ventas

    async def categoria(self, texto: str) -> str:
        await self.categorias()
        buscada = normal(texto)
        for c in self._categorias:
            if normal(c) == buscada or normal(c).rstrip("s") == buscada.rstrip("s"):
                return c
        if self.activa("categoria"):
            # C2 (24-oct): «aseo» es «Aseo hogar» si es la única categoría con esas palabras
            raices = [p[:5] for p in buscada.split() if len(p) >= 3]
            unicas = [c for c in self._categorias
                      if raices and all(any(w.startswith(r) for w in normal(c).split()) for r in raices)]
            if len(unicas) == 1:
                return unicas[0]
        raise ErrorHerramienta(422, f"No existe la categoría «{texto}». Categorías: {', '.join(self._categorias)}")

    async def buscar_por_palabras(self, ruta: str, texto: str, campo: str, **params) -> tuple[list[dict], bool]:
        """Las filas cuyo `campo` tiene todas las palabras de `texto`, en cualquier orden y con las abreviaturas
        de la bodega (B1). Se pide al Core API la palabra más larga y cada una de sus abreviaturas. Devuelve
        también si alguna búsqueda quedó cortada en las 3 páginas."""
        buscadas = palabras(texto, self.activa("busqueda"))
        clave = max((p for p in buscadas if not p.isdigit() and p != KILO), key=len, default=buscadas[0])
        vistas: dict[tuple, dict] = {}
        cortada = False
        for variante in (clave, *abreviaturas_de(clave)):
            total, items = await self.paginas(ruta, **params, busqueda=variante)
            cortada |= total > len(items)
            for i in items:
                vistas.setdefault((i.get("id_producto"), i.get("id_sucursal")), i)
        return [i for i in vistas.values() if contiene_todas(i[campo], buscadas)], cortada

    async def buscar_productos(self, texto: str) -> tuple[int, list[Producto]]:
        total, items = await self.paginas("/api/consulta/productos", busqueda=texto)
        if requiere_busqueda_por_palabras(texto, [i["nombre"] for i in items], self.activa("busqueda")):
            por_palabras, _ = await self.buscar_por_palabras("/api/consulta/productos", texto, "nombre")
            vistos = {i["id_producto"] for i in items}
            items = items + [i for i in por_palabras if i["id_producto"] not in vistos]
            total = len(items)
        return total, _ordenar([_producto(i) for i in items], texto)

    async def producto(self, texto: str) -> Producto | Candidatos:
        total, productos = await self.buscar_productos(texto)
        n = normal(texto)
        exactos = [p for p in productos if normal(p.codigo) == n] or [p for p in productos if normal(p.nombre) == n]
        if len(exactos) == 1:
            return exactos[0]
        if total == 1 and productos:
            return productos[0]
        if total == 0:
            return Candidatos("no_encontrado", texto, 0)
        return Candidatos("ambiguo", texto, total, productos[:MAX_CANDIDATOS])
