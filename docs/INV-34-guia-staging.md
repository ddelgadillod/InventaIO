# INV-34 · Guía del staging en AWS

Pasos para crear y desplegar el staging en la consola de AWS, en la región **us-east-2 (Ohio)**. Las decisiones están en `docs/INV-34-requerimientos.md` (parte 2). Los comandos de la instancia se corren en Session Manager, sin SSH.

## Valores de este staging

| Dato | Valor |
| --- | --- |
| Región | `us-east-2` (Ohio) |
| Bucket del traslado | `<bucket>`: el nombre real está en tu equipo, no en el repositorio |
| Volcado inicial | `20261112-1526`: la bodega sin las ventas de 2026 (§15 para recargarla) |
| IP elástica | `3.149.216.15` |
| Dominio del staging | `inventaio-staging.duckdns.org`; después, el de GitHub Student (§14) |
| Rol de la instancia | `inventaio-staging-ec2` |
| Grupo de seguridad | `inventaio-staging-web` |
| Instancia | `inventaio-staging`, t3.medium con Amazon Linux 2023 |

## Avance

Las secciones 0 a 2 y el DNS (§5) se hacen antes del PR. Desde la §3, después de integrar el PR de INV-34 en `develop`.

- [x] Bucket y usuario del traslado (§0), 12-nov
- [x] Volcado inicial subido a `volcados/20261112-1526/`, 12-nov
- [x] IP elástica asignada (§4), 12-nov
- [x] Subdominios creados en DuckDNS (§5), 12-nov
- [ ] Límite de gasto y cuota de EC2 revisados (§0)
- [ ] Rol de la instancia (§1)
- [ ] Grupo de seguridad (§2)
- [ ] `inventaio-staging.duckdns.org` apuntando a `3.149.216.15` (§5)
- [ ] PR de INV-34 integrado en `develop` y workflow «Imágenes» en verde
- [ ] Instancia (§3) e IP asociada (§4)
- [ ] Instancia preparada (§7) y primer despliegue (§8)
- [ ] Bodega restaurada (§9), usuarios y cuenta de humo (§10)
- [ ] Despliegue con humo en verde (§11) y reversa probada (§12)
- [ ] Casos críticos y evidencia en Jira (§16)

## 0. Antes de empezar

- **Límite de gasto** (settings.aws.com → Billing → Spend limit): sin pausas activas. El control «Stop new resource launches» impediría crear la instancia.
- **Cuota de EC2:** en Service Quotas → Amazon EC2, busca «Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances». Debe ser al menos 2 vCPU.
- **Región:** Ohio, arriba a la derecha.

### Bucket del traslado (hecho el 12-nov)

En S3 → **Create bucket**:

1. **Tipo y nombre:** *General purpose*, con un nombre como `inventaio-staging-<sufijo>`, único en todo S3. Es el `<bucket>` de toda la guía; reemplázalo en los comandos y las políticas.
2. **Lo demás:** como viene. Revisa que diga *ACLs disabled*, *Block all public access* marcado y cifrado *SSE-S3*. Luego pulsa **Create bucket**.
3. **Regla de ciclo de vida:** en el bucket → pestaña **Management** → **Create lifecycle rule**:
    - nombre `expirar-volcados`;
    - alcance *Limit the scope… using one or more filters*, con el prefijo `volcados/`;
    - acción *Expire current versions of objects*, a los 30 días;
    - **Create rule**.

### Usuario del traslado y su llave (hecho el 12-nov)

Con este usuario subes el volcado desde tu equipo. Solo puede escribir en `volcados/`: el 12-nov se comprobó que no puede escribir fuera de esa carpeta ni leer.

1. IAM → Users → **Create user**: nombre `inventaio-volcados`, **sin** marcar el acceso a la consola. En permisos, *Attach policies directly* sin elegir ninguna. Pulsa **Create user**.
2. En el usuario: Permissions → Add permissions → **Create inline policy** → JSON. Pega esto y nómbrala `subir-volcados`:

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

3. En el usuario: Security credentials → **Create access key**, con el caso de uso *Command Line Interface (CLI)*. AWS muestra la llave y su secreto **una sola vez**: déjala en pantalla para el paso siguiente. No la pegues en el chat ni en el repositorio.
4. **En tu equipo (WSL):** agrega el perfil al final de los dos archivos, sin borrar lo que ya tienen:

```bash
nano ~/.aws/credentials
```

