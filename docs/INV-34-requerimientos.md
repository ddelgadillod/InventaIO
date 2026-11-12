# INV-34 · Primer despliegue en AWS (staging) · Requerimientos

| Campo | Valor |
| --- | --- |
| Jira | INV-34 «Primer despliegue en AWS (staging)» · Sprint 7 · Release 3 · límite 19-nov · 8 SP |
| Depende de | INV-63 (bodega con las ventas de 2026), INV-66 (`docker-compose.prod.yml`), INV-67 (Bedrock en us-east-2) |
| Bloquea a | INV-68 (criterios en staging) · INV-69 (producción) |
| Rama | `feature/INV-34-staging`, desde `develop` (`d3e3d52`), en el worktree `~/InventaIO-wt/INV-34` |
| Arquitectura | Plan 1 del documento «Arquitectura en AWS y plan de migración» (11-nov): EC2 con compose y servicios administrados alrededor |

Este documento empieza por la **parte 1: la base de datos**: cómo se crea el esquema, cómo viaja la bodega a la nube y cómo se valida que llegó igual. La **parte 2** (secciones 10 a 16) cubre la EC2, el TLS, el script de despliegue, la versión visible y las pruebas de humo. Los pasos en la consola están en `docs/INV-34-guia-staging.md`.

Revisión del 11 de noviembre de 2026 contra `develop` y la bodega local. El usuario tomó las decisiones B1 a B4 ese día en un formulario; las demás son técnicas y siguen de los hallazgos.

## 1. Historia de Jira

> Como desarrollador, quiero desplegar la versión 2 en un entorno de staging en AWS con un procedimiento reproducible, para validar en la nube los criterios críticos y preparar las pruebas con usuarios.

La ficha tiene nueve criterios, todos (M). De esta parte depende el **CA 4**: «La bodega restaurada en la instancia, sin puerto publicado». También toca el DoD 3: los secretos quedan fuera del repositorio.

En la ficha quedan fuera de alcance RDS, las copias en S3, el dominio propio, el monitoreo y el workflow con OIDC, que pasan a INV-69. El bucket de esta parte no es de copias: solo sirve para trasladar el volcado, y lo que deja ahí expira (B10).

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| K1 | `database/init.sql` es idempotente: se aplica desde cero y otra vez encima sin errores (prueba del 11-nov en una base temporal). El esquema que crea es idéntico al de la bodega local: el `pg_dump --schema-only` de `dw` y `app` no tiene diferencias | `init.sql` sirve como paso de migración sin herramienta nueva (B1) |
| K2 | El volcado comprimido (`-Fc`) de `dw` y `app` pesa 32 MB y tarda 8,5 s. Postgres local: 16.13 | El traslado es liviano. Las herramientas deben ser de Postgres 16 (B7) |
| K3 | `docker-compose.prod.yml` monta `init.sql` en `/docker-entrypoint-initdb.d`: con el volumen vacío, el contenedor ya crea el esquema al arrancar | La restauración llega sobre tablas vacías: solo datos (B6) |
| K4 | `app.usuarios` tiene 5 usuarios de desarrollo y apunta a `dw.dim_sucursal` con una clave foránea. `app.config_alertas` está vacía | A staging solo viaja `dw`. Los usuarios se crean allá con `python -m scripts.seed_usuarios --nube` (INV-66) (B5) |
| K5 | `database/test-dw-real.SQL` no falla por sí solo: imprime un informe, sin `RAISE` ni `ASSERT`. No lee datos de `app` ni usa la fecha actual | Su salida, sin los tiempos, entra a la huella: si el informe cambia, la validación falla (B9) |
| K6 | En RDS, el usuario maestro no es superusuario (para INV-69): no puede usar `--disable-triggers` ni cambiar dueños. Las claves foráneas de `dw` no forman ciclos | La restauración usa `--no-owner --no-privileges` y no desactiva triggers. El orden lo resuelve `pg_restore` |
| K7 | En el entorno no está la CLI de AWS, pero `botocore` 1.44.0 sí está en `~/venvs/inventaio` (INV-67) | La subida usa botocore, sin instalar nada (B11) |
| K8 | Las ventas de 2026 (INV-63) se cargan esta semana | El procedimiento se repite completo después de la carga (B6) |
| K9 | El repositorio es público y los registros de Actions también | Ningún paso imprime valores de la bodega: solo nombres de comprobaciones y su resultado (B8) |
| K10 | Tres consultas de `test-dw-real.SQL` ordenaban con empates posibles: categorías por cantidad de productos, sucursales por total y las 10 de menor cobertura (con `LIMIT`). En la segunda prueba con la bodega real, el destino devolvió los empates en otro orden y H10 falló aunque los datos eran iguales | Las tres llevan un desempate (nombre o código), sin cambiar lo que muestran. El encabezado del archivo pide que toda consulta nueva de varias filas se ordene por completo |

