"""
Un Core API simulado con `httpx.MockTransport` (INV-32).

Las formas de las respuestas, los mensajes de error y las cifras salen del
sondeo del 18-oct contra el Core API real con los tres roles (hallazgos C1–C19
de docs/INV-32-requerimientos.md): nombres y códigos de producto reales, la
fecha 2025-12-31, el 403 de `admin_sucursal` y el 422 de la Bodega en el
pronóstico. Guarda cada petición para revisar ruta, parámetros y encabezados.

Los permisos se simulan como en api/core/ubicaciones.py: gerente y admin_bodega
ven todo; admin_sucursal, su sucursal (y la Bodega solo en el stock).
"""
import json
import re

import httpx

FECHA = "2025-12-31"
SUCURSALES = [(1, "PRINCIPAL", "principal"), (2, "LA 21", "estandar"), (3, "GLORIETA", "estandar"),
              (5, "BODEGA_CENTRAL", "bodega_central")]
NOMBRE = {i: n for i, n, _ in SUCURSALES}
ID = {n: i for i, n, _ in SUCURSALES}
# (id, código, nombre, categoría, unidad). PAPA PASTUSA lleva un código de prueba
PRODUCTOS = [
    (91, "P1632", "HUEVOS *UND", "Huevos", "unidad"),
    (548, "P618", "ARROZ CAROLINA *500 GR", "Arroz", "unidad"),
    (640, "P617", "ARROZ CAROLINA *1000 GR", "Arroz", "unidad"),
    (378, "P615", "ARROZ CAROLINA *3000 GR", "Arroz", "unidad"),
    (958, "P614", "ARROZ CAROLINA *5000 GR", "Arroz", "unidad"),
    (3478, "00805", "ARROZ BETARROZ *500GR", "Arroz", "unidad"),
    (2372, "P3833", "ARROZ CON LECHE ROA TRADICIONAL * 150GR", "Lácteos", "unidad"),
    (3640, "P126", "CAFE CON LECHE COLCAFE *22GR *6 UND", "Lácteos", "unidad"),
    (2238, "P9001", "VELON N. 2 VELAS LUZ DE ORO", "Velas y velones", "unidad"),
    (7001, "P9002", "PAPA PASTUSA *KL", "Frutas y verduras", "kg"),
]
CATEGORIAS = ["Arroz", "Frutas y verduras", "Huevos", "Lácteos", "Velas y velones"]
# (id_producto, id_sucursal, stock, mínimo, días de cobertura, semáforo)
INVENTARIO = [
    (91, 3, 420, 800, 1.6, "critico"), (91, 1, 1250, 800, 9.4, "ok"), (91, 5, 0, 100, 0.0, "critico"),
    (548, 3, 2, 10, 0.3, "critico"), (640, 2, 35, 12, 14.0, "ok"), (2238, 3, 0, 1, 0.0, "critico"),
    (7001, 1, 77.145, 40, 3.2, "ok"), (3478, 2, -44, 0, -347.4, "inconsistencia"),
]
# Unidades vendidas en 30 días (INV-65); en la Bodega, las de la red
VENTAS_30D = {(91, 3): 4497.0, (91, 1): 4608.0, (91, 5): 11006.0, (548, 3): 13.0, (7001, 1): 210.5}
ALERTAS = [
    (2238, 3, "stock_critico", "critica", "Stock 0 unidades; mínimo 1 unidad"),
    (548, 3, "stock_critico", "critica", "Stock 2 unidades; mínimo 10 unidades"),
    (3478, 2, "inconsistencia_inventario", "critica", "Stock negativo en la foto (-44 unidades): verificar el conteo"),
    (91, 1, "sin_movimiento", "media", "Sin ventas en 30 días"),
]
ALERTAS_ML = [
    (91, 3, "riesgo_desabastecimiento_ml", "critica", "ambos",
     "Stock 420 unidades; según el pronóstico (3.871 unidades en 15 días hábiles) alcanza 1,6 días hábiles"),
    (640, 2, "sobrestock_previsto_ml", "media", "ml", "Stock 35 unidades; el pronóstico prevé 4 unidades en 15 días hábiles"),
]
INTERPRETACION = ("Demanda estable, producto perecedero. Proyección: 3.871 unidades en 15 días hábiles. El límite "
                  "superior no incluye margen de seguridad: el modelo evita sobre-stock para reducir merma. No usar "
                  "como cota de reposición.")
