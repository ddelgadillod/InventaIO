# Pruebas de carga y de seguridad (INV-41)

Requerimientos y decisiones: `docs/INV-41-requerimientos.md`. Todo corre desde el equipo de desarrollo contra staging,
por CloudFront, como un usuario. Las claves salen de `~/.config/inventaio/claves-staging.json` y nunca van al
repositorio. Los resultados crudos quedan en `evidencias/inv41/`, que no se publica, y el resumen va en
`docs/INV-41-carga-y-seguridad.md`.

## Herramientas

- **k6** v2.3.0, como binario en `~/.local/bin/k6`. Se baja del release de GitHub y se verifica contra su lista de
  huellas:

  ```bash
  V=v2.3.0; gh release download $V -R grafana/k6 -p "k6-$V-linux-amd64.tar.gz" -p "k6-$V-checksums.txt"
  grep "k6-$V-linux-amd64.tar.gz" k6-$V-checksums.txt | sha256sum -c -
  tar -xzf k6-$V-linux-amd64.tar.gz && install -m 0755 k6-$V-linux-amd64/k6 ~/.local/bin/k6
  ```

- **OWASP ZAP** en Docker, la imagen estable de GHCR fijada por su huella en los scripts.

## Carga (`pruebas/carga/`)

| Comando | Qué hace |
| --- | --- |
| `bash pruebas/carga/correr.sh lectura 10` | 10 usuarios virtuales durante 5 min, más un login cada 2 s |
| `bash pruebas/carga/correr.sh lectura 20` | Igual, con 20: es el criterio 1 |
| `bash pruebas/carga/correr.sh lectura escalera` | Sube de 20 a 80, en pasos de 20 cada 3 minutos, y se corta sola con más del 5 % de errores: es el criterio 6 |
| `bash pruebas/carga/correr.sh vera` | 3 usuarios distintos conversan con Vera durante 5 min: es el criterio 2. Cuesta menos de US$0,10 en Bedrock |
| `bash pruebas/carga/correr.sh recorrido` | Una vuelta por cada pantalla, con renovación y cierre de sesión |

- **Navegación:** cada usuario virtual abre una pantalla cada 1 a 3 s. Abre el Dashboard con el inventario la mitad
  de las veces, Alertas (por reglas y con IA) un cuarto y Recomendaciones el otro cuarto.
- **Peticiones:** las de cada pantalla salen a la vez, como en el navegador.
- **Caché:** antes de medir, el guion calienta la caché de recomendaciones.
- **Umbrales:** p95 ≤ 2 s y 0 % de 5xx, por escenario.
- **Salida:** k6 sale con 99 si algún umbral no se cumple; el resumen queda igual.

**Métricas de la máquina.** Se sacan después de cada corrida, en AWS CloudShell, con las horas en UTC que imprime
`correr.sh`:

```bash
bash pruebas/carga/metricas_ec2.sh 2026-11-25T20:00:00Z 2026-11-25T20:06:00Z
```

Durante la corrida, el uso por pod se ve en la máquina, por Session Manager, con
`watch -n 15 kubectl top pods -n inventaio`.

## Seguridad (`pruebas/seguridad/`)

| Comando | Qué hace |
| --- | --- |
| `bash pruebas/seguridad/zap_baseline.sh` | Baseline de ZAP sobre la web pública, con la araña AJAX |
| `bash pruebas/seguridad/zap_api_pasivo.sh` | ZAP como proxy local: el recorrido de k6 pasa por él y ZAP revisa en pasivo cada respuesta de la API con sesión |
| `python3 pruebas/seguridad/resumen_zap.py evidencias/inv41/….json` | Resume un reporte por riesgo. Sale con 1 si hay alguna alerta alta |

Ninguno ataca: el escaneo activo está fuera de alcance.
