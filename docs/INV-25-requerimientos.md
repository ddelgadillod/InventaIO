# INV-25 · Requerimientos de auditoría y homologación del Core API

Versión del 2026-10-01. Reemplaza el borrador del mismo día. La Fase 1
(auditoría) ya se hizo y su resultado está en
[`INV-25-auditoria.md`](INV-25-auditoria.md). Con esa evidencia se tomaron las
decisiones D1–D10 y se cerró el alcance de la Fase 2. Los pendientes del final
no bloquean.

## Resumen

INV-25 homologa los endpoints del Core API construidos en Release 1 contra la
bodega simulada para que funcionen con la bodega real de INV-60/61: corrige los
que fallan, unifica la regla de permisos, incorpora la Bodega Central como
ubicación con su propio trato y suma el pronóstico al Swagger del Core API, con
la misma autenticación. Reemplaza el alcance original de la historia (proxy
genérico hacia `ml_service`), que en parte ya cubrió el cliente de INV-23.

**Historia de usuario.** Como desarrollador, quiero auditar y homologar los endpoints existentes del Core API contra la bodega de datos real, para que todo el sistema —no solo los endpoints nuevos de ML— funcione consistentemente con los datos reales de INV-60/61, incluyendo Bodega Central como ubicación válida.

| Campo | Valor |
| --- | --- |
| Prioridad | Highest |
| Puntos | 5 (reestimado después de la Fase 1, D10) |
| Épica | E8 Infraestructura |
| Sprint | Sprint 5 (21 sep – 10 oct) · etiqueta momento-ii |
| Depende de | INV-60/61 (bodega real) e INV-23 (cliente hacia `ml_service` y patrón de permisos) |
| Alimenta a | Todo lo que consume el Core API: dashboard (E9) y agente NLP (E10) |

**Dentro del alcance**

- Los 14 endpoints que la auditoría marcó "requiere ajuste" (causas A–F).
- Una sola regla de permisos por ubicación para inventario, alertas y reportes (D1, D2).
- La Bodega Central como `bodega_central`, distinta de una sucursal física (D6).
- `POST /api/ml/predict` en el Core API, con token y permisos (D8).
- Pruebas de integración de los módulos ajustados y los 4 scripts de Release 1 al día.

**Fuera del alcance**

- Cambios en el frontend (D9): quedan para INV-27 o la Fase 4 del plan privado. Esta historia solo garantiza que no se rompe.
- Proxy de Nginx y contratos de `ml_service` (predict, transferencias y compras no cambian).
- Cambios en las recomendaciones de INV-23 (D3).
- El historial de 30 días del detalle de inventario: lo limita el dato (una sola foto); solo se documenta.
- Endurecer la seguridad (puerto 8001 abierto, secreto JWT de desarrollo, CORS abierto): riesgo anotado para Release 3.

## Qué cambió frente al borrador

| Hallazgo | Evidencia | Decisión |
| --- | --- | --- |
| Rutas que no existen | No hay `/api/catalogo/*` ni `/api/dashboard/*`: los catálogos e inventario están en `/api/consulta/*` y el dashboard usa `/api/reportes/*` | La tabla de auditoría usa las rutas reales |
| La Fase 1 se podía hacer sin código | Se recorrieron los 23 endpoints con los tres roles y la evidencia quedó en `INV-25-auditoria.md` | Fase 1 entregada |
| "Permisos existentes sin cambios" no se puede cumplir | Los permisos se contradicen: `admin_bodega` ve todo en inventario y alertas, solo la Bodega en reportes y recibe 403 en el detalle. Los scripts de Release 1 esperaban que viera solo su sucursal | D1 |
| La excepción de la Bodega chocaba con INV-23 | En INV-23, un `admin_sucursal` que pide BODEGA_CENTRAL recibe 403 (C1) | D2, D3 |
| "Swagger unificado, mismo esquema de auth" | `predict`, `transferencias` y `compras` viven en `ml_service` (puerto 8001), sin autenticación | D8 |
| Alertas de la Bodega sin sentido | 1.415 "sin movimiento" de una ubicación que no vende | D4 |
| Stock negativo como "stock crítico" | 202 filas como crítico y 18 sin ninguna alerta | D4 |
| Proveedores por categoría | Solo 2.540 de 4.449 productos tienen alguno | D5 |
| 2 puntos | 14 endpoints a ajustar, el pronóstico y las pruebas | D10 |

