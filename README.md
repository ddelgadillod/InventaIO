
<p align="center">
  <img src="frontend/public/logo/logo-icon.svg" alt="InventAI/o" width="80" height="80"/>
</p>

<h1 align="center">InventAI/o</h1>

<p align="center">
  <strong>Sistema Inteligente de Consulta y Gestión Logística para Distribuidores de Abarrotes</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.0.1-2563EB?style=flat-square" alt="Version"/>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://github.com/ddelgadillod/InventaIO/actions/workflows/ci.yml/badge.svg" alt="CI"/>
  <img src="https://github.com/ddelgadillod/InventaIO/actions/workflows/images.yml/badge.svg" alt="Imágenes"/>
</p>

---

## Descripción

InventAI/o es un sistema inteligente de consulta y soporte a la toma de decisiones para distribuidores de abarrotes pequeños y medianos en Colombia. La aplicación no captura datos transaccionales; se especializa exclusivamente en análisis, predicción y recomendación.

**Hoy funciona** (Release 2 en curso):

- **Bodega de datos analítica** con esquema estrella (PostgreSQL 16), cargada con las ventas reales de un distribuidor (enero de 2022 a diciembre de 2025) y una foto de su inventario físico al 31 de diciembre de 2025
- **Modelos de pronóstico de demanda** a 15 días hábiles (LightGBM), servidos por `ml_service`, que también calcula las **recomendaciones de traslado entre ubicaciones y de compra a proveedor**
- **Core API** (FastAPI) con autenticación JWT y tres roles: gerente, administrador de sucursal y administrador de bodega
- **Aplicación web** (React, Vite y Tailwind) con seis pantallas: Dashboard, Inventario, Alertas, Reportes, Predicciones y Recomendaciones
- **CI/CD** con GitHub Actions e imágenes de producción publicadas en GHCR (ver más abajo)

**Está en el plan** (el detalle vive en Jira, proyecto INV): un **agente conversacional** basado en RAG (un modelo Llama local con Ollama) con su pantalla de chat, y el despliegue en AWS. Hasta entonces la aplicación no tiene chat y se abre en el navegador; todavía no es una PWA instalable.

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│              Aplicación web (React + Vite)              │
│      Dashboard · Inventario · Alertas · Reportes ·      │
│              Predicciones · Recomendaciones             │
├─────────────────────────────────────────────────────────┤
│                    Core API (FastAPI)                   │
│        Auth · Consulta · Reportes · Alertas · ML        │
├────────────────────────────┬────────────────────────────┤
│    ml_service (FastAPI)    │       PostgreSQL 16        │
│    LightGBM · traslados    │     bodega con esquema     │
│         y compras          │        en estrella         │
└────────────────────────────┴────────────────────────────┘
```

Nginx sirve la aplicación y le pasa `/api` al Core API. El caché del Core API es en memoria; Redis está en el compose para cuando haya más de un servidor. Planeado: el agente conversacional (Ollama + RAG) y su chat.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 (esquema estrella) |
| API | FastAPI + Pydantic (Core API y servicio de pronóstico) |
| Modelos | LightGBM; MLflow para los experimentos |
| Aplicación web | React 18, Vite, Tailwind CSS y Recharts |
| Servidor web | Nginx (imagen sin root) |
| Contenedores | Docker Compose; imágenes de producción en GHCR |
| CI/CD | GitHub Actions, Trivy y Dependabot |
| Planeado | Agente conversacional (Ollama) y despliegue en AWS |

## Estructura del Repositorio

```
InventaIO/
├── api/                       # Core API (FastAPI): auth, consulta, inventario, reportes, alertas, ml
├── ml_service/                # Servicio de pronóstico: prediccion/, transferencias/, compras/
├── frontend/                  # Aplicación web (React + Vite): src/, Dockerfile, nginx.conf
├── database/
│   ├── init.sql               # DDL esquema estrella
│   └── test-dw-real.SQL       # Verificación de la bodega cargada
├── etl_real/                  # DW real (INV-60/61) -- ver etl_real/README.md
├── etl/                       # Pipeline del dataset simulado original (Favorita)
├── notebooks/                 # EDA + features + modelos (INV-14/15/17) y prerregistro
├── models/                    # Modelos de Nivel 1 serializados, con SHA256SUMS
├── docs/
│   ├── AMBIENTE-DESARROLLO.md # Cómo levantar todo desde cero
│   ├── CI-CD.md               # Pipeline, comandos locales y configuración del repositorio
│   ├── mockups/               # Pantallas HTML y demo navegable (diseño original)
│   └── INV-*.md               # Historias de usuario y decisiones documentadas
├── .github/                   # Workflows (ci.yml, images.yml), Dependabot y plantilla de PR
├── scripts/                   # Utilidades (prueba de tiempos de Nginx, init-repo)
├── docker-compose.yml         # PostgreSQL, Redis, pgAdmin, Core API, ml-service y web (perfil `web`)
├── docker-compose.verify.yml  # Comprobación de las imágenes de producción
├── requirements-dev.txt       # pytest, ruff y pip-audit con las versiones del CI
├── ruff.toml                  # Configuración de ruff de los tres servicios de Python
├── .env.example
├── CONTRIBUTING.md            # Branching + commits
└── README.md
```

`ml_service` carga y sirve los modelos de `models/` (INV-20). Los cuadernos de `notebooks/` son el pipeline de investigación y no forman parte del stack en ejecución; están documentados en `docs/INV-14-eda-resumen.md`, `docs/INV-15-feature-engineering.md` y `docs/INV-17-modelo-baseline.md`.

## Inicio Rápido

El ambiente de referencia es Ubuntu (en WSL2 si se trabaja desde Windows) con Docker. La guía completa, con requisitos y verificaciones, es [`docs/AMBIENTE-DESARROLLO.md`](docs/AMBIENTE-DESARROLLO.md). Los datos del negocio no están en el repositorio: se entregan por separado y se cargan en el paso 3.

```bash
# 1. Clonar y configurar
git clone https://github.com/ddelgadillod/InventaIO.git ~/InventaIO
cd ~/InventaIO
cp .env.example .env