COMPRAS = [
    # (código, nombre, categoría, destino, cantidad, unidad, urgencia, días hasta agotarse, necesidad por sucursal)
    ("00002", "CHOCOLAT JET BURBUJA *12 UND", "Confitería", "BODEGA_CENTRAL", 4, "unidad", "normal", 10.5, {"LA 21": 1.2}),
    ("P618", "ARROZ CAROLINA *500 GR", "Arroz", "BODEGA_CENTRAL", 24, "unidad", "urgente", 0.3, {"GLORIETA": 8.0, "LA 21": 2.5}),
    ("P9002", "PAPA PASTUSA *KL", "Frutas y verduras", "PRINCIPAL", 120, "kg", "alta", 3.2, {"PRINCIPAL": 118.4}),
    ("P1632", "HUEVOS *UND", "Huevos", "GLORIETA", 900, "unidad", "urgente", 1.6, {"GLORIETA": 880.0}),
]
PERFILES = {
    "Bearer token-de-prueba": ("gerente", None),
    "Bearer token-bodega": ("admin_bodega", "BODEGA_CENTRAL"),
    "Bearer token-la21": ("admin_sucursal", "LA 21"),
}
EMAILS = {"gerente@inventaio.co": "Bearer token-de-prueba", "bodega@inventaio.co": "Bearer token-bodega",
          "admin.norte@inventaio.co": "Bearer token-la21", "admin.principal@inventaio.co": "Bearer token-principal",
          "admin.sur@inventaio.co": "Bearer token-glorieta"}
PERFILES |= {"Bearer token-principal": ("admin_sucursal", "PRINCIPAL"), "Bearer token-glorieta": ("admin_sucursal", "GLORIETA")}


def _producto(pid: int) -> tuple:
    return next(p for p in PRODUCTOS if p[0] == pid)


def _ilike(texto: str, valor: str) -> bool:
    return texto.lower() in valor.lower()