## Decisiones acordadas

| Código | Tema | Decisión |
| --- | --- | --- |
| D1 | Regla para `admin_bodega` | Ve todo, como el gerente, en inventario, detalle, alertas y reportes, y puede filtrar por cualquier ubicación |
| D2 | La Bodega para un `admin_sucursal` | Ve su sucursal y el **stock** de la Bodega: cada fila de su inventario trae `stock_bodega`, y con el `sucursal_id` de la Bodega ve la lista y el detalle del stock de la Bodega. **No** ve alertas de la Bodega, solo las de su sucursal |
| D3 | La Bodega en las recomendaciones de INV-23 | Sin cambios: sigue el 403 si pide BODEGA_CENTRAL. Con su sucursal sigue viendo sus compras directas, las de la Bodega que cubren su necesidad (vistas desde su sucursal) y los traslados hacia su sucursal o desde ella |
| D4 | Alertas de la Bodega y stock negativo | La Bodega sale de `sin_movimiento` y `rotacion_baja`, y mantiene `stock_critico` y `stock_bajo` contra la demanda de la red. El stock negativo pasa a un tipo nuevo, `inconsistencia_inventario`, con urgencia `critica` |
| D5 | Proveedores | `productos/{id}` y `proveedores/{id}` usan `dw.producto_proveedor` |
| D6 | Tipo de ubicación | Campo nuevo `tipo_ubicacion` (`sucursal` o `bodega_central`) en inventario y alertas. `/consulta/sucursales` ya trae `tipo` |
| D7 | SIN_SUCURSAL | Sus ventas siguen en los totales; sale de `/consulta/sucursales` y no se puede filtrar por ella |
| D8 | ML en el Swagger | `POST /api/ml/predict` en el Core API, con token y permisos, sobre el cliente de INV-23. `ml_service` queda como servicio interno |
| D9 | Frontend | Fuera del alcance |
| D10 | Puntos | 5 |

**Reglas que se desprenden** (no estaban en el formulario; revisar)

| Código | Regla |
| --- | --- |
| R1 | **Ubicación ajena: 403.** Si un `admin_sucursal` pide explícitamente otra sucursal (o la Bodega donde D2 no la permite), recibe 403, como en el detalle de inventario y en INV-23. Hoy inventario, alertas y reportes lo ignoran en silencio y le devuelven su sucursal. El frontend no se afecta: un `admin_sucursal` no envía `sucursal_id` |
| R2 | **`sucursal_id` inválido: 422.** Un id que no existe, o el de SIN_SUCURSAL (D7), responde 422. Hoy devuelve listas vacías o ventas de SIN_SUCURSAL |
| R3 | **`stock_bodega`.** El stock de la Bodega para el mismo producto; 0 si la Bodega no tiene fila (como en INV-22), y nulo en las filas de la propia Bodega |
| R4 | **Inconsistencia con cobertura 999.** Las 18 filas con stock negativo y cobertura centinela 999, que hoy no generan ninguna alerta, también son `inconsistencia_inventario` |
| R5 | **Errores de `predict`.** Los 404 y 422 de `ml_service` son errores de la petición (producto o sucursal desconocidos, historia insuficiente, sucursal no física) y pasan tal cual, con su `detail`. Los demás se traducen como en INV-23 (503, 504 y 502) |
| R6 | **`dias` en tendencias.** Se acepta el parámetro que el frontend ya envía: sin `fecha_inicio`, la serie empieza `dias` días antes de `fecha_fin` (30 por defecto, como hoy) |

