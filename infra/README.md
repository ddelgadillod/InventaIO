# Infraestructura en AWS (OpenTofu)

La infraestructura del plan de staging en k3s con servicios serverless (`docs/INFRA-k3s-serverless-requerimientos.md`, fase 4). Se aplica desde AWS CloudShell con `despliegue/aws/tofu.sh`, sin llaves de AWS fuera de la cuenta (P11). El CI solo corre `tofu fmt` y `tofu validate`, sin credenciales (job «Infraestructura (OpenTofu)»).

```
infra/
├── modulos/ambiente/   lo de un ambiente; producción lo reutiliza en la fase 6
│   ├── maquina.tf      rol de la máquina, grupos de seguridad, EC2 con IMDSv2 de dos saltos, IP elástica
│   ├── web.tf          bucket privado, CloudFront (/* → S3, /api/* → la máquina), cabeceras de seguridad, secreto de origen
│   ├── parametros.tf   /inventaio/<ambiente>/origen-secreto, dominio-origen y url-publica
│   ├── monitoreo.tf    tema de SNS con el correo y seis alarmas de la máquina
│   ├── horario.tf      encendido y apagado con EventBridge Scheduler
│   ├── copias.tf       instantánea diaria del disco con Data Lifecycle Manager
│   ├── github.tf       permiso del rol de GitHub para publicar la web e invalidar CloudFront
│   └── arranque.sh.tftpl  primer arranque: clona el repositorio y corre despliegue/preparar_k3s.sh
└── staging/            el ambiente: backend, proveedores, variables e importación del rol existente
```

| Pieza | Qué queda |
| --- | --- |
| Máquina | `inventaio-staging-k3s`, t3.medium con Amazon Linux 2023, 30 GB gp3 cifrado, IMDSv2 con dos saltos (H21), sin el 22 ni el 6443 abiertos. El primer arranque instala k3s fijado por versión y SHA-256, el swap y el agente de CloudWatch |
| Entrada | El 443 solo desde la lista de CloudFront y el 80 abierto para el desafío de Let's Encrypt |
| Web | CloudFront con su nombre (`dxxxx.cloudfront.net`) mientras llega el dominio (P6). La CSP y HSTS salen de `frontend/nginx/cabeceras-seguridad.conf` |
| Rol de la máquina | `inventaio-staging-ec2`, el que ya existía: se adopta con bloques `import` y gana Parameter Store, el agente de CloudWatch y la escritura en `volcados/` |
| Avisos | Correo para el fallo del sistema (la recupera), el de la instancia (la reinicia), CPU, créditos de CPU, memoria y disco |
| Horario | Encendido de lunes a viernes a las 7:00 y apagado a las 23:00, hora de Bogotá |
| Copias | Una instantánea del disco cada día a las 22:30, guardada 7 días |

**Costo estimado de staging:** ~US$18 al mes, con la máquina encendida 264 horas. Mientras conviven la máquina de compose y la nueva, unos US$10 más.

## Aplicar staging, paso a paso

**Antes:** el PR de la fase 4 integrado en `develop`, porque el primer arranque clona esa rama.

1. **DuckDNS:** en duckdns.org, crea el subdominio `inventaio-origen-stg`. Por ahora con cualquier IP; su IP real se pone en el paso 6.
2. **CloudShell** (us-east-2): clona el repositorio, o actualízalo si ya está:
   ```bash
   git clone https://github.com/ddelgadillod/InventaIO.git && cd InventaIO      # o: cd InventaIO && git pull
   ```
3. **Variables privadas:** crea `infra/staging/privado.auto.tfvars`. Git lo ignora y no sale de CloudShell:
   ```hcl
   correo_avisos   = "tu correo"
   bucket_volcados = "el bucket del traslado (guía de staging, §0)"
   ```
4. **Plan:** `bash despliegue/aws/tofu.sh staging plan`.
   - La primera vez instala OpenTofu y crea el bucket del estado.
   - Revisa que diga **4 to import** (el rol, su perfil, su política y Session Manager) y **0 to destroy**.
   - Pégame solo la línea que empieza con `Plan:`. El resto trae ARN con el número de la cuenta.
5. **Aplicar:** `bash despliegue/aws/tofu.sh staging apply` y escribe `yes`. Tarda unos 5 minutos; CloudFront es lo más lento.
6. **Salidas y DuckDNS:** `bash despliegue/aws/tofu.sh staging output`.
   - En DuckDNS, pon `ip_elastica` como IP de `inventaio-origen-stg`.
   - `url_publica` es la dirección del staging nuevo.
7. **Correo:** acepta la suscripción que llega de AWS Notifications. Sin eso no llegan los avisos.
8. **Primer arranque:** EC2 → `inventaio-staging-k3s` → Conectar → Session Manager:
   ```bash
   sudo tail -n 8 /var/log/inventaio-preparar.log
   ```
   Debe terminar en «listo», con el nodo `Ready` y la memoria disponible.
9. **Cuenta de humo**, en CloudShell: el correo y la clave que hoy están en `/opt/inventaio/estado/humo.env` de la máquina de compose. Se guardan cifrados, sin pasar por el chat ni por el repositorio:
   ```bash
   read -r -p "Correo de la cuenta de humo: " e; read -r -s -p "Clave: " c; echo
   aws ssm put-parameter --name /inventaio/staging/humo-email --type SecureString --value "$e" --overwrite >/dev/null
   aws ssm put-parameter --name /inventaio/staging/humo-clave --type SecureString --value "$c" --overwrite >/dev/null
   unset e c
   ```

El traslado de la base, el primer despliegue, la web en S3 y el humo ampliado son la segunda parte de la fase 4.

## Reconstruir o cambiar

- **Cambiar algo:** se edita, pasa por un PR, y luego `plan` y `apply` desde CloudShell con `git pull`.
- **Reconstruir la máquina:** `bash despliegue/aws/tofu.sh staging apply -replace=module.ambiente.aws_instance.maquina`. El primer arranque deja k3s listo, y después se despliega el tag guardado en `/inventaio/staging/tag-actual`.
- **Una AMI nueva** no reemplaza la máquina por sí sola: `ami` y `user_data` están en `ignore_changes`.
