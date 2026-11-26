# INV-41 · Pruebas de carga y revisión de seguridad · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-41 «Pruebas de carga y revisión de seguridad» · 5 SP · Sprint 8 · Release 4 · límite 3-dic (antes 26-nov) |
| Depende de | El staging nuevo en k3s (docs/INFRA-k3s-serverless-requerimientos.md), con Redis en disco |
| Alimenta a | INV-69: la primera versión de producción, v4.0.0-rc.1, lleva estos arreglos. El tamaño de producción sale del reporte |
| Rama | `feature/INV-41-carga-seguridad`, desde `develop` (`74acd00`) |
| Hallazgos de origen | INV-66, hallazgo C11 (comentario 10094 en Jira) |

Revisión del 25 de noviembre de 2026 contra `develop` y el staging nuevo (`https://d32ramysc8c7pj.cloudfront.net`, v3.0.0 · `74acd00`). El usuario tomó ese día las decisiones D1 a D4 en un formulario. Las demás son técnicas y siguen de los hallazgos.

## 1. Historia de Jira

> Como responsable del sistema, quiero medir cuánta carga aguanta InventAI/o y cerrar los huecos de seguridad que quedaron de INV-66, para pasar a producción sabiendo sus límites.

Son seis criterios: cinco (M) y uno (S). Uso esperado: un gerente y unos cinco administradores, con picos de 10 a 20 sesiones a la vez. Fuera de alcance: pruebas de penetración activas, WAF y autoescalado.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| H1 | El login responde 403 «Cuenta desactivada» antes de verificar la clave (`api/auth/router.py`), así que deja saber qué correos tienen una cuenta desactivada | Criterio 4: la clave se verifica primero, y la respuesta es un 401 igual para todos |
| H2 | Con un correo inexistente, el login responde sin calcular bcrypt; con uno existente, tarda lo que tarda bcrypt (unos cientos de milisegundos). El tiempo de respuesta también delata si la cuenta existe | Con un correo inexistente se verifica contra un hash ficticio del mismo costo |
| H3 | La lista negra de refresh tokens es un `set` en la memoria del proceso: un reinicio la borra, y un token de una sesión cerrada vuelve a servir hasta que vence, a los 7 días | Criterio 3: pasa a Redis, que guarda en disco desde el plan de k3s |
| H4 | La renovación revisa la lista y después agrega el token, en dos pasos: dos renovaciones simultáneas con el mismo token pueden pasar las dos | La rotación es atómica: `SET NX` con el vencimiento del token |
| H5 | El cierre de sesión agrega a la lista cualquier texto que llegue como refresh token, sin verificar que sea un token vigente de esa persona | Solo se revoca un refresh token válido del mismo usuario; lo demás se ignora |
| H6 | El frontend renueva sin coordinar (`tryRefresh` en `frontend/src/api/client.js`). Al vencer el token de acceso (30 min), el Dashboard lanza unas 6 consultas en paralelo y cada una renueva con el mismo refresh token: la primera gana, las demás reciben 401 y la app manda al login. Con dos pestañas pasa lo mismo, porque los tokens viven en `localStorage`. Con la rotación atómica de H4 pasaría siempre | La renovación se coordina en el frontend (D3) |
| H7 | El Core API admite `CHAT_MAX_FLUJOS=1` conversación de Vera en total. Ese tope se puso para Ollama en local, con 8 GB de GPU (INV-36), y staging lo hereda porque el ConfigMap no lo define. Con Bedrock, el agente llama al modelo de forma asíncrona (`httpx.AsyncClient`) y no tiene un límite propio | Criterio 2: con el tope en 1, dos de tres flujos simultáneos reciben 429. Sube a 6 en el ConfigMap, uno por persona del negocio; el límite de uno por usuario sigue |
| H8 | El límite de login solo cuenta los fallos (INV-66): k6 desde una sola IP, con claves correctas, no lo dispara | El escenario de login no necesita varias IP |
| H9 | La caché de recomendaciones vive en la memoria del Core API, con una clave por endpoint y 6 horas de vida (decisión 14). La primera consulta tarda de 20 a 40 s | La corrida calienta la caché antes de medir. El criterio 1 es con la caché caliente |
| H10 | El Core API corre en un solo proceso de uvicorn, y las rutas síncronas van al grupo de hilos de AnyIO (40 por defecto). El servicio de predicción tiene 2 GiB de límite, medido el 25-nov | Es lo que la carga pone a prueba. La línea base de memoria del 25-nov sirve para el criterio 6 |
| H11 | Vera cuesta unos US$0,0011 por pregunta en Bedrock (decisión 35) | Tres flujos durante 5 minutos cuestan menos de US$0,10 |
| H12 | La ficha dice que el mensaje del login será «Correo o contraseña incorrectos», pero la app, la guía de uso y la guía del cliente dicen «Credenciales inválidas» | Se mantiene «Credenciales inválidas» (D4) y se corrige la ficha |
| H13 | El origen de la máquina solo acepta a CloudFront con una cabecera secreta | k6 y ZAP van contra la dirección de CloudFront, como un usuario |
| H14 | Hallado en el ensayo del 25-nov, con 3 usuarios virtuales: el p95 del Dashboard y de Alertas ya pasaba de 7 s. La lista del inventario de un administrador de sucursal tardaba de 3,4 a 4,7 s sin carga, en staging y en local. Las consultas filtran la foto con `JOIN dw.dim_tiempo t … WHERE t.fecha = :fecha`, y Postgres estima esa unión con la selectividad de `dim_tiempo` (miles de fechas). Espera 2 filas donde hay 4.156 y, con el filtro de sucursal, elige bucles anidados que recorren las ventas de 30 días una vez por fila | Las 14 consultas con ese patrón filtran además `fi.id_tiempo` (o `v.id_tiempo`) con una subconsulta sobre la misma fecha (`api/core/foto.py`). En local, esa lista pasa de 3,3 s a 0,31 s y las 24 respuestas comparadas con tres roles son idénticas |
| H15 | Las alertas por reglas se ordenan por urgencia y valor, sin desempate: el orden de las que empatan, y con él la paginación, dependía del plan de Postgres | Desempatan el tipo, el producto y la sucursal, como el inventario desde INV-65 |
| H16 | Corridas oficiales del 25-nov en staging (`785b458`), con pausas de 1 a 3 s entre pantallas. Con 10 usuarios virtuales, la CPU de la EC2 llegó al 100 % y el p95 a 7 s, sin errores. Con 20, el p95 fue de 15 s y hubo 1,1 % de 5xx. La escalera se cortó sola a los 5 minutos, con unos 40 usuarios. En local, sin límite de CPU, cada lectura cuesta unos 0,3 s de CPU: 0,23 s en Postgres y 0,07 s en el Core API. Los resúmenes recorren la bodega en cada petición, aunque sus datos solo cambian al recargarla. Una t3.medium da unas 6 o 7 lecturas por segundo, y el perfil pide unas 35 | La caché de lecturas en Redis (D5). En local, con el mismo perfil, la CPU baja de 4,5 núcleos a 0,6 con más peticiones atendidas, y el p95 del Dashboard de 1,06 s a 0,22 s |
| H17 | Los 5xx con 20 usuarios eran del pool de conexiones: el registro del Core API mostró 69 «QueuePool limit» y 138 «TimeoutError». SQLAlchemy abre 5 conexiones más 10 de reserva, frente a los 40 hilos de AnyIO; con la CPU saturada, las peticiones esperaban conexión y a los 30 s daban 500 | El pool queda en 10 más 30 de reserva (`DB_POOL_SIZE` y `DB_MAX_OVERFLOW`) |
| H18 | El guion pausaba de 1 a 3 s entre pantallas, unas 4 o 5 veces más rápido que una persona que lee el Dashboard | La pausa del criterio 1 pasa a ser de 5 a 15 s (D6) |
| H19 | Corridas del 25-nov con la caché (`2aa1546`). Con 10 usuarios y la pausa lectora se cumple el criterio 1. Con 20, el Dashboard y Alertas cumplen (p95 de 1,2 s, 0 % de 5xx), pero Recomendaciones da 3,2 s. Su primer byte llega en 0,4 s y el resto es transferencia: las respuestas de la API viajaban sin comprimir (compras, 825 KB en vez de 78 KB). Detrás de CloudFront y Caddy toda petición trae «Via», y con `gzip_proxied` en `off` (el valor por defecto) Nginx no comprime. La web estática sí llega comprimida, desde CloudFront | `gzip_proxied any` y `gzip_vary on` en `frontend/nginx.conf`. El chat por SSE sigue sin compresión |
| H20 | Corridas del 25-nov con la caché y la compresión (`549e101`). Con 20 usuarios y la pausa lectora, el peor p95 es el del login, 1,28 s, y no hay errores en 2.866 peticiones: se cumple el criterio 1. La escalera, con la pausa rápida, llega al final: con 40 usuarios sostiene unas 50 peticiones por segundo con un p95 de 2,3 s y sin errores; con 60, el p95 pasa de 5 s y aparecen errores (1,5 %), y con 80 llegan al 7,6 %. Los errores tienen tres firmas: 502 al instante, 504 a los 10 s (el `proxy_connect_timeout` de Nginx hacia el Core API) y 26 respuestas 500 a los 32 s (la espera del pool de conexiones) | El límite observado y la recomendación de tamaño van al reporte (criterio 6). La causa de los 502 y 504 se confirma con los eventos de Kubernetes de esa hora |
| H21 | ZAP del 25-nov contra `549e101`. El baseline de la web y el escaneo pasivo de la API con sesión no dan alertas altas ni medias: se cumple el criterio 5. Quedan cinco bajas, todas de la web en CloudFront: faltan Permissions-Policy, Cross-Origin-Opener-Policy, Cross-Origin-Resource-Policy y Cross-Origin-Embedder-Policy, y S3 se anuncia en «Server: AmazonS3» | Se corrigen en la política de cabeceras de CloudFront (D9) |
| H22 | Lista de chequeo de ASVS 4.0.3, nivel 1. La API acepta claves nuevas de 8 caracteres, y el punto 2.1.1 pide 12. Tampoco revisa claves filtradas (2.1.7) ni muestra un medidor de fortaleza (2.1.8) | Se justifican en el reporte (D7) |
| H23 | Cada renovación entrega un refresh token nuevo de 7 días: una sesión que se usa nunca vuelve a pedir la clave. El punto 3.3.2 pide reautenticar al menos cada 30 días. Los tokens viven en `localStorage`, y el punto 3.2.3 prefiere cookies seguras o `sessionStorage` | Tope de 30 días desde el login (D8). `localStorage` se justifica |
| H24 | Las respuestas de la API no traen `Cache-Control`: el navegador podría guardar datos del negocio (punto 8.2.1) | `Cache-Control: no-store` en Nginx (D9) |
| H25 | `/api/docs`, `/api/redoc` y `/api/openapi.json` quedan públicos en staging. La página de `/api/docs` ni carga, porque trae sus scripts de un CDN que la CSP bloquea, y el OpenAPI ya está versionado en el repositorio | Solo con `ENTORNO=desarrollo` (D10) |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| D1 | k6 y ZAP corren desde el equipo de desarrollo (WSL). k6 como binario verificado por su huella y ZAP en Docker, desde GHCR. Las claves salen de `~/.config/inventaio/claves-staging.json` y nunca van al repositorio. Los reportes crudos quedan en `evidencias/inv41/`, que es privado, y el repositorio solo lleva el resumen. ZAP hace el baseline de la web y además escanea en pasivo el tráfico de la API con sesión: k6 pasa por ZAP como proxy, sin ataques activos | Usuario, 25-nov |
| D2 | Si Redis no responde, la renovación falla cerrada: responde 401 y la persona vuelve a iniciar sesión. El login sigue con su respaldo en memoria. Un token de una sesión cerrada nunca vuelve a servir | Usuario, 25-nov |
| D3 | La renovación se coordina en el frontend. Hay una sola renovación a la vez entre todas las pestañas, con Web Locks del navegador. Si el token de acceso guardado ya no es el que falló, otra consulta u otra pestaña ya renovó, y se usa ese sin llamar al servidor. El servidor mantiene la rotación estricta | Usuario, 25-nov |
| D4 | El 401 del login dice «Credenciales inválidas» para un correo inexistente, una clave incorrecta y una cuenta desactivada | Usuario, 25-nov |
| D5 | Caché de lecturas en Redis (`api/core/cache_lecturas.py`) para los GET de inventario, alertas por reglas, consulta y reportes. La clave combina el endpoint, sus parámetros, el rol y la sucursal, que es todo aquello de lo que dependen los permisos. Una versión de los datos (los cambios del esquema `dw` en `pg_stat_user_tables` y la fecha de hoy) invalida las entradas al recargar, y cada una vence a los 10 minutos. El usuario se resuelve antes de leer la caché, y solo se guardan las respuestas 200 | Usuario, 25-nov |
| D6 | El criterio 1 se mide con pausas de 5 a 15 s entre pantallas, como una persona que lee. La escalera usa de 1 a 3 s, como prueba de estrés del criterio 6. El reporte trae las dos | Usuario, 25-nov |
| D7 | Las claves nuevas siguen con un mínimo de 8 caracteres. El mínimo de 12, la revisión de claves filtradas y el medidor de fortaleza se justifican en el reporte como riesgo aceptado | Usuario, 25-nov |
| D8 | La sesión dura como máximo 30 días desde el login, aunque se use. Después hay que volver a iniciar sesión. `localStorage` se justifica: la CSP estricta frena la inyección de scripts, y con `sessionStorage` habría que iniciar sesión en cada pestaña | Usuario, 25-nov |
| D9 | Se corrigen las cinco alertas bajas de ZAP en la política de cabeceras de CloudFront, que el usuario aplica con OpenTofu. Además, la API responde con `Cache-Control: no-store` desde Nginx | Usuario, 25-nov |
| D10 | La documentación interactiva y el OpenAPI del Core API y del servicio de predicción solo se sirven con `ENTORNO=desarrollo` | Usuario, 25-nov |
| T1 | La lista negra guarda en Redis la huella SHA-256 del token, no el token, con la clave `auth:revocado:<huella>` y un vencimiento igual a lo que le queda al token. Redis guarda en disco, y así el disco no tiene credenciales | Técnica (H3) |
| T2 | La renovación valida el token, al usuario y su estado, y solo entonces lo marca como usado con `SET NX`. Si ya estaba marcado, responde 401 «Token invalidado» | Técnica (H4) |
| T3 | El cierre de sesión revoca el refresh token solo si es válido, de tipo refresh y del mismo usuario. Si Redis no responde, responde 503: el frontend borra la sesión local igual, y el registro del Core API lo deja anotado | Técnica (H5) |
| T4 | Una cuenta desactivada con la clave correcta cuenta como fallo para el límite de login, igual que una clave incorrecta | Técnica (D4) |
| T5 | `CHAT_MAX_FLUJOS=6` en el ConfigMap de k8s (base). Compose y el desarrollo local siguen con 1, por Ollama | Técnica (H7) |
| T6 | Las cuentas de k6 son las 5 de staging (gerente, tres administradores de sucursal y bodega), repartidas entre los usuarios virtuales | Técnica |
| T7 | Las métricas de la EC2 (CPU, memoria y créditos de CPU) se leen de CloudWatch en CloudShell con `pruebas/carga/metricas_ec2.sh`, que solo imprime porcentajes. Durante la corrida, el uso por pod sale de `kubectl top` en la máquina | Técnica |

