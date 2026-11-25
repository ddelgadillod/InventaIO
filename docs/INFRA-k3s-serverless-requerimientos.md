# Staging en k3s con servicios serverless, despliegue y recuperación automáticos · Requerimientos

| Campo | Valor |
| --- | --- |
| Tipo | Trabajo técnico del Sprint 8, sin historia propia. Cubre parte del alcance de INV-69 (producción), INV-70 (alojamiento de la PWA) e INV-41 (Redis con persistencia) |
| Aprobado | 24-nov-2026, con las decisiones P1 a P20 en su opción recomendada |
| Depende de | INV-34 (staging en EC2), INV-24 (CI e imágenes en GHCR), INV-66 (`docker-compose.prod.yml`), INV-67 (Bedrock en us-east-2) |
| Ramas | Una por fase, desde `develop`. La primera es `infra/despliegue-automatico` (fases 0 y 1) |
| Antecedentes | Documento «Arquitectura en AWS y plan de migración» (11-nov) y propuesta de nube del 18-oct |

Revisión del 24 de noviembre de 2026 contra `develop` (`9fac5a4`).

## 1. Objetivo

- **Staging:** pasa de Docker Compose a k3s, una distribución liviana y certificada de Kubernetes, en una EC2.
- **Alrededor de la máquina:** servicios serverless donde bajan el costo o suben la robustez: la web, los secretos, el horario de encendido, el monitoreo y las copias.
- **Despliegue automático:** GitHub Actions despliega solo cada versión y vuelve a la anterior si las pruebas de humo fallan.
- **Producción** se arma con la misma receta, más RDS y una aprobación manual por despliegue.

**Fuera de alcance**, para después de la entrega del 19-dic:
- la API principal o el agente en Lambda;
- Aurora Serverless, EKS y varias zonas de disponibilidad;
- GitOps;
- Graviton;
- el reemplazo automático de la máquina con un grupo de autoescalado.

## 2. Contraste con lo ya construido

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| H1 | El código de los tres servicios de Python se configura solo por variables de entorno, no guarda estado y expone salud: `/api/health` (api y ml-service), `/health` y `/ready` (agente), `/` (web). Las cuatro imágenes corren sin root | Pasan a Kubernetes sin cambiar el código |
| H2 | `frontend/nginx.conf` resuelve los servicios con el DNS de Docker (`resolver 127.0.0.11`) | El DNS pasa a una variable: el de Docker en compose y el del clúster en k3s |
| H3 | `despliegue/nginx-ip-real.conf` confía en la subred del compose (`172.30.0.0/24`) para tomar la IP del cliente | El rango de confianza pasa a una variable. Sin eso, el límite de login por IP (INV-66) vería una sola IP para todos |
| H4 | `scripts/desplegar_staging.sh` usa Compose; `scripts/bd/migrar.sh` se conecta por la red de un contenedor (`BD_RED=container:…`); `scripts/bd/restaurar_staging.sh` busca el contenedor por sus etiquetas de Compose | Se agrega `scripts/desplegar.sh` para k3s y los dos de la base aceptan una conexión por `kubectl` |
| H5 | El Redis de producción corre sin disco (`--save ""`, `--appendonly no`). Lo usa el límite de login, que tiene un respaldo en memoria. INV-41 le agrega la lista negra de refresh tokens | Un reinicio de Redis borraría la lista negra: pasa a persistencia en disco (P9) |
| H6 | El agente manda un comentario SSE `: ping` tras 15 s de silencio (`CHAT_PING_S`) | El chat pasa por CloudFront, que espera 30 s entre paquetes por defecto y admite hasta 120 s |
| H7 | La primera consulta de recomendaciones tarda de 20 a 42 s. Nginx espera 135 s y el Core API espera 120 s al ML Service | `/api/*` en CloudFront con 120 s de espera |
| H8 | `/api/health` no consulta la base | La base se vigila con sus propias alarmas |
| H9 | En la t3.medium de staging, los 7 contenedores usan ~0,9 GiB (ml-service 655 MiB) y quedan 2,3 GiB (INV-34) | k3s, que mide entre 1,4 y 1,6 GB, cabe justo: hay que medir en la fase 4 |
| H10 | El secreto de la base y la clave JWT se generan en la máquina (`/opt/inventaio/estado/.env.prod`) y no existen en otro lugar | Si se pierde la máquina, se pierden: pasan a Parameter Store (P8) |
| H11 | El contrato de INV-24 ya prevé un rol de IAM por OIDC, Session Manager y aprobación manual. El repositorio conserva el claim `sub` clásico (`repo:ddelgadillod/InventaIO:…`) | La fase 1 lo implementa sin cambiar `desplegar_staging.sh` |
| H12 | El workflow «Imágenes» publica `sha-…` en cada push a develop y main, y `vX.Y.Z` en cada tag | Es el disparador del despliegue automático |

