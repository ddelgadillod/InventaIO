# INV-66 · Hardening mínimo antes de exponer a internet · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-66 «Hardening mínimo antes de exponer a internet» · 5 SP · Sprint 7 · Release 3 · límite 13-nov |
| Depende de | INV-24 (CI, imágenes en GHCR y el contrato con INV-34 de `docs/CI-CD.md`) |
| Alimenta a | INV-34 (primer despliegue en staging): usa `docker-compose.prod.yml` y le agrega TLS |
| Rama | `feature/INV-66-hardening`, desde `develop` (`db82183`), en el worktree `~/InventaIO-wt/INV-66` |
| Hecho antes | CA 3 (PyJWT en lugar de python-jose) desde el 28-oct: `d6a7d2f`, comentario 10052 |

Revisión del 10 de noviembre de 2026 contra `develop` y las imágenes publicadas. Las decisiones H1 a H4 las tomó el usuario ese día en un formulario; las demás son técnicas y siguen de los hallazgos.

## 1. Historia de Jira

> Como responsable del sistema, quiero cerrar los riesgos de seguridad conocidos antes de exponer la aplicación a internet, para que el primer despliegue en la nube no publique secretos ni puertas abiertas.

Siete criterios: seis (M) y uno (S). El 3 está hecho. Fuera de alcance: TLS y dominio (INV-34), pruebas de carga y revisión de seguridad (INV-41), WAF y gestión de secretos en un servicio de AWS.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| C1 | `api/core/config.py` y `ml_service/core/config.py` traen valores por defecto para `JWT_SECRET_KEY` (`inventaio-secret-key-change-in-production`) y `POSTGRES_PASSWORD` (`inventaio_pass_2025`), y `docker-compose.yml` repite la contraseña como respaldo. Los dos valores están en el repositorio público | Fuera de desarrollo se rechazan (H1, H7). El agente no tiene credenciales propias (criterio 6 de INV-30): el CA 1 no lo toca |
| C2 | `api/core/database.py` crea el motor de SQLAlchemy al importarse, con `get_settings()` | Si la validación vive en `Settings`, el servicio se detiene antes de abrir una conexión o un puerto |
| C3 | El Core API y el ML Service aceptan CORS `*` con credenciales. Pero ningún navegador cruza de origen: en desarrollo Vite pasa `/api` al 8000 por proxy (`frontend/vite.config.js`) y en la imagen web Nginx sirve la aplicación y `/api` desde el mismo origen. El frontend manda el token en `Authorization`, no en cookies | CORS sobra en los dos ambientes. Queda apagado por defecto y configurable (H5) |
| C4 | El login no limita intentos y verifica con bcrypt en cada uno, así que cada intento cuesta CPU | El límite se consulta antes de ir a la base y de verificar la clave (H3) |
| C5 | Detrás de Nginx, uvicorn 0.34 solo confía en `127.0.0.1` para leer `X-Forwarded-For`: la IP del cliente es la del contenedor web y un límite por IP bloquearía a todos. Si confía en `*`, toma el **primer** elemento de la cabecera, y Nginx agrega la IP real al final (`$proxy_add_x_forwarded_for`): el cliente puede falsificar el primero | Nginx sobrescribe la cabecera con `$remote_addr` y el Core API, que no se publica, confía en el proxy (H6) |
| C6 | Redis está en el compose y `redis==5.2.1` en `api/requirements.txt`, pero el Core API no lo usa (C4 de INV-36) | El límite de login no suma dependencias |
| C7 | `docker-compose.yml` publica 5432, 6379, 8000, 8001 y 5050 (pgAdmin `latest` con `admin123`). No hay compose de producción. Las cuatro imágenes de GHCR (`api`, `ml-service`, `nlp-agent`, `web`) se descargan sin credenciales en v2.0.0 (comprobado el 10-nov) | `docker-compose.prod.yml` nuevo; el de desarrollo no cambia, salvo `ENTORNO: desarrollo` (H8) |
| C8 | `api/scripts/seed_usuarios.py` crea los cinco usuarios de prueba con `admin123` y no tiene modo para la nube | Modo `--nube` con claves aleatorias (H2) |
| C9 | En `frontend/nginx.conf`, `location /` y `location /assets/` tienen su propio `add_header`: en Nginx eso anula las cabeceras del `server`. La imagen web trae Nginx 1.30.5, que acepta `add_header_inherit merge` (comprobado con `nginx -t` el 10-nov) | Las cabeceras de seguridad van en el `server` y esas dos ubicaciones las heredan (H9) |
| C10 | `Login.jsx` muestra el `detail` que devuelve la API (`textoDetalle` en `src/api/client.js`) | Un 429 con un `detail` claro no requiere cambios en el frontend |
| C12 | Hallado al implementar: `docker-compose.verify.yml` (el check obligatorio «Imágenes sanas») arranca el Core API y el ML Service sin variables. Con H1 dejarían de arrancar | Corren como `staging` con secretos de mentira, y el job comprueba además que sin secretos no arrancan (P19 en el CI) |
| C13 | Hallado al implementar: pydantic copia las variables de entrada en el mensaje de error (`input_value={...}`). Con la contraseña de la base válida y la clave JWT corta, la contraseña quedaría en el log | `hide_input_in_errors` en las dos configuraciones, con su prueba |
| C11 | Fuera de los criterios: la lista negra de refresh tokens vive en memoria (`_blacklisted_tokens`), así que tras un reinicio un token de un logout vuelve a servir hasta 7 días; y el login responde «Cuenta desactivada» antes de verificar la clave, lo que permite saber si una cuenta existe | Se anotan en INV-41 (H4) |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| H1 | `ENTORNO` admite `desarrollo`, `staging` y `produccion`. **Si falta, se asume producción.** Los valores por defecto de los secretos solo se aceptan con `desarrollo`. El compose de desarrollo, las pruebas (`conftest.py`) y `.env.example` declaran `desarrollo` | Usuario, 10-nov |
| H2 | `python -m scripts.seed_usuarios --nube` genera una clave aleatoria por usuario (`secrets.token_urlsafe`), la muestra una sola vez y no la guarda. Sin `--nube`, el seed de `admin123` se niega a correr fuera de `desarrollo` | Usuario, 10-nov |
| H3 | Login: 5 intentos fallidos por email e IP y 20 por IP en una ventana de 15 minutos, configurables. Un login correcto limpia el contador de su email e IP. Los contadores van en Redis; si Redis no responde, se cuenta en la memoria del proceso y se deja un aviso en el log | Usuario, 10-nov |
| H4 | Los hallazgos de C11 no entran sin puntos: se anotan en INV-41 (revisión de seguridad, Release 4) | Usuario, 10-nov |
| H5 | `CORS_ORIGENES` (lista separada por comas) vacía por defecto: sin middleware de CORS. Fuera de desarrollo, `*` se rechaza. El ML Service queda sin CORS | Técnica (C3) |
| H6 | Nginx manda `X-Forwarded-For: $remote_addr` (sobrescribe, no agrega) y el compose de producción declara `FORWARDED_ALLOW_IPS=*` para el Core API, que solo se alcanza desde Nginx. Si INV-34 pone un balanceador delante, Nginx debe tomar la IP real con `set_real_ip_from` | Técnica (C5) |
| H7 | Fuera de desarrollo, `JWT_SECRET_KEY` debe ser distinta de la del repositorio y tener al menos 32 bytes (PyJWT advierte por debajo, comentario 10052), y `POSTGRES_PASSWORD` no puede ser vacía ni la del repositorio. El error nombra la variable | Técnica (C1) |
| H8 | `docker-compose.prod.yml`: imágenes `${INVENTAIO_REGISTRO}/inventaio-<servicio>:${INVENTAIO_TAG}` (por defecto `ghcr.io/ddelgadillod`; el tag es obligatorio); los secretos con `${VAR:?mensaje}` para que el compose falle antes de arrancar; solo `web` publica; sin pgAdmin ni `build`; Ollama en el perfil `llm` como opción de CPU (el Bedrock de D26 llega con INV-67); Redis sin persistencia; logs con tope de tamaño, por el disco de la instancia | Técnica (CA 4) |
| H9 | Cabeceras en Nginx: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Content-Security-Policy: frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin` y HSTS de un año sin `includeSubDomains`. Los navegadores ignoran HSTS sobre HTTP: rige cuando INV-34 active TLS. Una CSP completa espera a INV-68, que lleva las fuentes al servidor (hoy `index.html` carga Google Fonts) | Técnica (CA 7) |

## 4. Interfaz

### 4.1 Variables nuevas

| Variable | Servicio | Por defecto | Uso |
| --- | --- | --- | --- |
| `ENTORNO` | api, ml-service | `produccion` | H1 |
| `CORS_ORIGENES` | api | vacía | H5 |
| `LOGIN_MAX_FALLOS_USUARIO_IP` | api | 5 | H3 |
| `LOGIN_MAX_FALLOS_IP` | api | 20 | H3 |
| `LOGIN_VENTANA_S` | api | 900 | H3 |
| `FORWARDED_ALLOW_IPS` | api (uvicorn) | `127.0.0.1` | H6; `*` solo en el compose de producción |
| `INVENTAIO_REGISTRO`, `INVENTAIO_TAG` | compose de producción | `ghcr.io/ddelgadillod`, obligatorio | H8 |

### 4.2 Arranque en producción sin secretos

```
ENTORNO=produccion: JWT_SECRET_KEY no está definida o es la del repositorio (mínimo 32 bytes).
Generar una con: python -c "import secrets; print(secrets.token_urlsafe(48))"
```

El servicio no arranca. El compose de producción falla antes, con `${JWT_SECRET_KEY:?…}`.

### 4.3 Login bloqueado

`POST /api/auth/login` → **429** con `Retry-After: <segundos que faltan>` y
`{"detail": "Demasiados intentos fallidos. Intenta de nuevo en N minutos."}`.
Solo cuentan los 401 (email inexistente o clave errada). El bloqueo se revisa antes de consultar la base, así que también rechaza una clave correcta mientras dura.

### 4.4 Usuarios de la nube

```
$ docker compose -f docker-compose.prod.yml exec api python -m scripts.seed_usuarios --nube
creado        gerente@inventaio.co           <clave>
...
Las claves se muestran solo esta vez: guárdalas fuera del repositorio.
```

Correrlo de nuevo crea las que falten y cambia todas las claves (sirve para rotarlas).

## 5. Criterios de aceptación

| CA | Cómo se cumple |
| --- | --- |
| 1 (M) Sin valores por defecto utilizables | H1, H7; `Settings` del Core API y del ML Service |
| 2 (M) CORS restringido | H5 |
| 3 (M) PyJWT | Hecho el 28-oct |
| 4 (M) `docker-compose.prod.yml` | H8 |
| 5 (M) Límite de login con 429 y Retry-After | H3, H6 |
| 6 (M) Contraseñas propias en la nube | H2 |
| 7 (S) Cabeceras de seguridad | H9 |

## 6. Casos de prueba

| # | Caso | Esperado | Dónde |
| --- | --- | --- | --- |
| P1 | Sin `ENTORNO` y con los valores por defecto | Error que nombra `JWT_SECRET_KEY` (api) o `POSTGRES_PASSWORD` (ml-service) | Unitaria |
| P2 | `produccion` con clave de menos de 32 bytes, o con la contraseña del repositorio | Error | Unitaria |
| P3 | `produccion` con secretos válidos; `desarrollo` con los valores por defecto | Arranca | Unitaria |
| P4 | `ENTORNO=prod` (valor desconocido) | Error | Unitaria |
| P5 | Preflight sin `CORS_ORIGENES` | Sin `Access-Control-Allow-Origin` | Unitaria |
| P6 | `CORS_ORIGENES=https://a.co`: preflight desde `https://a.co` y desde `https://b.co` | Permitido el primero; rechazado el segundo | Unitaria |
| P7 | `CORS_ORIGENES=*` fuera de desarrollo | Error | Unitaria |
| P8 | Preflight al ML Service desde cualquier origen | Sin `Access-Control-Allow-Origin` | Unitaria |
| P9 | 5 fallos con el mismo email e IP; el sexto intento, con la clave correcta | 429 con `Retry-After` | Unitaria |
| P10 | Vence la ventana | Vuelve a aceptar | Unitaria (reloj falso) |
| P11 | 20 fallos desde una IP con emails distintos | 429 | Unitaria |
| P12 | 4 fallos y un login correcto; luego 4 fallos más | No bloquea | Unitaria |
| P13 | Redis no responde | Sigue limitando en memoria; un aviso en el log | Unitaria |
| P14 | `seed_usuarios --nube` | Claves distintas entre sí, de al menos 24 caracteres y ninguna `admin123` | Unitaria |
| P15 | `seed_usuarios` sin `--nube` fuera de desarrollo | Se niega | Unitaria |
| P16 | `docker compose -f docker-compose.prod.yml config` | Solo `web` con `ports`; sin pgAdmin ni `build`; sin secretos, falla con el nombre de la variable | Local y CI |
| P17 | Compose de producción con imágenes de la rama y un `.env` de prueba | Los servicios quedan sanos, solo responde el puerto de web, login por Nginx y 429 al sexto fallo aunque se falsifique `X-Forwarded-For` | Local |
| P18 | Cabeceras en `/`, `/assets/…`, `/api/health` y `/api/chat/health` | Las cinco de H9 en las cuatro rutas | Local |
| P19 | Imagen del Core API con `ENTORNO=produccion` y sin secretos | Sale con el mensaje de 4.2 | Local |
| P20 | Compose de desarrollo (stack 8000/8080) | Igual que antes: login con los usuarios de prueba | Local |