## 4. Diseño

### 4.1 Lista negra en Redis (`api/auth/lista_negra.py`)

- `ListaNegra(cliente)` tiene dos métodos:
  - `revocar(token, exp)` hace `SET auth:revocado:<sha256> 1 NX EX <segundos hasta exp>` y devuelve si lo marcó ahora;
  - `revocada(token)` lo consulta.
- Los errores de Redis no se ocultan: el endpoint decide qué hacer con ellos (D2, T3).
- `get_lista_negra()` crea el cliente con los mismos tiempos cortos del límite de login (0,5 s).

### 4.2 Endpoints (`api/auth/router.py`)

| Endpoint | Antes | Después |
| --- | --- | --- |
| `POST /api/auth/login` | 401 sin usuario (sin bcrypt); 403 «Cuenta desactivada» antes de la clave; 401 con clave incorrecta | Siempre se verifica con bcrypt (con un hash ficticio si no hay usuario). Sin usuario, con clave incorrecta o con la cuenta desactivada: 401 «Credenciales inválidas» y un fallo para el límite |
| `POST /api/auth/refresh` | Revisa el `set` y luego agrega | Valida el token, el tipo, el usuario y si está activo, y luego `SET NX`. Si ya estaba: 401 «Token invalidado. Inicie sesión nuevamente.». Si Redis no responde: 401 «No se pudo renovar la sesión. Inicie sesión nuevamente.» |
| `POST /api/auth/logout` | Agrega cualquier texto | Revoca el refresh token si es válido y del mismo usuario. Si Redis no responde: 503 |