## 3. Decisiones (aprobadas el 24-nov)

| # | Decisión | Elegido |
| --- | --- | --- |
| P1 | Plataforma | k3s en EC2. EKS costaría ~US$170 a 190 al mes más |
| P2 | Máquina | Una EC2 nueva por ambiente. La de staging reemplaza a la actual al cortar, sin caída y con vuelta atrás |
| P3 | Tamaño | t3.medium con 2 GB de swap; t3.large si la medición deja menos del 25 % de memoria libre. Graviton, después |
| P4 | Entrada | Caddy como pod en el 443, con su Caddyfile adaptado a CloudFront (k8s/base/Caddyfile). Traefik apagado; ServiceLB de k3s publica el 80 y el 443 (H15). No se usa ingress-nginx, que se retiró en marzo de 2026 |
| P5 | Web | S3 + CloudFront en los dos ambientes, con cobro por uso, que es gratis a este volumen y admite la CSP propia |
| P6 | Dominio | El de GitHub Student, con subdominios. Mientras llega, el nombre de CloudFront. Los orígenes siguen en DuckDNS |
| P7 | Manifiestos | Kustomize: base y variantes `staging`, `produccion` y `ci` |
| P8 | Secretos | Parameter Store, estándar y cifrado. El script los vuelca a un Secret sin escribirlos a disco; k3s con cifrado de secretos |
| P9 | Redis | Persistencia en disco (AOF) en un volumen |
| P10 | Infraestructura como código | OpenTofu, con el estado en un bucket S3 cifrado y con bloqueo nativo |
| P11 | Quién aplica la infraestructura | El usuario, en AWS CloudShell, sin llaves de larga duración fuera de AWS |
| P12 | Despliegue | Staging en cada push a develop. Producción con cada tag `vX.Y.Z`, después de que el mismo tag pase por staging y con aprobación |
| P13 | Recuperación | Kubernetes reinicia contenedores; el despliegue vuelve solo a la versión anterior; la EC2 se recupera o se reinicia por alarma; la máquina se reconstruye con un comando |
| P14 | Monitoreo | Chequeo de Route 53 sobre producción, alarmas de EC2, RDS y CloudFront, agente de CloudWatch y Budgets, con avisos por correo |
| P15 | Copias | RDS: 7 días con restauración a un punto en el tiempo. Volcado semanal a S3 que se guarda 30 días. Instantánea diaria del disco de staging que se guarda 7 días |
| P16 | Horario de staging | Encendido de lunes a viernes a las 7:00, apagado todos los días a las 23:00 (Bogotá). Al encender se pone al día con develop |
| P17 | Base de producción | RDS db.t4g.micro, privada, cifrada, en una zona y con protección contra borrado |
| P18 | Primera versión en producción | `v4.0.0-rc.1`, con los arreglos de INV-41 |
| P19 | Calendario | Producción en k3s el 7-dic; pruebas con usuarios del 8 al 10-dic |
| P20 | Espacio en el Sprint 8 | INV-81 pasa al Sprint 9 e INV-39 se acota. Jira y Confluence se actualizan con formulario |

