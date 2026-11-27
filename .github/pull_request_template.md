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
  - contra la pila de pruebas (foto al 31-dic-2025): `bash scripts/bd/pila_pruebas.sh levantar`
  - `docker exec inventaio-api-dic2025 python -m pytest`, con `INVENTAIO_ESPERAS` para los montos privados
  - `cd ml_service && POSTGRES_HOST=localhost POSTGRES_DB=inventaio_dic2025 ~/venvs/inventaio/bin/python -m pytest`
- [ ] Self-review documentado
- [ ] Documentación técnica actualizada
- [ ] Funcionalidad verificada en Docker Compose local
- [ ] Sin bugs bloqueantes

## Capturas / evidencia

<!-- Screenshots, logs, o queries SQL que demuestren el funcionamiento -->

## Notas adicionales

<!-- Cualquier contexto extra para el reviewer -->