### 4.3 Renovación en el frontend (`frontend/src/api/client.js` y `chat.js`)

- `tryRefresh(accessVencido)` recibe el token de acceso que recibió el 401.
- Dentro de la pestaña, las consultas que fallan a la vez comparten una sola promesa de renovación.
- Entre pestañas, `navigator.locks.request('inventaio-renovar-sesion', …)` deja pasar una sola renovación a la vez. Donde no existe la API (las pruebas con jsdom), se renueva sin candado.
- Dentro del candado, si el token de acceso guardado ya no es el que falló, se devuelve `true` sin llamar al servidor.

### 4.4 Carga (`pruebas/carga/`)

- `inventaio.js` es el guion de k6. Los escenarios se eligen con variables de entorno:

| Escenario | Qué hace | Perfil |
| --- | --- | --- |
| `login` | Un login con clave correcta cada 2 s, con cuentas que rotan | Tasa constante, 5 min |
| `dashboard` | `reportes/kpis`, `reportes/tendencias`, `reportes/ventas/top-productos`, `consulta/inventario/resumen`, `alertas/resumen` y la primera página del inventario, como abre el Dashboard | Usuarios virtuales con pausas de 1 a 3 s |
| `alertas` | Alertas por reglas (primera página) y con IA | Igual |
| `recomendaciones` | Compras y traslados, con la caché caliente | Igual |
| `vera` | 3 usuarios distintos, cada uno con su conversación, en serie y por SSE. Solo corre si se pide | 3 usuarios virtuales, 5 min |