def _pagina(items: list, params, defecto: int | None = 20) -> dict:
    page, size = params.get("page"), params.get("page_size")
    if page is None and size is None and defecto is None:
        return {"items": items, "total": len(items), "page": None, "page_size": None, "pages": None}
    page, size = int(page or 1), int(size or defecto or 50)
    return {"items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "page_size": size,
            "pages": -(-len(items) // size)}


class CoreFalso:
    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.forzar: dict[str, tuple[int, object]] = {}     # ruta -> (status, detail)
        self.caido = False
        self.lento = False

    def params(self, i: int = -1) -> dict:
        q = self.peticiones[i].url.params
        return {k: (q.get_list(k) if len(q.get_list(k)) > 1 else q[k]) for k in q.keys()}

    def rutas(self) -> list[str]:
        return [p.url.path for p in self.peticiones]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        if self.caido:
            raise httpx.ConnectError("conexión rechazada", request=request)
        if self.lento:
            raise httpx.ReadTimeout("lento", request=request)
        ruta = request.url.path
        if ruta in self.forzar:
            status, detail = self.forzar[ruta]
            return httpx.Response(status, json={"detail": detail})
        if ruta == "/api/auth/login":
            token = EMAILS.get(json.loads(request.content)["email"])
            return httpx.Response(200 if token else 401, json={"access_token": token.split()[1]} if token else {"detail": "Credenciales inválidas"})
        perfil = PERFILES.get(request.headers.get("authorization", ""))
        if perfil is None:
            return httpx.Response(401, json={"detail": "Token inválido o expirado"})
        rol, propia = perfil
        q = request.url.params
        try:
            return self._responder(request, ruta, q, rol, propia)
        except PermissionError as exc:
            return httpx.Response(403, json={"detail": str(exc)})

    def _ubicacion(self, q, rol, propia, stock: bool = False) -> int | None:
        sid = int(q["sucursal_id"]) if "sucursal_id" in q else None
        if rol == "admin_sucursal":
            if sid is None:
                return ID[propia]
            if sid != ID[propia] and not (stock and sid == 5):
                extra = "" if stock else "; la Bodega Central, solo en el stock" if sid == 5 else ""
                raise PermissionError(f"Solo puede consultar su sucursal ({propia}){extra}")
        return sid

    def _responder(self, request, ruta, q, rol, propia) -> httpx.Response:
        if ruta == "/api/auth/me":
            return httpx.Response(200, json={"id": 3, "email": "admin.norte@inventaio.co", "nombre": "Andrés Rivera",
                                             "rol": rol, "id_sucursal": ID.get(propia), "sucursal_nombre": propia,
                                             "activo": True, "created_at": "2026-03-16T02:22:45"})
        if ruta == "/api/consulta/sucursales":
            items = [{"id_sucursal": i, "codigo_tienda": i, "nombre": n, "ciudad": None, "departamento": None, "tipo": t,
                      "cluster": None, "factor_volumen": None} for i, n, t in SUCURSALES]
            return httpx.Response(200, json={"items": items, "total": len(items)})
        if ruta == "/api/consulta/categorias":
            return httpx.Response(200, json={"items": [{"categoria": c, "total_productos": 1} for c in CATEGORIAS],
                                             "total": len(CATEGORIAS)})
        if ruta == "/api/consulta/productos":
            b = q.get("busqueda", "")
            items = sorted(({"id_producto": i, "codigo_item": c, "nombre": n, "familia": cat, "clase": None, "categoria": cat,
                             "es_perecedero": False, "unidad_medida": "UND", "unidad": u, "precio_base": None,
                             "costo_base": None, "margen_pct": None, "iva_pct": 0.0}
                            for i, c, n, cat, u in PRODUCTOS if _ilike(b, n) or _ilike(b, c)), key=lambda x: x["nombre"])
            return httpx.Response(200, json=_pagina(items, q))
        if ruta == "/api/consulta/inventario":
            sid = self._ubicacion(q, rol, propia, stock=True)
            filas = []
            for pid, s, stock, minimo, cob, sem in INVENTARIO:
                _, _, nombre, cat, unidad = _producto(pid)
                if (sid and s != sid) or (q.get("semaforo") and q["semaforo"] != sem) or \
                        (q.get("categoria") and q["categoria"] != cat) or not _ilike(q.get("busqueda", ""), nombre):
                    continue
                filas.append({"id_producto": pid, "nombre_producto": nombre, "categoria": cat, "es_perecedero": False,
                              "unidad": unidad, "sucursal": NOMBRE[s], "id_sucursal": s,
                              "tipo_ubicacion": "bodega_central" if s == 5 else "sucursal", "stock_disponible": float(stock),
                              "stock_bodega": None, "stock_minimo": float(minimo), "stock_maximo": float(minimo) * 3,
                              "punto_reorden": float(minimo), "dias_cobertura": cob, "semaforo": sem,
                              "ventas_30d": VENTAS_30D.get((pid, s), 0.0), "fecha": FECHA})
            return httpx.Response(200, json={**_pagina(filas, q), "fecha_inventario": FECHA})
        if ruta in ("/api/alertas", "/api/alertas/ml"):
            sid = self._ubicacion(q, rol, propia)
            ml = ruta.endswith("/ml")
            filas = []
            for fila in ALERTAS_ML if ml else ALERTAS:
                pid, s, tipo, urgencia = fila[:4]
                if (sid and s != sid) or (q.get_list("tipo") and tipo not in q.get_list("tipo")) or \
                        (q.get_list("urgencia") and urgencia not in q.get_list("urgencia")):
                    continue
                _, codigo, nombre, cat, unidad = _producto(pid)
                item = {"id_producto": pid, "nombre_producto": nombre, "categoria": cat, "sucursal": NOMBRE[s],
                        "id_sucursal": s, "tipo_ubicacion": "sucursal", "tipo": tipo, "urgencia": urgencia,
                        "valor": 0.0, "umbral": 0.0, "detalle": fila[-1], "fecha": FECHA}
                if ml:
                    item |= {"codigo_item": codigo, "origen": fila[4], "unidad": unidad, "stock": 0.0, "q50": 0.0,
                             "accion": "compra", "llega_tarde": None, "fecha_pronostico": FECHA}
                filas.append(item)
            cuerpo = {**_pagina(filas, q, defecto=None), "fecha_inventario": FECHA}
            if ml:
                cuerpo |= {"resumen": {"total": 1587, "riesgo_desabastecimiento_ml": 866, "sobrestock_previsto_ml": 721,
                                       "critica": 483, "alta": 383, "media": 721, "ambos": 395, "ml": 1192},
                           "fecha_pronostico": FECHA, "politicas": {}, "calculado_en": "2026-10-19T03:38:01Z"}
            return httpx.Response(200, json=cuerpo)
        if ruta == "/api/alertas/resumen":
            sid = self._ubicacion(q, rol, propia)
            datos = {"BODEGA_CENTRAL": (592, 79, 15), "PRINCIPAL": (297, 138, 873), "GLORIETA": (243, 109, 1092),
                     "LA 21": (202, 60, 752)}
            items = [{"sucursal": n, "id_sucursal": ID[n], "tipo_ubicacion": "sucursal",
                      "contadores": {"critica": c, "alta": a, "media": m, "total": c + a + m}}
                     for n, (c, a, m) in datos.items() if not sid or ID[n] == sid]
            return httpx.Response(200, json={
                "items": items, "global_": {"critica": 1334, "alta": 386, "media": 2732, "total": 4452},
                "por_tipo": {"inconsistencia_inventario": 220, "stock_critico": 1114, "stock_bajo": 386,
                             "sin_movimiento": 2453, "rotacion_baja": 279}, "fecha_inventario": FECHA})
        if ruta == "/api/ml/predict":
            cuerpo = json.loads(request.content)
            sucursal = cuerpo["sucursal_id"]
            if sucursal == "BODEGA_CENTRAL":
                return httpx.Response(422, json={"detail": "La sucursal BODEGA_CENTRAL (bodega_central) no es una sucursal "
                                                           "física: el modelo solo se entrenó con PRINCIPAL, LA 21 y GLORIETA."})
            if rol == "admin_sucursal" and sucursal != propia:
                raise PermissionError(f"Solo puede pronosticar su sucursal ({propia})")
            pid, codigo, *_ = next(p for p in PRODUCTOS if p[1] == cuerpo["producto_id"])
            q50 = {"GLORIETA": 3871.25, "PRINCIPAL": 2050.0, "LA 21": 1290.4}[sucursal]
            return httpx.Response(200, json={
                "producto_id": codigo, "id_producto": pid, "sucursal_id": sucursal, "id_sucursal": ID[sucursal],
                "horizonte_dias": 15, "rama": "suave_perecedero", "prediccion_q50": q50,
                "intervalo_confianza": {"limite_inferior": 0.0, "limite_superior": 3094.03, "alpha_negocio": 0.167},
                "interpretacion": INTERPRETACION, "fecha_features": FECHA, "modelo_entrenado_en": "2026-09-25T01:30:56+00:00"})
        if m := re.fullmatch(r"/api/consulta/productos/(\d+)/ventas", ruta):
            pid = int(m.group(1))
            sid = int(q["sucursal_id"]) if "sucursal_id" in q else None
            if rol == "admin_sucursal":
                if sid not in (None, ID[propia]):
                    raise PermissionError(f"Solo puede consultar su sucursal ({propia})")
                sid = ID[propia]
            elif sid is None:
                return httpx.Response(422, json={"detail": "sucursal_id es obligatorio. Válidos: 1 (PRINCIPAL), 2 (LA 21), 3 (GLORIETA)"})
            _, codigo, nombre, cat, unidad = _producto(pid)
            n = int(q.get("ventanas", 8))
            base = [(f"2025-{mes:02d}-02", f"2025-{mes:02d}-16", 3000.0 + 100 * mes) for mes in range(1, 13)]
            ventanas = base[-(n - 2):] if n > 2 else []
            ventanas += [("2025-12-02", "2025-12-16", 3722.0), ("2025-12-17", "2025-12-31", 4497.0)]
            return httpx.Response(200, json={
                "id_producto": pid, "codigo_item": codigo, "nombre_producto": nombre, "categoria": cat, "unidad": unidad,
                "id_sucursal": sid, "sucursal": NOMBRE[sid], "horizonte_dias_habiles": 15, "fecha_fin": FECHA,
                "ventanas": [{"desde": d, "hasta": h, "unidades": u} for d, h, u in ventanas[-n:]]})
        if ruta == "/api/ml/recomendaciones/compras":
            sucursal = q.get("sucursal")
            por_rol = False
            if rol == "admin_sucursal":
                if sucursal and sucursal.upper() != propia:
                    raise PermissionError(f"Solo puede consultar su sucursal ({propia})")
                sucursal, por_rol = propia, sucursal is None
            lineas = []
            for codigo, nombre, cat, destino, cantidad, unidad, urgencia, dias, necesidades in COMPRAS:
                if (q.get("urgencia") and urgencia != q["urgencia"]) or (q.get("categoria") and q["categoria"] != cat):
                    continue
                if sucursal and sucursal != "BODEGA_CENTRAL" and sucursal not in necesidades:
                    continue
                lineas.append({"producto_id": codigo, "nombre_producto": nombre, "categoria": cat, "destino": destino,
                               "tipo_destino": "bodega_central" if destino == "BODEGA_CENTRAL" else "sucursal",
                               "grupo": "quincenal", "cantidad": cantidad, "unidad": unidad, "urgencia": urgencia,
                               "dias_hasta_agotarse": dias, "fecha_pedido": "2026-01-02", "fecha_llegada": "2026-01-07",
                               "fecha_llegada_sucursal": "2026-01-09", "llega_tarde": urgencia == "urgente",
                               "necesidad": sum(necesidades.values()),
                               "necesidad_sucursal": necesidades.get(sucursal) if sucursal and sucursal != "BODEGA_CENTRAL" else None,
                               "sobrante_bodega": 0.0, "motivo": "reposicion", "detalle": None})
            kg = sum(x["cantidad"] for x in lineas if x["unidad"] == "kg")
            return httpx.Response(200, json={
                "fecha_inventario": FECHA, "fecha_pronostico": FECHA, "lead_time_dias": 5, "politicas": {},
                "calendario": [], "compras": lineas, "cubrir_con_traslado": [], "alertas": [], "no_encontrados": [],
                "resumen": {"productos": len(lineas), "lineas": len(lineas), "lineas_sucursal": 0, "lineas_bodega": 0,
                            "cantidad": {"unidad": sum(x["cantidad"] for x in lineas) - kg, "kg": kg},
                            "cantidad_directa": {"unidad": 0, "kg": 0}, "cantidad_bodega": {"unidad": 0, "kg": 0},
                            "necesidad_via_bodega": None, "cubiertos_por_bodega": 2, "alertas": 0},
                "filtros_aplicados": {"sucursal": sucursal, "sucursal_por_rol": por_rol, "categoria": q.get("categoria"),
                                      "urgencia": q.get("urgencia")},
                "calculado_en": "2026-10-18T00:20:11Z"})
        return httpx.Response(404, json={"detail": "Not Found"})
