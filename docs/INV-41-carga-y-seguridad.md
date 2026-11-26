# INV-41 · Pruebas de carga y revisión de seguridad: resultados

**Fecha:** 25 y 26-nov-2026, contra el staging en k3s (`https://d32ramysc8c7pj.cloudfront.net`, v3.0.0).

- **Veredicto:** se cumplen los seis criterios de aceptación. Con 20 usuarios que leen, el peor p95 es el del login, 1,28 s, y no hay errores. Vera responde a tres flujos simultáneos sin errores. Los refresh tokens cerrados siguen rechazados después de reiniciar. El login da el mismo 401 en sus tres fallas. ZAP no deja alertas altas ni medias.
- **Límite observado:** el p95 pasa de 2 s con unos 40 usuarios rápidos, que piden unas 50 peticiones por segundo a la t3.medium de staging. Equivale a unas 110 personas leyendo a la vez, frente a un pico esperado de 20. Lo pone el Core API, que corre en un solo proceso: la máquina no pasó del 81 % de CPU.
- **Recomendación para producción:** la t3.medium con k3s alcanza y deja margen. RDS db.t4g.micro alcanza con la caché de lecturas; se vigilan sus créditos de CPU (sección 3).
- **Arreglos que salieron de las pruebas:** las consultas de la foto de inventario, la caché de lecturas en Redis, el pool de conexiones, la compresión de la API, el tope de la sesión, las cabeceras de la web, la API sin caché del navegador y la documentación interactiva solo en desarrollo.

**Documentos y código:**

- Requerimientos, hallazgos (H1 a H25) y decisiones (D1 a D10): `docs/INV-41-requerimientos.md`.
- Guion de carga y su resumen por escalón: `pruebas/carga/` (k6 v2.3.0). Escaneos: `pruebas/seguridad/` (OWASP ZAP 2.17.0). Cómo correrlos: `pruebas/README.md`.
- Los resúmenes crudos de k6, los reportes de ZAP y las métricas de la máquina quedan en `evidencias/inv41/`, que no se publica.
- Pull Requests: #67 (seguridad, k6 y ZAP), #68 (consultas de la foto), #69 (caché y pool), #70 (compresión) y #71 (sesión, cabeceras y documentación).

**Cómo leer las cifras:**

- **Usuario virtual:** un proceso de k6 que inicia sesión y recorre pantallas como una persona. Cada pantalla lanza a la vez sus consultas, como el navegador.
- **Pausa lectora:** de 5 a 15 s entre pantallas, como una persona que lee el Dashboard. Es la del criterio 1 (D6).
- **Pausa rápida:** de 1 a 3 s, unas 4 o 5 veces más rápida que una persona. Es la de la escalera, que busca el límite.
- **p95:** el tiempo por debajo del cual queda el 95 % de las peticiones de esa pantalla, medido desde el equipo de pruebas, a través de CloudFront.
- **5xx:** respuestas de error del servidor. Un 4xx esperado (por ejemplo, el login con una clave errada del recorrido) no cuenta.

## 1. Cómo se probó

| Pieza | Valor |
| --- | --- |
| Ambiente | Staging en k3s: una EC2 t3.medium (2 vCPU, 4 GiB) con todos los servicios, detrás de CloudFront y Caddy. Postgres en la misma máquina |
| Cuentas | Las 5 de staging (gerente, tres administradores de sucursal y bodega), repartidas entre los usuarios virtuales |
| Mezcla de pantallas | Dashboard con el inventario la mitad de las veces, Alertas (por reglas y con IA) un cuarto y Recomendaciones (compras y traslados) el otro cuarto. Además, un login cada 2 s |
| Caché | Antes de medir, la corrida calienta la caché de recomendaciones y de alertas con IA (H9) |
| Perfiles | 10 y 20 usuarios durante 5 minutos con la pausa lectora. Escalera de 20 a 80 usuarios, en pasos de 20 cada 3 minutos, con la pausa rápida |
| Desde dónde | El equipo de desarrollo, contra la dirección pública de CloudFront, como un usuario (D1, H13) |

## 2. Carga

### 2.1 Lecturas: criterio 1

Corridas con la pausa lectora, contra `549e101` (con la caché y la compresión):

