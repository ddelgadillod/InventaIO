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
import re
import unicodedata
from dataclasses import dataclass, field

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


def palabras(texto: str) -> list[str]:
    return [p for p in normal(texto).split() if p not in VACIAS and (len(p) > 1 or p.isdigit())]


def contiene_todas(nombre: str, buscadas: list[str]) -> bool:
    """Las palabras, como subcadena; los números, completos («500» está en «*500GR», no en «*5000 GR»)."""
    n = normal(nombre)
    return all(re.search(rf"(?<!\d){p}(?!\d)", n) if p.isdigit() else p in n for p in buscadas)


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
    def __init__(self, core: ClienteCoreAPI, autorizacion: str, request_id: str):
        self.core = core
        self.autorizacion = autorizacion
        self.request_id = request_id
        self._perfil: Perfil | None = None
        self._sucursales: list[Sucursal] | None = None
        self._categorias: list[str] | None = None

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

    async def categoria(self, texto: str) -> str:
        if self._categorias is None:
            d = await self.get("/api/consulta/categorias")
            self._categorias = [c["categoria"] for c in d["items"]]
        buscada = normal(texto)
        for c in self._categorias:
            if normal(c) == buscada or normal(c).rstrip("s") == buscada.rstrip("s"):
                return c
        raise ErrorHerramienta(422, f"No existe la categoría «{texto}». Categorías: {', '.join(self._categorias)}")

    async def buscar_productos(self, texto: str) -> tuple[int, list[Producto]]:
        total, items = await self.paginas("/api/consulta/productos", busqueda=texto)
        buscadas = palabras(texto)
        if total == 0 and len(buscadas) > 1:
            clave = max((p for p in buscadas if not p.isdigit()), key=len, default=buscadas[0])
            _, items = await self.paginas("/api/consulta/productos", busqueda=clave)
            items = [i for i in items if contiene_todas(i["nombre"], buscadas)]
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
