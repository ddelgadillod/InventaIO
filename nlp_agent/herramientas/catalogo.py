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
from typing import Literal

from pydantic import BaseModel, Field

from conocimiento.bm25 import Indice
from herramientas.base import MAX_FILAS, Columna, Herramienta, Resultado, tabla
from herramientas.contexto import (
    Candidatos,
    Contexto,
    Producto,
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

SUCURSAL = "Sucursal o BODEGA_CENTRAL."
# Con solo «Omítelo para no filtrar», qwen3:8b ponía PRINCIPAL en un pronóstico sin sucursal (18-oct, T9)
POR_ROL = "Solo si la pregunta nombra una sucursal; si no, se consultan todas las que ve el usuario."
CODIGO = re.compile(r"[A-Za-z]?\d{3,6}")            # P626, 00196: códigos de producto
TEXTO_ESTADO = {"ok": "ok", "bajo": "bajo", "critico": "crítico", "inconsistencia": "inconsistencia"}
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
        return Resultado(para_modelo={"total": total, "mostrando": len(filas),
                                      "conteo": _conteo(total, len(filas), "productos"), "filas": filas})


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
        if texto and requiere_busqueda_por_palabras(texto, [i["nombre_producto"] for i in items]):
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
        if any(f["sucursal"] == "BODEGA_CENTRAL" for f in filas):
            # INV-65: la Bodega no vende; el Core API le pone las ventas de la red
            extra["nota_bodega"] = "En BODEGA_CENTRAL, ventas_30d son las de las 3 sucursales: la Bodega no vende."
        fecha = d["fecha_inventario"]
        return Resultado(
            para_modelo={"fecha_dato": fecha, "total": total, "mostrando": len(filas),
                         "conteo": _conteo(total, len(filas), "filas de inventario"), **extra, "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, total) if filas else None,
            fecha_dato=fecha,
        )


class ListarAlertas(Herramienta):
    nombre = "listar_alertas"
    descripcion = ("Alertas activas. origen 'reglas': stock crítico o bajo, sin movimiento, rotación baja o "
                   "inconsistencias. origen 'ia': productos que el pronóstico de la IA ve en riesgo de agotarse o con "
                   "sobrestock. Sin origen, las de reglas.")
    titulo_base = "Alertas"
    _params = frozenset({"sucursal_id", "tipo", "urgencia", "page", "page_size"})
    endpoints = (("GET", "/api/alertas", _params), ("GET", "/api/alertas/ml", _params))
    COLUMNAS = [Columna("producto", "Producto"), Columna("sucursal", "Sucursal"), Columna("tipo", "Tipo"),
                Columna("urgencia", "Urgencia", "urgencia"), Columna("detalle", "Detalle")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        origen: Literal["reglas", "ia"] | None = None
        tipo: TipoAlerta | None = None
        urgencia: UrgenciaAlerta | None = None

    @staticmethod
    def _ia(p) -> bool:
        return p.origen == "ia" or (p.origen is None and p.tipo in TIPOS_IA)

    def lenta(self, p):
        return self._ia(p)

    def etiqueta(self, p):
        return _etiqueta("Alertas con IA" if self._ia(p) else "Alertas", p.sucursal, TEXTO_URGENCIA.get(p.urgencia))

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
    descripcion = "Conteo de las alertas de reglas de cada sucursal (críticas, altas y medias) y por tipo. Solo filtra por sucursal."
    titulo_base = "Resumen de alertas"
    endpoints = (("GET", "/api/alertas/resumen", frozenset({"sucursal_id"})),)
    COLUMNAS = [Columna("sucursal", "Sucursal"), Columna("critica", "Crítica", "numero"), Columna("alta", "Alta", "numero"),
                Columna("media", "Media", "numero"), Columna("total", "Total", "numero")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)

    def etiqueta(self, p):
        return _etiqueta(self.titulo_base, p.sucursal)

    async def ejecutar(self, ctx, p):
        d = await ctx.get("/api/alertas/resumen", sucursal_id=(await ctx.sucursal(p.sucursal)).id if p.sucursal else None)
        contar = lambda c: {k: texto_numero(c[k]) for k in ("critica", "alta", "media", "total")}  # noqa: E731
        filas = [{"sucursal": s["sucursal"], **contar(s["contadores"])} for s in d["items"]]
        fecha = d["fecha_inventario"]
        return Resultado(
            para_modelo={"fecha_dato": fecha, "global": contar(d["global_"]),
                         "por_tipo": {k: texto_numero(v) for k, v in d["por_tipo"].items()}, "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, len(filas)) if filas else None,
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
        filas = [{"sucursal": t, "demanda": texto_cantidad(d["prediccion_q50"], por_kilo(prod.unidad)),
                  "horizonte": HORIZONTE, "interpretacion": d["interpretacion"]} for t, d in hechas]
        fecha = hechas[0][1]["fecha_features"]
        base = {"fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo}
        if len(tiendas) == 1:
            titulo = _etiqueta("Pronóstico", prod.nombre, tiendas[0])
            columnas = [Columna("demanda", "Demanda esperada", "cantidad"), Columna("horizonte", "Horizonte"),
                        Columna("interpretacion", "Interpretación")]
            return Resultado(para_modelo={**base, **filas[0]}, data=tabla(titulo, columnas, filas, 1, forma="tarjeta"),
                             fecha_dato=fecha)
        titulo = _etiqueta("Pronóstico", prod.nombre, f"{len(tiendas)} sucursales")
        columnas = [Columna("sucursal", "Sucursal"), Columna("demanda", "Demanda esperada", "cantidad"),
                    Columna("interpretacion", "Interpretación")]
        para_modelo = {**base, "horizonte": HORIZONTE, "total": len(filas),
                       "filas": [{k: f[k] for k in ("sucursal", "demanda", "interpretacion")} for f in filas]}
        if errores:
            para_modelo["errores"] = errores
        return Resultado(para_modelo=para_modelo, data=tabla(titulo, columnas, filas, len(filas)), fecha_dato=fecha)


class HistorialVentas(Herramienta):
    nombre = "historial_ventas"
    descripcion = "Ventas de un producto en los últimos meses, en periodos de 15 días hábiles."
    titulo_base = "Historial de ventas"
    endpoints = (("GET", "/api/consulta/productos/{id_producto}/ventas", frozenset({"sucursal_id", "ventanas"})),)

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
        para_modelo = {"fecha_dato": fecha, "producto": prod.nombre, "codigo": prod.codigo, "periodo": HORIZONTE,
                       "suma_por_sucursal": sumas, "total": len(filas), "filas": filas}
        if errores:
            para_modelo["errores"] = errores
        return Resultado(para_modelo=para_modelo, data=tabla(titulo, columnas, filas, len(filas)), fecha_dato=fecha)


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
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), columnas, filas, r["lineas"]) if filas else None,
                         fecha_dato=d["fecha_inventario"])


class ResumenInventario(Herramienta):
    """INV-33, brecha B2: el estado general del inventario, sin listar productos."""
    nombre = "resumen_inventario"
    descripcion = ("Cuántos productos hay en cada estado del semáforo (ok, bajo, crítico, inconsistencia) en cada sucursal "
                   "y en total. Para el estado general del inventario; para ver productos, consultar_inventario.")
    titulo_base = "Resumen del inventario"
    endpoints = (("GET", "/api/consulta/inventario/resumen", frozenset({"sucursal_id"})),)
    COLUMNAS = [Columna("sucursal", "Sucursal"), Columna("ok", "OK", "numero"), Columna("bajo", "Bajo", "numero"),
                Columna("critico", "Crítico", "numero"), Columna("inconsistencia", "Inconsistencia", "numero"),
                Columna("en_riesgo", "En riesgo", "numero"), Columna("total", "Total", "numero")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)

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
        return Resultado(
            para_modelo={"fecha_dato": fecha, "global": contar(d["global_"]), "filas": filas},
            data=tabla(self.etiqueta(p), self.COLUMNAS, filas, len(filas)) if filas else None,
            fecha_dato=fecha,
        )


class RecomendarTraslados(Herramienta):
    """INV-33, brecha B3. El Core API filtra la sucursal por origen o por destino a la vez; la dirección se
    separa aquí, sobre las filas que devuelve."""
    nombre = "recomendar_traslados"
    descripcion = ("Traslados sugeridos de stock entre sucursales y desde la Bodega Central: producto, origen, destino, "
                   "cantidad, urgencia y llegada. Con sucursal, direccion 'hacia' son los que llegan a ella y 'desde' los "
                   "que salen.")
    titulo_base = "Traslados sugeridos"
    endpoints = (("GET", "/api/ml/recomendaciones/transferencias", frozenset({"sucursal", "categoria", "urgencia"})),)
    COLUMNAS = [Columna("producto", "Producto"), Columna("origen", "Origen"), Columna("destino", "Destino"),
                Columna("cantidad", "Cantidad", "cantidad"), Columna("urgencia", "Urgencia", "urgencia"),
                Columna("fecha_llegada", "Llega", "fecha")]

    class Parametros(BaseModel):
        sucursal: Sucursal | None = Field(None, description=SUCURSAL)
        direccion: Direccion | None = Field(None, description="Solo con sucursal: 'hacia' (llegan a ella) o 'desde' (salen de ella).")
        categoria: str | None = None
        urgencia: UrgenciaTraslado | None = None

    def lenta(self, p):
        return True                                     # la primera llamada tras una foto nueva tarda unos 20 s

    def etiqueta(self, p):
        lugar = f"{p.direccion} {p.sucursal}" if p.sucursal and p.direccion else p.sucursal
        return _etiqueta(self.titulo_base, lugar, TEXTO_URGENCIA.get(p.urgencia))

    async def ejecutar(self, ctx, p):
        d = await ctx.get("/api/ml/recomendaciones/transferencias", sucursal=p.sucursal,
                          categoria=await ctx.categoria(p.categoria) if p.categoria else None, urgencia=p.urgencia)
        sucursal = d["filtros_aplicados"]["sucursal"]
        traslados = d["traslados"]
        if sucursal and p.direccion:
            campo = "destino" if p.direccion == "hacia" else "origen"
            traslados = [t for t in traslados if t[campo] == sucursal]
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
                       "filtro": {"sucursal": sucursal, "direccion": p.direccion if sucursal else None,
                                  "por_tu_rol": d["filtros_aplicados"]["sucursal_por_rol"]},
                       "filas": filas}
        return Resultado(para_modelo=para_modelo,
                         data=tabla(self.etiqueta(p), self.COLUMNAS, filas, total) if filas else None, fecha_dato=fecha)


class BuscarEnGlosario(Herramienta):
    """INV-31: definiciones y reglas del negocio con su fuente (criterios 3 y 4). El índice BM25 se arma
    una vez desde conocimiento/corpus.json, que va en la imagen."""
    nombre = "buscar_en_glosario"
    descripcion = ("Qué significa un término o cómo funciona una regla: semáforo, cobertura, punto de pedido, calendario "
                   "de pedidos, Bodega Central, perecederos, alertas, indicadores, compras, traslados, y términos del "
                   "pronóstico y los modelos (WAPE, LightGBM, cuantil). Devuelve la definición con su fuente; no trae "
                   "cifras de inventario.")
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
            "indicacion": ("Responde con estos fragmentos, en lenguaje sencillo, y cita la fuente. "
                           "Si das un ejemplo, usa el del fragmento."),
        })


CATALOGO: tuple[Herramienta, ...] = (
    BuscarProducto(), ListarSucursales(), ConsultarInventario(), ListarAlertas(), ResumenAlertas(),
    PronosticarDemanda(), HistorialVentas(), RecomendarCompras(), BuscarEnGlosario(),
    ResumenInventario(), RecomendarTraslados(),
)
POR_NOMBRE = {h.nombre: h for h in CATALOGO}
# Lo que pide el Contexto para resolver nombres (T2, C18, C19); también va a la prueba de contrato
ENDPOINTS_CONTEXTO = (
    ("GET", "/api/auth/me", frozenset()),
    ("GET", "/api/consulta/sucursales", frozenset()),
    ("GET", "/api/consulta/categorias", frozenset()),
    ("GET", "/api/consulta/productos", frozenset({"busqueda", "page", "page_size"})),
    ("GET", "/api/consulta/inventario", frozenset({"sucursal_id", "busqueda", "categoria", "semaforo", "page", "page_size"})),
)


def esquemas() -> list[dict]:
    """El catálogo en el formato de Ollama."""
    return [h.esquema() for h in CATALOGO]