| Pantalla | p95 con 10 usuarios | p95 con 20 usuarios |
| --- | --- | --- |
| Dashboard | 0,39 s | 0,28 s |
| Alertas | 0,50 s | 0,52 s |
| Recomendaciones | 0,74 s | 0,67 s |
| Login | 0,55 s | 1,28 s |
| 5xx | 0 % de 1.504 | 0 % de 2.842 |
| Peticiones por segundo | 4,7 | 8,9 |

El criterio pide un p95 de 2 s o menos y 0 % de 5xx con 20 usuarios: se cumple con margen.

### 2.2 Cómo se llegó ahí

| Versión | Qué cambió | Resultado |
| --- | --- | --- |
| `74acd00` | Punto de partida | Con solo 3 usuarios, el p95 del Dashboard y de Alertas pasaba de 7 s. Las consultas de la foto de inventario recorrían las ventas una vez por fila (H14) |
| `785b458` | Consultas de la foto con su `id_tiempo` (#68) | Con 10 usuarios y la pausa rápida, la CPU de la máquina llegaba al 100 % y el p95 a 7 s. Con 20, el p95 era de 15 s y había 1,1 % de 5xx, por el pool de conexiones (H16, H17). La escalera se cortó sola a los 5 minutos con 5,9 % de errores |
| `2aa1546` | Caché de lecturas en Redis y pool de 10 más 30 (#69) | Con 10 usuarios y la pausa lectora se cumplía el criterio. Con 20, Recomendaciones daba 3,2 s: su primer byte llegaba en 0,4 s y el resto era transferencia (H19) |
| `549e101` | Compresión de la API en Nginx (#70) | Se cumple el criterio con 20 usuarios (sección 2.1). Las compras de toda la red bajan de 825 KB a 78 KB, y las alertas de 1,4 MB a 123 KB |

### 2.3 Vera: criterio 2

Tres usuarios distintos, cada uno con su conversación, durante 5 minutos (`2aa1546`): 94 respuestas, todas terminadas en `done` y sin `error`, con un p95 de 3,9 s y la más lenta en 5,5 s. El tope es de 120 s. Antes de las pruebas, staging admitía una sola conversación en total (H7); con `CHAT_MAX_FLUJOS=6` caben las seis personas del negocio. La corrida cuesta menos de US$0,10 en Bedrock.

### 2.4 Escalera y límite: criterio 6

Corrida con la pausa rápida contra `549e101`, por escalón sostenido (sin las rampas):

| Usuarios | Peticiones por segundo | Dashboard p95 | Alertas p95 | Recomendaciones p95 | Login p95 | 5xx |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | 36,8 | 0,33 s | 0,65 s | 0,83 s | 0,74 s | 0 % |
| 40 | 49,8 | 1,32 s | 2,09 s | 2,29 s | 1,96 s | 0 % |
| 60 | 40,0 | 5,10 s | 6,83 s | 6,86 s | 14,53 s | 1,5 % |
| 80 | 42,7 | 9,80 s | 9,79 s | 9,80 s | 9,63 s | 7,6 % |

- **El límite está en unas 50 peticiones por segundo.** Con 40 usuarios rápidos, staging las sostiene con un p95 de 2,3 s y sin errores; con más usuarios no atiende más, solo hace esperar.
- **Lo pone el Core API, no la máquina.** La CPU de la EC2 no pasó del 81 % (sección 2.5). El Core API corre en un solo proceso de uvicorn (H10), y Python no ejecuta su código en más de un núcleo a la vez: con 2 vCPU, ese proceso se llena antes que la máquina.
- **Dónde el p95 pasa de 2 s** (lo que pide el criterio 6): con unos 40 usuarios rápidos, en Alertas (2,09 s) y Recomendaciones (2,29 s). Con 20 usuarios rápidos, todas las pantallas quedan por debajo de 0,9 s.
- **En personas:** una persona con la pausa lectora genera unas 0,45 peticiones por segundo (8,9 con 20 usuarios). Los 40 usuarios rápidos, con unas 50 peticiones por segundo, equivalen a unas 110 personas leyendo a la vez.
- **Comparación:** con `2aa1546`, la misma escalera promediaba 13,6 peticiones por segundo con un p95 de 16 s. Con `785b458`, se cortaba sola con unos 40 usuarios.

**Cómo falla al pasar el límite.** Desde los 60 usuarios aparecen tres tipos de error:

| Código | Cuántos | Cuánto tardan | Qué lo produce |
| --- | --- | --- | --- |
| 502 | 119 | Al instante (mediana de 0,26 s) | Nginx no encuentra al Core API |
| 504 | 574 | 9,8 s | Nginx no logra conectarse al Core API en sus 10 s (`proxy_connect_timeout`) |
| 500 | 26, en el mismo segundo | 32 s | Una petición esperó 30 s por una conexión del pool a la base |

La hipótesis es que, con el proceso del Core API lleno, la sonda de preparación excede su espera de 1 s, y Kubernetes saca al pod del Service hasta que vuelve a responder. Eso explicaría los 502 inmediatos y los 504. Los eventos de Kubernetes que la confirmarían se perdieron: el despliegue siguiente reemplazó el pod, y Kubernetes solo guarda los eventos una hora.

### 2.5 La máquina

Métricas de CloudWatch de la EC2 en las corridas de `549e101` (`pruebas/carga/metricas_ec2.sh`). La CPU es la de cada tramo de 5 minutos, que es lo que da el monitoreo básico de EC2; la memoria, minuto a minuto, del agente de CloudWatch:

| Corrida | CPU | Memoria (máximo) | Créditos cobrados |
| --- | --- | --- | --- |
| 10 usuarios | 19,8 % | 55,4 % | 0 |
| 20 usuarios | 29,3 % | 55,3 % | 0 |
| Escalera, hasta 40 usuarios | 62,7 % | 56,0 % | 0 |
| Escalera, de 40 a 60 usuarios | 81,3 % | 58,1 % | 0 |
| Escalera, 80 usuarios | 76,0 % | 57,4 % | 0 |

- **CPU:** antes de la caché (`785b458`), con la pausa rápida, la CPU llegaba al 99,9 % con 10 usuarios y al 100 % con 20, y la escalera se cortó con unos 40. Con la caché y la compresión, la misma escalera sostuvo 40 usuarios rápidos sin errores con la CPU entre el 62,7 % y el 81,3 %. Con la pausa lectora del criterio 1, 20 usuarios usan el 29,3 %.
- **Memoria:** entre el 55 % y el 58 % en todas las corridas, también antes de la caché. Quedan más de 1,6 GiB libres, por encima del 25 % que pide la decisión de tamaño del plan k3s.
- **Créditos:** la t3 va en modo «unlimited», y AWS no cobró créditos por encima de la línea base en ninguna corrida.

## 3. Recomendación para producción

| Pieza | Recomendación | Por qué |
| --- | --- | --- |
| Máquina de k3s | t3.medium, como en el plan (decisión de tamaño P3 del plan k3s) | El pico esperado (20 personas) usa unas 9 peticiones por segundo y el 29 % de la CPU, la quinta parte del límite medido. La memoria queda por encima del 25 % libre aun en la escalera |
| Base | RDS db.t4g.micro, como en el plan | En producción, Postgres sale de la máquina, que era la mayor parte del costo de una lectura sin caché (0,23 de 0,30 s de CPU, H16). Con la caché, la mayoría de las lecturas no llega a la base. Su CPU base es del 10 % de 2 vCPU y gasta créditos al pasar de ahí, así que conviene que las alarmas de RDS del plan incluyan sus créditos de CPU. Si se agotan a menudo, el siguiente paso es db.t4g.small |
| Caché de lecturas | `CACHE_LECTURAS_S=600`, como en staging | Las entradas se invalidan solas cuando cambia la bodega |
| Vera | `CHAT_MAX_FLUJOS=6` | Una conversación por persona del negocio, con el límite de una por usuario |
| Seguimiento | Revisar la latencia y los créditos en la primera semana de pruebas con usuarios (8 al 10-dic) | Las pruebas fueron con datos de staging; producción tiene su propia base |

**Lo que no hace falta:** autoescalado, una máquina más grande ni una segunda réplica del Core API para el uso esperado. Si algún día hace falta más capacidad, el primer paso no es la máquina sino el Core API: un segundo proceso de uvicorn aprovecharía el 20 % de CPU que queda libre. Antes habría que resolver dos cosas: la caché de recomendaciones vive en la memoria de cada proceso (H9), y cada proceso suma memoria. También conviene darle a la sonda de preparación una espera de 3 s, para que la saturación no saque al pod del Service (sección 2.4).

## 4. Seguridad

### 4.1 Arreglos de autenticación y sesión

| Criterio | Qué se hizo | Comprobación |
| --- | --- | --- |
| 3 · Un refresh token de una sesión cerrada sigue rechazado tras reiniciar | La lista negra pasó de la memoria del proceso a Redis, con la huella del token y su vencimiento. La rotación es atómica, y el cierre de sesión solo revoca un token válido de la misma persona. Sin Redis, la renovación falla cerrada (D2) | Pruebas con un Redis falso. En staging, el token cerrado siguió rechazado después del reinicio del despliegue |
| 4 · El login da el mismo 401 | Un correo inexistente, una clave incorrecta y una cuenta desactivada responden «Credenciales inválidas» (D4). Con un correo inexistente, la clave se verifica contra un hash del mismo costo, y el tiempo no delata nada: 0,466 s frente a 0,469 s en staging | Pruebas, y las tres variantes en staging |
| Renovación sin coordinar (H6) | Una sola renovación a la vez entre todas las pestañas, con Web Locks del navegador (D3). Antes, al vencer el token de acceso, las consultas del Dashboard renovaban a la vez y mandaban al login | Pruebas del frontend |
| Duración de la sesión (H23) | La sesión dura como máximo 30 días desde el login, aunque se use (D8) | Pruebas, y en staging: la renovación conserva la hora del login |

### 4.2 ZAP: criterio 5

Escaneos pasivos, sin ataques (D1):

- **Baseline de la web:** la araña tradicional y la AJAX recorren la web pública durante 3 minutos. Corrió contra `549e101` y se repitió con la política de CloudFront nueva (`a7b75a1`, D9).
- **API con sesión:** el recorrido de k6 (login, cada pantalla, renovar y cerrar sesión) pasa por ZAP como proxy. ZAP revisó 36 respuestas, contra `549e101` y otra vez contra `a7b75a1`, con el mismo resultado.

| Riesgo | Baseline (`549e101`) | Baseline con la política nueva | API con sesión |
| --- | --- | --- | --- |
| Alto | 0 | 0 | 0 |
| Medio | 0 | 0 | 0 |
| Bajo | 5 | 0 | 0 |
| Informativo | 12 | 12 | 3 |

Las cinco bajas del primer baseline y su clasificación:

| Alerta | Clasificación |
| --- | --- |
| Falta Permissions-Policy | Corregida (D9): apaga la cámara, el micrófono, la ubicación, los pagos y el USB. El portapapeles sigue, por el botón de copiar de Vera |
| Falta Cross-Origin-Opener-Policy | Corregida (D9): `same-origin` |
| Falta Cross-Origin-Resource-Policy | Corregida (D9): `same-origin` |
| Falta Cross-Origin-Embedder-Policy | Corregida (D9): `require-corp`. La web solo carga recursos de su origen, como ya exigía la CSP |
| «Server: AmazonS3» | Corregida (D9): CloudFront quita «Server» y las cabeceras `x-amz-*` de S3, y pone «Server: CloudFront» |

Las informativas no piden cambios:

- **Caché** (Re-examine Cache-control Directives, Non-Storable Content, Storable and Cacheable Content, Storable but Non-Cacheable Content y Retrieved from Cache): describen la política de la web. Los archivos con huella en el nombre se guardan un año y la página se revalida siempre. Las respuestas de la API, además, salen con `Cache-Control: no-store` (D9).
- **Sec-Fetch-Dest, -Mode, -Site y -User:** faltan en las peticiones de la araña, que no es un navegador. Las pone el navegador, no el servidor.
- **Base64 Disclosure:** es el identificador de petición que CloudFront agrega a cada respuesta (`x-amz-cf-id`), un valor aleatorio, y bytes de la fuente tipográfica.
- **Suspicious Comments:** la palabra «query» dentro del JavaScript minificado.
- **Modern Web Application:** solo avisa que la web es una aplicación de una página; por eso corre la araña AJAX.
- **API con sesión** (Authentication Request Identified y Session Management Response Identified): ZAP reconoce el login y la renovación.
- **Re-examine Cache-control Directives en la API:** sigue con `a7b75a1`, porque ZAP pide `no-cache, no-store, must-revalidate` y la API manda `no-store`. Por sí solo, `no-store` prohíbe al navegador y a los proxies guardar la respuesta (RFC 9111, sección 5.2.2.5); `no-cache` y `must-revalidate` solo cambian cómo se reutiliza una respuesta ya guardada.

**Comprobación en el navegador.** Con la política nueva, un recorrido con Chromium (k6 con su módulo de navegador) inició sesión, abrió el Dashboard, Alertas y Recomendaciones sin errores en la consola, y la página quedó aislada de otros orígenes (`crossOriginIsolated`).

### 4.3 Lista de chequeo: OWASP ASVS 4.0.3, nivel 1

Solo los puntos que aplican a InventAI/o. Los estados son: cumple, corregido en INV-41, riesgo aceptado (con su justificación) y no aplica.

| Punto | Requisito | Estado | Evidencia o justificación |
| --- | --- | --- | --- |
| 2.1.1 | Claves de al menos 12 caracteres | Riesgo aceptado (D7) | La API acepta 8. Son unas seis cuentas creadas por el gerente, el login limita los intentos fallidos y bcrypt hace costoso probar claves |
| 2.1.2 | Se admiten claves de 64 caracteres o más, y no más de 128 | Cumple | `max_length=128` en el cambio de clave |
| 2.1.3 | La clave no se trunca | Cumple, con una salvedad | La API no la recorta, pero bcrypt solo usa los primeros 72 bytes: dos claves de más de 72 bytes con el mismo comienzo valen igual. Solo afecta claves muy largas |
| 2.1.4 | Cualquier carácter Unicode en la clave | Cumple | Sin restricción de caracteres |
| 2.1.5 y 2.1.6 | La persona cambia su clave, y para hacerlo da la actual | Cumple | `PATCH /api/auth/password` |
| 2.1.7 | Se rechazan claves filtradas | Riesgo aceptado (D7) | Igual que 2.1.1. Revisar contra una lista de claves filtradas pide una dependencia o un servicio externo |
| 2.1.8 | Medidor de fortaleza de la clave | Riesgo aceptado (D7) | Igual que 2.1.1 |
| 2.1.9 y 2.1.10 | Sin reglas de composición ni cambio obligatorio periódico | Cumple | Solo se pide el largo |
| 2.2.1 | Límite de intentos de autenticación | Cumple | INV-66: 5 fallos por correo e IP y 20 por IP en 15 minutos, en Redis. Responde 429 con `Retry-After` |
| 2.2.3 | Aviso a la persona cuando cambian sus credenciales | No aplica | El sistema no envía correos |
| 2.5 | Recuperación de la clave | No aplica | La web no tiene «olvidé mi clave» |
| 3.1.1 | Los tokens no van en la URL | Cumple | Van en la cabecera `Authorization`, también en el chat |
| 3.2.1 | Token nuevo en cada autenticación | Cumple | El login emite tokens nuevos; cada refresh token lleva un `jti` aleatorio de 128 bits |
| 3.2.2 | Tokens con al menos 64 bits de entropía | Cumple | JWT firmados con HS256 y una clave de 32 bytes o más (INV-66) |
| 3.2.3 | Tokens guardados de forma segura en el navegador | Riesgo aceptado (D8) | Viven en `localStorage`. La CSP solo admite scripts del propio origen, lo que frena su robo por inyección de scripts. Con `sessionStorage`, cada pestaña pediría iniciar sesión |
| 3.3.1 | El cierre de sesión invalida la sesión | Cumple, con una salvedad aceptada | El refresh token queda revocado en Redis (criterio 3). El token de acceso, un JWT sin estado, sirve hasta 30 minutos después |
| 3.3.2 | Reautenticación periódica, al menos cada 30 días | Corregido en INV-41 (D8) | Tope de 30 días desde el login |
| 3.7.1 | Reautenticación antes de una operación sensible | Cumple | Cambiar la clave pide la actual |
| 4.1.1 y 4.1.2 | El control de acceso se aplica en el servidor, con datos que la persona no puede alterar | Cumple | El rol y la sucursal salen del token firmado y de la base, en cada endpoint |
| 4.1.3 | Mínimo privilegio | Cumple | Un administrador de sucursal solo ve su sucursal. La caché de lecturas incluye el rol y la sucursal en su clave (D5) |
| 4.1.5 | El control de acceso falla de forma segura | Cumple | Sin Redis, la renovación se rechaza (D2) |
| 4.2.2 | Protección contra peticiones cruzadas (CSRF) | No aplica | La sesión no usa cookies: el token va en una cabecera que otro sitio no puede poner |
| 4.3.2 | Sin listado de directorios | Cumple | S3 es privado detrás de CloudFront, y Nginx no lista |
| 5.1.3 | Validación de las entradas | Cumple | Pydantic y los tipos de FastAPI en cada parámetro |
| 5.3.3 | Escape de la salida contra la inyección de scripts | Cumple | React escapa todo; no hay `dangerouslySetInnerHTML` ni `innerHTML` |
| 5.3.4 | Consultas parametrizadas | Cumple | Las consultas armadas con texto solo concatenan constantes; los valores van como parámetros |
| 7.1.1 | Los registros no guardan claves ni tokens | Cumple | La lista negra guarda la huella, no el token; el registro del chat anota el usuario y el resultado |
| 7.4.1 | Mensajes de error genéricos | Cumple | Un error interno responde «Internal Server Error», sin detalles |
| 8.2.1 | Cabeceras para que el navegador no guarde datos sensibles | Corregido en INV-41 (D9) | `Cache-Control: no-store` en las respuestas de la API |
| 8.3.1 | Los datos sensibles van en el cuerpo o en cabeceras, no en la URL | Cumple | El login y el cambio de clave van en el cuerpo |
| 9.1.1 a 9.1.3 | TLS en todo, con versiones y cifrados fuertes | Cumple | CloudFront redirige HTTP a HTTPS con 301 y rechaza TLS 1.0 y 1.1. HSTS de un año |
| 10.3.2 | Sin componentes de origen no confiable | Cumple | Las acciones del CI, Trivy, ZAP y k6 van fijados por su huella; las imágenes base, por su etiqueta oficial y revisadas por Trivy. Dependencias con versiones fijas, pip-audit, npm audit y Dependabot |
| 12 | Carga de archivos | No aplica | La web no recibe archivos |
| 13.2.1 | Solo los métodos HTTP que usa cada endpoint | Cumple | FastAPI responde 405 a los demás |
| 14.2.1 | Componentes al día y sin vulnerabilidades conocidas | Cumple | Auditorías del CI y Dependabot (INV-76) |
| 14.3.2 | Sin modos de depuración en producción | Corregido en INV-41 (D10) | Sin depuración, y la documentación interactiva de la API solo con `ENTORNO=desarrollo` |
| 14.3.3 | Las cabeceras no delatan versiones | Corregido en INV-41 (D9) | Nginx con `server_tokens off`; CloudFront quita «Server» y las cabeceras de S3 |
| 14.4.1 | Cada respuesta trae su tipo de contenido y el juego de caracteres | Cumple, con una salvedad | La API responde `application/json`. La página llega de S3 como `text/html` sin juego de caracteres en la cabecera, y lo declara en su primera línea (`<meta charset="UTF-8">`), que el navegador lee antes de mostrar texto |
| 14.4.3 a 14.4.7 | CSP, `nosniff`, HSTS, Referrer-Policy y bloqueo de marcos | Cumple | Política de cabeceras de CloudFront y `frontend/nginx/cabeceras-seguridad.conf` |
| 14.5.3 | CORS solo para orígenes de confianza | Cumple | Sin CORS: el navegador llega por el mismo origen. Fuera de desarrollo, la configuración no admite `*` (INV-66) |

## 5. Riesgos aceptados

- **Claves de 8 caracteres, sin revisión de claves filtradas ni medidor de fortaleza** (D7). Mitigan el límite de intentos y el costo de bcrypt. Conviene revisarlo si el sistema pasa a tener muchas más cuentas.
- **Tokens en `localStorage`** (D8). Mitiga la CSP estricta.
- **El token de acceso vive hasta 30 minutos después de cerrar sesión.** Es un JWT sin estado; su vida corta es la mitigación.
- **Pasado el límite, el Core API sale del Service** (sección 2.4). No afecta el uso esperado.

## 6. Cómo repetirlo

Desde la raíz del repositorio, con el archivo de claves de staging en `~/.config/inventaio/claves-staging.json`:

```bash
bash pruebas/carga/correr.sh lectura 20          # criterio 1
bash pruebas/carga/correr.sh lectura escalera    # criterio 6, con el resumen por escalón
bash pruebas/carga/correr.sh vera                # criterio 2
bash pruebas/seguridad/zap_baseline.sh           # criterio 5
bash pruebas/seguridad/zap_api_pasivo.sh
```

Cada corrida imprime las horas en UTC para sacar las métricas de la máquina en CloudShell con `pruebas/carga/metricas_ec2.sh`.