- `PERFIL=10` y `PERFIL=20` reparten los usuarios virtuales entre dashboard, alertas y recomendaciones (50, 25 y 25 %) durante 5 minutos, más el login. `PERFIL=escalera` sube de 20 a 80 en pasos de 20, con un minuto de subida y dos sostenidos por paso (12 minutos), y se corta solo si los errores pasan del 5 %. Sirve para el criterio 6.
- El `setup()` calienta la caché: compras, traslados y alertas con IA, con 130 s de espera.
- Cada petición lleva una etiqueta con su escenario, y los umbrales del criterio 1 se miden por escenario.
- `metricas_ec2.sh` (CloudShell): CPU, memoria, disco y créditos de la máquina de staging entre dos horas, en tramos de un minuto.
- Los resúmenes de k6 (JSON) y los de CloudWatch van a `evidencias/inv41/`.

### 4.5 Seguridad (`pruebas/seguridad/`)

- `zap_baseline.sh` corre `zap-baseline.py` de `ghcr.io/zaproxy/zaproxy:stable` contra la URL de staging, con la araña AJAX, y deja los reportes HTML y JSON en `evidencias/inv41/`.
- `zap_api_pasivo.sh` hace el escaneo pasivo de la API con sesión:
  - levanta ZAP como demonio;
  - pasa por él una iteración de cada escenario de k6, con un usuario y el proxy;
  - espera a que termine el escaneo pasivo;
  - saca su reporte.
