# Guía de contribución — InventAI/o

## Estrategia de ramas

### Ramas permanentes

| Rama | Propósito | Protegida |
|------|-----------|-----------|
| `main` | Código estable, releases tagueados | Sí: ruleset con PR obligatoria, los checks del CI, sin force-push ni borrado |
| `develop` | Integración de features del sprint | No: merge local y push; el CI corre después del push |

### Ramas temporales

| Patrón | Ejemplo | Origen | Destino |
|--------|---------|--------|---------|
| `feature/INV-xxx-descripcion` | `feature/INV-28-alertas-ml` | develop | develop |
| `fix/descripcion` | `fix/correcciones-guia-parte-ii` | develop | develop |
| `docs/descripcion` | `docs/politica-ramas` | develop | develop |
| `hotfix/descripcion` | `hotfix/fix-db-connection` | main | main + develop |

Cada historia de usuario tiene su propia rama `feature/`.

### Ramas en GitHub

Las **3 últimas ramas integradas en develop** también están en GitHub. Al hacer el
merge, la rama se sube con `git push -u origin <rama>`. Las que salen de esa
ventana no se borran del remoto, y ninguna rama se borra en local al integrarla.

Para ver cuáles son las 3 últimas:

```bash
git log develop --first-parent --merges --format='%s' \
  | sed -n "s/^Merge branch '\(.*\)' into develop$/\1/p" | awk '!visto[$0]++' | head -3
```

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

El merge conserva los commits de la rama (`--no-ff`, sin squash), y la rama no se
borra.

```bash
git checkout develop
git pull origin develop
git merge --no-ff feature/INV-28-alertas-ml
git push origin develop
git push -u origin feature/INV-28-alertas-ml   # ventana de las 3 últimas
```

Después del push, el CI y la publicación de imágenes corren sobre develop.

### 4. Release (al final del bloque de sprints)

`main` no acepta push directo: el release es una Pull Request de `develop` a `main`
en GitHub, que debe pasar los checks del CI. Después del merge de la PR se crea el tag:

```bash
git checkout main
git pull origin main
git tag -a v2.0.0 -m "release: v2.0.0 - API completa + Frontend PWA"
git push origin v2.0.0
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
| `v1.0.0` | R1 | 1-3 | Infraestructura + Bodega + Core API base + aplicación web (correcciones en `v1.0.1` y `v1.0.2`) |
| `v2.0.0` | R2 | 4-6 | Pronóstico + recomendaciones + alertas con IA + CI/CD + agente y chat Vera |
| `v3.0.0` | R3 | 7 | Primera versión en la nube (staging) |
| `v4.0.0` | R4 | 8 | Producción + PWA + Vera responde cómo usar la aplicación + pruebas con usuarios |
| `v5.0.0` | R5 | 9 | Validación y entrega |

Un release es una PR de `develop` a `main` (el ruleset de `main` no deja empujar) que se integra con **merge commit**, no con squash ni rebase, para que `main` y `develop` no se separen. Después se crea el tag sobre ese merge y se publica el GitHub Release con sus notas (`docs/releases/`).

---

## Checklist pre-merge

Antes de mergear una feature a develop:

- [ ] Código cumple criterios de aceptación de la HU
- [ ] Tests pasan (cobertura ≥ 80%)
- [ ] Sin bugs bloqueantes
- [ ] Documentación actualizada
- [ ] Self-review realizado
- [ ] Funcionalidad verificada en Docker Compose local
