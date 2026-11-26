# Conjunto `inv82` · Consultas compuestas de ventas

Son 15 preguntas para el análisis de ventas desde Vera. Este trabajo pasó de INV-82 a INV-72. Las preguntas cubren:
- el mismo mes en varios años, también como seguimiento de una conversación;
- el mejor y el peor periodo;
- un grupo de productos sumado, también con un error de escritura;
- la comparación con el año anterior;
- rankings de categorías y de sucursales;
- un año con periodos parciales;
- otra sucursal, sin permiso;
- dos controles: el ranking de productos y la pregunta por los años anteriores.

Usan los tres roles. Las preguntas 01 a 04 salen del reporte del bug, así que se vieron al diseñar y no cuentan como preguntas a ciegas.

- **Congelado** el 26-nov-2026, antes de medir. La huella está en la línea `meta` de cada corrida.
- **Uso:** contra el Core API con datos al 30-sep-2026 y venta sin IVA, es decir, staging recargado con la corrección de INV-82, y con la rama del análisis desplegada.
- **Hechos fuera del repositorio:** el repositorio es público y los hechos son ventas del negocio. Quedan en `hechos_inv82.json` (`{id: {hechos_reales, hechos_alguno_reales, prohibido}}`), en una carpeta privada. Se indica con `INVENTAIO_HECHOS_DIR`. Sin esa variable, el arnés no corre este conjunto. Las corridas también se guardan fuera del repositorio, con `--salida`.
- **Qué se califica:**
  - la herramienta y sus argumentos (`anios`, `grupo`, `por`, `comparar`…);
  - las cifras de los hechos;
  - el rechazo sin cifras de la otra sucursal;
  - que nunca diga que no hay historia.
- **Qué se revisa a mano:** lo que dicen las notas. Por ejemplo, que la conclusión vaya primero, que diga que buscó «arroz» y que no compare un año incompleto.