## Regla de permisos por ubicación

Una sola función resuelve qué ubicaciones puede ver cada usuario en cada tipo
de dato, y la usan inventario, alertas y reportes.

| Rol | Stock: inventario (lista, detalle, resumen, valorizado) | Alertas | Ventas y KPIs (reportes) |
| --- | --- | --- | --- |
| `gerente`, `admin_bodega` | Todas; con `sucursal_id`, esa | Todas; con `sucursal_id`, esa | Todas; con `sucursal_id`, esa |
| `admin_sucursal` | Su sucursal por defecto; la Bodega con su `sucursal_id`; otra, 403 | Solo su sucursal; la Bodega u otra, 403 | Solo su sucursal; la Bodega u otra, 403 |

En todos los casos, un `sucursal_id` que no existe o el de SIN_SUCURSAL da 422 (R2).

## Cambios por endpoint

| Endpoint | Cambio | Paquete |
| --- | --- | --- |
| `GET /api/consulta/productos` | `codigo_item` como texto | P1 |
| `GET /api/consulta/productos/{id}` | `codigo_item` como texto; `proveedores` desde `producto_proveedor` | P1, P6 |
| `GET /api/consulta/sucursales` | `ciudad`, `departamento` y `factor_volumen` opcionales; sin SIN_SUCURSAL | P1 |
| `GET /api/consulta/proveedores/{id}` | `productos` desde `producto_proveedor`, con `codigo_item` como texto | P1, P6 |
| `GET /api/consulta/inventario` | Regla de permisos; `tipo_ubicacion` y `stock_bodega` en cada fila | P2, P5 |
| `GET /api/consulta/inventario/detalle` | Regla de permisos (arregla el 403 de `admin_bodega`); `tipo_ubicacion` y `stock_bodega` | P2, P5 |
| `GET /api/consulta/inventario/resumen` | Acepta `sucursal_id`; regla de permisos; `tipo_ubicacion` por sucursal | P2, P4, P5 |
| `GET /api/consulta/inventario/valorizado` | Acepta `sucursal_id`; regla de permisos; `tipo_ubicacion` por grupo | P2, P4, P5 |
| `GET /api/alertas` | Regla de permisos; reglas de D4; `tipo=inconsistencia_inventario` como filtro; `tipo_ubicacion` | P2, P3, P5 |
| `GET /api/alertas/resumen` | Acepta `sucursal_id`; reglas de D4; `por_tipo` con la clave nueva | P2, P3, P4 |
| `GET /api/reportes/*` (6) | Regla de permisos: `admin_bodega` ve todo y filtra; validación de `sucursal_id` | P2 |
| `GET /api/reportes/tendencias` | Además, acepta `dias` (R6) | P4 |
| `POST /api/ml/predict` (nuevo) | Pronóstico con token y permisos (D8, R5) | P7 |

**Cambios de contrato y por qué se justifican**

| Cambio | Justificación |
| --- | --- |
| `codigo_item` entero → texto | Hoy da 500 con 2.786 de 4.449 productos, y los numéricos pierden los ceros. El frontend no usa estos endpoints |
| `ciudad`, `departamento` y `factor_volumen` pueden ser nulos | Hoy `/sucursales` da 500: la bodega real no tiene esos datos |
| `/sucursales` sin SIN_SUCURSAL | D7: no tiene inventario y no tiene sentido elegirla |
| Alerta nueva `inconsistencia_inventario` y la Bodega sin `sin_movimiento` | D4. El frontend muestra el tipo nuevo con su nombre crudo (`TIPO_LABEL[tipo] \|\| tipo`) hasta que se le agregue la etiqueta |
| 403 y 422 donde hoy se ignora el parámetro | R1 y R2: el usuario sabe que su filtro no se aplicó |

