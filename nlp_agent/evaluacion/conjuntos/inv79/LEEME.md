# Conjunto `inv79` · Pronóstico para una fecha elegida

Son 8 preguntas para el pronóstico desde Vera con fecha (INV-79, con el contrato de INV-62):
- una fecha pasada, comparada con lo vendido;
- un día y un rango futuros, que son aproximados;
- un periodo con nombre;
- otra sucursal, sin permiso;
- una fecha fuera del calendario de la bodega;
- un control sin fecha.

Usan el producto P1632 y los tres roles.

- **Congelado** el 18-nov-2026 (sha256 `bf90ff2e44f6…`), antes de medir.
- **Uso:** solo contra el Core API con datos al 30-sep-2026, es decir, contra staging recargado, y con la rama de INV-62 desplegada.
- **Qué se califica:** la herramienta con `desde` (y `hasta` donde aplica), y el rechazo sin cifras en la de otra sucursal. Las notas dicen qué se revisa a mano: que diga lo vendido, que avise que es aproximado y que no invente cifras fuera del calendario.