- Cada alerta media o alta se clasifica en el reporte: corregida o justificada.
- La lista de chequeo es OWASP ASVS 4.0.3, nivel 1, solo lo aplicable. Va en el reporte, con el estado y la evidencia de cada punto.

### 4.6 Arreglos de la lista de chequeo y de ZAP (D8 a D10)

- **Tope de la sesión** (`api/core/security.py` y `api/auth/router.py`):
  - el refresh token lleva `auth_time`, la hora del login;
  - cada renovación la copia al refresh token nuevo;
  - el vencimiento es el menor entre 7 días desde ahora y 30 días desde el login (`SESION_MAX_DIAS`);
  - un token pasado del tope llega vencido, y la renovación lo rechaza con el 401 de siempre;
  - un refresh token emitido antes del cambio no trae `auth_time`, y su tope cuenta desde la primera renovación.
- **Cabeceras de la web** (`infra/modulos/ambiente/web.tf`):
  - Permissions-Policy apaga la cámara, el micrófono, la ubicación, los pagos y el USB; el portapapeles sigue, porque Vera tiene un botón de copiar;
  - Cross-Origin-Opener-Policy y Cross-Origin-Resource-Policy en `same-origin`, y Cross-Origin-Embedder-Policy en `require-corp`; la web solo carga recursos de su origen, como ya exige la CSP;
  - se quitan «Server», `x-amz-version-id` y `x-amz-server-side-encryption`. En lugar del de S3, CloudFront pone «Server: CloudFront».
