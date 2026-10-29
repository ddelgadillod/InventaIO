## Historia de usuario

**Jira:** INV-XXX
**Épica:** EX — Nombre de la épica
**Sprint:** INVENTAIO Sprint X

## Descripción

<!-- Breve descripción de lo que hace esta PR -->

## Cambios realizados

<!-- Lista de cambios principales -->

## Criterios de aceptación verificados

- [ ] CA1: ...
- [ ] CA2: ...

## Definition of Done

- [ ] Código cumple todos los criterios de aceptación
- [ ] Pruebas unitarias con cobertura ≥ 80%
- [ ] Checks del CI en verde (CI e Imágenes)
- [ ] Pruebas de integración contra la bodega real en verde, en local: el CI no las corre porque la bodega no está en GitHub (ver `docs/CI-CD.md`)
  - `docker compose exec api pytest`
  - `cd ml_service && POSTGRES_HOST=localhost ~/venvs/inventaio/bin/python -m pytest`
- [ ] Self-review documentado
- [ ] Documentación técnica actualizada
- [ ] Funcionalidad verificada en Docker Compose local
- [ ] Sin bugs bloqueantes

## Capturas / evidencia

<!-- Screenshots, logs, o queries SQL que demuestren el funcionamiento -->

## Notas adicionales

<!-- Cualquier contexto extra para el reviewer -->