```ini
[inventaio-volcados]
aws_access_key_id = <la llave>
aws_secret_access_key = <el secreto>
```

```bash
nano ~/.aws/config
```

```ini
[profile inventaio-volcados]
region = us-east-2
```

5. **Comprobación:** imprime cuántos archivos hay en `volcados/` (con el bucket vacío, `0`):

```bash
~/venvs/inventaio/bin/python -c "import botocore.session as s; print(s.Session(profile='inventaio-volcados').create_client('s3').list_objects_v2(Bucket='<bucket>', Prefix='volcados/')['KeyCount'])"
```

## 1. Rol de la instancia

1. IAM → Roles → **Create role**.
2. Trusted entity: **AWS service**, caso de uso **EC2**. La consola crea también el *instance profile* con el mismo nombre, que es el que se elige en la §3.
3. Permisos: busca y marca `AmazonSSMManagedInstanceCore`.
4. Nombre: `inventaio-staging-ec2`. Pulsa **Create role**.
5. En el rol creado: Add permissions → **Create inline policy** → JSON. Pega esto y nómbrala `inventaio-staging`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ModeloDeVera",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:us-east-2::foundation-model/qwen.qwen3-32b-v1:0"
    },
    {
      "Sid": "LeerVolcados",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::<bucket>/volcados/*"
    }
  ]
}
```

6. **Comprobación:**
    - en la pestaña **Permissions** deben quedar dos políticas, `AmazonSSMManagedInstanceCore` e `inventaio-staging`;
    - en **Trust relationships**, el servicio `ec2.amazonaws.com`.

## 2. Grupo de seguridad

En EC2 → Security Groups → **Create security group**:

- **Nombre y red:** `inventaio-staging-web`, con la descripción «Staging de InventAI/o: solo HTTP y HTTPS», en la VPC por defecto.
- **Entrada:** dos reglas, HTTP (80) y HTTPS (443), cada una desde Anywhere-IPv4. **Sin SSH.**
- **Salida:** la que viene por defecto (todo).

## 3. Instancia (después del PR)

EC2 → Instances → **Launch instance**. La página tiene varias secciones; cambia solo lo de la tabla:

| Sección | Campo | Valor |
| --- | --- | --- |
| Name and tags | Name | `inventaio-staging` |
| Application and OS Images | AMI | **Amazon Linux 2023 AMI**, arquitectura 64-bit (x86) |
| Instance type | — | `t3.medium` |
| Key pair (login) | — | **Proceed without a key pair** |
| Network settings → **Edit** | VPC y subred | La VPC por defecto, sin preferencia de subred |
| | Auto-assign public IP | **Enable**: la instancia la necesita hasta asociar la elástica |
| | Firewall | *Select existing security group* → `inventaio-staging-web` |
| Configure storage | Volumen raíz | **30** GiB, **gp3**; en *Advanced*, **Encrypted: Encrypted** con la llave por defecto |
| Advanced details | IAM instance profile | `inventaio-staging-ec2` |
| | Termination protection | **Enable**, para no borrarla por error |
| | Metadata accessible | Enabled |
| | Metadata version | **V2 only (token required)** |
| | Metadata response hop limit | **2**: sin esto, los contenedores no ven el rol |

Revisa el resumen de la derecha y pulsa **Launch instance**. Espera a que *Instance state* diga *Running* y *Status check*, *2/2 checks passed*.

## 4. IP elástica

La IP `3.149.216.15` ya está asignada. Falta asociarla, después de lanzar la instancia:

1. EC2 → Elastic IPs → selecciona `3.149.216.15`.
2. Actions → **Associate Elastic IP address** → Resource type *Instance* → `inventaio-staging` → **Associate**.

La IP pública que la instancia tomó al arrancar se libera y queda la elástica. La IP elástica se cobra aunque la instancia esté apagada: US$3,65 al mes.

## 5. DNS

**DuckDNS (el de ahora).** En duckdns.org, en el renglón `inventaio-staging`, pon `3.149.216.15` en *current ip* y pulsa **update ip**. Como la IP elástica no cambia, no hace falta su programa de actualización. `inventaio.duckdns.org` queda reservado, apuntando a `127.0.0.1`. El token de la cuenta no se comparte ni se usa aquí.

Para comprobarlo desde tu equipo, `nslookup inventaio-staging.duckdns.org` debe dar `3.149.216.15`.

**Con el dominio de GitHub Student (cuando se active).** Reclámalo desde la oferta de Name.com en education.github.com/pack, con la extensión que esté disponible (.app, .dev…). En Name.com → My Domains → `<dominio>` → **Manage DNS Records**, crea este registro:

| Type | Host | Answer | TTL |
| --- | --- | --- | --- |
| A | `staging.inventaio` | `3.149.216.15` | 300 |

Después, el cambio de dominio en la instancia va por la §14.

**Último recurso: sslip.io.** `3-149-216-15.sslip.io` no pide registro, pero todos sus usuarios comparten el límite de certificados de Let's Encrypt, que se agotó en febrero de 2026.

## 6. Entrar a la instancia

1. En EC2 → Instances, selecciona `inventaio-staging` → **Connect** → pestaña **Session Manager** → **Connect**. Si aparece apagado, espera unos minutos: el agente tarda en registrarse.
2. Se abre una terminal en el navegador, como `ssm-user`. Pasa al usuario de trabajo:

```bash
sudo su - ec2-user
```

La sesión se cierra sola tras 20 minutos sin actividad; los comandos que siguen se pueden retomar en una sesión nueva.

## 7. Preparar la instancia (una sola vez)

```bash
sudo dnf install -y git
sudo mkdir -p /opt/inventaio && sudo chown ec2-user:ec2-user /opt/inventaio
git clone --branch develop https://github.com/ddelgadillod/InventaIO.git /opt/inventaio/repo
sudo bash /opt/inventaio/repo/despliegue/preparar_instancia.sh
exit
sudo su - ec2-user          # de nuevo, para entrar ya en el grupo docker
```

El clon va con `--branch develop` porque la rama por defecto del repositorio es `main`, que todavía no trae el despliegue.

`preparar_instancia.sh` instala Docker y Compose y crea el swap de 2 GB y las carpetas de `/opt/inventaio`. Al final muestra las versiones instaladas y debe decir «Compose habla con Docker: listo».

## 8. Primer despliegue

El tag es `sha-` más los 7 primeros caracteres del último commit de `develop`. El workflow «Imágenes» lo publica unos minutos después de cada merge.

```bash
cd /opt/inventaio/repo && git pull
TAG=sha-$(git rev-parse HEAD | cut -c1-7) && echo $TAG
DOMINIO=inventaio-staging.duckdns.org BUCKET_VOLCADOS=<bucket> bash scripts/desplegar_staging.sh $TAG --primera-vez
```

La primera vez, el script hace dos cosas más:
- genera `/opt/inventaio/estado/.env.prod` con secretos aleatorios, que no salen de la máquina;
- omite las pruebas de humo, porque todavía no hay bodega ni usuarios.

Caddy pide el certificado al arrancar y el script espera hasta 2 minutos a que HTTPS responda. Tarda unos 4 minutos en total, casi todo en bajar las imágenes. Si dice que no pudo bajar las imágenes, el workflow aún no termina: espera y repite.

## 9. Bodega

El volcado inicial ya está en el bucket (`20261112-1526`). En la instancia:

```bash
cd /opt/inventaio/repo
bash scripts/bd/restaurar_staging.sh 20261112-1526
```

Debe terminar con «PASÓ: 30 comprobaciones». La restauración tarda unos 5 minutos.

Para un volcado nuevo, en tu equipo (§15 para recargarlo en la instancia):

```bash
cd ~/InventaIO
export BD_RED=container:inventaio-db PGHOST=localhost PGUSER=inventaio_user PGDATABASE=inventaio
export PGPASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' .env)
bash scripts/bd/volcar.sh
~/venvs/inventaio/bin/python scripts/bd/subir_volcado.py ~/inventaio-volcados/<carpeta> --bucket <bucket>
```

## 10. Usuarios y cuenta de humo

```bash
docker exec -it inventaio-prod-api-1 python -m scripts.seed_usuarios --nube
```

Guarda las cinco claves en tu gestor: se muestran una sola vez y no van en Jira ni en el chat. Después, registra la cuenta de gerente para las pruebas de humo:

```bash
bash scripts/desplegar_staging.sh --configurar-humo     # pide el email y la clave, sin mostrarla
```

## 11. Despliegue con pruebas de humo

```bash
cd /opt/inventaio/repo
TAG=sha-$(git rev-parse HEAD | cut -c1-7)
bash scripts/desplegar_staging.sh $TAG
```

Debe terminar con «Humo: 8 de 8 pruebas en ok». La aplicación queda en `https://inventaio-staging.duckdns.org`: ábrela en el navegador y revisa que el login y la barra superior muestren `v2.x.x · <commit>`.

## 12. Reversa (una vez, para el DoD 5)

Hace falta un segundo tag: cualquier merge posterior a `develop` publica uno. Despliégalo como en la §11 (`git pull` y el `TAG` nuevo) y después:

```bash
bash scripts/desplegar_staging.sh --reversa
```

Vuelve al tag anterior y corre el humo otra vez. Para regresar al nuevo, el script muestra el comando.

## 13. Encender y apagar

- **Apagar y encender:** EC2 → Instance state → **Stop** o **Start**.
- **Al encender:** Docker levanta los contenedores solo, en unos 2 minutos. La IP y el DNS no cambian.
- **Costo:** encendida, ~US$1 al día. Apagada, ~US$6 al mes por el disco y la IP.

## 14. Cambiar de dominio

Por ejemplo, de DuckDNS al dominio de GitHub Student. Primero crea el registro A del nombre nuevo (§5) y comprueba que resuelva. Después:

```bash
DOMINIO=staging.inventaio.<dominio> bash scripts/desplegar_staging.sh "$(cat /opt/inventaio/estado/actual)"
```

Caddy pide el certificado del nombre nuevo y el humo se corre contra él.

## 15. Cargar un volcado nuevo

Por ejemplo, después de integrar las ventas de 2026. `restaurar_staging.sh` se niega si la bodega ya tiene datos (sale con 3), así que recargar es recrear la base. Eso borra también los usuarios del staging, que se crean otra vez con claves nuevas.

1. **En tu equipo:** vuelca y sube la bodega, como al final de la §9.
2. **En la instancia:**

```bash
cd /opt/inventaio/repo
docker rm -f inventaio-prod-postgres-1 && docker volume rm inventaio-prod_pgdata
bash scripts/desplegar_staging.sh "$(cat /opt/inventaio/estado/actual)" --primera-vez   # base vacía; .env.prod no cambia
bash scripts/bd/restaurar_staging.sh <carpeta-nueva>
```

3. **Usuarios y humo:** como en los §10 y §11.

## 16. Cierre: casos críticos y evidencia

**Casos críticos (CA 8).** Con cada rol, entra a `https://inventaio-staging.duckdns.org` y recorre los cinco casos, con una captura por caso:
- **Roles:** gerente, un administrador de sucursal y bodega, con las claves de la §10.
- **Casos:** login, una consulta, el pronóstico, las alertas con IA y una pregunta a Vera.

Las capturas no deben mostrar claves ni tokens.

**Evidencia por criterio**, para Jira:

| Criterio | Evidencia | Cómo sacarla |
| --- | --- | --- |
| CA 1 | Límite de gasto con avisos al 50, 75 y 90 % | Captura de la consola (§0) |
| CA 2 y DoD 3 | Solo Caddy publica puertos, y solo el 80 y el 443 | `docker ps --format '{{.Names}}\t{{.Ports}}'` y captura de las reglas del grupo de seguridad |
| CA 3 | Certificado de Let's Encrypt para el dominio | Desde tu equipo: `echo \| openssl s_client -connect inventaio-staging.duckdns.org:443 -servername inventaio-staging.duckdns.org 2>/dev/null \| openssl x509 -noout -issuer -dates` |
| CA 4 | Bodega restaurada y validada, sin puerto publicado | La salida de `restaurar_staging.sh` con «PASÓ: 30» y la de `docker ps` de arriba |
| CA 5 y DoD 5 | Despliegue por tag y reversa | La salida de la §11 y la de `--reversa` |
| CA 6 y DoD 2 | Versión y commit visibles | `curl -s https://inventaio-staging.duckdns.org/api/health` y capturas del login y la barra superior |
| CA 7 y DoD 4 | Humo automático en verde | La salida «Humo: 8 de 8» |
| CA 8 y DoD 4 | Casos críticos con los tres roles | Las capturas de arriba |
| CA 9 | Vera responde con el rol, sin llaves | La prueba `chat` del humo en ok y `grep -cE '^AWS_(ACCESS_KEY_ID\|SECRET_ACCESS_KEY)' /opt/inventaio/estado/.env.prod`, que debe dar `0` |
| DoD 6 | Despliegue, reversa y costo documentados | `docs/CI-CD.md`, sección «Despliegue a staging» |

**Al terminar:** en IAM → Users → `inventaio-volcados` → Security credentials, **desactiva** su llave de acceso. Se vuelve a activar si hay que subir otro volcado.