- **API sin caché** (`frontend/nginx.conf`): `add_header Cache-Control "no-store" always` en `/api/`, también en los errores. El chat conserva su `no-cache`, que pone el Core API.
- **Documentación** (`api/main.py` y `ml_service/main.py`): `rutas_de_documentacion()` devuelve las tres rutas solo en desarrollo. El OpenAPI versionado se sigue generando con `tests.postman.exportar_openapi`.
- **Escalera por escalón** (`pruebas/carga/escalones.py`): la escalera guarda cada medición de k6 en un CSV comprimido. El script da el p95 de cada pantalla, las peticiones por segundo y los 5xx, por minuto y por escalón sostenido.

## 5. Criterios de aceptación

| # | Criterio | Cómo se comprueba |
| --- | --- | --- |
| 1 (M) | Con 20 usuarios virtuales durante 5 minutos, las lecturas con la caché caliente dan un p95 ≤ 2 s y 0 % de 5xx | Umbrales de k6 por escenario, con `PERFIL=20` |
| 2 (M) | Vera con 3 flujos simultáneos responde sin errores, dentro de 120 s | Escenario `vera`: cada respuesta trae `done` y no trae `error`, en menos de 120 s |
| 3 (M) | Tras reiniciar el Core API, un refresh token de una sesión cerrada sigue rechazado | Pruebas unitarias con Redis falso. En staging: cerrar sesión, `kubectl rollout restart deployment/api` y renovar da 401 |
| 4 (M) | El login responde 401 con el mismo texto para un correo inexistente, una clave incorrecta y una cuenta desactivada | Pruebas unitarias, más la comprobación en staging con las tres variantes |
| 5 (M) | ZAP baseline sin alertas altas abiertas, y las medias corregidas o justificadas | Reportes de ZAP y su clasificación en el reporte |
| 6 (S) | El reporte dice el límite observado y la recomendación de tamaño para producción | `PERFIL=escalera` y las métricas de la EC2 |

