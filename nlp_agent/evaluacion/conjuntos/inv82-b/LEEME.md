# Conjunto `inv82-b` · Confirmación de los arreglos del análisis de ventas

Son 8 preguntas nuevas para confirmar los arreglos de INV-72 que salieron de la primera corrida de `inv82` y de la regresión del v1 (26-nov-2026):
- un mes y un trimestre contra los del año anterior, también con el rol de sucursal;
- dos diciembres por sucursal y su variación;
- un ranking de sucursales por margen y uno de categorías;
- el histórico de un producto;
- desde cuándo hay ventas de una sucursal;
- un control: el ranking de productos sigue en `productos_mas_vendidos`.

Usan los tres roles. Ninguna se vio al diseñar los arreglos: el borrador se escribió antes de tocar el código.

- **Congelado** el 26-nov-2026, antes de medir los arreglos. La huella está en la línea `meta` de cada corrida.
- **Uso:** el mismo de `inv82`. Se corre contra el Core API con datos al 30-sep-2026 y venta sin IVA, es decir, contra staging.
- **Hechos fuera del repositorio:** quedan en `hechos_inv82-b.json`, en la carpeta privada de `INVENTAIO_HECHOS_DIR`. Salen de llamadas directas al Core API, no de la herramienta de Vera. Las corridas se guardan con `--salida`, también fuera del repositorio.
- **Qué se califica:** la herramienta y sus argumentos, las cifras de los hechos y las frases prohibidas.
- **Qué se revisa a mano:** lo que dicen las notas, por ejemplo que no sume dos años ni deduzca el comienzo de los datos de los años que consultó.