## 3. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| B1 | El paso de migración es `init.sql`, aplicado con `ON_ERROR_STOP` en cada despliegue. El CI prueba que siga siendo idempotente. Si algún día un cambio no se puede escribir así, se pasa a archivos numerados | Usuario, 11-nov |
| B2 | El volcado se sube con un usuario de IAM nuevo, solo para esto (`inventaio-volcados`), con una política que solo deja escribir en `volcados/` del bucket. La llave vive en el perfil `inventaio-volcados` de `~/.aws/credentials`: nunca pasa por el chat ni por el repositorio. Se desactiva al cerrar INV-34 | Usuario, 11-nov |
| B3 | En INV-34 entran el validador completo (sección 5) y un job del CI con Postgres 16 y datos sintéticos. La parte propia de RDS (latencia y restauración desde una copia) queda en INV-69 | Usuario, 11-nov |
| B4 | Este alcance se agrega a INV-34 con un comentario, sin cambiar sus 8 SP | Usuario, 11-nov |
| B5 | Solo viaja el esquema `dw`. En staging, `app` lo crea `init.sql` y los usuarios los crea `seed_usuarios --nube`, con una clave aleatoria por usuario que se muestra una sola vez. Los usuarios de desarrollo nunca salen del equipo | Técnica (K4) |
| B6 | La restauración es de solo datos (`pg_restore --data-only --single-transaction -n dw`) sobre el esquema que crea `init.sql`, y se niega a correr si alguna tabla de `dw` tiene filas. Recargar la bodega en staging significa recrear la base y volver a crear los usuarios. En producción, donde los usuarios se conservan, la recarga la define INV-69 | Técnica (K3, K8) |
| B7 | `psql`, `pg_dump` y `pg_restore` corren dentro de `postgres:16-alpine`, con `docker run`, para usar siempre la versión de la base. La conexión va por las variables estándar `PG*`, pasadas al contenedor como entorno, nunca en la línea de comandos. `BD_RED` dice a qué red se une el contenedor: `container:<id>` para un contenedor de la base, `host` en el CI y vacía para RDS | Técnica (K2) |
| B8 | La **huella** es una línea por comprobación con su nombre y el md5 de su resultado; H8 dice «al dia» o «ATRASADA». El detalle con los valores se escribe solo donde se calcula y no se sube. Ni la huella ni el detalle se imprimen: los registros dicen «PASÓ: N comprobaciones» o «NO PASÓ: k de N», con los nombres de las que difieren | Técnica (K9) |
| B9 | Las comprobaciones son las de la sección 5. Comparan el destino contra la huella que se sacó del origen al hacer el volcado. Origen y destino nunca se conectan entre sí | Técnica |
| B10 | Cada volcado va a una carpeta con fecha, fuera del repositorio (`~/inventaio-volcados/AAAAMMDD-HHMM/`), con `dw.dump`, `dw.dump.sha256`, `huella.txt` y `huella-detalle.txt`. Al bucket suben las tres primeras, bajo `volcados/AAAAMMDD-HHMM/`. El bucket es privado y cifrado, y sus objetos expiran a los 30 días. `.gitignore` agrega `*.dump` y `huella-detalle*.txt` | Técnica |
| B11 | `scripts/bd/subir_volcado.py` sube con botocore (`PutObject` con suma SHA-256) usando el perfil de B2. No imprime contenido, solo las claves de los objetos | Técnica (K7) |
| B12 | El job `base-de-datos` del CI corre `scripts/bd/probar.sh`, que hace lo siguiente: aplica `init.sql` dos veces y compara los esquemas; carga `database/datos-sinteticos.sql`; vuelca, restaura en otra base y valida, y eso debe pasar. Además, dos pruebas negativas: un dato alterado en el destino debe fallar la validación, y restaurar sobre una base con filas debe negarse | Técnica (B3) |
| B13 | En la EC2 (parte 2), la instancia baja la carpeta con su rol, por SSM, y corre `restaurar` y `validar` contra el contenedor de la base. El rol solo puede leer `volcados/*` | Técnica |