## 6. Casos de prueba automáticos

| Caso | Dónde |
| --- | --- |
| Revocar marca una vez: la segunda vez devuelve falso, y el vencimiento es lo que le queda al token | `api/tests/test_lista_negra.py` |
| La clave en Redis es la huella, no el token | Igual |
| Renovar dos veces con el mismo token: la segunda da 401 | Igual, con el endpoint |
| Un token cerrado en una instancia sigue rechazado en otra que comparte el mismo Redis, que es lo que pasa al reiniciar | Igual |
| Con Redis caído, la renovación da 401 y el cierre de sesión 503 | Igual |
| El cierre de sesión ignora un token de otro usuario o inválido | Igual |
| Login: correo inexistente, clave incorrecta y cuenta desactivada dan 401 con el mismo `detail`, y las tres cuentan como fallo | `api/tests/test_login_generico.py` |
| Con un correo inexistente, el login verifica contra el hash ficticio | Igual |
| Varias consultas con 401 a la vez hacen una sola renovación y se repiten todas | `frontend/src/api/client.test.js` |
| Si otra pestaña ya renovó (el token guardado cambió), no se llama al servidor | Igual |
| El chat usa el mismo mecanismo | `frontend/src/api/chat.test.js` |
| El login marca la hora y dura 7 días; la renovación la conserva; cerca del tope dura lo que queda; pasados 30 días da 401; un token sin `auth_time` empieza a contar al renovar | `api/tests/test_lista_negra.py` |
| Fuera de desarrollo, `/api/docs`, `/api/redoc` y `/api/openapi.json` dan 404; en desarrollo, 200 | `api/tests/test_documentacion.py` y `ml_service/tests/test_documentacion.py` |

## 7. Ruta de implementación

1. Los arreglos de seguridad (H1 a H6), el cupo de Vera (T5), el guion de k6 y los scripts de ZAP, con sus pruebas. Pull Request a `develop`.
2. Al integrarse, el despliegue automático lo lleva a staging. Se comprueban los criterios 3 y 4 en staging.
3. Las corridas con 10, 20 y la escalera, Vera, y ZAP en sus dos modos, con las métricas de la EC2.
4. Los arreglos de la lista de chequeo y de ZAP (D8 a D10) y el resumen por escalón. Pull Request a `develop`; el usuario aplica la política de CloudFront con OpenTofu.
5. Un segundo baseline de ZAP y la comprobación del tope y de las cabeceras en staging.
6. El reporte `docs/INV-41-carga-y-seguridad.md`, con la lista de chequeo y la clasificación de las alertas. Último Pull Request.

## 8. Definition of Done

La de Jira, con 7 casillas. Además: revisión con grep de claves y de nombres del negocio antes de cada push, porque el repositorio es público.

## 9. Riesgos

- **La escalera puede tumbar el staging.** Se corta sola con más del 5 % de errores. Kubernetes reinicia lo que caiga, y la alarma de memoria avisa si pasa del 85 %.
- **ZAP baseline no ve la API sin sesión.** Por eso el escaneo pasivo con el tráfico de k6.
- **CloudFront limita la espera del origen a 60 s.** Las recomendaciones en frío tardan hasta 42 s. Si la carga las lleva a más de 60 s, CloudFront da 504 y queda en el reporte.
- **El token de acceso sigue vivo hasta 30 minutos después de cerrar sesión**, porque es un JWT sin estado. Se acepta por su vida corta y queda anotado en la lista de chequeo.