## 4. Arquitectura

```
Usuario ─▶ CloudFront (HTTPS, protección DDoS, cabeceras de seguridad)
             ├─ /*      ─▶ S3 privado: la aplicación web compilada
             └─ /api/*  ─▶ EC2 con k3s: el 443 solo acepta CloudFront y exige una cabecera secreta de origen
                              Caddy → Nginx → API principal ─┬─▶ servicio de pronóstico
                                                             ├─▶ agente ─▶ Bedrock
                                                             ├─▶ Redis con disco
                                                             └─▶ PostgreSQL (k3s en staging; RDS en producción)
Alrededor: Parameter Store · S3 (copias) · instantáneas del disco · Route 53 → CloudWatch → SNS (correo) ·
recuperación de la EC2 · Budgets · EventBridge Scheduler · GitHub Actions → OIDC → Session Manager
```

## 5. Contratos y nombres

| Elemento | Definición |
| --- | --- |
| Etiquetas | `Proyecto=inventaio` y `Ambiente=staging` o `Ambiente=produccion` en todo recurso. Session Manager elige la máquina por `Ambiente` |
| Parámetros | `/inventaio/<ambiente>/` + `postgres-password`, `jwt-secret-key`, `humo-email`, `humo-clave`, `origen-secreto`, `tag-actual` y `tag-anterior`. Los secretos son `SecureString` |
| Roles de GitHub | `inventaio-gha-staging` e `inventaio-gha-produccion`. Confían solo en `repo:ddelgadillod/InventaIO:environment:<entorno>` y solo pueden mandar el documento de despliegue a las máquinas de su ambiente, leer el resultado, escribir en su bucket web e invalidar su distribución |
| Roles de las máquinas | `inventaio-<ambiente>-ec2`: Session Manager, Bedrock (Qwen3-32B en us-east-2), los parámetros de su ambiente, sus copias en S3 y el agente de CloudWatch |
| Documento de Session Manager | `inventaio-desplegar`, con un solo parámetro `tag` validado con `^(sha-[0-9a-f]{7}\|v[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?)$`. Corre el script de despliegue como `ec2-user` |
| Entornos de GitHub | `staging`, solo desde develop. `produccion`, solo desde tags `v*.*.*` y con aprobación |
| Registros públicos de Actions | Solo «pasó» o «no pasó» y cuántas comprobaciones hubo. La cuenta, los ARN y las IP se ocultan con `::add-mask::` |

## 6. Fases y criterios de salida

| Fase | Alcance | Sale cuando | Vuelta atrás |
| --- | --- | --- | --- |
| 0 · Preparación | Este documento y la verificación de la cuenta (`despliegue/aws/verificar_cuenta.sh`, solo lectura) | Las decisiones están registradas y la cuenta permite los servicios | — |
| 1 · Despliegue automático sobre el staging actual | Proveedor OIDC, rol de staging, documento de Session Manager y `.github/workflows/desplegar.yml` | Un push a develop queda en staging con su commit en `/api/health`; un tag que no pasa el humo vuelve solo al anterior; sin datos de la cuenta en el registro | Desactivar el workflow |
| 2 · Manifiestos y ajustes | `k8s/`, DNS e IP real configurables, Redis con AOF, `scripts/desplegar.sh`, scripts de la base con `kubectl` | Compose sigue igual y los manifiestos pasan kubeconform | Revertir el PR |
| 3 · Validación local y en el CI | k3d en local y el job «Kubernetes (k3d)» | Lo que comprueba `docker-compose.verify.yml` pasa en k3d | — |
| 4 · Serverless y staging en k3s | `infra/` con OpenTofu, `despliegue/preparar_k3s.sh`, la web en S3 + CloudFront y el humo ampliado | Humo completo; Bedrock solo desde el agente; alarmas en OK; horario probado; primera instantánea | El staging actual sigue igual |
| 5 · Corte de staging | Etiqueta y DuckDNS a la máquina nueva; prueba de carga corta | Tres despliegues seguidos en verde; carga dentro de lo medido por INV-41 | Etiqueta y DNS de vuelta |
| 6 · Producción | La variante de producción, RDS, usuarios y secretos nuevos y el entorno con aprobación | Humo y casos críticos de los tres roles; alarma probada; restauración de RDS probada | La versión anterior y la restauración a un punto en el tiempo |

