"""
InventAI/o — Filtros, vista desde la sucursal y resumen de las recomendaciones (INV-23)
Funciones puras sobre las respuestas de ml_service: no hacen I/O ni modifican
lo que está en la caché (una fila que cambia es una copia). Las reglas están
en docs/INV-23-requerimientos.md (C2, C4, R1, R2, R4, R6).
"""
from dataclasses import dataclass
from typing import Optional

BODEGA = "BODEGA_CENTRAL"
LISTAS_COMPRAS = ("compras", "cubrir_con_traslado", "alertas")
LISTAS_TRANSFERENCIAS = ("traslados", "balance", "alertas")


@dataclass(frozen=True)
class Filtros:
    sucursal: Optional[str] = None
    categoria: Optional[str] = None
    urgencia: Optional[str] = None
    sucursal_por_rol: bool = False

    @property
    def sucursal_fisica(self) -> bool:
        return self.sucursal is not None and self.sucursal != BODEGA

    def aplicados(self) -> dict:
        return {"sucursal": self.sucursal, "sucursal_por_rol": self.sucursal_por_rol,
                "categoria": self.categoria, "urgencia": self.urgencia}

    def categoria_ok(self, fila: dict) -> bool:
        # R6: sin fila en dim_producto la categoría es nula y no pasa el filtro
        return self.categoria is None or fila.get("categoria") == self.categoria

    def urgencia_ok(self, fila: dict) -> bool:
        # R2: coincidencia exacta; la urgencia nula no pasa
        return self.urgencia is None or fila.get("urgencia") == self.urgencia


# ── Enriquecimiento ─────────────────────────────────

def enriquecer(respuesta: dict, listas: tuple, productos: dict) -> dict:
    """Copia de `respuesta` con nombre_producto y categoria en cada fila de
    `listas`; nulos si el producto no tiene fila en dim_producto (R6)."""
    out = dict(respuesta)
    for lista in listas:
        if out.get(lista) is not None:
            out[lista] = [_con_producto(f, productos) for f in out[lista]]
    return out


def _con_producto(fila: dict, productos: dict) -> dict:
    nombre, categoria = productos.get(fila["producto_id"], (None, None))
    return {**fila, "nombre_producto": nombre, "categoria": categoria}


def _por_unidad(filas: list, campo: str) -> dict:
    """R4: suma separada por unidad, para no mezclar unidades con kilos."""
    total = {"unidad": 0, "kg": 0}
    for f in filas:
        if f.get(campo) is not None:
            total[f["unidad"]] += f[campo]
    return {u: round(v, 2) for u, v in total.items()}


def _sin_listas(respuesta: dict, listas: tuple) -> dict:
    """Los campos que pasan sin cambios (fechas, políticas, calendario...)."""
    return {k: v for k, v in respuesta.items() if k not in listas and k != "resumen"}


# ── Compras ─────────────────────────────────────────

def _vista_desde(fila: dict, sucursal: str) -> Optional[dict]:
    """R1: la fila de la Bodega (o de cubrir_con_traslado) vista desde
    `sucursal`: su detalle, su urgencia y su parte de la necesidad. Las
    cantidades siguen siendo las de toda la compra. None si no participa."""
    propia = next((d for d in fila.get("detalle") or [] if d["sucursal"] == sucursal), None)
    if propia is None:
        return None
    vista = {**fila, "detalle": [propia], "urgencia": propia["urgencia"],
             "dias_hasta_agotarse": propia["dias_hasta_agotarse"], "necesidad_sucursal": propia["necesidad"]}
    if "llega_tarde" in fila:                 # cubrir_con_traslado no los trae
        vista.update(llega_tarde=propia["llega_tarde"], motivo=propia["motivo"])
    return vista


def _linea_compra(fila: dict, filtros: Filtros) -> Optional[dict]:
    """C2: con sucursal física, las directas a ella y las de la Bodega donde
    participa; con BODEGA_CENTRAL, solo las de la Bodega."""
    if filtros.sucursal_fisica:
        if fila["destino"] == filtros.sucursal:
            return {**fila, "necesidad_sucursal": fila["necesidad"]}
        if fila["tipo_destino"] == "bodega_central":
            return _vista_desde(fila, filtros.sucursal)
        return None
    if filtros.sucursal == BODEGA and fila["tipo_destino"] != "bodega_central":
        return None
    return {**fila, "necesidad_sucursal": None}


