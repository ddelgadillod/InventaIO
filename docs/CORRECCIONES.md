# Registro de correcciones

Qué se encontró que no coincidía con el código o con los datos, y qué se hizo. Cada entrada lleva su fecha, dónde se detectó y en qué estado quedó. Una corrección que no toca el código, como la errata de un documento, también va aquí.

## 2026-10-08 · Después de la guía del sistema (Parte II)

La «Guía del sistema: de los pronósticos a las decisiones», continuación del documento «Metodología de tratamiento de datos y modelado de demanda» (Parte I), recalculó cada cifra contra el sistema en marcha y contra el repositorio. De ahí salió lo siguiente.

### Corregido

| # | Hallazgo | Corrección | Dónde |
| --- | --- | --- | --- |
| 1 | `docs/PREREGISTRO-HOLDOUT-2026.md` cita el commit `a340983`, que no existe: ni en GitHub, ni en el clon, ni en la copia anterior de Windows | Fe de erratas al final del documento y aviso al principio. Lo congelado se verifica por SHA-256: las huellas del JSON del prerregistro coinciden con los archivos de `models/` y con `models/SHA256SUMS`, y los cuatro archivos no han cambiado desde `e7bfe50`. El JSON y el run de MLflow no se tocan | `ce4cd42` |
| 2 | El comentario de `etl_real/construir_fact_inventario_real.py` decía 235 filas con stock negativo y la bodega tiene 220 | El 235 es correcto para el Excel (11.371 filas); a la bodega llegan 11.101 y, de las negativas, 220, porque 15 son de productos que no están en el catálogo. Comentario aclarado | `04b59c9` |
| 3 | El README describía un agente conversacional, un chat y una PWA en TypeScript que no existen, y los datos de la bodega simulada original | Reescrito según el estado actual: lo que funciona hoy y lo que está en el plan, arquitectura, stack, estructura, inicio rápido, datos de la bodega, metodología según los releases de Jira y diseño de interfaces | `74fdcd6` |
| 4 | Siete avisos de ESLint | Cuatro resueltos: `AuthProvider` ya no cambia el estado dentro del efecto, y la regla `react-refresh/only-export-components` acepta el contexto, su hook y `textoError`. Quedan tres, todos de `useConsulta` | `a22c4b3` |
| 5 | Jira: INV-24 «En curso» con los cinco criterios originales; INV-34 con «S3 para modelos y backups» y en el Release 3, que venció el 29 de septiembre; INV-41 sin sprint | INV-24 pasó a Finalizada con los criterios de `docs/INV-24-requerimientos.md`. INV-34 quedó con «S3 solo para copias de seguridad» y en el Release 4. INV-41 quedó en el Sprint 7, con INV-34, porque el hardening bloquea la exposición a internet | Jira |
| 6 | El ruleset de `main` se creó sin rama objetivo: estaba activo y no protegía nada | Se agregó *Include default branch*. Se verifica con las reglas efectivas de la API (ver `docs/CI-CD.md`) | GitHub y `7c53726` |
| 7 | `docs/INV-24-requerimientos.md` y `docs/CI-CD.md` decían «no verificado» y «pendiente» sobre lo que ya se había hecho | Actualizados con el estado real | `7c53726` |

Un primer análisis de la guía afirmó además que al prerregistro le faltaban las huellas SHA-256 de los modelos. Es incorrecto: están en `congelado.archivos_sha256` del JSON y coinciden con los archivos. Lo único que falla es la referencia al commit.

### Pendiente

| Tema | Dónde sigue |
| --- | --- |
| La Parte I (2.6) dice 219 filas con stock negativo; los conteos reproducibles son 235 (Excel) y 220 (bodega). Es un documento externo a este repositorio | Corregirlo en la versión 1.1 de la Parte I |
| Comprobar el run `preregistro_v1` de MLflow, que respalda la fecha del 25 de septiembre. No se pudo consultar: el servidor de MLflow no estaba disponible | Cuando el servidor esté disponible |
| `useConsulta`: `react-hooks/refs`, `react-hooks/set-state-in-effect` y `react-hooks/exhaustive-deps` | Refactor aparte, con sus pruebas de tiempos y cancelación |
| Seguridad antes de exponer el sistema: secretos por defecto, CORS abierto, `ml_service` sin autenticación y con el puerto 8001 publicado, lista negra de tokens en memoria, sin límite de intentos de acceso y usuarios de demostración visibles en el login | INV-41 (hardening) e INV-34 |
| Las excepciones de pip-audit de `ecdsa` y `python-jose` vencen el 2 de noviembre de 2026 y el CI falla ese día | Reemplazar `python-jose` por PyJWT, o renovarlas |
| PWA instalable: INV-10 figura finalizada en Jira, pero no hay manifiesto ni service worker | Decisión del negocio; hoy la aplicación se abre en el navegador |
| La etiqueta de urgencia de un producto a 5,03 días hábiles: Predicciones redondea y Recomendaciones no (HUEVOS en LA 21: «Urgente» y «Alta») | Decisión del negocio |
| Jira: las descripciones de los releases R2 y R3 no coinciden con las historias asignadas (INV-30 a INV-33 están en R2, cuya descripción no menciona el agente) y la fecha del R3 ya pasó | Replanear los releases |