## 7. Resultado de la fase 0 (24-nov)

`despliegue/aws/verificar_cuenta.sh` en CloudShell: 36 comprobaciones en OK, ninguna negada por la organización ni por IAM.

| Comprobación | Resultado | Consecuencia |
| --- | --- | --- |
| Usuario y plan de la cuenta | Usuario de IAM, no raíz; cuenta de pago | CloudShell sirve para aplicar la infraestructura (P11) |
| Simulaciones de EC2 | t3.medium, t3.large, IP elástica y grupo de seguridad permitidos | — |
| Cuota de vCPU On-Demand estándar | 32; hacen falta 8 | Alcanza para las dos máquinas de staging mientras conviven y la de producción, aun en t3.large |
| IP elásticas | Cuota de 5, 1 en uso; hacen falta 3 | — |
| VPC por defecto | Existe | Las máquinas nuevas van en ella |
| Lista de CloudFront para el origen | Existe; la API no informa su tamaño | Ocupa la mayor parte de las 60 reglas de un grupo de seguridad. Va sola en su propio grupo, y el 80 va en otro |
| Proveedor OIDC de GitHub | No existe | Lo crea la fase 1 |
| Session Manager | Administra la instancia de staging | La fase 1 despliega por ahí |
| CloudFront, ACM en us-east-1, Route 53, CloudWatch, SNS, EventBridge Scheduler, DLM y RDS | Accesibles | — |
| AWS Budgets | Ningún presupuesto | La fase 1 crea el presupuesto mensual antes que cualquier otro recurso |
| PostgreSQL en db.t4g.micro | 16.13 y 16.15 | 16.13 coincide con la bodega local |

## 8. Fase 1: diseño

- **El despliegue es un trabajo más de «Imágenes»** (`desplegar-staging`), después de publicar y solo en push a develop. Llama al workflow reutilizable `.github/workflows/desplegar.yml`. No se usa `workflow_run`: ese evento solo corre el archivo de main, que cambia solo con cada release.
- **`desplegar.yml`:**
  - entorno de GitHub del ambiente;
  - OIDC con `aws-actions/configure-aws-credentials` v6.3.0, fijada por SHA;
  - busca la máquina por las etiquetas `Proyecto` y `Ambiente`; si está apagada, avisa y termina sin fallar;
  - manda el documento `inventaio-desplegar` y espera hasta 40 minutos;
  - resume el resultado según el código del script (0, 1 o 2);
  - comprueba que `/api/health` público muestre el commit.
- **El documento `inventaio-desplegar`** (`despliegue/aws/inventaio-desplegar.json`):
  - valida el tag con una expresión regular;
  - corre como `ec2-user` lo mismo que la guía de staging (§11): `git pull` y `desplegar_staging.sh <tag>`;
  - si falla `git pull`, sale con 2 y no toca lo que corre.
- **En AWS** lo crea `despliegue/aws/fase1_despliegue_automatico.sh`, en CloudShell, sin tocar lo que corre:
  - el presupuesto `inventaio-mensual`, de US$100, con avisos al 50, 80 y 100 % del gasto real y al 100 % del pronóstico;
  - el proveedor OIDC;
  - el rol `inventaio-gha-staging` con su confianza y sus permisos;
  - el documento;
  - las etiquetas de la instancia.
- **En GitHub:**
  - el entorno `staging`, solo desde develop;
  - el secreto `AWS_ROL_DESPLIEGUE`;
  - la variable `URL_PUBLICA`, `https://inventaio-staging.duckdns.org`.