def filtrar_compras(respuesta: dict, filtros: Filtros, incluir_detalle: bool = True) -> dict:
    compras = []
    for fila in respuesta["compras"]:
        if not filtros.categoria_ok(fila):
            continue
        linea = _linea_compra(fila, filtros)
        if linea is not None and filtros.urgencia_ok(linea):
            compras.append(linea)
    cubrir = []
    for fila in respuesta["cubrir_con_traslado"]:
        if not filtros.categoria_ok(fila):
            continue
        # con BODEGA_CENTRAL van todos: los cubre el stock de la Bodega
        vista = _vista_desde(fila, filtros.sucursal) if filtros.sucursal_fisica else {**fila, "necesidad_sucursal": None}
        if vista is not None and filtros.urgencia_ok(vista):
            cubrir.append(vista)
    # R2: la urgencia no filtra las alertas
    alertas = [a for a in respuesta["alertas"]
               if filtros.categoria_ok(a) and (filtros.sucursal is None or a["sucursal"] == filtros.sucursal)]

    cuerpo = _sin_listas(respuesta, LISTAS_COMPRAS)
    cuerpo.update(compras=compras, cubrir_con_traslado=cubrir, alertas=alertas,
                  resumen=resumen_compras(compras, cubrir, alertas, filtros))
    if not incluir_detalle:
        for fila in compras + cubrir:          # copias: la caché no cambia
            fila.pop("detalle", None)
    return cuerpo


def resumen_compras(compras: list, cubrir: list, alertas: list, filtros: Filtros) -> dict:
    directas = [f for f in compras if f["tipo_destino"] == "sucursal"]
    bodega = [f for f in compras if f["tipo_destino"] == "bodega_central"]
    return {
        "productos": len({f["producto_id"] for f in compras + cubrir}),
        "lineas": len(compras),
        "lineas_sucursal": len(directas),
        "lineas_bodega": len(bodega),
        "cantidad": _por_unidad(compras, "cantidad"),
        "cantidad_directa": _por_unidad(directas, "cantidad"),
        "cantidad_bodega": _por_unidad(bodega, "cantidad"),
        "necesidad_via_bodega": _por_unidad(bodega, "necesidad_sucursal") if filtros.sucursal_fisica else None,
        "cubiertos_por_bodega": len(cubrir),
        "alertas": len(alertas),
    }


# ── Transferencias ──────────────────────────────────

def filtrar_transferencias(respuesta: dict, filtros: Filtros, incluir_balance: bool = False) -> dict:
    suc = filtros.sucursal
    traslados = [f for f in respuesta["traslados"]
                 if filtros.categoria_ok(f) and filtros.urgencia_ok(f) and (suc is None or suc in (f["origen"], f["destino"]))]
    balance = [f for f in respuesta.get("balance") or []
               if filtros.categoria_ok(f) and filtros.urgencia_ok(f) and (suc is None or f["sucursal"] == suc)]
    alertas = [a for a in respuesta["alertas"]
               if filtros.categoria_ok(a) and (suc is None or a["sucursal"] == suc)]
    # C4: sin balance, las alertas sin_pronostico se cuentan pero no se listan
    listadas = alertas if incluir_balance else [a for a in alertas if a["tipo"] != "sin_pronostico"]

    cuerpo = _sin_listas(respuesta, LISTAS_TRANSFERENCIAS)
    cuerpo.update(traslados=traslados, alertas=listadas,
                  resumen=resumen_transferencias(traslados, balance, alertas, listadas))
    if incluir_balance:
        cuerpo["balance"] = balance
    return cuerpo


def resumen_transferencias(traslados: list, balance: list, alertas: list, listadas: list) -> dict:
    return {
        "productos": len({f["producto_id"] for f in traslados} | {f["producto_id"] for f in balance}),
        "traslados": len(traslados),
        "cantidad_trasladada": _por_unidad(traslados, "cantidad"),
        "filas_balance": len(balance),
        "deficit_total": _por_unidad(balance, "deficit"),
        "deficit_neto": _por_unidad(balance, "deficit_neto"),
        "excedente_sin_destino": _por_unidad(balance, "excedente_sin_destino"),
        "alertas": len(listadas),
        "alertas_stock_negativo": sum(a["tipo"] == "stock_negativo" for a in alertas),
        "alertas_sin_pronostico": sum(a["tipo"] == "sin_pronostico" for a in alertas),
    }