Lo demás es aditivo: `tipo_ubicacion`, `stock_bodega`, `sucursal_id` en los
resúmenes, `dias` en tendencias y el endpoint de pronóstico.

## Alertas (D4)

| Tipo | Regla | Ubicaciones |
| --- | --- | --- |
| `inconsistencia_inventario` (nuevo, urgencia `critica`) | Stock negativo, con cualquier cobertura (R4) | Todas |
| `stock_critico` (`critica`) | Cobertura < 3 días y stock ≥ 0 | Todas; en la Bodega, contra la demanda de la red |
| `stock_bajo` (`alta`) | Cobertura de 3 a 7 días | Todas |
| `sin_movimiento` (`media`) | Stock > 0 y 0 ventas en 30 días | Sucursales físicas |
| `rotacion_baja` (`media`) | Ventas < 20 % del promedio del producto | Sucursales físicas |

El `detalle` de `inconsistencia_inventario` dice "Stock negativo en la foto:
verificar el conteo", como en INV-21.

## Pronóstico en el Core API (D8)

`POST /api/ml/predict` recibe el mismo cuerpo que `POST /api/predict` de
`ml_service` (`producto_id` o `id_producto`, `sucursal_id` o `id_sucursal`,
`horizonte`, `fecha_corte` opcional) y devuelve su respuesta sin cambios.

| Rol | Puede pronosticar |
| --- | --- |
| `gerente`, `admin_bodega` | Cualquier sucursal física |
| `admin_sucursal` | Solo su sucursal; otra, 403 |

Errores (R5): 404 y 422 de `ml_service` pasan tal cual; 503 si `ml_service` o
la bodega no están disponibles; 504 si no responde en 120 s; 502 para otro
error. No usa caché: cada pronóstico tarda menos de un segundo.

## Criterios de aceptación

**Fase 1** (cumplida)

1. Todos los endpoints del Core API quedan listados en la tabla de auditoría.
2. Cada uno verificado contra la bodega real y marcado compatible, requiere ajuste u obsoleto, con evidencia.
3. La tabla queda en `docs/INV-25-auditoria.md` antes de iniciar la Fase 2.

**Fase 2**

4. Los 14 endpoints "requiere ajuste" responden bien contra la bodega real: ninguno da 500 y los datos coinciden con `dw.*`.
5. La regla de permisos de la tabla se aplica igual en inventario, alertas y reportes (D1, D2, R1, R2).
6. Un `admin_sucursal` ve el stock de la Bodega (`stock_bodega` y la lista con su `sucursal_id`) y no ve sus alertas.
7. La Bodega se distingue con `tipo_ubicacion = bodega_central` en inventario y alertas, y con `tipo` en `/sucursales` (D6).
8. Las alertas siguen D4: la Bodega sin `sin_movimiento` ni `rotacion_baja`, y el stock negativo como `inconsistencia_inventario`.
9. `productos/{id}` y `proveedores/{id}` usan `producto_proveedor` (D5).
10. `POST /api/ml/predict` responde en el Swagger del Core API, con el mismo esquema de autenticación que los demás (D8, R5).
11. Ningún endpoint pierde funcionalidad de la que dependa el frontend: el recorrido con los tres roles no muestra pantallas rotas.
12. Las recomendaciones de INV-23 y los endpoints de `ml_service` no cambian, y sus pruebas siguen pasando.

## Casos de prueba