### Resultado de la fase 1 (25-nov)

- **PR #57 y #58.** La primera corrida falló en las credenciales: un workflow reutilizable no recibe secretos sin `secrets: inherit`.
- **Corrida 45535908921** (`a784cae`): «Desplegado: el humo pasó».
  - El `/api/health` público muestra el commit.
  - El registro no expone la cuenta, los ARN ni el id de la máquina.
- **Tag inexistente** (`sha-0000000`, mandado desde CloudShell): sale con 2 y no toca lo que corre.
- **Entorno `staging`:** queda con «Required reviewers», así que cada despliegue espera la aprobación del usuario.

## 9. Fase 2: diseño y hallazgos

| # | Hallazgo | Solución |
| --- | --- | --- |
| H13 | Nginx usa el DNS de Docker y el nombre corto `api` (`frontend/nginx.conf`). En Kubernetes no usa los dominios de búsqueda del clúster | `frontend/nginx/upstream.conf` con los valores de compose; en el clúster lo reemplaza `k8s/base/nginx/upstream.conf` (DNS 10.43.0.10 y `api.inventaio.svc.cluster.local`) |
| H14 | Los scripts de la base corren `psql` y `pg_restore` con `docker run`; en k3s no hay Docker | Con `BD_POD`, `scripts/bd/comun.sh` los corre en el pod de herramientas (`k8s/plantillas/bd-herramientas.yaml`) con `kubectl exec`, y los archivos viajan con `tar`. Sin `BD_POD`, todo sigue con Docker |
| H15 | Pod Security «restricted» prohíbe `hostPort` | Caddy se publica con ServiceLB de k3s (Service LoadBalancer) y abre el 80 y el 443 sin root con la sysctl `net.ipv4.ip_unprivileged_port_start=0`, que Kubernetes considera segura. Se apaga solo Traefik, no ServiceLB (ajuste a P4) |
| H16 | Kustomize agrega un sufijo al nombre de los ConfigMap generados; un Job creado aparte no los encuentra | La conexión a la base va en `inventaio-bd`, con nombre fijo. Lo usan las aplicaciones, Postgres, la migración y el pod de herramientas |
| H17 | Con CloudFront delante, Caddy ve la IP del borde de CloudFront y no la del visitante | `k8s/base/Caddyfile` toma la IP de `CloudFront-Viewer-Address` (CloudFront la sobrescribe), le quita el puerto y la manda en `X-Forwarded-For`. Nginx confía solo en la red de pods (10.42.0.0/16). Además, Caddy rechaza con 403 lo que no trae la cabecera secreta de origen |
| H18 | Las imágenes de Python fijan `USER app` con nombre: el nivel «restricted» necesita el uid numérico | `runAsUser: 10001` en las tres; 101 en web, 999 en Redis, 70 en Postgres y 10003 en Caddy |

**`scripts/desplegar.sh`** tiene el mismo contrato que `desplegar_staging.sh`: uso, salidas 0, 1 o 2 y vuelta automática. Hace esto:
1. Saca `k8s`, `database`, `scripts` y `VERSION` del tag con `git archive`.
2. Comprueba en GHCR que existan las cuatro imágenes antes de tocar nada.
3. Vuelca los secretos de Parameter Store a un Secret. Si faltan la primera vez, los genera y los guarda cifrados.
4. Crea el ConfigMap del esquema y escribe la kustomization del ambiente con los tags, el `DOMINIO` y, en producción, el endpoint de RDS.
5. Corre el Job de migración antes de los servicios. La primera vez, Postgres crea el esquema al arrancar.
6. Aplica, espera cada actualización y corre el humo contra la URL de CloudFront.
7. Guarda el tag en `estado/` y en Parameter Store.