## 7. Ruta de implementación

1. `ENTORNO` y la validación en `Settings` (api y ml-service), `conftest.py`, `ENTORNO: desarrollo` en `docker-compose.yml` y `.env.example`. P1 a P4.
2. CORS por variable en el Core API y sin CORS en el ML Service. P5 a P8.
3. `api/auth/limite_login.py` (Redis con respaldo en memoria) y su uso en `POST /api/auth/login`. P9 a P13.
4. `seed_usuarios --nube`. P14 y P15.
5. Nginx: cabeceras y `X-Forwarded-For`.
6. `docker-compose.prod.yml`, `.env.prod.example` y `.gitignore`.
7. Documentación: contrato con INV-34 en `docs/CI-CD.md` y `docs/AMBIENTE-DESARROLLO.md`.
8. Verificación local: suites, P16 a P20.
9. Pull Request a `develop`, con self-review.

## 8. Definition of Done

La de Jira, en casillas: criterios (M) y el (S); CI en verde con pip-audit sin excepciones; pruebas de los criterios 1, 2 y 5 con la cobertura mínima del Core API (70 %) y del ML Service (90 %); el compose de producción arranca en local y solo publica web; el de desarrollo sigue igual; `docs/CI-CD.md` y `.env.example` al día; Pull Request a `develop` con self-review; sin bugs bloqueantes.