| Caso | Resultado esperado |
| --- | --- |
| `admin_sucursal` sin `sucursal_id` en inventario | Su sucursal, igual que hoy, con `stock_bodega` en cada fila |
| `admin_sucursal` con el `sucursal_id` de la Bodega en inventario y en el detalle | 200 con el stock de la Bodega |
| `admin_sucursal` con otra sucursal física | 403 en inventario, alertas y reportes |
| `admin_sucursal` con la Bodega en alertas o reportes | 403 |
| `gerente` y `admin_bodega` con cualquier ubicación | 200 en todo; `admin_bodega` ve reportes con ventas |
| `admin_bodega` en el detalle de una sucursal | 200 (hoy 403) |
| `sucursal_id` inexistente o de SIN_SUCURSAL | 422 |
| Productos con código de texto y con ceros | `P1632` y `00008`, sin error |
| `/consulta/sucursales` | 4 ubicaciones, sin SIN_SUCURSAL, con `tipo`; sin error por los nulos |
| Detalle de producto y de proveedor | El proveedor de `producto_proveedor`; P1632 → Lácteos del Cauca |
| Alertas con stock negativo | `inconsistencia_inventario`, nunca `stock_critico` |
| Alertas de la Bodega | Sin `sin_movimiento` ni `rotacion_baja`; sí `stock_critico` y `stock_bajo` |
| Resúmenes con `sucursal_id` | Cuentan solo esa ubicación |
| `tendencias?dias=7` | La serie empieza 7 días antes de `fecha_fin` |
| Pronóstico como `admin_sucursal` de su sucursal / de otra | 200 / 403 |
| Pronóstico de la Bodega o con historia insuficiente | 422 / 404 con el `detail` de `ml_service` |
| Endpoint "obsoleto" | No hay ninguno |

**Pruebas**

- **Integración** (pytest, marca `integracion`, dentro del contenedor `api`): cada endpoint ajustado contra la bodega real con los usuarios de prueba, incluidas las cifras de "Resultados esperados". Las rutas de Release 1 son SQL directo contra la base, así que esta es la prueba principal.
- **Unitarias** (pytest, sin servicios): la regla de permisos por ubicación y `POST /api/ml/predict` con el transporte falso de INV-23.
- La cobertura mínima es 80 % sobre los módulos tocados (`consulta`, `inventario`, `alertas`, `reportes`, la regla de permisos y `predict`), medida con las dos marcas.
- Los 4 scripts de Release 1 (`test_consulta.sh`, `test_inventario.sh`, `test_alertas.sh`, `test_reportes.sh`) se actualizan a los datos y las reglas nuevas, sin fallas. `test_auth.sh` no cambia.

## Definition of Done

- [ ] Cumple los criterios de aceptación de ambas fases.
- [ ] Tabla de auditoría de la Fase 1 entregada y versionada en `docs/` (escrita; falta el commit).
- [ ] Pruebas con cobertura ≥ 80 % sobre los módulos tocados, incluidos los casos de la tabla.
- [ ] Autorrevisión documentada en el commit o PR.
- [ ] `docs/INV-25-homologacion.md` con los cambios por endpoint; `docs/AMBIENTE-DESARROLLO.md` al día.
- [ ] Integrado en `develop`.
- [ ] Verificado en Docker Compose local con los 3 roles (gerente, `admin_sucursal` y `admin_bodega`).
- [ ] Swagger del Core API verificado con `predict` y los endpoints de INV-23 junto a los demás.
- [ ] Sin bugs bloqueantes.

## Resultados esperados con los datos reales

Calculados con consultas a la bodega (foto al 2025-12-31). La implementación
debe confirmarlos.

| Consulta | Hoy | Después |
| --- | --- | --- |
| `/consulta/productos` | 500 | 4.449 productos; `P1632` y `00008` como texto |
| `/consulta/sucursales` | 500 | 4 ubicaciones: PRINCIPAL, LA 21, GLORIETA y BODEGA_CENTRAL |
| `/consulta/productos/91` (P1632) | 500 | Proveedor: Lácteos del Cauca Ltda. |
| `/consulta/proveedores/1` | 500 | Distribuidora Valle S.A.S. con 1.978 productos |
| Alertas, gerente | 5.849 | 4.452: `stock_critico` 1.114 (Bodega 592), `stock_bajo` 386, `sin_movimiento` 2.453, `rotacion_baja` 279, `inconsistencia_inventario` 220 |
| Alertas, `admin_sucursal` PRINCIPAL | 1.307 | 1.308: crítico 202, bajo 138, sin movimiento 865, rotación baja 8, inconsistencia 95 |
| Inventario de la Bodega para `admin_sucursal` | Imposible (devuelve PRINCIPAL) | 1.973 filas |
| `stock_bodega` en las filas de las sucursales | No existe | 9.128 filas: 4.607 con fila en la Bodega y 3.370 con stock > 0. Arroz P3937 en PRINCIPAL: stock 556, cobertura 5,3 días, Bodega 4.024. Huevos P1632: Bodega 0 |
| Reportes de `admin_bodega` | Vacíos | Iguales a los del gerente: diciembre 737,9 millones |
| Resumen de inventario con `sucursal_id=2` | 11.101 (ignora el filtro) | 1.888 (LA 21) |