Se probó con `aws`, `curl`, `kubectl` y el humo simulados, y con Kustomize real:
- primera vez con los 3 secretos generados;
- migración antes de los servicios;
- humo que falla: vuelve al anterior y sale con 1;
- imagen ausente: sale con 2 sin aplicar nada;
- endpoint de RDS en producción;
- uso incorrecto.

**Validación estática:** las tres variantes y las dos plantillas pasan kubeconform. Nginx carga en sus dos variantes (`nginx -t`) y el Caddyfile del clúster pasa `caddy validate`.

**Redis:** `docker-compose.prod.yml` pasa a AOF (`--appendonly yes`) con el volumen `redis_datos`. El próximo despliegue en compose recrea Redis con disco; no se pierde nada, porque solo había contadores que vencen.

**Para la fase 3 (k3d):**
- que `header_up X-Forwarded-For` de Caddy reemplace la cabecera que Caddy agrega por su cuenta;
- que Postgres arranque con el sistema de archivos de solo lectura;
- que las reglas de red dejen pasar a ServiceLB.

**Para la fase 4:**
- `restaurar_staging.sh` aprende el modo k3s (`herramientas_k8s`);
- el traslado de la base de staging incluye el esquema `app` (usuarios y sus claves);
- comparar el `.env.prod` actual de la instancia con la configuración de la base (por ejemplo `MEJORAS` y `PERFIL_PROMPT`).

## 10. Fase 3: prueba en un clúster (k3d)

`k8s/probar_k3d.sh` corre igual en local y en el job «Kubernetes (k3d)» de `images.yml`.
- **Clúster:** crea un clúster k3s como el de la máquina, sin Traefik y con ServiceLB y las reglas de red de k3s. Usa la versión fijada v1.37.2+k3s1, la estable al 24-nov, que es la misma que instalará la fase 4.
- **Despliegue:** carga las cuatro imágenes del commit y despliega `k8s/overlays/ci` con las funciones de `scripts/desplegar.sh`: `preparar_cluster`, `esperar_servicios`, `migrar` y `hay_base_lista`. Así se prueban las mismas que usa la máquina.
- **CI:** el job además pasa kubeconform sobre las tres variantes y las plantillas. Todavía no detiene la publicación: entra en `needs` de «Publicar» con el corte de la fase 5.

| Comprobación | Cómo |
| --- | --- |
| Pod Security «restricted» | Ninguna advertencia al aplicar. Los siete pods corren con un uid distinto de 0 y no escriben en `/`. Un pod privilegiado se rechaza (`--dry-run=server`) |
| Postgres y la migración | Postgres crea el esquema al arrancar con la raíz de solo lectura. El Job de migración corre dos veces seguidas sin errores |
| Caddy | 403 sin la cabecera secreta y con otra. Con ella pasa el humo sin cuenta: HTTPS con la CA interna, la app con HSTS y CSP, la salud con la versión y el 404 |
| IP del visitante | Un login fallido manda `CloudFront-Viewer-Address`, en IPv4 y en IPv6, y una `X-Forwarded-For` falsa. Redis debe guardar el contador del login con la IP del visitante, sin la falsa y sin una IP interna. Comprueba de paso que el Core API llega a Postgres (responde 401) y a Redis |
| Reglas de red | 19 conexiones, entre permitidas y bloqueadas, desde los servicios y desde un pod «intruso». Incluye que solo el agente sale a Bedrock por el 443 |
| Scripts de la base | `herramientas_k8s`, `exigir_conexion` y `pg_sql` con `BD_POD`; un `pg_dump` de `app` va y vuelve con tar |
| Redis con AOF | Una llave y los contadores del login sobreviven a borrar el pod |
| Tamaño de la máquina | `kubectl top` de cada pod y del nodo, para decidir entre t3.medium y t3.large |

