"""
Catálogo v1 del agente (INV-32, T1): 8 herramientas de solo lectura sobre el
Core API, con el token del usuario. Ninguna llama a ml_service ni a una URL
que arme el modelo (criterio 2): las rutas son fijas. INV-31 suma la novena,
`buscar_en_glosario`, que no llama al Core API: busca en el glosario de negocio.

Cada una devuelve a lo sumo 10 filas, el total real que informa el Core API y
la fecha del dato (criterio 4), con las cantidades por `texto_cantidad`. Las
descripciones son las del catálogo v0 que midió el spike, con los ajustes que
pidieron los datos reales (docs/INV-32-requerimientos.md, sección 4).
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from conocimiento.bm25 import Indice
from herramientas.base import (
    MAX_FILAS,
    Columna,
    Herramienta,
    Resultado,
    grafico,
    tabla,
    tarjeta,
)
from herramientas.contexto import (
    Candidatos,
    Contexto,
    Producto,
    aclaracion_abreviatura,
    normal,
    palabras,
    requiere_busqueda_por_palabras,
)
from herramientas.core_api import ErrorHerramienta
from herramientas.formato import por_kilo, texto_cantidad, texto_dias, texto_numero

Sucursal = Literal["PRINCIPAL", "LA 21", "GLORIETA", "BODEGA_CENTRAL"]
Tienda = Literal["PRINCIPAL", "LA 21", "GLORIETA"]
Estado = Literal["ok", "bajo", "critico", "inconsistencia"]
TIPOS_REGLAS = ("stock_critico", "stock_bajo", "sin_movimiento", "rotacion_baja", "inconsistencia_inventario")
TIPOS_IA = ("riesgo_desabastecimiento_ml", "sobrestock_previsto_ml")
TipoAlerta = Literal[TIPOS_REGLAS + TIPOS_IA]
UrgenciaAlerta = Literal["critica", "alta", "media"]
UrgenciaCompra = Literal["urgente", "alta", "normal"]
UrgenciaTraslado = Literal["urgente", "alta", "normal", "vigilancia"]
Direccion = Literal["hacia", "desde"]
Agrupacion = Literal["quincena", "semana", "mes", "trimestre", "anio"]

SUCURSAL = "Sucursal o BODEGA_CENTRAL."
# Con solo «Omítelo para no filtrar», qwen3:8b ponía PRINCIPAL en un pronóstico sin sucursal (18-oct, T9)
POR_ROL = "Solo si la pregunta nombra una sucursal; si no, se consultan todas las que ve el usuario."
# INV-40: los resúmenes decían «Sucursal o BODEGA_CENTRAL.» y el modelo llamaba una vez por sucursal hasta agotar las
# rondas («estado general de sucursales» terminaba en la respuesta de respaldo)
SUCURSAL_RESUMEN = ("Solo si la pregunta nombra una sucursal o la Bodega Central. Sin sucursal, una sola llamada trae "
                    "todas las que ve el usuario y el total: nunca una llamada por sucursal.")
CODIGO = re.compile(r"[A-Za-z]?\d{3,6}")            # P626, 00196: códigos de producto
TEXTO_ESTADO = {"ok": "ok", "bajo": "bajo", "critico": "crítico", "inconsistencia": "inconsistencia"}
TEXTO_TIPO_ALERTA = {"stock_critico": "stock crítico", "stock_bajo": "stock bajo", "sin_movimiento": "sin movimiento",
                     "rotacion_baja": "rotación baja", "inconsistencia_inventario": "inconsistencia",
                     "riesgo_desabastecimiento_ml": "riesgo de desabastecimiento", "sobrestock_previsto_ml": "sobrestock previsto"}
TEXTO_URGENCIA = {"critica": "crítica", "alta": "alta", "media": "media", "urgente": "urgente", "normal": "normal"}
TEXTO_TIPO_SUCURSAL = {"principal": "principal", "estandar": "estándar",
                       "bodega_central": "bodega central (solo abastece a las sucursales)"}
ORDEN_URGENCIA_COMPRA = {"urgente": 0, "alta": 1, "normal": 2}
ORDEN_URGENCIA_TRASLADO = {"urgente": 0, "alta": 1, "normal": 2, "vigilancia": 3}
ESTADOS = ("ok", "bajo", "critico", "inconsistencia")
HORIZONTE = "15 días hábiles"


def _etiqueta(base: str, *partes: str | None) -> str:
    return " · ".join([base, *[p for p in partes if p]])


def _conteo(total: int, mostrando: int, que: str) -> str:
    """El total en palabras: con solo `total` y `mostrando`, qwen3:8b decía «hay 10» de 173 (18-oct)."""
    if total == mostrando:
        return f"{texto_numero(total)} {que} en total; se muestran todos."
    return f"{texto_numero(total)} {que} en total; se muestran los primeros {mostrando}."


def _resuelto_o_candidatos(prod) -> Resultado | None:
    return Resultado(para_modelo=prod.para_modelo()) if isinstance(prod, Candidatos) else None


async def _categoria_en_producto(ctx: Contexto, p) -> str | None:
    """C3 (24-oct): «Confitería» en `producto` es una categoría si no hay productos con ese nombre; pasa a su filtro.
    Devuelve la nota para el modelo, o None."""
    if not ctx.activa("categoria") or not getattr(p, "producto", None) or getattr(p, "categoria", None):
        return None
    try:
        categoria = await ctx.categoria(p.producto)
    except ErrorHerramienta:
        return None
    total, _ = await ctx.buscar_productos(p.producto)
    if total:
        return None
    texto, p.producto, p.categoria = p.producto, None, categoria
    return f"«{texto}» es una categoría: se consultó con el filtro de categoría ({categoria})."


PERIODO = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2])|-T([1-4]))?$")


def rango_periodo(periodo: str) -> tuple[str, str, str]:
    """C1 (24-oct): «2025-11», «2025-T4» o «2025» → (desde, hasta, agrupación por defecto)."""
    m = PERIODO.match(periodo.strip().upper().replace("Q", "T"))
    if not m:
        raise ErrorHerramienta(422, f"periodo «{periodo}» no es válido: usa «2025» (un año), «2025-T4» (un trimestre) "
                                    "o «2025-11» (un mes).")
    anio = int(m.group(1))
    if m.group(2):
        mes = int(m.group(2))
        fin = (date(anio + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1))
        return date(anio, mes, 1).isoformat(), fin.isoformat(), "mes"
    if m.group(3):
        t = int(m.group(3))
        fin = (date(anio + (t == 4), (3 * t) % 12 + 1, 1) - timedelta(days=1))
        return date(anio, 3 * t - 2, 1).isoformat(), fin.isoformat(), "mes"
    return f"{anio}-01-01", f"{anio}-12-31", "trimestre"


class BuscarProducto(Herramienta):
    nombre = "buscar_producto"
    descripcion = "Busca productos por nombre, marca o código. Devuelve código, nombre y categoría."
    titulo_base = "Búsqueda de productos"
    endpoints = (("GET", "/api/consulta/productos", frozenset({"busqueda", "page", "page_size"})),)

    class Parametros(BaseModel):
        texto: str = Field(min_length=1)

    async def ejecutar(self, ctx, p):
        total, productos = await ctx.buscar_productos(p.texto)
        filas = [{"codigo": x.codigo, "nombre": x.nombre, "categoria": x.categoria, "unidad": x.unidad}
                 for x in productos[:MAX_FILAS]]
        aclarar = aclaracion_abreviatura(p.texto, [x.categoria for x in productos]) or {}
        return Resultado(para_modelo={"total": total, "mostrando": len(filas),
                                      "conteo": _conteo(total, len(filas), "productos"), **aclarar, "filas": filas})


class ListarSucursales(Herramienta):
    nombre = "listar_sucursales"
    descripcion = "Lista las sucursales y la Bodega Central con su tipo."
    titulo_base = "Sucursales"
    endpoints = (("GET", "/api/consulta/sucursales", frozenset()),)

    class Parametros(BaseModel):
        pass

    async def ejecutar(self, ctx, p):
        filas = [{"nombre": s.nombre, "tipo": TEXTO_TIPO_SUCURSAL.get(s.tipo, s.tipo)} for s in await ctx.sucursales()]
        return Resultado(para_modelo={"total": len(filas), "filas": filas})


class ConsultarInventario(Herramienta):
    nombre = "consultar_inventario"
    descripcion = "Stock actual según la última foto de inventario, con semáforo y días de cobertura."
    titulo_base = "Inventario"
    endpoints = (("GET", "/api/consulta/inventario",
                  frozenset({"sucursal_id", "busqueda", "categoria", "semaforo", "page", "page_size"})),)
    COLUMNAS = [Columna("producto", "Producto"), Columna("sucursal", "Sucursal"), Columna("stock", "Stock", "cantidad"),
                Columna("minimo", "Mínimo", "cantidad"), Columna("cobertura", "Cobertura"),
                Columna("ventas_30d", "Ventas 30 d", "cantidad"), Columna("semaforo", "Estado", "semaforo")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        producto: str | None = Field(None, description="Texto a buscar en el nombre.")
        categoria: str | None = None
        estado: Estado | None = None

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal, TEXTO_ESTADO.get(p.estado))

    async def ejecutar(self, ctx, p):
        nota_categoria = await _categoria_en_producto(ctx, p)
        params = {
            "sucursal_id": (await ctx.sucursal(p.sucursal)).id if p.sucursal else None,
            "categoria": await ctx.categoria(p.categoria) if p.categoria else None,
            "semaforo": p.estado,
        }
        texto = p.producto
        d = await ctx.get("/api/consulta/inventario", **params, busqueda=texto, page=1, page_size=MAX_FILAS)
        items, total, extra = d["items"], d["total"], {}
        if texto and total == 0 and CODIGO.fullmatch(texto.strip()):
            # El inventario busca en el nombre, no en el código (B1): «P1234» se resuelve primero a su producto
            producto = await ctx.producto(texto.strip())
            if isinstance(producto, Producto):
                texto = producto.nombre
                d = await ctx.get("/api/consulta/inventario", **params, busqueda=texto, page=1, page_size=MAX_FILAS)
                items, total = d["items"], d["total"]
        if texto and requiere_busqueda_por_palabras(texto, [i["nombre_producto"] for i in items], ctx.activa("busqueda")):
            # «arroz carolina 500» no es subcadena de «ARROZ CAROLINA *500 GR» (C4); «chocolate sol» está como
            # CHOC SOL; «PAPA * KL» encuentra RAPI PAPA y no las papas por kilo (B1)
            por_palabras, cortada = await ctx.buscar_por_palabras("/api/consulta/inventario", texto, "nombre_producto",
                                                                  **params)
            vistas = {(i["id_producto"], i["id_sucursal"]) for i in items}
            nuevas = [i for i in por_palabras if (i["id_producto"], i["id_sucursal"]) not in vistas]
            if nuevas or not items:
                items, total = items + nuevas, len(items) + len(nuevas)
                if cortada:
                    extra["nota"] = "Conteo sobre las primeras filas de cada búsqueda: puede haber más."
        filas = [{
            "producto": i["nombre_producto"], "sucursal": i["sucursal"],
            "stock": texto_cantidad(i["stock_disponible"], por_kilo(i["unidad"])),
            "minimo": texto_cantidad(i["stock_minimo"], por_kilo(i["unidad"])),
            "cobertura": texto_dias(i["dias_cobertura"]),
            "ventas_30d": texto_cantidad(i.get("ventas_30d", 0), por_kilo(i["unidad"])),
            "semaforo": i["semaforo"],
        } for i in items[:MAX_FILAS]]
        if ctx.activa("catalogo") and texto and nombra_presentacion(texto) and len({i["id_producto"] for i in items}) > 1:
            # Decisión del 23-oct (§3f): «Arroz Roa de 500» nombra una presentación y coincide con varios productos:
            # se pregunta cuál (P2), como en el pronóstico. Las búsquedas genéricas («jabones») siguen listando
            producto = await ctx.producto(texto)
            if isinstance(producto, Candidatos) and producto.estado == "ambiguo":
                return Resultado(para_modelo=producto.para_modelo())
            if isinstance(producto, Producto):
                items = [i for i in items if i["id_producto"] == producto.id]
                total = len(items)
        categorias = [i.get("categoria") or "" for i in items]
        if texto and (aclarar := aclaracion_abreviatura(texto, categorias)):
            extra.update(aclarar)
        elif texto and not p.categoria and len(distintas := sorted(set(categorias) - {""})) > 1:
            # Z5 (C10, «¿cuánta leche hay?»): el texto está en productos de varias categorías
            extra.update({"aclarar": True, "categorias": distintas,
                          "indicacion": f"«{texto}» está en productos de varias categorías: pregunta al usuario cuál "
                                        "quiere, con estas categorías, antes de responder con cifras."})
        if any(f["sucursal"] == "BODEGA_CENTRAL" for f in filas):
            # INV-65: la Bodega no vende; el Core API le pone las ventas de la red
            extra["nota_bodega"] = "En BODEGA_CENTRAL, ventas_30d son las de las 3 sucursales: la Bodega no vende."
        if ctx.activa("totales") and len(items) > 1 and len(items) <= MAX_FILAS and len({i["id_producto"] for i in items}) == 1:
            # C8 (24-oct): el modelo sumaba mal (dijo 58 de 68, h2-12); el total del stock lo da la herramienta
            kg = por_kilo(items[0]["unidad"])
            extra["stock_total"] = f"{texto_cantidad(sum(i['stock_disponible'] for i in items), kg)} en {len(items)} ubicaciones"
        if nota_categoria:
            extra["nota_categoria"] = nota_categoria
        fecha = d["fecha_inventario"]
        return Resultado(
            para_modelo={"fecha_dato": fecha, "total": total, "mostrando": len(filas),
                         "conteo": _conteo(total, len(filas), "filas de inventario"), **extra, "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, total) if filas else None,
            fecha_dato=fecha,
        )


def viernes_santo(anio: int) -> date:
    """El Viernes Santo (dos días antes de la Pascua, algoritmo gregoriano anónimo)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l_) // 433
    mes = (h + l_ - 7 * m + 90) // 25
    dia = (h + l_ - 7 * m + 33 * mes + 19) % 32
    return date(anio, mes, dia) - timedelta(days=2)