# 2. Levantar la bodega
docker compose up -d postgres

# 3. Construir y cargar la bodega con los datos reales:
#    secciones 3 a 5 de docs/AMBIENTE-DESARROLLO.md (ETL de etl_real/ y cargar_postgres.py)

# 4. Levantar el servicio de pronóstico y el Core API
docker compose up -d --build ml-service api

# 5. Aplicación web en desarrollo (Node 22)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Cómo correr las pruebas y los controles del CI en local: [`docs/CI-CD.md`](docs/CI-CD.md).

## CI/CD

Dos workflows de GitHub Actions corren en cada PR y push a `develop` y `main`
(detalle, comandos locales y configuración del repositorio en
[`docs/CI-CD.md`](docs/CI-CD.md)):

- **CI** (`ci.yml`): sin datos reales.
  - En `api`, `ml_service` y `etl_real`: ruff, pruebas con cobertura mínima y auditoría de dependencias.
  - En el frontend: ESLint, Vitest, `npm audit` y el build.
  - El OpenAPI versionado y los SHA-256 de los modelos se comprueban.
- **Imágenes** (`images.yml`): las imágenes de producción de `api`, `ml-service` y `web`, sin root y con healthcheck.
  - Las escanea Trivy y verifica que arranquen sanas.
  - Las publica en `ghcr.io/ddelgadillod/inventaio-*` en `develop`, `main` y las etiquetas `vX.Y.Z`.

Las pruebas de integración contra la bodega real no corren en el CI, porque los
datos del negocio no están en GitHub: se corren en local antes de cada merge.
El despliegue en AWS es de INV-34.

## Datos de la Bodega

| Métrica | Valor |
|---------|-------|
| Productos | 4.449 en 33 categorías |
| Ubicaciones | 3 sucursales (PRINCIPAL, LA 21 y GLORIETA) y la Bodega Central |
| Proveedores | 10, simulados: los reportes de ventas no traen compras ni plazos |
| Ventas | 2.056.210 registros, del 2 de enero de 2022 al 31 de diciembre de 2025 |
| Inventario | 11.101 registros: una sola foto, al 31 de diciembre de 2025 |
| Calendario | 2.190 días (2022–2027) con 108 festivos de Colombia (Ley Emiliani) |

## Metodología

**Scrum + CRISP-DM**: cuatro releases y sprints de tres semanas. El plan y el avance viven en Jira (proyecto INV).

| Release | Alcance |
|---------|---------|
| R1 · MVP Operacional | Bodega de datos, Core API y pantallas básicas (publicada en abril de 2026) |
| R2 · Predictivo y Conversacional v1 | Modelos de pronóstico y servicio de predicción, recomendaciones de traslado y de compra, vistas de Predicciones y Recomendaciones, alertas con ML y CI/CD |
| R3 · Conversacional | Agente conversacional: RAG, herramientas y prompts por rol |
| R4 · Producción y Entrega | Despliegue en AWS, chat en la PWA, pruebas con usuarios reales, documentación y entrega |

## Diseño de Interfaces

Hoy la aplicación tiene seis pantallas (Dashboard, Inventario, Alertas, Reportes, Predicciones y Recomendaciones), con menú lateral y datos según el rol. El diseño original planteaba un enfoque **chat-first**, con el agente conversacional como pantalla principal; el chat llegará con el agente (ver «Descripción»).


> 📂 Demo navegable disponible en [`docs/mockups/inventaio-demo.html`](docs/mockups/inventaio-demo.html)

### Paleta de Colores

| Color | Hex | Uso |
|-------|-----|-----|
| 🔵 Blue 600 | `#2563EB` | Primario, botones, links |
| 🔷 Navy 900 | `#1E3A5F` | Sidebar, headings |
| 🟢 Teal 500 | `#14B8A6` | Acento, agente IA, FAB |
| ⬜ Slate 50 | `#F8FAFC` | Fondo general |

### Semáforo de Inventario (WCAG AA)

| Estado | Color | Icono | Significado |
|--------|-------|-------|------------|
| ✅ OK | `#16A34A` | ✓ | Cobertura > 7 días |
| ⚠️ Bajo | `#CA8A04` | ⚠ | Cobertura 3–7 días |
| 🔴 Crítico | `#DC2626` | ✕ | Cobertura < 3 días |
| 🟣 Inconsistencia | `#7008E7` | ◆ | Stock negativo en la foto: verificar el conteo |

## Autor

**Diego Alejandro Delgadillo Durán** — Código 2508140-7729

Maestría en Computación para el Desarrollo de Aplicaciones Inteligentes
Universidad del Valle — 2026


## Licencia

Este proyecto es parte de un trabajo académico de maestría. Todos los derechos reservados.
