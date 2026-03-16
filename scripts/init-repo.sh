#!/bin/bash
# ============================================================
# InventAI/o — Inicialización del repositorio Git
# Ejecutar una sola vez al crear el repo
# ============================================================

set -e

echo "🚀 Inicializando repositorio InventAI/o"

# 1. Crear estructura del monorepo
mkdir -p services/core-api
mkdir -p frontend
mkdir -p etl
mkdir -p database/migrations/versions
#mkdir -p ml/models ml/notebooks
#mkdir -p nlp-agent
#mkdir -p nginx
mkdir -p docs
mkdir -p data/raw data/processed
mkdir -p scripts

# 2. Inicializar git
git init
#git checkout -b main

# 3. Primer commit
git add .
git commit -m "chore: initial project structure

- Monorepo structure: services/, frontend/, etl/, database/, ml/, nlp-agent/
- Docker Compose with PostgreSQL 16 + Redis 7
- Star schema DDL (init.sql)
- ETL pipeline (4 steps)
- Environment configuration (.env.example)
- Documentation (Confluence + Jira test cases)"

# 4. Crear rama develop
git checkout -b develop
echo "✅ Rama develop creada desde main"

# 5. Tag inicial
git checkout main
git tag -a v0.0.0 -m "chore: project scaffolding"
git checkout develop

echo ""
echo "============================================================"
echo "✅ Repositorio inicializado"
echo ""
echo "Ramas:"
echo "  main    → código estable (solo releases)"
echo "  develop → integración de features"
echo ""
echo "Siguiente paso:"
echo "  git checkout -b feature/INV-001-setup-env"
echo "  # ... trabajar en la feature ..."
echo "  git add . && git commit -m 'feat(infra): configure dev environment'"
echo "  git checkout develop && git merge --squash feature/INV-001-setup-env"
echo "  git commit -m 'feat(infra): INV-001 configure dev environment'"
echo "  git branch -d feature/INV-001-setup-env"
echo "============================================================"
