# InventAI/o en Kubernetes (k3s)

Manifiestos del plan de staging en k3s con servicios serverless (`docs/INFRA-k3s-serverless-requerimientos.md`). Las imágenes son las mismas de GHCR que corren en compose; el código no cambia.

```
k8s/
├── base/                     lo común: los seis servicios, la configuración, las reglas de red y el espacio de nombres
│   ├── Caddyfile             Caddy detrás de CloudFront: cabecera secreta e IP real del visitante
│   └── nginx/                fragmentos que reemplazan a los de la imagen web: DNS del clúster e IP real
├── componentes/postgres/     PostgreSQL 16 dentro del clúster (staging y ci)
├── overlays/
│   ├── staging/              base + PostgreSQL en el clúster
│   ├── produccion/           base + RDS (Service ExternalName «postgres»)
│   └── ci/                   base + PostgreSQL, Caddy con su CA interna e imágenes locales con el tag «ci»
└── plantillas/               el Job de migración de cada despliegue y el pod de herramientas de la base
```

## Qué corre y cómo se protege

| Pieza | Objeto | Notas |
| --- | --- | --- |
| api, ml-service, nlp-agent, web | Deployment + Service | Sin root (uid 10001 o 101), sin capacidades, solo lectura y con sondas de salud. ml-service se actualiza con Recreate por memoria |
| Redis | Deployment + volumen | AOF en disco: la lista negra de tokens sobrevive a los reinicios |
| PostgreSQL | StatefulSet (staging y ci) o ExternalName a RDS (producción) | El esquema llega en el ConfigMap «inventaio-esquema» |
| Caddy | Deployment + Service LoadBalancer | ServiceLB de k3s publica el 80 y el 443. Abre esos puertos sin root con la sysctl `net.ipv4.ip_unprivileged_port_start=0`, que Pod Security considera segura: no hace falta `hostPort`, que el nivel «restricted» prohíbe |
| Reglas de red | NetworkPolicy | Niegan todo por defecto. Solo el agente llega a los metadatos de la máquina (rol de IAM para Bedrock) |
| Espacio de nombres | `inventaio` | Pod Security «restricted» |

**Lo que no está en el repositorio** lo crea `scripts/desplegar.sh` desde Parameter Store (`/inventaio/<ambiente>/…`):
- el Secret «inventaio-secretos», con `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` y `ORIGEN_SECRETO`;
- el nombre del origen (`DOMINIO`);
- en producción, el endpoint de RDS.

Las imágenes de la base llevan el tag `por-definir`, así que aplicar la base sin el script no baja nada.

**Conexión a la base:** el ConfigMap `inventaio-bd` tiene nombre fijo (sin el sufijo que Kustomize agrega a lo generado), porque lo usan también el Job de migración y el pod de herramientas, que se crean aparte.

## Validar sin clúster

```bash
kubectl kustomize k8s/overlays/staging | docker run --rm -i ghcr.io/yannh/kubeconform:v0.7.0 -strict -summary -
```

Hay que repetirlo con `produccion` y `ci`. La prueba con un clúster de verdad (k3d) es la fase 3.

## Desplegar (en la máquina, como ec2-user)

```bash
bash scripts/desplegar.sh <tag> --primera-vez   # sin humo: todavía no hay bodega ni usuarios
bash scripts/desplegar.sh <tag>                 # migración, servicios y humo; si falla, vuelve solo al tag anterior
bash scripts/desplegar.sh --reversa
```

Sale con 0, 1 o 2, igual que `scripts/desplegar_staging.sh`. Por eso el documento de Session Manager y el workflow «Desplegar» solo cambian de script en el corte (fase 5).

**Herramientas de la base:** con `BD_POD`, `scripts/bd/comun.sh` corre `psql`, `pg_dump` y `pg_restore` dentro del pod de herramientas, porque en k3s no hay Docker. Sin `BD_POD`, todo sigue con Docker, como en compose y en el CI.
