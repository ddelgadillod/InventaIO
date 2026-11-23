# Conjunto `guia` · Guía de uso (aceptación)

Son 35 preguntas de «cómo hago» y «por qué esta cifra». Cada una lleva una o más secciones esperadas de la guía (Partes II y III). Responde al criterio 5 de la historia.

- **Congelado** el 18-nov-2026 (sha256 `8e4cac0b8888…`), antes de escribir el corpus (`docs/GUIA-USO.md`) y sus sinónimos, y antes de calibrar la búsqueda.
- **Qué se mide:**
  - **hit@3, sin modelo:** alguno de los 3 primeros fragmentos que devuelve la búsqueda con la pregunta es de una sección esperada. La meta es al menos 0,9. Lo mide una prueba del CI.
  - **Con el agente:** que use `buscar_en_glosario` y que la respuesta cite una sección esperada (criterio `cita`).
- **No se usa para ajustar.** Los sinónimos y los umbrales se calibran con `guia-dev`.