## 4. Interfaz

Los scripts van en `scripts/bd/` y se corren desde la raíz del repositorio. Todos leen `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` y `BD_RED` (B7).

| Script | Qué hace | Salida y códigos |
| --- | --- | --- |
| `migrar.sh` | Aplica `database/init.sql` con `ON_ERROR_STOP` | 0 si aplicó; 2 si hubo un error |
| `volcar.sh [CARPETA]` | Vuelca `dw` (`-Fc --no-owner --no-privileges`), calcula su SHA-256 y saca la huella y su detalle del origen. Por defecto, la carpeta es `~/inventaio-volcados/<fecha>` | La ruta de la carpeta; 0 o 2 |
| `restaurar.sh CARPETA` | Comprueba el SHA-256, aplica `migrar.sh` (el esquema lo crea `init.sql`), comprueba que `dw` esté vacía y restaura solo datos | 0; 2 si hubo un error; 3 si `dw` tiene filas |
| `validar.sh CARPETA` | Saca la huella del destino y la compara con `CARPETA/huella.txt`. Solo si algo difiere, saca también el detalle del destino | «PASÓ: N» y 0; «NO PASÓ: k de N» con los nombres y 1; 2 si hubo un error |
| `huella.sql` | Las comprobaciones de la sección 5. Con `-v detalle=1` devuelve los valores en vez del md5 | — |
| `subir_volcado.py CARPETA --bucket B` | Comprueba el SHA-256 del volcado y sube `dw.dump`, `dw.dump.sha256` y `huella.txt` con el perfil `inventaio-volcados`, en `us-east-2`. Con `--simular`, solo comprueba | Las claves subidas; 0 o 2 |
| `probar.sh [--origen BASE]` | Todo lo anterior, de punta a punta, en bases temporales que borra al terminar (B12). Sin `--origen`, con datos sintéticos | «ok» o «FALLA» por paso, con tiempos; 0 o 1 |

`database/datos-sinteticos.sql` carga datos inventados con `generate_series`: pocas sucursales, productos, dos años de calendario y algunos miles de ventas. Lo usan el CI y las pruebas locales del mecanismo.

## 5. Comprobaciones de la huella

| # | Comprobación | Alcance |
| --- | --- | --- |
| H1 | Columnas: tabla, nombre, tipo, nulabilidad y valor por defecto | `dw` y `app` |
| H2 | Restricciones: nombre, tipo y definición | `dw` y `app` |
| H3 | Índices: nombre y definición | `dw` y `app` |
| H4 | Vistas: nombre y definición | `dw` |
| H5 | Conteo de filas de cada tabla | Las 8 tablas de `dw` |
| H6 | Suma de los hashes de las filas, que no depende del orden | Las 8 tablas de `dw` |
| H7 | Ventas por año, mes y sucursal: filas, suma de `cantidad` y de `valor_total` | `dw.fact_ventas` |
| H8 | Cada secuencia está en un valor mayor o igual que el máximo de su columna | Las 7 secuencias de `dw` |
| H9 | Conteo, unidades y valor de la vista | `dw.v_ventas_diarias_netas` |
| H10 | Informe de `database/test-dw-real.SQL`, sin las líneas de tiempo | `dw` |

En total son unas 30 líneas. H5 y H6 detectan cualquier diferencia de datos; H7 y H9 dicen dónde está. H1 a H4 confirman que `init.sql` produce el mismo esquema que el origen.

## 6. Traslado a staging

1. **En tu equipo:** `bash scripts/bd/volcar.sh` contra la bodega local, después de cargar las ventas de 2026.
2. **En tu equipo:** `python scripts/bd/subir_volcado.py <carpeta> --bucket <bucket>`, con el perfil `inventaio-volcados`.
3. **En la EC2 (parte 2):**
    1. el compose arranca con el volumen vacío y `init.sql` crea el esquema;
    2. por SSM, la instancia baja la carpeta con su rol;
    3. corre `restaurar.sh` y `validar.sh` contra el contenedor de la base;
    4. corre `seed_usuarios --nube` en el contenedor `api`.
