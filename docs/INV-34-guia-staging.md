# INV-34 · Guía del staging en AWS

Pasos para crear y desplegar el staging en la consola de AWS, en la región **us-east-2 (Ohio)**. Las decisiones están en `docs/INV-34-requerimientos.md` (parte 2). Los comandos de la instancia se corren en Session Manager, sin SSH. Reemplaza lo que va entre `<…>`.

## 0. Antes de empezar

- **Límite de gasto** (settings.aws.com → Billing → Spend limit): sin pausas activas. El control «Stop new resource launches» impediría crear la instancia.
- **Cuota de EC2:** en Service Quotas → Amazon EC2, busca «Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances». Debe ser al menos 2 vCPU.
- **Región:** Ohio, arriba a la derecha.
- **Dominio:** el de GitHub Student en Name.com, que se activa 72 horas después de la aprobación. Mientras tanto sirve DuckDNS (§5).
- **Imágenes:** el PR de INV-34 integrado en `develop` y el workflow «Imágenes» en verde. El `<tag>` es el `sha-xxxxxxx` del merge, o un `vX.Y.Z`.

## 1. Rol de la instancia

1. IAM → Roles → **Create role**.
2. Trusted entity: **AWS service**, caso de uso **EC2**.
3. Permisos: `AmazonSSMManagedInstanceCore`.
4. Nombre: `inventaio-staging-ec2`.
5. En el rol creado: Add permissions → **Create inline policy** → JSON. Reemplaza `<bucket>` por el bucket de la §7 de los requerimientos. Nombre de la política: `inventaio-staging`.

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

## 2. Grupo de seguridad

En EC2 → Security Groups → **Create security group**:

- **Nombre y red:** `inventaio-staging-web`, en la VPC por defecto.
- **Entrada:** HTTP (80) y HTTPS (443) desde Anywhere-IPv4. **Sin SSH.**
- **Salida:** la que viene por defecto (todo).

## 3. Instancia

EC2 → **Launch instance**:

| Campo | Valor |
| --- | --- |
| Name | `inventaio-staging` |
| AMI | Amazon Linux 2023 AMI, 64-bit (x86) |
| Instance type | `t3.medium` |
| Key pair | **Proceed without a key pair** |
| Network settings → Edit | VPC por defecto; Auto-assign public IP: Enable; grupo de seguridad existente `inventaio-staging-web` |
| Storage | 30 GiB, gp3, **Encrypted** |
| Advanced details → IAM instance profile | `inventaio-staging-ec2` |
| Advanced details → Metadata version | **V2 only (token required)** |
| Advanced details → Metadata response hop limit | **2**: sin esto, los contenedores no ven el rol |

## 4. IP elástica

En EC2 → Elastic IPs:

1. **Allocate Elastic IP address**.
2. Actions → **Associate**, con la instancia `inventaio-staging`.
3. Anota la IP: es la `<ip>` de los pasos que siguen.

La IP se cobra aunque la instancia esté apagada: US$3,65 al mes.

## 5. DNS

En los pasos que siguen, `<dominio-staging>` es el nombre que quede de esta sección.

**Con el dominio de GitHub Student.** Reclámalo desde la oferta de Name.com en education.github.com/pack, con la extensión que esté disponible (.app, .dev…). Después, en Name.com → My Domains → `<dominio>` → **Manage DNS Records**, crea este registro:

| Type | Host | Answer | TTL |
| --- | --- | --- | --- |
| A | `staging.inventaio` | `<ip>` | 300 |

El `<dominio-staging>` queda `staging.inventaio.<dominio>`.

**Mientras se activa el pack: DuckDNS.** Entra a duckdns.org con GitHub o Google, crea un subdominio (por ejemplo `inventaio-staging`) y pon `<ip>` en *current ip*. Como la IP elástica no cambia, no hace falta su programa de actualización. El `<dominio-staging>` queda `inventaio-staging.duckdns.org`; para pasar después al definitivo, ver §14.

**Último recurso: sslip.io.** `<ip-con-guiones>.sslip.io` (por ejemplo `3-14-15-92.sslip.io`) no pide registro, pero todos sus usuarios comparten el límite de certificados de Let's Encrypt, que se agotó en febrero de 2026.

Para comprobarlo desde tu equipo: `nslookup <dominio-staging>` debe dar `<ip>`.

## 6. Entrar a la instancia

1. En EC2, selecciona la instancia → **Connect** → **Session Manager** → **Connect**. Si el botón aparece apagado, espera unos minutos: el agente tarda en registrarse.
2. La sesión entra como `ssm-user`. Pasa al usuario de trabajo:

```bash
sudo su - ec2-user
```

## 7. Preparar la instancia (una sola vez)

```bash
sudo dnf install -y git
sudo mkdir -p /opt/inventaio && sudo chown ec2-user:ec2-user /opt/inventaio
git clone https://github.com/ddelgadillod/InventaIO.git /opt/inventaio/repo
sudo bash /opt/inventaio/repo/despliegue/preparar_instancia.sh
exit
sudo su - ec2-user          # de nuevo, para entrar ya en el grupo docker
```

`preparar_instancia.sh` instala Docker y Compose y crea el swap de 2 GB y las carpetas de `/opt/inventaio`. Al final muestra las versiones instaladas y debe decir «Compose habla con Docker: listo».

## 8. Primer despliegue

```bash
cd /opt/inventaio/repo && git pull
DOMINIO=<dominio-staging> BUCKET_VOLCADOS=<bucket> bash scripts/desplegar_staging.sh <tag> --primera-vez
```

La primera vez, el script hace dos cosas más:
- genera `/opt/inventaio/estado/.env.prod` con secretos aleatorios, que no salen de la máquina;
- omite las pruebas de humo, porque todavía no hay bodega ni usuarios.

Caddy pide el certificado al arrancar y el script espera hasta 2 minutos a que HTTPS responda. Tarda unos 4 minutos en total, casi todo en bajar las imágenes.

## 9. Bodega

1. **En tu equipo:** vuelca y sube la bodega, como en la §6 de los requerimientos (`volcar.sh` y `subir_volcado.py`).
2. **En la instancia:**

```bash
bash scripts/bd/restaurar_staging.sh <carpeta>     # la carpeta con fecha que creó volcar.sh
```

Debe terminar con «PASÓ: 30 comprobaciones». La restauración tarda unos 5 minutos.

## 10. Usuarios y cuenta de humo

```bash
docker exec -it inventaio-prod-api-1 python -m scripts.seed_usuarios --nube
```

Guarda las cinco claves en tu gestor: se muestran una sola vez. Después, registra la cuenta de gerente para las pruebas de humo:

```bash
bash scripts/desplegar_staging.sh --configurar-humo     # pide el email y la clave, sin mostrarla
```

## 11. Despliegue con pruebas de humo

```bash
bash scripts/desplegar_staging.sh <tag>
```

Debe terminar con «Humo: 8 de 8 pruebas en ok». La aplicación queda en `https://<dominio-staging>`.

## 12. Reversa (una vez, para el DoD 5)

Después de desplegar un segundo tag (cualquier merge posterior a `develop` publica uno):

```bash
bash scripts/desplegar_staging.sh --reversa
```

Vuelve al tag anterior y corre el humo otra vez.

## 13. Encender y apagar

- **Apagar y encender:** EC2 → Instance state → **Stop** o **Start**.
- **Al encender:** Docker levanta los contenedores solo, en unos 2 minutos. La IP y el DNS no cambian.
- **Costo:** encendida, ~US$1 al día. Apagada, ~US$6 al mes por el disco y la IP.

## 14. Cambiar de dominio

Por ejemplo, de DuckDNS al dominio de GitHub Student. Primero crea el registro A del nombre nuevo (§5) y comprueba que resuelva. Después:

```bash
DOMINIO=<dominio-staging-nuevo> bash scripts/desplegar_staging.sh "$(cat /opt/inventaio/estado/actual)"
```

Caddy pide el certificado del nombre nuevo y el humo se corre contra él.

## 15. Cargar un volcado nuevo

Por ejemplo, después de integrar las ventas de 2026. `restaurar_staging.sh` se niega si la bodega ya tiene datos (sale con 3), así que recargar es recrear la base. Eso borra también los usuarios del staging, que se crean otra vez con claves nuevas.

1. **En tu equipo:** vuelca y sube la bodega, como en el §9.
2. **En la instancia:**

```bash
cd /opt/inventaio/repo
docker rm -f inventaio-prod-postgres-1 && docker volume rm inventaio-prod_pgdata
bash scripts/desplegar_staging.sh "$(cat /opt/inventaio/estado/actual)" --primera-vez   # base vacía; .env.prod no cambia
bash scripts/bd/restaurar_staging.sh <carpeta-nueva>
```

3. **Usuarios y humo:** como en los §10 y §11.

## 16. Al cerrar INV-34

En IAM → Users → `inventaio-volcados` → Security credentials, **desactiva** su llave de acceso.
