
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
</p>

---

## Descripción

InventAI/o es un sistema inteligente de consulta y soporte a la toma de decisiones para distribuidores de abarrotes pequeños y medianos en Colombia. Integra:

- **Bodega de datos analítica** con esquema estrella (PostgreSQL)
- **Modelos de Machine Learning** para predicción de demanda (LightGBM)
- **Agente conversacional NLP** basado en RAG (Llama 3.1)
- **PWA con interfaz chat-first** donde el agente entrega reportes, semáforos de inventario y recomendaciones directamente en la conversación

La aplicación no captura datos transaccionales; se especializa exclusivamente en análisis, predicción y recomendación.

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    PWA (React + TS)                  │
│        Chat IA  ·  Dashboard  ·  Configuración      │
├─────────────────────────────────────────────────────┤
│                  Core API (FastAPI)                   │
│     Auth · Consulta · Reportes · Alertas · NLP       │
├──────────┬──────────┬──────────┬────────────────────┤
│ PostgreSQL│  Redis   │ LightGBM │  Llama 3.1 (RAG)  │
│  (Bodega) │ (Caché)  │   (ML)   │     (Agente)      │
└──────────┴──────────┴──────────┴────────────────────┘
```

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 (esquema estrella) |
| API | FastAPI + Pydantic |

## Estructura del Repositorio

```
InventaIO/
├── database/
│   ├── init.sql              # DDL esquema estrella
│   └── verify.sql            # Script de verificación
├── etl/
│   ├── config.py             # Configuración + festivos Colombia
│   ├── paso_01_transformar.py
│   ├── paso_02_sinteticos.py
│   ├── paso_03_validar.py
│   ├── paso_04_cargar.py
│   └── run_pipeline.py       # Orquestador
├── docs/
│   ├── mockups/              # 7 pantallas HTML + demo navegable
│   └── brand/                # Prompts de diseño (Stitch, Nanobanana)
├── frontend/
│   └── public/               # Logos, favicons, avatares, OG image
├── docker-compose.yml        # PostgreSQL + Redis + pgAdmin
├── .env.example
├── CONTRIBUTING.md           # Branching + commits
└── README.md
```

## Inicio Rápido

```bash
# 1. Clonar y configurar
git clone https://github.com/ddelgadillod/InventaIO.git
cd InventaIO
cp .env.example .env

# 2. Levantar servicios
docker-compose up -d

# 3. Ejecutar ETL (requiere dataset Favorita en data/raw/)
cd etl
pip install -r requirements.txt
python run_pipeline.py

# 4. Verificar carga
docker-compose exec postgres psql -U inventaio_user -d inventaio -f /tmp/verify.sql
```

## Datos de la Bodega

| Métrica | Valor |
|---------|-------|
| Productos | 292 en 15 categorías |
| Sucursales | 3  |
| Proveedores | 10 con lead times 3–15 días |
| Ventas | 510,438 registros |
| Inventario | 1,470,804 registros |
| Periodo | 1,679 días |
| Festivos COL | 284 fechas (2010–2025, Ley Emiliani) |

## Metodología

**Scrum + CRISP-DM híbrido** — 44 historias de usuario, 4 releases, 11 sprints de 3 semanas.

| Release | Alcance | Sprints |
|---------|---------|---------|
| R1 | Bodega de datos + ETL + Frontend base | S1–S4 |
| R2 | Modelos ML (demanda, reposición) | S5–S7 |
| R3 | Agente NLP (RAG + Llama 3.1) | S8–S9 |
| R4 | Integración + evaluación + despliegue | S10–S11 |

## Diseño de Interfaces

La interfaz sigue un enfoque **chat-first**: el agente NLP es la pantalla principal. El usuario consulta inventario, ventas, alertas y recomendaciones a través de la conversación.


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

## Autor

**Diego Alejandro Delgadillo Durán** — Código 2508140-7729

Maestría en Computación para el Desarrollo de Aplicaciones Inteligentes
Universidad del Valle — 2026


## Licencia

Este proyecto es parte de un trabajo académico de maestría. Todos los derechos reservados.