4. La validación debe decir «PASÓ». Si dice «NO PASÓ», el detalle se saca con `huella.sql -v detalle=1` en los dos lados, sin subirlo a ninguna parte.

## 7. Pasos en la consola de AWS (los haces tú)

En us-east-2 (Ohio). Primero revisa que el límite de gasto no vaya a pausar recursos nuevos.

1. **Bucket** `inventaio-staging-<sufijo>`. El nombre debe ser único en todo S3, así que el sufijo puede ser aleatorio. Configúralo así:
    - bloqueo de acceso público activado (viene así);
    - cifrado SSE-S3 (viene así) y propietario del bucket obligatorio (viene así);
    - una regla de ciclo de vida que expire `volcados/` a los 30 días.
2. **Usuario de IAM** `inventaio-volcados`: sin acceso a la consola, con esta política en línea (reemplaza `<bucket>`):

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "SubirVolcados",
          "Effect": "Allow",
          "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
          "Resource": "arn:aws:s3:::<bucket>/volcados/*"
        },
        {
          "Sid": "ListarVolcados",
          "Effect": "Allow",
          "Action": "s3:ListBucket",
          "Resource": "arn:aws:s3:::<bucket>",
          "Condition": { "StringLike": { "s3:prefix": ["volcados/*"] } }
        }
      ]
    }
    ```

3. **Llave de acceso** del usuario, con el uso «Command Line Interface». Guárdala tú en `~/.aws/credentials`, bajo `[inventaio-volcados]`, con `region = us-east-2` en `~/.aws/config`. No la pegues en el chat.

La llave de INV-67 (`inventaio-spike-bedrock`) sigue desactivada y no se usa aquí.

## 8. Pruebas

- **CI:** el job `base-de-datos` (B12), con datos sintéticos.
- **Local, con la bodega real:**
    - volcar;
    - restaurar en una base temporal del contenedor local y validar (debe pasar);
    - alterar un dato y validar (debe fallar);
    - borrar la base temporal.

    Se anotan los tiempos de volcado, restauración y validación. Los valores no salen del equipo.
- **Staging (parte 2):** el mismo `validar.sh` en la EC2, con evidencia del «PASÓ» en Jira.

**Resultados del 11-nov, en el stack local**, con `probar.sh`. Las bases temporales quedaron borradas.

| Prueba | Volcado y huella | Restauración | Validación | Resultado |
| --- | --- | --- | --- | --- |
| Datos sintéticos (lo del CI) | 4 s (208 KB) | 6 s | 2 s | 30 de 30 iguales; la fila alterada se detecta en H6, H7, H9 y H10; restaurar sobre datos se niega |
| Bodega real, 1.ª corrida | 76 s (33 MB) | 315 s | 57 s | 30 de 30 iguales; la fila alterada se detecta en las mismas cuatro; restaurar sobre datos se niega |
| Bodega real, 2.ª corrida | 61 s | 260 s | 52 s | H10 falló con datos iguales: empates sin desempate en `test-dw-real.SQL` (K10) |
| Bodega real, 3.ª corrida, con el desempate | 62 s | 250 s | 25 s | 30 de 30 iguales; la fila alterada se detecta en las mismas cuatro; restaurar sobre datos se niega |

En la 3.ª corrida, la validación ya no saca el detalle cuando todo coincide, y bajó de 57 s a 25 s.

## 9. Riesgos

| Riesgo | Mitigación |
| --- | --- |
| La recarga de staging borra los usuarios y les da claves nuevas | Es aceptable en staging: son las 5 cuentas del seed. En producción la recarga es otra (INV-69) |
| `pg_restore --data-only` falla por el orden de las claves foráneas | No hay ciclos; el CI y la prueba local lo cubren antes de la EC2 |
| La restauración tarda entre 4 y 5 min en local, porque los datos entran con los índices y las claves foráneas ya creados | Es un paso de una vez por recarga. En la t3.medium puede tardar más por los créditos de CPU; se mide en la parte 2 |
| La huella tarda con 2 millones de filas | Medido: unos 28 s en local, incluidos H6 y el informe H10. No hace falta calcularla por mes |
| La organización administrada no deja crear el usuario o el bucket | Ya dejó crear el usuario de INV-67. Si algo falla, se revisa antes de la parte 2 |
| El job del CI se vuelve lento | Usa datos sintéticos de unos miles de filas |

# Parte 2 · La instancia, el TLS y el despliegue

Revisión del 12 de noviembre de 2026 contra `develop` (`d3e3d52`). El usuario tomó las decisiones C1 a C7 el 11 y el 12-nov en dos formularios; las demás son técnicas y siguen de los hallazgos.

## 10. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| K11 | En `docker-compose.prod.yml`, el agente solo tiene las variables de Ollama: falta `LLM_PROVEEDOR` y la región de Bedrock (INV-67 llegó después de INV-66) | El compose pasa las variables de Bedrock (B16) |
| K12 | Dentro de Docker, el rol de la instancia solo se alcanza con IMDSv2 y *hop limit* 2: con el valor por defecto (1), la respuesta no llega al contenedor | La instancia se crea con *hop limit* 2 (B21) |
| K13 | La imagen `web` solo escucha HTTP en el 8080. El 8443 del contrato de `docs/CI-CD.md` nunca se construyó | El TLS lo pone Caddy (C5, B14) |
| K14 | Nginx sobrescribe `X-Forwarded-For` con `$remote_addr` (INV-66, H6). Con un proxy delante, todos los clientes llegarían con la IP del proxy, y el límite de intentos de login por IP (20 en 15 min) se volvería uno solo para todos | Nginx toma la IP real del proxy de confianza (B15) |
| K15 | CA 6 a medias: la interfaz muestra el commit solo si la imagen recibe `VITE_COMMIT`, y `images.yml` no se lo pasa. `/api/health` devuelve la versión, sin el commit | `images.yml` pasa el commit y el api lo devuelve (B17) |
| K16 | `seed_usuarios --nube` crea 5 usuarios (gerente, tres administradores de sucursal y bodega) con claves aleatorias que se muestran una sola vez. Correrlo otra vez cambia todas | Las pruebas de humo usan la cuenta de gerente, con su clave en un archivo de la instancia que solo lee su dueño (B20) |
| K17 | La imagen oficial de Caddy 2.11 trae el binario con la capacidad de abrir puertos bajos y guarda sus datos en `/data` y `/config`. En local: Compose v5.6.0 y Docker 29.8.2 | Caddy sin root (B14). La versión de Docker de Amazon Linux 2023 se confirma en la instancia (riesgo) |
| K18 | CA 1: la cuenta está en el plan de pago (paso 4 de INV-67) y el límite de gasto avisa al 50, 75 y 90 % | Se verifica en la consola; no hace falta otra alarma |

## 11. Decisiones

| # | Decisión | Origen |
| --- | --- | --- |
| C1 | La infraestructura se crea en la consola con una guía paso a paso (`docs/INV-34-guia-staging.md`), sin llave de administrador en el equipo. Se pasa a código en INV-69 | Usuario, 11-nov |
| C2 | Amazon Linux 2023: trae el agente de SSM y la CLI de AWS | Usuario, 11-nov |
| C3 | Sin horario automático: la instancia se enciende y se apaga a mano | Usuario, 11-nov |
| C4 | Dominio propio, gratis el primer año con el GitHub Student Developer Pack en Name.com: la extensión que esté disponible en la oferta (.app, .dev u otra; .com no está). El usuario fue aprobado el 12-nov y los beneficios se activan en 72 horas. Staging: `staging.inventaio.<dominio>`, con un registro A sin proxy. Mientras llega, o si falla: DuckDNS (`<nombre>.duckdns.org`, con límite propio de Let's Encrypt) o `<ip-con-guiones>.sslip.io` (límite compartido). Cambiar de dominio es redesplegar con `DOMINIO=…` | Usuario, 11 y 12-nov |
| C5 | El TLS lo pone Caddy delante de `web` | Usuario, 12-nov |
| C6 | El despliegue se corre desde Session Manager en la consola: sin SSH y con el puerto 22 cerrado | Usuario, 12-nov |
| C7 | Los secretos se generan en la instancia, en el primer despliegue, y no salen de ella | Usuario, 12-nov |
| B14 | Caddy (`caddy:2.11.x-alpine`, fijado por digest) es el único servicio que publica puertos (80 y 443). `web` queda en la red interna. `despliegue/Caddyfile` sirve `{$DOMINIO}` con `reverse_proxy web:8080`, sin esperar a llenar el búfer, para que el streaming del chat no se corte. Corre sin root (uid 10003), sin capacidades, con `no-new-privileges` y el sistema de archivos de solo lectura: Docker deja abrir el 80 y el 443 a cualquier usuario del contenedor. Sus volúmenes van en `/data/caddy` y `/config/caddy`, que la imagen deja escribir a cualquier usuario. Sin API de administración ni HTTP/3, porque el grupo de seguridad no abre el UDP. Sus certificados van en un volumen con nombre: un despliegue nuevo no pide otro certificado (Let's Encrypt permite 5 por semana para el mismo nombre) | Técnica (K13, K17) |
| B15 | `frontend/nginx.conf` incluye `/etc/nginx/snippets/ip-real*.conf` si existe. El compose de producción monta `despliegue/nginx-ip-real.conf`, que confía en `X-Forwarded-For` solo cuando viene de la subred fija de la red del compose. También toma el esquema de `X-Forwarded-Proto`, para que el api sepa que el cliente llegó por HTTPS. En desarrollo no hay archivo y nada cambia | Técnica (K14) |
| B16 | El compose pasa al agente `LLM_PROVEEDOR` (`bedrock` en `.env.prod.example`), `BEDROCK_REGION` (`us-east-2`) y `AWS_REGION`. Sin llaves: la cadena estándar de botocore toma el rol de la instancia (CA 9). `.env.prod.example` fija también `LLM_MODELO=qwen.qwen3-32b-v1:0`, porque el compose siempre pasa `LLM_MODELO` y con el de Ollama Bedrock rechazaría el id. Ollama queda con el perfil `llm` para quien no use Bedrock | Técnica (K11, K12) |
| B17 | `images.yml` pasa `VITE_COMMIT` e `INVENTAIO_COMMIT` (el SHA del commit) a las imágenes. El Dockerfile del api lo guarda como variable de entorno y `/api/health` devuelve `commit` con 7 caracteres, vacío si no hay | Técnica (K15, CA 6) |
| B18 | En la instancia, todo vive en `/opt/inventaio/`: `repo/` (el clon público, sin credenciales), `versiones/<tag>/` (los archivos de cada tag, sacados con `git archive`), `estado/.env.prod` y `estado/humo.env` (600), `estado/actual` y `estado/anterior`. El proyecto de Compose sigue siendo `inventaio-prod`, así que los volúmenes de la base y de Caddy sobreviven a cada versión | Técnica |
| B19 | `scripts/desplegar_staging.sh TAG` hace lo siguiente: comprueba que las cuatro imágenes existan en GHCR; saca los archivos del tag; la primera vez genera `.env.prod` con secretos aleatorios y el dominio; baja las imágenes; levanta Postgres; aplica `migrar.sh`; levanta el resto esperando a que estén sanos; y corre las pruebas de humo. Si el humo falla, vuelve solo al tag anterior y sale con 1. `--reversa` despliega el anterior. `--primera-vez` omite el humo, porque todavía no hay bodega ni usuarios. `--configurar-humo` pide el email y la clave de la cuenta de humo sin mostrarla y escribe `estado/humo.env`. Además: un candado impide dos despliegues a la vez; `DOMINIO=…` y `BUCKET_VOLCADOS=…` delante del comando los cambian en `.env.prod`; y tras un despliegue sano borra las imágenes sin uso, porque el disco es de 30 GB (una reversa las vuelve a bajar) | Técnica (CA 5) |
| B20 | `scripts/humo_staging.py URL`, solo con la biblioteca estándar de Python, comprueba: HTTP redirige a HTTPS con un certificado válido; `/` sirve la aplicación con HSTS y CSP; `/api/health` trae la versión y el commit esperados; login de la cuenta de humo; datos de `/api/consulta/sucursales`; el componente inteligente (`/api/alertas/ml` y una pregunta a Vera por `/api/chat/message`, que transmite hasta el final); y un 404 controlado. La cuenta sale de `estado/humo.env`. Imprime el nombre y el resultado de cada prueba, sin datos | Técnica (CA 7, K16) |
| B21 | La instancia es una t3.medium con Amazon Linux 2023 y 30 GB de gp3 cifrado. Tiene IMDSv2 obligatorio con *hop limit* 2, ningún par de llaves, una IP elástica y 2 GB de swap. Su grupo de seguridad abre solo el 80 y el 443. Su rol `inventaio-staging-ec2` lleva SSM, `bedrock:InvokeModel*` sobre Qwen3-32B en us-east-2 y `s3:GetObject` en `volcados/*`. `despliegue/preparar_instancia.sh`, idempotente, instala Docker, Compose (fijado), git y el swap | Técnica (C2, K12) |
| B22 | `scripts/bd/restaurar_staging.sh <carpeta>` baja el volcado del bucket (`BUCKET_VOLCADOS` de `.env.prod`) con el rol de la instancia, toma la conexión de `.env.prod`, restaura y valida contra el contenedor de la base (sección 6), con los scripts del tag desplegado | Técnica |
| B23 | `docs/CI-CD.md` pasa a decir que publica Caddy y no `web`, y agrega el despliegue, la reversa y el costo mensual (DoD 6) | Técnica |

## 12. Archivos

| Archivo | Cambio |
| --- | --- |
| `docker-compose.prod.yml` | Servicio `caddy`; `web` sin puertos; red con subred fija; montaje de `nginx-ip-real.conf`; variables de Bedrock del agente; volumen de Caddy |
| `.env.prod.example` | `DOMINIO`, `BUCKET_VOLCADOS`, `LLM_PROVEEDOR=bedrock`, `BEDROCK_REGION`; Ollama como alternativa |
| `despliegue/Caddyfile` y `despliegue/nginx-ip-real.conf` | Nuevos (B14 y B15) |
| `despliegue/preparar_instancia.sh` | Nuevo (B21) |
| `scripts/desplegar_staging.sh` y `scripts/humo_staging.py` | Nuevos (B19 y B20) |
| `scripts/bd/restaurar_staging.sh` | Nuevo (B22) |
| `frontend/nginx.conf` | El `include` opcional de la IP real (B15) |
| `api/Dockerfile`, `api/core/config.py`, `api/main.py`, su prueba y el OpenAPI versionado | El commit en `/api/health` (B17) |
| `database/README.md` | `restaurar_staging.sh` en la tabla de scripts |
| `.github/workflows/images.yml` | Los argumentos `VITE_COMMIT` e `INVENTAIO_COMMIT` (B17) |
| `docs/CI-CD.md` y `docs/INV-34-guia-staging.md` | El contrato nuevo y la guía (B23 y C1) |

## 13. Pruebas

- **Pruebas del api:** `/api/health` con commit y sin commit.
- **Local, con el compose de producción y `DOMINIO=localhost`:** Caddy usa su certificado interno para `localhost`. Comprueba lo siguiente:
    - la redirección a HTTPS y las cabeceras;
    - la IP real en el api: tras varios logins fallidos, otra IP no queda bloqueada;
    - el streaming del chat a través de Caddy;
    - `humo_staging.py` contra `https://localhost`.

    Bedrock no se prueba en local, porque la única llave con permiso está desactivada.
- **Staging:**
    - el humo completo;
    - la restauración con el «PASÓ» del validador;
    - una reversa probada al tag anterior (DoD 5);
    - los casos críticos con los tres roles: gerente, administrador de sucursal y bodega (CA 8), con evidencia en Jira.

**Resultados locales (12-nov).** Corrieron los scripts reales con `INVENTAIO_BASE` en una carpeta temporal, un clon con dos commits de prueba (A y B), las imágenes en un registro local, `DOMINIO=localhost`, Ollama en lugar de Bedrock y un `aws` simulado que copiaba el volcado. Al terminar se borró todo, también el volcado.

| Prueba | Resultado |
| --- | --- |
| Api: `/api/health` con y sin commit; suite unitaria completa | 275 pasan, 1 se salta; ruff limpio |
| Primer despliegue (`--primera-vez`) | 3 min 43 s; los 7 servicios sanos; Caddy con uid 10003 y sin capacidades; `.env.prod` en 600 con secretos aleatorios |
| HTTPS y cabeceras | HTTP responde 308 hacia HTTPS; HTTP/2; HSTS y CSP de Nginx; sin `Alt-Svc` (sin HTTP/3); `/api/health` con el commit del tag |
| IP real | El api registra la IP de quien se conecta a Caddy, no la de Caddy ni un `X-Forwarded-For` inventado |
| Streaming por Caddy | Con un servidor falso, 5 eventos llegan a 0,03, 1,03, 2,03, 3,03 y 4,03 s. Con el agente, la respuesta llega junta al final por la verificación de fidelidad (`FIDELIDAD_RETENER`, INV-33), no por Caddy |
| `restaurar_staging.sh` con la bodega real | Restaurada en 370 s; «PASÓ: 30 comprobaciones» |
| Humo de un tag con el commit equivocado | Falla `salud`, vuelve solo al tag anterior, que pasa 8 de 8, y sale con 1 (4 min 46 s) |
| Despliegue de B y reversa a A | 8 de 8 en los dos; la reversa tarda 1 min 50 s, bajando otra vez las imágenes |
| Recrear la base (§15 de la guía) | La base queda vacía y `.env.prod` igual |
| `probar_nginx_streaming.sh` y `probar_nginx_timeout.sh` | Siguen en verde con el `nginx.conf` nuevo |

Quedan para staging: Bedrock con el rol, el certificado real de Let's Encrypt, S3 con el rol y Compose v5.6.1 con el Docker de Amazon Linux 2023.

## 14. Orden de trabajo

1. **Código** (rama `feature/INV-34-staging`): las secciones 11 y 12, con las pruebas locales.
2. **PR único** a `develop` con las partes 1 y 2. Al integrarlo, el CI publica las imágenes con el tag `sha-…` que se despliega.
3. **Consola** (el usuario, con la guía): el rol, el grupo de seguridad, la instancia, la IP elástica y el DNS en Name.com (o DuckDNS mientras se activa el pack).
4. **Instancia** (el usuario, por Session Manager):
    1. `preparar_instancia.sh`;
    2. `desplegar_staging.sh <tag> --primera-vez`;
    3. `restaurar_staging.sh`;
    4. `seed_usuarios --nube` y `humo.env`;
    5. `desplegar_staging.sh <tag>` con el humo.
5. **Cierre:** reversa probada, casos críticos con evidencia y `docs/CI-CD.md`.

## 15. Costos

| Concepto | Encendida | Apagada |
| --- | --- | --- |
| t3.medium | US$0,0416 por hora | US$0 |
| Disco gp3 de 30 GB | US$2,40 al mes | US$2,40 al mes |
| IP elástica | US$3,65 al mes | US$3,65 al mes |
| Bedrock | ~US$0,0011 por pregunta | — |

Encendida todo el mes cuesta ~US$37. Apagada, ~US$6 al mes por el disco y la IP. El dominio sale gratis el primer año con el GitHub Student Developer Pack; después se paga la renovación de Name.com o, si se transfiere, la de Porkbun (~US$12 al año para .dev). No se cobra en AWS.

## 16. Riesgos de la parte 2

| Riesgo | Mitigación |
| --- | --- |
| La versión de Docker de Amazon Linux 2023 no es compatible con Compose v5 | `preparar_instancia.sh` comprueba `docker compose version` y una corrida de prueba. Si falla, se usa la última versión 2.x de Compose |
| El DNS del dominio nuevo tarda en propagarse y Caddy no obtiene el certificado | Caddy reintenta solo. Mientras tanto, `DOMINIO=<ip-con-guiones>.sslip.io` |
| El límite de Let's Encrypt (5 certificados por semana para el mismo nombre) | El volumen de Caddy conserva el certificado entre despliegues |
| Los beneficios de GitHub Student tardan hasta 72 horas | La instancia espera al PR. Si el dominio no llega a tiempo, DuckDNS, y después se cambia con `DOMINIO=…` |
| El límite compartido de Let's Encrypt en sslip.io se agota (pasó en febrero de 2026) | DuckDNS, que tiene su propio límite |
| El humo falla en el primer despliegue porque todavía no hay datos ni usuarios | `--primera-vez` lo omite; el despliegue siguiente lo exige |
| El límite de gasto pausa la instancia | Revisarlo antes de crearla (paso 0 de la guía) |
| Se olvida apagar la instancia | Cuesta ~US$1 al día encendida; el límite de gasto avisa |
| La t3.medium se queda corta durante la restauración o en las recomendaciones en frío | Se mide en staging; el swap da margen e INV-41 lo confirma |