def ventana_habil(fecha_dato: str, dias: int = 15) -> tuple[date, date]:
    """Los días hábiles que cubre el pronóstico, desde el siguiente a la fecha de los datos. Hacia adelante son todos
    los días salvo los cierres que se conocen: el 1 de enero y el Viernes Santo (Parte II, 10.3)."""
    d, contados, desde = date.fromisoformat(fecha_dato), 0, None
    while contados < dias:
        d += timedelta(days=1)
        if (d.month, d.day) == (1, 1) or d == viernes_santo(d.year):
            continue
        desde, contados = desde or d, contados + 1
    return desde, d


BOGOTA = timezone(timedelta(hours=-5))      # Colombia no tiene horario de verano


def hoy() -> date:
    """La fecha de hoy en Bogotá, como la fecha de operación de INV-62 (se reemplaza en las pruebas). Con
    date.today() el contenedor, en UTC, pasaba al día siguiente desde las 7 de la noche."""
    return datetime.now(BOGOTA).date()


def al_dia(fecha_dato: str, respuesta: dict | None = None) -> dict:
    """INV-40 (pronóstico al día presente, punto 1.3 de la hoja de ruta): desde y hasta cuándo cubre el pronóstico, la
    fecha de hoy y si cae dentro. Con el servicio de INV-62 (fecha de operación = hoy), la ventana y los días sin
    datos llegan en la respuesta del pronóstico y se usan tal cual; con el servicio anterior, la ventana parte de la
    fecha de los datos y se calcula aquí."""
    r = respuesta or {}
    actual = hoy()
    if r.get("ventana_desde") and r.get("ventana_hasta"):
        desde, hasta = date.fromisoformat(str(r["ventana_desde"])), date.fromisoformat(str(r["ventana_hasta"]))
    else:
        desde, hasta = ventana_habil(fecha_dato)
    # El pronóstico está al día si hoy cae entre su punto de partida (la fecha de operación de INV-62, o la de los
    # datos con el servicio anterior) y el final de la ventana, que empieza el día hábil siguiente
    inicio = date.fromisoformat(str(r.get("fecha_operacion") or fecha_dato)[:10])
    dentro = inicio <= actual <= hasta
    salida = {"ventana": {"desde": desde.isoformat(), "hasta": hasta.isoformat()}, "hoy": actual.isoformat(),
              "hoy_en_ventana": dentro,
              **({"fecha_operacion": str(r["fecha_operacion"])} if r.get("fecha_operacion") else {})}
    if r.get("fuera_de_lo_medido"):
        salida["fuera_de_lo_medido"] = True
        salida["nota_fuera_de_lo_medido"] = ("Pronóstico fuera de lo medido: con más de 90 días hábiles sin datos de ventas no "
                                             "se comprobó su precisión. Hay que cargar las ventas recientes.")
    if r.get("dias_habiles_sin_datos"):
        salida["nota_datos"] = (f"El pronóstico parte de hoy, pero los datos llegan al {r.get('fecha_datos') or fecha_dato}: "
                                f"{r['dias_habiles_sin_datos']} días hábiles sin datos.")
    if actual > hasta:
        salida["nota_hoy"] = (f"Hoy ({actual.isoformat()}) queda después de la ventana del pronóstico: los datos llegan "
                              f"al {fecha_dato}. Para pronosticar desde hoy hay que cargar las ventas y el inventario "
                              "hasta hoy.")
    return salida


MESES_TEXTO = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MES_NOMBRADO = re.compile(r"^(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*(?: (\d{4}))?$")
RELLENO_PERIODO = {"el", "en", "de", "del", "mes", "pasado", "anterior"}
# INV-40, ronda de ajuste: «mes pasado» llegaba como un mes inventado (2024-03); se resuelve contra la fecha de los datos
RELATIVOS = {"este mes": 0, "mes actual": 0, "ultimo mes": 0, "mes pasado": -1, "mes anterior": -1,
             "este ano": "anio", "ano actual": "anio", "ano pasado": "anio-1", "ano anterior": "anio-1"}


def normalizar_periodo(periodo: str, fecha_datos: date | None) -> str:
    """INV-40 (decisión 2): «diciembre», «dic 2024» o «septiembre de 2025» → «AAAA-MM». Sin año, el último mes con
    ese nombre hasta la fecha de los datos («diciembre» con datos al 30-sep-2026 es 2025-12). Lo demás, igual."""
    relativo = RELATIVOS.get(" ".join(x for x in normal(periodo).split() if x not in {"el", "del"}))
    if relativo is not None:
        if fecha_datos is None:
            raise ErrorHerramienta(422, f"periodo «{periodo}»: falta la fecha de los datos.")
        if relativo == "anio":
            return str(fecha_datos.year)
        if relativo == "anio-1":
            return str(fecha_datos.year - 1)
        mes = fecha_datos.month + relativo
        return f"{fecha_datos.year - (mes < 1)}-{(mes - 1) % 12 + 1:02d}"
    m = MES_NOMBRADO.match(" ".join(x for x in normal(periodo).split() if x not in RELLENO_PERIODO))
    if not m:
        return periodo
    mes = 9 if m.group(1) == "set" else MESES_TEXTO.index(m.group(1)) + 1
    if m.group(2):
        anio = int(m.group(2))
    elif fecha_datos is None:
        raise ErrorHerramienta(422, f"periodo «{periodo}»: di el año, por ejemplo «{periodo} de 2025».")
    else:
        anio = fecha_datos.year if mes <= fecha_datos.month else fecha_datos.year - 1
    return f"{anio}-{mes:02d}"


async def rango_pedido(ctx: Contexto, periodo: str) -> tuple[str, str, str]:
    """El rango de un periodo del usuario; pide la fecha de los datos solo si nombra un mes sin año."""
    con_anio = PERIODO.match(periodo.strip().upper().replace("Q", "T")) or re.search(r"\d{4}", periodo)
    con_anio = con_anio and not RELATIVOS.get(" ".join(x for x in normal(periodo).split() if x not in {"el", "del"}))
    return rango_periodo(normalizar_periodo(periodo, None if con_anio else await ctx.fecha_ventas()))


