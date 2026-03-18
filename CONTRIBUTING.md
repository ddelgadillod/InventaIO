# Guía de contribución — InventAI/o

## Estrategia de ramas

### Ramas permanentes

| Rama | Propósito | Protegida |
|------|-----------|-----------|
| `main` | Código estable, releases tagueados | Sí |
| `develop` | Integración de features del sprint | Sí |

### Ramas temporales

| Patrón | Ejemplo | Origen | Destino |
|--------|---------|--------|---------|
| `feature/INV-xxx-descripcion` | `feature/INV-002-star-schema` | develop | develop |
| `hotfix/descripcion` | `hotfix/fix-db-connection` | main | main + develop |

### Convención de nombres

```
feature/INV-{número}-{descripcion-corta}
```

- Usar el código de la historia de Jira (INV-001, INV-002, etc.)
- Descripción en kebab-case, máximo 4 palabras
- Ejemplos:
  - `feature/INV-001-setup-env`
  - `feature/INV-002-star-schema`
  - `feature/INV-003-etl-pipeline`
  - `feature/INV-004-auth-module`

---

## Flujo de trabajo por historia de usuario

### 1. Crear la feature branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/INV-002-star-schema
```

### 2. Desarrollar con commits convencionales

```bash
# Trabajar en la feature...
git add .
git commit -m "feat(database): implement star schema DDL"

# Más trabajo...
git commit -m "feat(etl): add step 1 transform favorita data"

# Correcciones...
git commit -m "fix(etl): handle null values in unit_sales"
```

### 3. Mergear a develop

```bash
git checkout develop
git pull origin develop
git merge --squash feature/INV-002-star-schema
git commit -m "feat(database): INV-002 star schema implementation

- Star schema DDL with fact_ventas, fact_inventario
- 5 dimension tables: tiempo, producto, sucursal, proveedor, evento
- Optimized indexes for analytical queries
- Alembic migrations

Closes INV-002"

git push origin develop
git branch -d feature/INV-002-star-schema
```

### 4. Release (al final del bloque de sprints)

```bash
git checkout main
git merge develop
git tag -a v1.0.0 -m "release: v1.0.0 - Infraestructura + Bodega de Datos

Release 1 (Sprints 1-3):
- INV-001: Entorno de desarrollo
- INV-002: Esquema estrella
- INV-003: Datos sintéticos + ETL
- INV-004: Módulo Auth
- INV-005: Consulta de inventario
- INV-006: Módulo Reportes
- INV-007: Alertas de stock"

git push origin main --tags
git checkout develop
```

---

## Convención de commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/) con scopes del proyecto:

### Formato

```
<tipo>(<scope>): <descripción>

[cuerpo opcional]

[footer: Closes INV-xxx]
```

### Tipos

| Tipo | Cuándo usarlo |
|------|---------------|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `docs` | Solo documentación |
| `test` | Agregar o corregir tests |
| `refactor` | Cambio que no agrega feature ni corrige bug |
| `chore` | Mantenimiento (deps, CI, configs) |
| `perf` | Mejora de rendimiento |
| `style` | Formateo, espacios, puntos y comas |

### Scopes del proyecto

| Scope | Componente |
|-------|-----------|
| `infra` | Docker, CI/CD, configuración general |
| `database` | Schema, migraciones, DDL |
| `etl` | Pipeline ETL, datos sintéticos |
| `api` | Core API (FastAPI) |
| `auth` | Autenticación y RBAC |
| `frontend` | PWA React |
| `ml` | Modelos ML, LightGBM, MLflow |
| `nlp` | Agente NLP, RAG, Llama |
| `cloud` | AWS, despliegue |
| `docs` | Documentación |
| `test` | Pruebas |

### Ejemplos

```bash
feat(database): implement star schema with 5 dimensions
feat(etl): add synthetic price generation per category
feat(api): add GET /api/reportes/kpis endpoint
feat(auth): implement JWT login with role-based access
feat(frontend): create inventory dashboard with traffic light
feat(ml): train LightGBM demand forecasting model
feat(nlp): implement RAG agent with tool-calling
fix(etl): handle negative unit_sales as returns
fix(api): correct Redis cache invalidation on stock update
docs(database): add ER diagram to Confluence
test(api): add auth endpoint integration tests
chore(infra): upgrade PostgreSQL to 16.2
perf(etl): optimize chunk size for train.csv processing
```

---

## Releases y tags

| Tag | Release | Sprints | Contenido |
|-----|---------|---------|-----------|
| `v1.0.0` | R1 | 1-3 | Infraestructura + Bodega + Core API base |
| `v2.0.0` | R2 | 4-6 | API completa + Frontend PWA |
| `v3.0.0` | R3 | 7-9 | ML Predicción + NLP Agent + ML Dashboard |
| `v4.0.0` | R4 | 10-11 | Cloud + Pruebas + Producción |

---

## Checklist pre-merge

Antes de mergear una feature a develop:

- [ ] Código cumple criterios de aceptación de la HU
- [ ] Tests pasan (cobertura ≥ 80%)
- [ ] Sin bugs bloqueantes
- [ ] Documentación actualizada
- [ ] Self-review realizado
- [ ] Funcionalidad verificada en Docker Compose local