| # | Hallazgo | Solución |
| --- | --- | --- |
| H19 | Con Bedrock, `/ready` del agente exige credenciales de AWS. En k3d no hay metadatos de máquina, así que el agente nunca quedaría listo | `k8s/overlays/ci` le da credenciales de mentira. `/ready` no llama a Bedrock (INV-67, B10), así que no abren nada |
| H20 | Para probar el origen sin CloudFront, el humo necesita mandar la cabecera secreta | `scripts/humo_staging.py --cabecera 'NOMBRE: valor'`, repetible. Es solo para pruebas, porque el valor queda en la lista de procesos |
| H21 | En la máquina, los pods salen a los metadatos (IMDSv2) con un salto más que un proceso de la máquina | La fase 4 crea la instancia con `http_tokens = required` y `http_put_response_hop_limit = 2`, y el humo ampliado comprueba que el agente llega a Bedrock |
| H22 | La primera corrida en el CI encontró Postgres en el espacio de nombres `default`. El `namespace` de la base no alcanza lo que agrega cada variante: el componente de Postgres en staging y ci, y el Service de RDS en producción. kubeconform no lo ve | `namespace: inventaio` también en las tres variantes, y `probar_k3d.sh` comprueba antes de crear el clúster que ningún objeto quede fuera |
| H23 | La segunda corrida encontró la migración con «Connection refused»: corrió 5 s después de que arrancara Postgres, justo cuando estaba recién lista y su Service todavía no le llevaba tráfico. El Job no reintenta (`backoffLimit: 0`) | El Job espera a la base hasta un minuto con `pg_isready` antes de `psql`. Sirve también durante una conmutación de RDS en producción |

**En el equipo de desarrollo (Docker Desktop en WSL):** el 24-nov, Docker Hub respondía de forma intermitente y el nodo de k3d no terminaba de bajar ni las imágenes de k3s. El Docker del equipo también se trababa: es la red de ese momento, no los manifiestos. Por eso la primera corrida completa es la del CI. Con buena conexión, la prueba local sirve igual (`k8s/README.md`).

**Resultado:** pendiente de la primera corrida del CI.

## 11. Humo ampliado (fase 4)

Además de las 9 comprobaciones de hoy:
- la web por CloudFront, con CSP y HSTS;
- Vera con streaming por CloudFront, terminando en `done`;
- recomendaciones en frío antes de 120 s;
- la IP real del cliente llega a la API;
- una petición directa al origen sin la cabecera secreta se rechaza.

## 12. Seguridad

- GitHub no guarda llaves de AWS: solo OIDC, con un rol por ambiente atado al entorno.
- Los volcados, el validador y los datos del negocio corren dentro de AWS, nunca en un runner.
- Exposición del origen:
  - el 443 solo acepta CloudFront y la cabecera secreta;
  - el 80 solo sirve el desafío de Let's Encrypt y redirige;
  - el 22 y la API de Kubernetes quedan cerrados.
- Dentro del clúster:
  - Pod Security «restricted»;
  - reglas de red que niegan todo por defecto;
  - solo el agente llega a los metadatos de la máquina.
- Cadena de suministro:
  - k3s con versión y SHA-256 fijos;
  - proveedores de OpenTofu con archivo de bloqueo;
  - acciones fijadas por SHA;
  - las mismas imágenes escaneadas por Trivy.

## 13. Riesgos

| Riesgo | Mitigación |
| --- | --- |
| La memoria de la t3.medium no alcanza con k3s | Recreate en ml-service, límites por pod y medición en la fase 4; si no alcanza, t3.large (P3) |
| La IP real del cliente se pierde entre CloudFront, Caddy y Nginx | Prueba obligatoria en el humo; se diseña en la fase 2 y se prueba en k3d |
| Una política de la organización de AWS bloquea un servicio | La verificación de la fase 0 |
| El calendario no alcanza | Las fases 0 y 1 dan valor solas. Si la fase 4 se atrasa, producción sale el 7-dic en compose con la misma receta serverless y pasa a k3s después |
| Let's Encrypt limita certificados repetidos | Entorno de pruebas de Let's Encrypt mientras se prueba |
| Primer uso de OpenTofu | Módulos pequeños, un ambiente a la vez |