class ListarAlertas(Herramienta):
    nombre = "listar_alertas"
    descripcion = ("Alertas activas. origen 'reglas': stock crítico o bajo, sin movimiento, rotación baja o "
                   "inconsistencias. origen 'ia': productos que el pronóstico de la IA ve en riesgo de agotarse o con "
                   "sobrestock. Sin origen, las de reglas. No filtra por fecha: son las activas a la fecha de los datos.")
    titulo_base = "Alertas"
    _params = frozenset({"sucursal_id", "tipo", "urgencia", "page", "page_size"})
    endpoints = (("GET", "/api/alertas", _params), ("GET", "/api/alertas/ml", _params))
    COLUMNAS = [Columna("producto", "Producto"), Columna("sucursal", "Sucursal"), Columna("tipo", "Tipo"),
                Columna("urgencia", "Urgencia", "urgencia"), Columna("detalle", "Detalle")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        origen: Literal["reglas", "ia"] | None = None
        # INV-40 (hallazgo H15): «¿Quieres ver las alertas críticas?» llegaba con tipo inconsistencia_inventario
        tipo: TipoAlerta | None = Field(None, description="Solo si la pregunta nombra el tipo de alerta. «Críticas», "
                                                          "«altas» o «medias» son la urgencia, no el tipo.")
        urgencia: UrgenciaAlerta | None = None

    @staticmethod
    def _ia(p) -> bool:
        return p.origen == "ia" or (p.origen is None and p.tipo in TIPOS_IA)

    def lenta(self, p):
        return self._ia(p)

    def etiqueta(self, p):
        return _etiqueta("Alertas con IA" if self._ia(p) else "Alertas", p.sucursal, TEXTO_TIPO_ALERTA.get(p.tipo),
                         TEXTO_URGENCIA.get(p.urgencia))

    async def ejecutar(self, ctx, p):
        ia = self._ia(p)
        if p.tipo and (p.tipo in TIPOS_IA) != ia:
            otro = "ia" if p.tipo in TIPOS_IA else "reglas"
            raise ErrorHerramienta(422, f"El tipo {p.tipo} es de las alertas de origen '{otro}': usa origen '{otro}' o quita el tipo.")
        d = await ctx.get(
            "/api/alertas/ml" if ia else "/api/alertas",
            sucursal_id=(await ctx.sucursal(p.sucursal)).id if p.sucursal else None,
            tipo=[p.tipo] if p.tipo else None, urgencia=[p.urgencia] if p.urgencia else None,
            page=1, page_size=MAX_FILAS,
        )
        filas = [{"producto": i.get("nombre_producto") or i.get("codigo_item"), "sucursal": i["sucursal"],
                  "tipo": i["tipo"], "urgencia": i["urgencia"], "detalle": i["detalle"]} for i in d["items"]]
        fecha, extra = d["fecha_inventario"], {}
        if ia:
            r = d["resumen"]
            extra = {"por_urgencia": {k: r[k] for k in ("critica", "alta", "media")},
                     "por_tipo": {k: r[k] for k in TIPOS_IA}}
        return Resultado(
            para_modelo={"fecha_dato": fecha, "origen": "ia" if ia else "reglas", "total": d["total"],
                         "mostrando": len(filas), "conteo": _conteo(d["total"], len(filas), "alertas"), **extra,
                         "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, d["total"]) if filas else None,
            fecha_dato=fecha,
        )


class ResumenAlertas(Herramienta):
    nombre = "resumen_alertas"
    descripcion = ("Conteo de las alertas de reglas de cada sucursal (críticas, altas y medias), por tipo y en total. Solo "
                   "filtra por sucursal.")
    titulo_base = "Resumen de alertas"
    endpoints = (("GET", "/api/alertas/resumen", frozenset({"sucursal_id"})),)
    COLUMNAS = [Columna("sucursal", "Sucursal"), Columna("critica", "Crítica", "numero"), Columna("alta", "Alta", "numero"),
                Columna("media", "Media", "numero"), Columna("total", "Total", "numero")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL_RESUMEN)

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal)

    async def ejecutar(self, ctx, p):
        d = await ctx.get("/api/alertas/resumen", sucursal_id=(await ctx.sucursal(p.sucursal)).id if p.sucursal else None)
        contar = lambda c: {k: texto_numero(c[k]) for k in ("critica", "alta", "media", "total")}  # noqa: E731
        filas = [{"sucursal": s["sucursal"], **contar(s["contadores"])} for s in d["items"]]
        fecha = d["fecha_inventario"]
        g = d["global_"]
        tarjetas = [tarjeta("Críticas", texto_numero(g["critica"]), tono="critico"),
                    tarjeta("Altas", texto_numero(g["alta"]), tono="atencion"), tarjeta("Medias", texto_numero(g["media"])),
                    tarjeta("Total", texto_numero(g["total"]))]
        dibujo = grafico("apiladas", "sucursal", [("critica", "Críticas"), ("alta", "Altas"), ("media", "Medias")],
                         [{"sucursal": s["sucursal"], **{k: s["contadores"][k] for k in ("critica", "alta", "media")}}
                          for s in d["items"]], "alertas") if len(d["items"]) > 1 else None
        return Resultado(
            para_modelo={"fecha_dato": fecha, "global": contar(d["global_"]),
                         "por_tipo": {k: texto_numero(v) for k, v in d["por_tipo"].items()}, "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, len(filas), tarjetas=tarjetas, grafico=dibujo)
            if filas else None,
            fecha_dato=fecha,
        )


async def _por_tienda(ctx: Contexto, tiendas: list[str], consulta) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Una consulta por sucursal física (T4, T9). Con una sola, su error es el de la herramienta;
    con varias, los errores se informan y se devuelve lo que sí respondió."""
    hechas, errores = [], []
    for tienda in tiendas:
        try:
            hechas.append((tienda, await consulta(tienda)))
        except ErrorHerramienta as exc:
            if len(tiendas) == 1:
                raise
            errores.append({"sucursal": tienda, "status": exc.status, "mensaje": exc.mensaje})
    if not hechas:
        raise ErrorHerramienta(errores[0]["status"], errores[0]["mensaje"])
    return hechas, errores


class PronosticarDemanda(Herramienta):
    nombre = "pronosticar_demanda"
    descripcion = ("Unidades que se venderán de un producto dado en los próximos 15 días hábiles. Para saber qué "
                   "productos se van a agotar, usa listar_alertas con origen 'ia'.")
    # P5 (23-oct, interruptor `catalogo`): con el stock y el veredicto
    descripcion_p5 = ("Unidades que se venderán de un producto dado en los próximos 15 días hábiles, con el stock actual "
                      "de cada sucursal y si alcanza. Para «¿alcanza?», «¿debo pedir?» o «¿tenemos suficiente?». Solo hacia "
                      "adelante: no pronostica fechas pasadas. Para saber qué productos se van a agotar, usa listar_alertas "
                      "con origen 'ia'.")
    # C4 (24-oct): sin el anzuelo, que llevaba a consultar sin producto («¿nos alcanza para la semana?», h2-11)
    descripcion_c4 = ("Unidades que se venderán de un producto dado en los próximos 15 días hábiles, con el stock actual "
                      "de cada sucursal y si alcanza. Solo con un producto concreto y solo hacia adelante: no pronostica "
                      "fechas pasadas. Para saber qué productos se van a agotar, usa listar_alertas con origen 'ia'.")
    titulo_base = "Pronóstico de demanda"
    endpoints = (("POST", "/api/ml/predict", frozenset({"producto_id", "sucursal_id", "horizonte"})),)

    class Parametros(BaseModel):
        producto: str = Field(min_length=1, description="Nombre o código del producto.")
        sucursal: Tienda | None = Field(None, description=POR_ROL)

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal)

    async def ejecutar(self, ctx, p):
        prod = await ctx.producto(p.producto)
        if r := _resuelto_o_candidatos(prod):
            return r
        tiendas = [p.sucursal] if p.sucursal else await ctx.tiendas_por_rol()
        hechas, errores = await _por_tienda(ctx, tiendas, lambda t: ctx.post(
            "/api/ml/predict", {"producto_id": prod.codigo, "sucursal_id": t, "horizonte": 15}))
        kg = por_kilo(prod.unidad)
        if not ctx.activa("catalogo"):
            return self._sin_cobertura(prod, tiendas, hechas, errores, kg)
        filas = []
        for t, d in hechas:
            stock = await self._stock(ctx, prod, t)
            filas.append({"sucursal": t, "demanda": texto_cantidad(d["prediccion_q50"], kg),
                          **({"stock": texto_cantidad(stock, kg)} if stock is not None else {}),
                          "veredicto": veredicto(stock, d["prediccion_q50"], d.get("intervalo_confianza"), kg,
                                                 con_cifras=ctx.activa("cobertura")),
                          "horizonte": HORIZONTE, "interpretacion": d["interpretacion"]})
        fecha = hechas[0][1]["fecha_features"]
        base = {"fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo}
        if len(tiendas) == 1:
            titulo = _etiqueta("Pronóstico", prod.nombre, tiendas[0])
            columnas = [Columna("demanda", "Demanda esperada", "cantidad"), Columna("stock", "Stock", "cantidad"),
                        Columna("veredicto", "¿Alcanza?"), Columna("horizonte", "Horizonte"),
                        Columna("interpretacion", "Interpretación")]
            return Resultado(para_modelo={**base, **filas[0]}, data=tabla(titulo, columnas, filas, 1, forma="tarjeta"),
                             fecha_dato=fecha)
        titulo = _etiqueta("Pronóstico", prod.nombre, f"{len(tiendas)} sucursales")
        columnas = [Columna("sucursal", "Sucursal"), Columna("demanda", "Demanda esperada", "cantidad"),
                    Columna("stock", "Stock", "cantidad"), Columna("veredicto", "¿Alcanza?"),
                    Columna("interpretacion", "Interpretación")]
        para_modelo = {**base, "horizonte": HORIZONTE, "total": len(filas),
                       "filas": [{k: f[k] for k in ("sucursal", "demanda", "stock", "veredicto", "interpretacion") if k in f}
                                 for f in filas]}
        if errores:
            para_modelo["errores"] = errores
        return Resultado(para_modelo=para_modelo, data=tabla(titulo, columnas, filas, len(filas)), fecha_dato=fecha)


    def _sin_cobertura(self, prod, tiendas, hechas, errores, kg) -> Resultado:
        """El pronóstico del 22-oct, sin el stock ni el veredicto (con `catalogo` apagado). INV-40: con la ventana que
        cubre frente a hoy, el promedio por día hábil, tarjetas y, con varias sucursales, barras."""
        filas = [{"sucursal": t, "demanda": texto_cantidad(d["prediccion_q50"], kg),
                  "por_dia_habil": texto_cantidad(d["prediccion_q50"] / 15, kg),
                  "horizonte": HORIZONTE, "interpretacion": d["interpretacion"]} for t, d in hechas]
        fecha = hechas[0][1]["fecha_features"]
        dia = al_dia(fecha, hechas[0][1])
        base = {"fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo, **dia}
        ventana = rango_corto(dia["ventana"]["desde"], dia["ventana"]["hasta"])
        if len(tiendas) == 1:
            titulo = _etiqueta("Pronóstico", prod.nombre, tiendas[0])
            columnas = [Columna("demanda", "Demanda esperada", "cantidad"), Columna("por_dia_habil", "Por día hábil", "cantidad"),
                        Columna("horizonte", "Horizonte"), Columna("interpretacion", "Interpretación")]
            alto = (hechas[0][1].get("intervalo_confianza") or {}).get("limite_superior")
            tarjetas = [tarjeta("Demanda esperada", filas[0]["demanda"], f"en {HORIZONTE}"),
                        tarjeta("Por día hábil", filas[0]["por_dia_habil"], "promedio"),
                        *([tarjeta("Límite de negocio", texto_cantidad(alto, kg))] if alto is not None else []),
                        tarjeta("Ventana", ventana, f"hoy: {fecha_corta(dia['hoy'])}", tono="neutro" if dia["hoy_en_ventana"] else "atencion")]
            return Resultado(para_modelo={**base, **filas[0]},
                             data=tabla(titulo, columnas, filas, 1, forma="tarjeta", tarjetas=tarjetas), fecha_dato=fecha)
        titulo = _etiqueta("Pronóstico", prod.nombre, f"{len(tiendas)} sucursales")
        columnas = [Columna("sucursal", "Sucursal"), Columna("demanda", "Demanda esperada", "cantidad"),
                    Columna("por_dia_habil", "Por día hábil", "cantidad"), Columna("interpretacion", "Interpretación")]
        para_modelo = {**base, "horizonte": HORIZONTE, "total": len(filas),
                       "filas": [{k: f[k] for k in ("sucursal", "demanda", "por_dia_habil", "interpretacion")} for f in filas]}
        if errores:
            para_modelo["errores"] = errores
        tarjetas = [tarjeta("Ventana", ventana, f"hoy: {fecha_corta(dia['hoy'])}", tono="neutro" if dia["hoy_en_ventana"] else "atencion")]
        dibujo = grafico("barras", "sucursal", [("demanda", "Demanda esperada")],
                         [{"sucursal": t, "demanda": d["prediccion_q50"]} for t, d in hechas], "kg" if kg else "unidades")
        return Resultado(para_modelo=para_modelo,
                         data=tabla(titulo, columnas, filas, len(filas), tarjetas=tarjetas, grafico=dibujo), fecha_dato=fecha)

    @staticmethod
    async def _stock(ctx: Contexto, prod: Producto, tienda: str) -> float | None:
        """INV-33 (P5): el stock del producto en la sucursal, de la misma foto del inventario."""
        s = await ctx.sucursal(tienda)
        d = await ctx.get("/api/consulta/inventario", sucursal_id=s.id, busqueda=prod.nombre, page=1, page_size=MAX_FILAS)
        return next((i["stock_disponible"] for i in d["items"] if i["id_producto"] == prod.id), None)


def veredicto(stock: float | None, demanda: float, intervalo: dict | None, kg: bool, con_cifras: bool = False) -> str:
    """INV-33 (P5, H4): si el stock alcanza para la demanda esperada, calculado aquí y no por el modelo. Con
    `con_cifras` (C4, 24-oct), el veredicto repite el stock y la demanda: con solo «faltan 178», el modelo omitía
    las dos cifras (h2-04)."""
    if stock is None:
        return "sin registro de inventario en esta sucursal"
    if stock < 0:
        return "no se sabe: el stock está negativo (inconsistencia)"
    cifras = (f"hay {texto_cantidad(stock, kg)} y se esperan vender {texto_cantidad(demanda, kg)} en {HORIZONTE}; "
              if con_cifras else "")
    if stock < demanda:
        return f"no alcanza: {cifras}faltan {texto_cantidad(demanda - stock, kg)} para la demanda esperada"
    alto = (intervalo or {}).get("limite_superior")
    if alto is not None and alto > demanda and stock < alto:
        return (f"alcanza para la demanda esperada{': ' + cifras.rstrip('; ') if cifras else ''}, pero está por debajo de "
                f"la cobertura recomendada ({texto_cantidad(alto, kg)})")
    return f"alcanza: {cifras.rstrip('; ')}" if cifras else "alcanza"


def nombra_presentacion(texto: str) -> bool:
    """«Arroz Roa de 500», «Leche Colanta * 1100»: el texto trae un tamaño (decisión del 23-oct, §3f)."""
    return any(p.isdigit() for p in palabras(texto)) and not CODIGO.fullmatch(texto.strip())


def _pesos(valor: float) -> str:
    return f"$ {texto_numero(valor)}"


MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def fecha_corta(iso: str) -> str:
    """«2026-10-01» → «1 oct 2026», como las pantallas (para las tarjetas; el modelo lee la fecha ISO)."""
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.day} {MESES_CORTOS[d.month - 1]} {d.year}"


def rango_corto(desde: str, hasta: str) -> str:
    """«1 oct a 15 oct 2026»; con años distintos, los dos años."""
    a, b = date.fromisoformat(str(desde)[:10]), date.fromisoformat(str(hasta)[:10])
    inicio = fecha_corta(desde) if a.year != b.year else f"{a.day} {MESES_CORTOS[a.month - 1]}"
    return f"{inicio} a {fecha_corta(hasta)}"


def _porcentaje(parte: float | None, total: float | None) -> str:
    """«23,4 %»; «—» si no hay total."""
    if not total or parte is None:
        return "—"
    return f"{texto_numero(100 * parte / total, 1)} %"


class HistorialVentas(Herramienta):
    """Ventas pasadas. Con un producto y sin agrupación, ventanas de 15 días hábiles para comparar con el pronóstico
    (INV-32). INV-33 (B4): con agrupación, o sin producto, cantidad, valor y margen por periodo del reporte de ventas
    del Core API, de un producto, una categoría o una sucursal."""
    nombre = "historial_ventas"
    descripcion = ("Ventas pasadas: cantidad, valor y margen por periodo. Sin filtros: las ventas de todas las sucursales que "
                   "el usuario puede ver, de los últimos 30 días; se puede filtrar por producto, sucursal o categoría. dias: los "
                   "últimos N días. periodo: un mes («diciembre», «mes pasado», «este mes», «2025-12»), un trimestre "
                   "(«2025-T4») o un año («2025», «este año»); no lo combines con agrupacion anio si es un mes. "
                   "Para el histórico (desde 2022), agrupacion 'anio' o 'trimestre'. Con un producto y sin "
                   "agrupación, días ni periodo: unidades en periodos de 15 días hábiles, para comparar con el pronóstico. "
                   "Para los productos más vendidos, productos_mas_vendidos.")
    titulo_base = "Historial de ventas"
    endpoints = (("GET", "/api/consulta/productos/{id_producto}/ventas", frozenset({"sucursal_id", "ventanas"})),
                 ("GET", "/api/reportes/ventas",
                  frozenset({"fecha_inicio", "fecha_fin", "sucursal_id", "categoria", "producto", "agrupacion"})))
    DESDE_SIEMPRE = "2000-01-01"

    class Parametros(BaseModel):
        producto: str | None = Field(None, description="Nombre o código del producto.")
        sucursal: Tienda | None = Field(None, description=POR_ROL)
        categoria: str | None = None
        agrupacion: Agrupacion | None = Field(None, description="Periodo de cada fila. «quincena»: 15 días hábiles.")
        dias: int | None = Field(None, ge=1, le=1500, description="Los últimos N días hasta la fecha de los datos.")
        # C1 (24-oct) oculto hasta INV-40 (decisión 2), que lo muestra y acepta un mes por nombre
        periodo: str | None = Field(None, description="Un periodo concreto: un mes («diciembre», «2025-12»), un "
                                                      "trimestre («2025-T4») o un año («2025»).")

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal, p.agrupacion if p.agrupacion != "quincena" else None)

    async def ejecutar(self, ctx, p):
        nota_categoria = await _categoria_en_producto(ctx, p)
        if p.producto and p.agrupacion in (None, "quincena") and p.dias is None and not p.periodo:
            r = await self._ventanas(ctx, p)
        else:
            r = await self._reporte(ctx, p)
        if nota_categoria and isinstance(r.para_modelo, dict):
            r.para_modelo["nota_categoria"] = nota_categoria
        return r

    async def _reporte(self, ctx, p):
        prod = None
        if p.producto:
            prod = await ctx.producto(p.producto)
            if r := _resuelto_o_candidatos(prod):
                return r
        rango = await rango_pedido(ctx, p.periodo) if p.periodo else None
        agrupacion = (p.agrupacion if p.agrupacion not in (None, "quincena")
                      else rango[2] if rango else ("mes" if p.dias is None else "semana"))
        params = {"sucursal_id": (await ctx.sucursal(p.sucursal)).id if p.sucursal else None,
                  "categoria": await ctx.categoria(p.categoria) if p.categoria else None,
                  "producto": prod.codigo if prod else None, "agrupacion": agrupacion}
        if rango:
            d = await ctx.get("/api/reportes/ventas", **params, fecha_inicio=rango[0], fecha_fin=rango[1])
        elif p.dias is None and agrupacion in ("trimestre", "anio"):
            d = await ctx.get("/api/reportes/ventas", **params, fecha_inicio=self.DESDE_SIEMPRE)
        else:
            # La fecha de los datos la da el Core API: se pide una vez para contar los días hacia atrás
            hasta = (await ctx.get("/api/reportes/ventas", **{**params, "agrupacion": "mes"}))["datos_hasta"]
            desde = (date.fromisoformat(hasta) - timedelta(days=(p.dias or 30) - 1)).isoformat()
            d = await ctx.get("/api/reportes/ventas", **params, fecha_inicio=desde, fecha_fin=hasta)
        kg = bool(prod) and por_kilo(prod.unidad)
        cantidad = (lambda v: texto_cantidad(v, kg)) if prod else texto_numero
        items = d["items"][-MAX_FILAS:]
        filas = [{"periodo": i["periodo"], "cantidad": cantidad(i["cantidad"]), "valor": _pesos(i["valor_total"]),
                  "margen": _pesos(i["margen"])} for i in items]
        total = len(d["items"])
        fecha = d["datos_hasta"]
        para_modelo = {"fecha_dato": fecha, "periodo": f"{max(d['fecha_inicio'], d['datos_desde'])} a {d['fecha_fin']}",
                       "agrupacion": agrupacion,
                       **({"producto": prod.nombre, "codigo": prod.codigo} if prod else {}),
                       **({"periodo_pedido": p.periodo} if p.periodo else {}),
                       **({"sucursal": p.sucursal} if p.sucursal else {}), **({"categoria": params["categoria"]} if p.categoria else {}),
                       "total": total, "mostrando": len(filas),
                       "conteo": _conteo(total, len(filas), "periodos").replace("los primeros", "los últimos"),
                       "totales": {"cantidad": cantidad(d["total_cantidad"]), "valor": _pesos(d["total_valor"]),
                                   "margen": _pesos(d["total_margen"])},
                       "filas": filas}
        if not prod:
            para_modelo["nota"] = "La cantidad suma unidades y kilos de productos distintos: compara mejor el valor."
        columnas = [Columna("periodo", "Periodo"), Columna("cantidad", "Cantidad", "cantidad"),
                    Columna("valor", "Valor"), Columna("margen", "Margen")]
        # INV-40: las cifras del periodo en tarjetas y el valor por periodo en barras (líneas si son muchos)
        tarjetas = [tarjeta("Ventas", _pesos(d["total_valor"]), rango_corto(max(d["fecha_inicio"], d["datos_desde"]), d["fecha_fin"])),
                    tarjeta("Margen", _pesos(d["total_margen"]),
                            f"{_porcentaje(d['total_margen'], d['total_valor'])} de las ventas"),
                    *([tarjeta("Cantidad", cantidad(d["total_cantidad"]))] if prod else [])]
        dibujo = grafico("linea" if len(items) > 12 else "barras", "periodo", [("valor", "Ventas"), ("margen", "Margen")],
                         [{"periodo": i["periodo"], "valor": i["valor_total"], "margen": i["margen"]} for i in items], "$")
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), columnas, filas, total, tarjetas=tarjetas, grafico=dibujo)
                         if filas else None, fecha_dato=fecha)

    async def _ventanas(self, ctx, p):
        prod = await ctx.producto(p.producto)
        if r := _resuelto_o_candidatos(prod):
            return r
        tiendas = [p.sucursal] if p.sucursal else await ctx.tiendas_por_rol()
        # Con una sucursal, ~5,5 meses; con las 3, las 3 últimas de cada una (9 filas, criterio 4)
        ventanas = 8 if len(tiendas) == 1 else 3

        async def consulta(tienda):
            s = await ctx.sucursal(tienda)
            return await ctx.get(f"/api/consulta/productos/{prod.id}/ventas", sucursal_id=s.id, ventanas=ventanas)

        hechas, errores = await _por_tienda(ctx, tiendas, consulta)
        filas, sumas = [], {}
        for tienda, d in hechas:
            kg = por_kilo(d["unidad"])
            filas += [{"sucursal": tienda, "desde": v["desde"], "hasta": v["hasta"], "ventas": texto_cantidad(v["unidades"], kg)}
                      for v in d["ventanas"]]
            sumas[tienda] = texto_cantidad(sum(v["unidades"] for v in d["ventanas"]), kg)
        fecha = hechas[0][1]["fecha_fin"]
        columnas = ([Columna("sucursal", "Sucursal")] if len(tiendas) > 1 else []) + [
            Columna("desde", "Desde", "fecha"), Columna("hasta", "Hasta", "fecha"), Columna("ventas", "Ventas", "cantidad")]
        titulo = _etiqueta("Ventas", prod.nombre, tiendas[0] if len(tiendas) == 1 else f"{len(tiendas)} sucursales")
        # INV-40: las ventanas de 15 días hábiles en barras, una serie por sucursal
        por_ventana: dict[str, dict] = {}
        for tienda, d in hechas:
            for v in d["ventanas"]:
                por_ventana.setdefault(str(v["hasta"]), {"hasta": str(v["hasta"])})[tienda] = v["unidades"]
        dibujo = grafico("barras", "hasta", [(t, t) for t, _ in hechas], [por_ventana[k] for k in sorted(por_ventana)],
                         "kg" if hechas and por_kilo(hechas[0][1]["unidad"]) else "unidades")
        para_modelo = {"fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo, "periodo": HORIZONTE,
                       "suma_por_sucursal": sumas, "total": len(filas), "filas": filas}
        if errores:
            para_modelo["errores"] = errores
        return Resultado(para_modelo=para_modelo, data=tabla(titulo, columnas, filas, len(filas), grafico=dibujo),
                         fecha_dato=fecha)


class ProductosMasVendidos(Herramienta):
    """INV-40 (decisión 2, hallazgo H14): el ranking de productos por valor vendido, sobre el top del Core API, que ya
    filtra por el rol. La cantidad mezcla unidades y kilos, así que el orden es por valor."""
    nombre = "productos_mas_vendidos"
    descripcion = ("Ranking de los productos más vendidos por valor, con su participación en las ventas, cantidad y margen. "
                   "Sin periodo ni días: el último mes de los datos. periodo: un mes («diciembre», «2025-12»), un trimestre "
                   "(«2025-T4») o un año («2025»); dias: los últimos N días. Se puede filtrar por sucursal o categoría.")
    titulo_base = "Productos más vendidos"
    endpoints = (("GET", "/api/reportes/ventas/top-productos",
                  frozenset({"limite", "fecha_inicio", "fecha_fin", "sucursal_id", "categoria"})),)
    COLUMNAS = [Columna("producto", "Producto"), Columna("valor", "Valor"), Columna("participacion", "Participación"),
                Columna("cantidad", "Cantidad", "cantidad"), Columna("margen", "Margen")]

    class Parametros(BaseModel):
        sucursal: Tienda | None = Field(None, description=POR_ROL)
        categoria: str | None = None
        periodo: str | None = Field(None, description="Un mes («diciembre», «2025-12»), un trimestre («2025-T4») o un "
                                                      "año («2025»).")
        dias: int | None = Field(None, ge=1, le=1500, description="Los últimos N días hasta la fecha de los datos.")
        limite: int | None = Field(None, ge=1, le=MAX_FILAS, description=f"Cuántos productos, hasta {MAX_FILAS}.")

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal, p.categoria, p.periodo)

    async def ejecutar(self, ctx, p):
        hasta = await ctx.fecha_ventas()
        if p.periodo:
            desde, fin, _ = await rango_pedido(ctx, p.periodo)
            fin = min(fin, hasta.isoformat())
        else:
            desde = (hasta - timedelta(days=p.dias - 1)).isoformat() if p.dias else hasta.replace(day=1).isoformat()
            fin = hasta.isoformat()
        categoria = await ctx.categoria(p.categoria) if p.categoria else None
        d = await ctx.get("/api/reportes/ventas/top-productos", limite=p.limite or MAX_FILAS, fecha_inicio=desde,
                          fecha_fin=fin, sucursal_id=(await ctx.sucursal(p.sucursal)).id if p.sucursal else None,
                          categoria=categoria)
        filas = [{"producto": i["nombre"], "categoria": i["categoria"], "valor": _pesos(i["valor_total"]),
                  "participacion": f"{texto_numero(round(i['participacion_pct'], 1))} %",
                  "cantidad": texto_numero(i["cantidad"]), "margen": _pesos(i["margen"])} for i in d["items"]]
        fecha = hasta.isoformat()
        para_modelo = {"fecha_dato": fecha, "periodo": f"{d['fecha_inicio']} a {d['fecha_fin']}",
                       **({"periodo_pedido": p.periodo} if p.periodo else {}),
                       **({"sucursal": p.sucursal} if p.sucursal else {}), **({"categoria": categoria} if categoria else {}),
                       "orden": "por valor vendido, de mayor a menor",
                       "ventas_del_periodo": _pesos(d["total_valor"]),
                       "total": len(filas), "mostrando": len(filas),
                       "nota": "La cantidad suma unidades y kilos según el producto: el ranking es por valor.",
                       "filas": filas}
        tarjetas = [tarjeta("Ventas del periodo", _pesos(d["total_valor"]), rango_corto(d["fecha_inicio"], d["fecha_fin"])),
                    tarjeta("Productos en el ranking", texto_numero(len(filas)), "por valor vendido")]
        dibujo = grafico("barras_h", "producto", [("valor", "Valor vendido")],
                         [{"producto": i["nombre"], "valor": i["valor_total"]} for i in d["items"]], "$")
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), self.COLUMNAS, filas, len(filas), tarjetas=tarjetas, grafico=dibujo)
                         if filas else None, fecha_dato=fecha)


TONO_SEMAFORO = {"ok": "ok", "bajo": "atencion", "critico": "critico", "inconsistencia": "atencion"}


async def _catalogo_producto(ctx: Contexto, prod: Producto) -> dict:
    """INV-40: precio, costo, margen e IVA del catálogo (los de la última venta registrada) y los proveedores."""
    d = await ctx.get(f"/api/consulta/productos/{prod.id}")
    return {"precio": _pesos(d["precio_base"]) if d.get("precio_base") is not None else "sin dato",
            "costo": _pesos(d["costo_base"]) if d.get("costo_base") is not None else "sin dato",
            "margen": f"{texto_numero(d['margen_pct'], 1)} %" if d.get("margen_pct") is not None else "sin dato",
            "iva": f"{texto_numero(d['iva_pct'])} %", "proveedores": d.get("proveedores") or [],
            "_precio": d.get("precio_base"), "_costo": d.get("costo_base")}


async def _rango_o_ultimos(ctx: Contexto, periodo: str | None, dias: int | None) -> tuple[str, str]:
    """El periodo pedido, o los últimos N días (30 por defecto) hasta la fecha de los datos."""
    hasta = await ctx.fecha_ventas()
    if periodo:
        desde, fin, _ = await rango_pedido(ctx, periodo)
        return desde, min(fin, hasta.isoformat())
    return (hasta - timedelta(days=(dias or 30) - 1)).isoformat(), hasta.isoformat()


class FichaProducto(Herramienta):
    """INV-40 (ampliación del 18-nov): el estado general de un producto en una sola consulta, para mostrarlo en
    tarjetas y una gráfica: catálogo, stock y semáforo por ubicación, pronóstico y ventas recientes con su margen."""
    nombre = "ficha_producto"
    descripcion = ("Ficha completa de un producto: precio, costo y margen del catálogo, stock y estado del semáforo en "
                   "cada ubicación, pronóstico de los próximos 15 días hábiles, alertas de inventario y ventas de los "
                   "últimos 30 días con su margen. Solo si piden la ficha, el estado general o varias de esas cosas a la "
                   "vez. Para una sola (cuánto hay, cuánto se vendió, el pronóstico, si alcanza o si hay que pedir), usa la "
                   "herramienta de esa cosa.")
    titulo_base = "Ficha de producto"
    endpoints = (("GET", "/api/consulta/productos/{id_producto}", frozenset()),
                 ("GET", "/api/consulta/inventario", frozenset({"busqueda", "page", "page_size"})),
                 ("POST", "/api/ml/predict", frozenset({"producto_id", "sucursal_id", "horizonte"})),
                 ("GET", "/api/reportes/ventas", frozenset({"fecha_inicio", "fecha_fin", "producto", "agrupacion"})))
    COLUMNAS = [Columna("ubicacion", "Ubicación"), Columna("stock", "Stock", "cantidad"), Columna("estado", "Estado"),
                Columna("cobertura", "Cobertura", "cantidad"), Columna("demanda", "Demanda esperada", "cantidad"),
                Columna("veredicto", "¿Alcanza?")]

    class Parametros(BaseModel):
        producto: str = Field(min_length=1, description="Nombre o código del producto.")

    def lenta(self, p):
        return True

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.producto)

    async def ejecutar(self, ctx, p):
        prod = await ctx.producto(p.producto)
        if r := _resuelto_o_candidatos(prod):
            return r
        kg = por_kilo(prod.unidad)
        catalogo = await _catalogo_producto(ctx, prod)
        inventario = await ctx.get("/api/consulta/inventario", busqueda=prod.nombre, page=1, page_size=MAX_FILAS)
        ubicaciones = [i for i in inventario["items"] if i["id_producto"] == prod.id]
        tiendas = [i["sucursal"] for i in ubicaciones if i["sucursal"] != "BODEGA_CENTRAL"]
        hechas, errores = await _por_tienda(ctx, tiendas, lambda t: ctx.post(
            "/api/ml/predict", {"producto_id": prod.codigo, "sucursal_id": t, "horizonte": 15})) if tiendas else ([], [])
        pronostico = dict(hechas)
        desde, hasta = await _rango_o_ultimos(ctx, None, 30)
        ventas = await ctx.get("/api/reportes/ventas", producto=prod.codigo, fecha_inicio=desde, fecha_fin=hasta,
                               agrupacion="mes")
        filas = []
        for i in ubicaciones:
            pr = pronostico.get(i["sucursal"])
            filas.append({"ubicacion": i["sucursal"], "stock": texto_cantidad(i["stock_disponible"], kg),
                          "estado": TEXTO_ESTADO.get(i["semaforo"], i["semaforo"]), "cobertura": texto_dias(i["dias_cobertura"]),
                          **({"demanda": texto_cantidad(pr["prediccion_q50"], kg),
                              "veredicto": veredicto(i["stock_disponible"], pr["prediccion_q50"],
                                                     pr.get("intervalo_confianza"), kg)} if pr else {})})
        en_riesgo = [i["sucursal"] for i in ubicaciones if i["semaforo"] in ("bajo", "critico", "inconsistencia")]
        stock_total = sum(i["stock_disponible"] for i in ubicaciones)
        demanda_total = sum(d["prediccion_q50"] for d in pronostico.values())
        fecha = inventario["fecha_inventario"]
        primero = next(iter(pronostico.values()), None)
        dia = al_dia(primero["fecha_features"], primero) if primero else {}
        para_modelo = {
            "fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo, "categoria": prod.categoria,
            "catalogo": {k: v for k, v in catalogo.items() if not k.startswith("_")},
            "stock_total": texto_cantidad(stock_total, kg), "ubicaciones": len(ubicaciones),
            "alertas_de_inventario": {"en_riesgo_o_inconsistencia": en_riesgo,
                                      "nota": "Bajo, crítico o inconsistencia del semáforo en esas ubicaciones."},
            "pronostico": {"demanda_total": texto_cantidad(demanda_total, kg), "horizonte": HORIZONTE, **dia},
            "ventas_30_dias": {"periodo": f"{desde} a {hasta}", "valor": _pesos(ventas["total_valor"]),
                               "cantidad": texto_cantidad(ventas["total_cantidad"], kg), "margen": _pesos(ventas["total_margen"]),
                               "margen_pct": _porcentaje(ventas["total_margen"], ventas["total_valor"])},
            "total": len(filas), "filas": filas,
        }
        if errores:
            para_modelo["errores"] = errores
        tarjetas = [tarjeta("Precio", catalogo["precio"], f"costo {catalogo['costo']} · IVA {catalogo['iva']}"),
                    tarjeta("Margen de catálogo", catalogo["margen"], "del precio de venta"),
                    tarjeta("Stock total", texto_cantidad(stock_total, kg), f"en {len(ubicaciones)} ubicaciones"),
                    tarjeta("Demanda esperada", texto_cantidad(demanda_total, kg), f"en {HORIZONTE}"),
                    tarjeta("Ventas 30 días", _pesos(ventas["total_valor"]),
                            f"margen {_pesos(ventas['total_margen'])} ({_porcentaje(ventas['total_margen'], ventas['total_valor'])})"),
                    tarjeta("Alertas de inventario", texto_numero(len(en_riesgo)),
                            ", ".join(en_riesgo) if en_riesgo else "ninguna ubicación en riesgo",
                            tono="critico" if en_riesgo else "ok")]
        dibujo = grafico("barras", "ubicacion", [("stock", "Stock"), ("demanda", "Demanda esperada")],
                         [{"ubicacion": i["sucursal"], "stock": i["stock_disponible"],
                           "demanda": (pronostico.get(i["sucursal"]) or {}).get("prediccion_q50")} for i in ubicaciones],
                         "kg" if kg else "unidades")
        return Resultado(para_modelo=para_modelo,
                         data=tabla(_etiqueta(self.titulo_base, prod.nombre), self.COLUMNAS, filas, len(filas),
                                    tarjetas=tarjetas, grafico=dibujo), fecha_dato=fecha)


class PreciosYMargenes(Herramienta):
    """INV-40 (ampliación del 18-nov, decisión «catálogo y margen realizado»): precios y márgenes de un producto, o el
    reporte de una categoría desglosado por producto. La tabla llega hasta 50 filas; el modelo lee las 10 primeras."""
    nombre = "precios_y_margenes"
    descripcion = ("Precios y márgenes. Con un producto: precio, costo, margen e IVA del catálogo y el margen realizado "
                   "en sus ventas de un periodo. Con una categoría: el reporte de la categoría desglosado por producto "
                   "(ventas, margen realizado, participación y precio de catálogo), de mayor a menor valor vendido. "
                   "Sin periodo ni días: los últimos 30 días.")
    titulo_base = "Precios y márgenes"
    FILAS_TABLA = 50
    endpoints = (("GET", "/api/consulta/productos/{id_producto}", frozenset()),
                 ("GET", "/api/consulta/productos", frozenset({"categoria", "page", "page_size"})),
                 ("GET", "/api/reportes/ventas", frozenset({"fecha_inicio", "fecha_fin", "sucursal_id", "producto", "agrupacion"})),
                 ("GET", "/api/reportes/ventas/top-productos",
                  frozenset({"limite", "fecha_inicio", "fecha_fin", "sucursal_id", "categoria"})))
    COLUMNAS = [Columna("producto", "Producto"), Columna("valor", "Ventas"), Columna("margen", "Margen realizado"),
                Columna("margen_pct", "Margen %"), Columna("participacion", "Participación"),
                Columna("precio", "Precio de catálogo")]

    class Parametros(BaseModel):
        producto: str | None = Field(None, description="Nombre o código del producto.")
        categoria: str | None = Field(None, description="Categoría del catálogo, para el reporte desglosado por producto.")
        sucursal: Tienda | None = Field(None, description=POR_ROL)
        periodo: str | None = Field(None, description="Un mes («diciembre», «2025-12»), un trimestre («2025-T4») o un "
                                                      "año («2025»).")
        dias: int | None = Field(None, ge=1, le=1500, description="Los últimos N días hasta la fecha de los datos.")

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.producto or p.categoria, p.sucursal, p.periodo)

    async def ejecutar(self, ctx, p):
        if not p.producto and not p.categoria:
            raise ErrorHerramienta(422, "Indica un producto o una categoría.")
        desde, hasta = await _rango_o_ultimos(ctx, p.periodo, p.dias)
        sucursal_id = (await ctx.sucursal(p.sucursal)).id if p.sucursal else None
        if p.producto:
            return await self._producto(ctx, p, desde, hasta, sucursal_id)
        return await self._categoria(ctx, p, desde, hasta, sucursal_id)

    async def _producto(self, ctx, p, desde, hasta, sucursal_id):
        prod = await ctx.producto(p.producto)
        if r := _resuelto_o_candidatos(prod):
            return r
        kg = por_kilo(prod.unidad)
        catalogo = await _catalogo_producto(ctx, prod)
        v = await ctx.get("/api/reportes/ventas", producto=prod.codigo, fecha_inicio=desde, fecha_fin=hasta,
                          sucursal_id=sucursal_id, agrupacion="mes")
        realizado = {"periodo": f"{desde} a {hasta}", "valor": _pesos(v["total_valor"]),
                     "cantidad": texto_cantidad(v["total_cantidad"], kg), "costo": _pesos(v["total_valor"] - v["total_margen"]),
                     "margen": _pesos(v["total_margen"]), "margen_pct": _porcentaje(v["total_margen"], v["total_valor"])}
        fila = {"producto": prod.nombre, "valor": realizado["valor"], "margen": realizado["margen"],
                "margen_pct": realizado["margen_pct"], "participacion": "—", "precio": catalogo["precio"]}
        para_modelo = {"fecha_dato": v["datos_hasta"], "producto": prod.nombre, "codigo": prod.codigo,
                       "catalogo": {k: val for k, val in catalogo.items() if not k.startswith("_")},
                       "margen_realizado": realizado, **({"sucursal": p.sucursal} if p.sucursal else {}),
                       "nota": "El catálogo usa el precio y el costo de la última venta registrada; el margen realizado "
                               "sale de las ventas del periodo."}
        tarjetas = [tarjeta("Precio", catalogo["precio"], f"IVA {catalogo['iva']}"),
                    tarjeta("Costo", catalogo["costo"]), tarjeta("Margen de catálogo", catalogo["margen"]),
                    tarjeta("Ventas del periodo", realizado["valor"], rango_corto(desde, hasta)),
                    tarjeta("Margen realizado", realizado["margen"], realizado["margen_pct"])]
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), self.COLUMNAS, [fila], 1, tarjetas=tarjetas), fecha_dato=v["datos_hasta"])

    async def _categoria(self, ctx, p, desde, hasta, sucursal_id):
        categoria = await ctx.categoria(p.categoria)
        d = await ctx.get("/api/reportes/ventas/top-productos", limite=self.FILAS_TABLA, fecha_inicio=desde,
                          fecha_fin=hasta, sucursal_id=sucursal_id, categoria=categoria)
        precios: dict[int, float | None] = {}
        pagina = 1
        while True:                     # el precio de catálogo de los productos de la categoría
            lista = await ctx.get("/api/consulta/productos", categoria=categoria, page=pagina, page_size=100)
            precios.update({x["id_producto"]: x.get("precio_base") for x in lista["items"]})
            if pagina >= lista.get("pages", 1):
                break
            pagina += 1
        filas = [{"producto": i["nombre"], "valor": _pesos(i["valor_total"]), "margen": _pesos(i["margen"]),
                  "margen_pct": _porcentaje(i["margen"], i["valor_total"]),
                  "participacion": f"{texto_numero(i['participacion_pct'], 1)} %",
                  "precio": _pesos(precios[i["id_producto"]]) if precios.get(i["id_producto"]) is not None else "sin dato"}
                 for i in d["items"]]
        valor, margen = sum(i["valor_total"] for i in d["items"]), sum(i["margen"] for i in d["items"])
        fecha = (await ctx.fecha_ventas()).isoformat()
        para_modelo = {"fecha_dato": fecha, "categoria": categoria, "periodo": f"{d['fecha_inicio']} a {d['fecha_fin']}",
                       **({"sucursal": p.sucursal} if p.sucursal else {}),
                       "orden": "por valor vendido, de mayor a menor",
                       "totales_de_los_productos": {"valor": _pesos(valor), "margen": _pesos(margen),
                                                    "margen_pct": _porcentaje(margen, valor)},
                       "total": len(filas), "mostrando": min(len(filas), MAX_FILAS),
                       "conteo": _conteo(len(filas), min(len(filas), MAX_FILAS), "productos con ventas"),
                       "filas": filas[:MAX_FILAS]}
        tarjetas = [tarjeta("Ventas", _pesos(valor), rango_corto(d["fecha_inicio"], d["fecha_fin"])),
                    tarjeta("Margen realizado", _pesos(margen), _porcentaje(margen, valor)),
                    tarjeta("Productos", texto_numero(len(filas)), "con ventas en el periodo")]
        dibujo = grafico("barras_h", "producto", [("valor", "Ventas"), ("margen", "Margen")],
                         [{"producto": i["nombre"], "valor": i["valor_total"], "margen": i["margen"]}
                          for i in d["items"][:MAX_FILAS]], "$")
        titulo = _etiqueta(self.titulo_base, categoria, p.sucursal, p.periodo)        # con el nombre del catálogo
        return Resultado(para_modelo=para_modelo,
                         data=tabla(titulo, self.COLUMNAS, filas, len(filas), tarjetas=tarjetas, grafico=dibujo)
                         if filas else None, fecha_dato=fecha)


class RecomendarCompras(Herramienta):
    nombre = "recomendar_compras"
    descripcion = "Qué comprar a los proveedores: compras sugeridas con cantidad, urgencia y fecha de pedido."
    titulo_base = "Compras sugeridas"
    endpoints = (("GET", "/api/ml/recomendaciones/compras", frozenset({"sucursal", "categoria", "urgencia", "incluir_detalle"})),)

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        categoria: str | None = None
        urgencia: UrgenciaCompra | None = None

    def lenta(self, p):
        return True

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal, TEXTO_URGENCIA.get(p.urgencia))

    async def ejecutar(self, ctx, p):
        d = await ctx.get("/api/ml/recomendaciones/compras", sucursal=p.sucursal,
                          categoria=await ctx.categoria(p.categoria) if p.categoria else None,
                          urgencia=p.urgencia, incluir_detalle=False)
        filtro = d["filtros_aplicados"]
        fisica = filtro["sucursal"] not in (None, "BODEGA_CENTRAL")
        compras = sorted(d["compras"], key=lambda c: (ORDEN_URGENCIA_COMPRA.get(c["urgencia"], 9),
                                                      c["dias_hasta_agotarse"], c.get("nombre_producto") or ""))
        filas = []
        for c in compras[:MAX_FILAS]:
            kg = c["unidad"] == "kg"
            fila = {"producto": c.get("nombre_producto") or c["producto_id"], "destino": c["destino"],
                    "cantidad": texto_cantidad(c["cantidad"], kg), "urgencia": c["urgencia"], "fecha_pedido": c["fecha_pedido"]}
            if fisica and c.get("necesidad_sucursal") is not None:
                fila["para_sucursal"] = texto_cantidad(c["necesidad_sucursal"], kg)
            filas.append(fila)
        r = d["resumen"]
        cantidad = [texto_cantidad(r["cantidad"]["unidad"], False)] + ([texto_cantidad(r["cantidad"]["kg"], True)] if r["cantidad"]["kg"] else [])
        para_modelo = {
            "fecha_dato": d["fecha_inventario"], "total": r["lineas"], "mostrando": len(filas),
            "conteo": _conteo(r["lineas"], len(filas), "líneas de compra"),
            "resumen": {"lineas": texto_numero(r["lineas"]), "productos": texto_numero(r["productos"]),
                        "cantidad": " y ".join(cantidad), "cubiertos_con_traslado": texto_numero(r["cubiertos_por_bodega"])},
            "filtro": {"sucursal": filtro["sucursal"], "por_tu_rol": filtro["sucursal_por_rol"]},
        }
        if fisica:
            # R1 de INV-21: la cantidad es la de toda la compra (C16)
            para_modelo["nota"] = f"cantidad es la de toda la compra; para_sucursal es la parte de {filtro['sucursal']}."
        para_modelo["filas"] = filas
        columnas = [Columna("producto", "Producto"), Columna("destino", "Destino"), Columna("cantidad", "Cantidad", "cantidad")]
        if fisica:
            columnas.append(Columna("para_sucursal", f"Para {filtro['sucursal']}", "cantidad"))
        columnas += [Columna("urgencia", "Urgencia", "urgencia"), Columna("fecha_pedido", "Fecha de pedido", "fecha")]
        urgentes = sum(c["urgencia"] == "urgente" for c in compras)
        tarjetas = [tarjeta("Líneas de compra", texto_numero(r["lineas"]), f"{texto_numero(r['productos'])} productos"),
                    tarjeta("Urgentes", texto_numero(urgentes), tono="critico" if urgentes else "ok"),
                    tarjeta("Cubiertos con traslado", texto_numero(r["cubiertos_por_bodega"]), "sin comprar")]
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), columnas, filas, r["lineas"], tarjetas=tarjetas) if filas else None,
                         fecha_dato=d["fecha_inventario"])


class ResumenInventario(Herramienta):
    """INV-33, brecha B2: el estado general del inventario, sin listar productos."""
    nombre = "resumen_inventario"
    descripcion = ("Cuántos productos hay en cada estado del semáforo (ok, bajo, crítico, inconsistencia) y en riesgo, en "
                   "cada sucursal y en total. Para el estado general del inventario o de las sucursales; para ver "
                   "productos, consultar_inventario.")
    titulo_base = "Resumen del inventario"
    endpoints = (("GET", "/api/consulta/inventario/resumen", frozenset({"sucursal_id"})),)
    COLUMNAS = [Columna("sucursal", "Sucursal"), Columna("ok", "OK", "numero"), Columna("bajo", "Bajo", "numero"),
                Columna("critico", "Crítico", "numero"), Columna("inconsistencia", "Inconsistencia", "numero"),
                Columna("en_riesgo", "En riesgo", "numero"), Columna("total", "Total", "numero")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL_RESUMEN)

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal)

    async def ejecutar(self, ctx, p):
        d = await ctx.get("/api/consulta/inventario/resumen",
                          sucursal_id=(await ctx.sucursal(p.sucursal)).id if p.sucursal else None)

        def contar(c: dict) -> dict:
            # «En riesgo» es bajo + crítico, el mismo indicador del dashboard: el modelo no tiene que sumar
            return {**{k: texto_numero(c[k]) for k in ESTADOS}, "en_riesgo": texto_numero(c["bajo"] + c["critico"]),
                    "total": texto_numero(c["total"])}
        filas = [{"sucursal": s["sucursal"], **contar(s["contadores"])} for s in d["items"]]
        fecha = d["fecha_inventario"]
        g = d["global_"]
        tarjetas = [tarjeta("OK", texto_numero(g["ok"]), tono="ok"), tarjeta("Bajo", texto_numero(g["bajo"]), tono="atencion"),
                    tarjeta("Crítico", texto_numero(g["critico"]), tono="critico"),
                    tarjeta("Inconsistencia", texto_numero(g["inconsistencia"]), tono="atencion"),
                    tarjeta("En riesgo", texto_numero(g["bajo"] + g["critico"]), "bajo + crítico",
                            tono="critico" if g["critico"] else "neutro")]
        dibujo = grafico("apiladas", "sucursal", [("ok", "OK"), ("bajo", "Bajo"), ("critico", "Crítico"),
                                                  ("inconsistencia", "Inconsistencia")],
                         [{"sucursal": s["sucursal"], **{k: s["contadores"][k] for k in ESTADOS}} for s in d["items"]],
                         "productos") if len(d["items"]) > 1 else None
        return Resultado(
            para_modelo={"fecha_dato": fecha, "global": contar(d["global_"]), "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, len(filas), tarjetas=tarjetas, grafico=dibujo)
            if filas else None,
            fecha_dato=fecha,
        )


class RecomendarTraslados(Herramienta):
    """INV-33, brecha B3. El Core API filtra la sucursal por origen o por destino a la vez; la dirección se
    separa aquí, sobre las filas que devuelve."""
    nombre = "recomendar_traslados"
    # INV-40 (decisión 3, INV-77 y hallazgo H13): origen y destino visibles. Con sucursal y dirección, la bodega pedía
    # «despachar a las sucursales» como destino = BODEGA_CENTRAL y la respuesta era «no hay»
    descripcion = ("Traslados sugeridos de stock entre sucursales y desde la Bodega Central: producto, origen, destino, "
                   "cantidad, urgencia y llegada. origen: de dónde salen («desde X», «de X a las demás»); para la Bodega "
                   "Central, despachar, enviar o mandar a las sucursales es origen BODEGA_CENTRAL. destino: la tienda que "
                   "los recibe («mover a X», «enviar a X», «para X»); la Bodega Central nunca es destino. Sin origen ni "
                   "destino: todos los que ve el usuario. Con producto, solo los de ese producto.")
    CAMPOS_22OCT = ("sucursal", "direccion")
    titulo_base = "Traslados sugeridos"
    endpoints = (("GET", "/api/ml/recomendaciones/transferencias", frozenset({"sucursal", "categoria", "urgencia"})),)
    COLUMNAS = [Columna("producto", "Producto"), Columna("origen", "Origen"), Columna("destino", "Destino"),
                Columna("cantidad", "Cantidad", "cantidad"), Columna("urgencia", "Urgencia", "urgencia"),
                Columna("fecha_llegada", "Llega", "fecha")]

    class Parametros(BaseModel):
        # Los del 22-oct; con `catalogo`, el esquema muestra destino y origen en su lugar (P6, «mover a La 21» se leía
        # como «desde La 21», h-03 del holdout). Se aceptan los cuatro: el esquema decide cuáles ve el modelo
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        direccion: Direccion | None = Field(None, description="Solo con sucursal: 'hacia' (llegan a ella) o 'desde' (salen de ella).")
        destino: Tienda | None = Field(None, description="La tienda a la que llegan los traslados (nunca la Bodega Central).")
        origen: Sucursal | None = Field(None, description="La sucursal o BODEGA_CENTRAL de la que salen los traslados.")
        categoria: str | None = None
        urgencia: UrgenciaTraslado | None = None
        producto: str | None = Field(None, description="Nombre o código del producto.")

    def lenta(self, p):
        return True                                     # la primera llamada tras una foto nueva tarda unos 20 s

    def etiqueta(self, p):
        if p.destino or p.origen:
            lugar = " ".join(x for x in (f"desde {p.origen}" if p.origen else "", f"hacia {p.destino}" if p.destino else "") if x)
        else:
            lugar = f"{p.direccion} {p.sucursal}" if p.sucursal and p.direccion else p.sucursal
        return _etiqueta(self.titulo_base, lugar or None, TEXTO_URGENCIA.get(p.urgencia))

    async def ejecutar(self, ctx, p):
        await _categoria_en_producto(ctx, p)
        prod = None
        if p.producto:
            # El Core API no filtra por producto: se resuelve primero (si es ambiguo, el modelo pregunta) y se filtra aquí
            prod = await ctx.producto(p.producto)
            if r := _resuelto_o_candidatos(prod):
                return r
        nuevos = bool(p.destino or p.origen)
        # Con origen o destino, el Core API recibe solo el filtro del rol y la dirección se separa aquí: un administrador
        # de sucursal ve los traslados que salen de otra hacia la suya (antes, el origen ajeno daba 403; hallazgo H13)
        d = await ctx.get("/api/ml/recomendaciones/transferencias", sucursal=None if nuevos else p.sucursal,
                          categoria=await ctx.categoria(p.categoria) if p.categoria else None, urgencia=p.urgencia)
        sucursal = d["filtros_aplicados"]["sucursal"]
        traslados = d["traslados"]
        if p.destino:
            traslados = [t for t in traslados if t["destino"] == p.destino]
        if p.origen:
            traslados = [t for t in traslados if t["origen"] == p.origen]
        if not nuevos and sucursal and p.direccion:
            campo = "destino" if p.direccion == "hacia" else "origen"
            traslados = [t for t in traslados if t[campo] == sucursal]
        if prod:
            traslados = [t for t in traslados if t["producto_id"] == prod.codigo]
        traslados = sorted(traslados, key=lambda t: (ORDEN_URGENCIA_TRASLADO.get(t["urgencia"], 9),
                                                     t["dias_hasta_agotarse"] if t["dias_hasta_agotarse"] is not None else 1e9,
                                                     t.get("nombre_producto") or ""))
        filas = [{"producto": t.get("nombre_producto") or t["producto_id"], "origen": t["origen"], "destino": t["destino"],
                  "cantidad": texto_cantidad(t["cantidad"], t["unidad"] == "kg"), "urgencia": t["urgencia"],
                  "fecha_llegada": t["fecha_llegada"], **({"llega_tarde": True} if t["llega_tarde"] else {})}
                 for t in traslados[:MAX_FILAS]]
        total = len(traslados)
        fecha = d["fecha_inventario"]
        para_modelo = {"fecha_dato": fecha, "total": total, "mostrando": len(filas),
                       "conteo": _conteo(total, len(filas), "traslados"),
                       "llegan_tarde": texto_numero(sum(bool(t["llega_tarde"]) for t in traslados)),
                       **({"producto": prod.nombre, "codigo": prod.codigo} if prod else {}),
                       "filtro": ({"destino": p.destino, "origen": p.origen, "sucursal": sucursal,
                                   "por_tu_rol": d["filtros_aplicados"]["sucursal_por_rol"]} if nuevos else
                                  {"sucursal": sucursal, "direccion": p.direccion if sucursal else None,
                                   "por_tu_rol": d["filtros_aplicados"]["sucursal_por_rol"]}),
                       "filas": filas}
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), self.COLUMNAS, filas, total) if filas else None, fecha_dato=fecha)


class BuscarEnGlosario(Herramienta):
    """INV-31: definiciones y reglas del negocio con su fuente (criterios 3 y 4). El índice BM25 se arma
    una vez desde conocimiento/corpus.json, que va en la imagen."""
    nombre = "buscar_en_glosario"
    descripcion = ("Qué significa un término o cómo funciona una regla: semáforo, cobertura, punto de pedido, calendario "
                   "de pedidos, Bodega Central, perecederos, alertas, indicadores, compras, traslados, y términos del "
                   "pronóstico y los modelos (WAPE, LightGBM, cuantil). También la guía de uso de la aplicación: cómo se "
                   "hace algo en una pantalla, qué muestra, por qué sale una cifra y cómo se usa Vera. Devuelve los "
                   "fragmentos con su fuente (en la guía, la sección); no trae cifras de inventario.")
    titulo_base = "Glosario"
    _indice: Indice | None = None

    class Parametros(BaseModel):
        consulta: str = Field(min_length=2, description="El término o la pregunta, con las palabras del usuario.")

    @classmethod
    def indice(cls) -> Indice:
        if cls._indice is None:
            cls._indice = Indice.desde_archivo()
        return cls._indice

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.consulta)

    async def ejecutar(self, ctx, p):
        encontrados = self.indice().responde(p.consulta)
        if not encontrados:
            return Resultado(para_modelo={
                "resultado": "sin_resultados", "consulta": p.consulta,
                "indicacion": "El glosario no tiene esa información: dilo y no la inventes. Ofrece lo que sí puedes consultar."})
        return Resultado(para_modelo={
            "resultado": "encontrado", "total": len(encontrados),
            "fragmentos": [{k: e.fragmento[k] for k in ("id", "titulo", "fuente", "texto")} for e in encontrados],
            "indicacion": ("Responde con estos fragmentos, en lenguaje sencillo, y cita la fuente; si es de la guía de "
                           "uso, nombra su sección (por ejemplo «Guía de uso, 12.7 Recomendaciones»). "
                           "Si das un ejemplo, usa el del fragmento."),
        })


CATALOGO: tuple[Herramienta, ...] = (
    BuscarProducto(), ListarSucursales(), ConsultarInventario(), ListarAlertas(), ResumenAlertas(),
    PronosticarDemanda(), HistorialVentas(), RecomendarCompras(), BuscarEnGlosario(),
    ResumenInventario(), RecomendarTraslados(), ProductosMasVendidos(), FichaProducto(), PreciosYMargenes(),
)
MAX_HERRAMIENTAS = 14                 # INV-40, decisión 1: más de 10 y menos de 15
POR_NOMBRE = {h.nombre: h for h in CATALOGO}
# Lo que pide el Contexto para resolver nombres (T2, C18, C19); también va a la prueba de contrato
ENDPOINTS_CONTEXTO = (
    ("GET", "/api/auth/me", frozenset()),
    ("GET", "/api/consulta/sucursales", frozenset()),
    ("GET", "/api/consulta/categorias", frozenset()),
    ("GET", "/api/consulta/productos", frozenset({"busqueda", "page", "page_size"})),
    ("GET", "/api/consulta/inventario", frozenset({"sucursal_id", "busqueda", "categoria", "semaforo", "page", "page_size"})),
)


def esquemas(mejoras=None) -> list[dict]:
    """El catálogo en el formato de Ollama. Las correcciones del 24-oct que cambian el esquema solo aparecen con su
    interruptor (`mejoras`, de agente.mejoras): `periodo` en historial_ventas (C1) y la descripción del pronóstico
    sin el anzuelo (C4)."""
    activa = lambda n: bool(mejoras is not None and getattr(mejoras, n, False))  # noqa: E731
    salida = [h.esquema() for h in CATALOGO]
    for e in salida:
        f = e["function"]
        if f["name"] == "pronosticar_demanda" and activa("catalogo"):
            f["description"] = PronosticarDemanda.descripcion_c4 if activa("cobertura") else PronosticarDemanda.descripcion_p5
        if f["name"] == "recomendar_traslados":
            # INV-40 (decisión 3): origen y destino siempre; sucursal y dirección se aceptan pero no se muestran
            for campo in RecomendarTraslados.CAMPOS_22OCT:
                f["parameters"]["properties"].pop(campo, None)
    return salida