## Pendientes de confirmar

| # | Pregunta | Valor por defecto mientras tanto |
| --- | --- | --- |
| 1 | ¿Las alertas de la Bodega deberían medirse de otra forma (por ejemplo, contra los traslados de INV-22)? | Cobertura contra la demanda de la red, la aproximación del ETL |
| 2 | ¿Los KPIs cuentan como "en riesgo" las filas con stock negativo? | Sí, como hoy (cobertura < 7 días) |
| 3 | ¿Dónde vive el seed de usuarios de prueba (repo o local)? | Local; las pruebas de integración se saltan sin usuarios |

El fix de INV-26 resolvió el 2 y el 3 (`docs/INV-26-fix-requerimientos.md`):
el stock negativo no cuenta como "en riesgo", que pasa a ser bajo + crítico del
semáforo (K9), y el seed vive en el repo, en `api/scripts/seed_usuarios.py` (K8).

## Ambiente de desarrollo

1. Crear la rama desde `develop` actualizado: `git checkout -b feature/INV-25-homologacion-api`.
2. Usuarios de prueba en la base local (ya aplicados en INV-23).
3. `docker compose up -d --build api`.
4. Pruebas dentro del contenedor:
   - `docker exec inventaio-api python -m pytest --cov=consulta --cov=inventario --cov=alertas --cov=reportes --cov=ml`;
   - `bash api/tests/test_<modulo>.sh` desde Ubuntu para los 4 scripts.

**Archivos a tocar**

| Archivo | Cambio |
| --- | --- |
| `api/core/ubicaciones.py` (nuevo) | La regla de permisos por ubicación |
| `api/schemas/consulta.py`, `api/consulta/router.py` | P1, P6 |
| `api/schemas/inventario.py`, `api/inventario/router.py` | P2, P4, P5 |
| `api/schemas/alertas.py`, `api/alertas/router.py` | P2, P3, P4, P5 |
| `api/reportes/router.py` | P2, R6 |
| `api/ml/router.py`, `api/ml/cliente.py`, `api/schemas/recomendaciones.py` o un esquema nuevo | P7 |
| `api/tests/test_homologacion_*.py` (nuevos) y los 4 `.sh` | P8 |
| `docs/INV-25-homologacion.md` (nuevo), `docs/AMBIENTE-DESARROLLO.md` | Documentación |

## Riesgos y limitaciones

- **403 y 422 donde antes se ignoraba el filtro (R1, R2).** Un cliente que mandara una sucursal ajena y esperara su propia sucursal ahora recibe un error. El frontend actual no lo hace.
- **Tipo de alerta nuevo.** Un cliente que liste los tipos fijos no conocerá `inconsistencia_inventario`. El frontend lo muestra con su nombre crudo.
- **Proveedores ficticios.** `producto_proveedor` es la relación de la bodega, pero los proveedores de INV-60 son inventados (B13 de INV-21).
- **Foto única.** El historial de inventario y las alertas de rotación dependen de cuántas fotos haya; con una sola, el historial trae un punto.
- **Seguridad.** `ml_service` sigue publicado en el puerto 8001 sin autenticación: el pronóstico por el Core API no cierra esa puerta.