## 9. Fuera de alcance y riesgos

- **Fuera de alcance:** TLS, dominio y el despliegue (INV-34); los hallazgos de C11 (INV-41); el proveedor Bedrock (INV-67); el ETL en la nube.
- **Riesgo:** quien corra el Core API fuera de Docker sin `ENTORNO=desarrollo` lo verá fallar al arrancar. El mensaje lo dice y `docs/AMBIENTE-DESARROLLO.md` lo explica.
- **Riesgo:** con un balanceador delante de Nginx, `$remote_addr` sería la IP del balanceador y el límite por IP volvería a ser uno para todos (H6).
- **Riesgo:** el límite en memoria (respaldo de H3) es por proceso. Con varios procesos, cada uno cuenta aparte mientras Redis esté caído.

## 10. Verificación (10-nov, en local)

| Prueba | Resultado |
| --- | --- |
| Core API, unitarias (P1 a P15) | 273 pasan, 1 omitida; cobertura 81,9 % (mínimo 70 %). Ruff sin hallazgos |
| ML Service | 182 pasan, 17 omitidas (las de la bodega); cobertura 94,4 % (mínimo 90 %) |
| P16 `config` del compose de producción | Sin secretos falla nombrando `INVENTAIO_TAG` y `POSTGRES_PASSWORD`; con ellos, solo `web` publica (8090 → 8080), sin `build` ni pgAdmin, Ollama solo con el perfil `llm` |
| P17 compose de producción con las imágenes de la rama | Los seis servicios sanos; 8000, 8001, 8002, 5432 y 6379 cerrados en el host. `seed_usuarios` sin `--nube` se niega; con `--nube` crea los cinco. Por Nginx: login correcto 200, `admin123` 401 y, tras 5 fallos con `X-Forwarded-For` distinto en cada uno, 429 con `Retry-After: 899` aunque la clave sea la correcta. Los contadores quedan en Redis con la IP real |
| P18 cabeceras | Las cinco en `/`, `/assets/…`, `/api/health`, `/api/chat/health` y en los 404, sin perder el `Cache-Control` de cada ubicación |
| P19 imágenes sin secretos | El Core API y el ML Service salen con el mensaje de 4.2; el error no muestra valores (C13) |
| P20 compose de desarrollo | Declara `ENTORNO=desarrollo` en `api` y `ml-service`; el Core API de desarrollo con el código de la rama arranca sin secretos |
| `docker-compose.verify.yml` (C12) | Las cuatro imágenes sanas y sin root, el proxy de Nginx responde, y sin secretos el Core API y el ML Service no arrancan |
| `scripts/probar_nginx_streaming.sh` y `probar_nginx_timeout.sh` | 4/4 y 3/3 |

**Al integrar en `develop`:** el stack local monta `./api` con `--reload`. Hay que recrear `api` y `ml-service` (`docker compose up -d api ml-service`) para que tomen `ENTORNO=desarrollo` del compose; si no, el Core API recarga el código nuevo sin la variable y no arranca.
