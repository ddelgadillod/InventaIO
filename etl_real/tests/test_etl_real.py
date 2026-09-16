#!/usr/bin/env python3
"""
INV-60 — Pruebas unitarias del pipeline etl_real/.

Cubren las funciones puras (sin Postgres, sin los CSV completos de
producción) y la consistencia de los 3 CSV de decisión de negocio
(categoria_manual_override.csv, correccion_heuristica.csv,
productos_excluidos.csv) contra config.CATEGORIAS_OBJETIVO.

Para validar la carga completa contra una base real, ver
database/test-dw-real.SQL (mismo patrón que database/test-dw.SQL usa
para el dataset simulado) -- este archivo no reemplaza esa verificación,
la complementa a nivel de código.

Correr con: python -m unittest discover -s tests -v   (desde etl_real/)
"""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import calendario_utils  # noqa: E402
import clasificar_productos  # noqa: E402
import construir_dim_tiempo  # noqa: E402
import construir_dim_sucursal  # noqa: E402
from construir_fact_ventas import _float  # noqa: E402


def _escribir_csv_temp(fieldnames, filas):
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", newline="", encoding="utf-8-sig", delete=False
    )
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(filas)
    f.close()
    return Path(f.name)


class TestCalendarioUtils(unittest.TestCase):
    """Duplicado intencional de parse_ventas_dir.py (ver docstring del
    módulo) -- estas pruebas fijan el contrato para que un cambio
    accidental al copiar la lógica no pase inadvertido."""

    def setUp(self):
        self.path = _escribir_csv_temp(
            ["fecha", "nombre_festivo"],
            [
                {"fecha": "2025-01-01", "nombre_festivo": "Año Nuevo"},   # miércoles
                {"fecha": "2025-01-06", "nombre_festivo": "Reyes Magos"},  # lunes
                {"fecha": "2025-12-25", "nombre_festivo": "Navidad"},      # jueves
            ],
        )

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_cargar_festivos(self):
        festivos = calendario_utils.cargar_festivos(self.path)
        self.assertEqual(len(festivos), 3)
        self.assertEqual(festivos["2025-01-01"], "Año Nuevo")

    def test_puente_festivo_que_cae_lunes_marca_sabado_y_domingo(self):
        festivos = calendario_utils.cargar_festivos(self.path)
        puentes = calendario_utils.construir_dias_puente(festivos)
        # 2025-01-06 es lunes -> puente el sabado 2025-01-04 y domingo 2025-01-05
        self.assertIn("2025-01-04", puentes)
        self.assertIn("2025-01-05", puentes)

    def test_puente_festivo_que_no_cae_lunes_marca_solo_dia_anterior(self):
        festivos = calendario_utils.cargar_festivos(self.path)
        puentes = calendario_utils.construir_dias_puente(festivos)
        # 2025-12-25 es jueves -> puente solo el 2025-12-24
        self.assertIn("2025-12-24", puentes)
        self.assertNotIn("2025-12-23", puentes)


class TestClasificarProductos(unittest.TestCase):
    def test_keyword_conocida_devuelve_categoria_y_regla(self):
        categoria, regla = clasificar_productos.clasificar_categoria("HUEVOS AA *30 UND")
        self.assertEqual(categoria, "Huevos")
        self.assertEqual(regla, "HUEVO")

    def test_sin_match_cae_al_default_documentado(self):
        categoria, regla = clasificar_productos.clasificar_categoria("PRODUCTO INVENTADO ZZZ")
        self.assertEqual(categoria, config.DEFAULT_CATEGORIA)
        self.assertEqual(regla, "default_sin_match")

    def test_clasificar_unidad_medida(self):
        self.assertEqual(clasificar_productos.clasificar_unidad_medida("ARROZ *500GR"), "g")
        self.assertEqual(clasificar_productos.clasificar_unidad_medida("ACEITE *900ML"), "ml")
        self.assertEqual(clasificar_productos.clasificar_unidad_medida("GALLETA X UND"), "un")

    def test_cargar_csv_categoria(self):
        path = _escribir_csv_temp(
            ["codigo_producto", "categoria"],
            [{"codigo_producto": "P1", "categoria": "Lácteos"}],
        )
        try:
            mapa = clasificar_productos.cargar_csv_categoria(path)
            self.assertEqual(mapa, {"P1": "Lácteos"})
        finally:
            path.unlink(missing_ok=True)

    def test_cargar_csv_categoria_archivo_inexistente_devuelve_vacio(self):
        # No debe fallar si el CSV de override aun no existe (catalogo
        # nuevo sin revision manual todavia).
        mapa = clasificar_productos.cargar_csv_categoria(Path("/no/existe/nada.csv"))
        self.assertEqual(mapa, {})


class TestConstruirDimTiempo(unittest.TestCase):
    def test_ultimo_dia_mes_febrero_no_bisiesto(self):
        self.assertEqual(construir_dim_tiempo.ultimo_dia_mes(date(2025, 2, 10)), date(2025, 2, 28))

    def test_ultimo_dia_mes_diciembre(self):
        self.assertEqual(construir_dim_tiempo.ultimo_dia_mes(date(2025, 12, 1)), date(2025, 12, 31))

    def test_clasificar_temporada_navidad_cruza_anio(self):
        self.assertEqual(construir_dim_tiempo.clasificar_temporada(date(2025, 12, 15)), "navidad")
        self.assertEqual(construir_dim_tiempo.clasificar_temporada(date(2025, 1, 3)), "navidad")

    def test_clasificar_temporada_regular_fuera_de_ventanas_conocidas(self):
        self.assertEqual(construir_dim_tiempo.clasificar_temporada(date(2025, 9, 15)), "regular")


class TestConstruirFactVentas(unittest.TestCase):
    def test_float_convierte_valores_validos(self):
        self.assertEqual(_float("123.45"), 123.45)
        self.assertEqual(_float(10), 10.0)

    def test_float_devuelve_default_si_no_es_numero(self):
        self.assertEqual(_float(""), 0.0)
        self.assertEqual(_float(None), 0.0)
        self.assertEqual(_float("no-es-numero", default=-1.0), -1.0)


class TestConstruirDimSucursal(unittest.TestCase):
    def test_calcular_volumen_ignora_devoluciones_y_sucursales_desconocidas(self):
        path = _escribir_csv_temp(
            ["sucursal", "cantidad", "valor_venta"],
            [
                {"sucursal": "PRINCIPAL", "cantidad": "2", "valor_venta": "1000"},
                {"sucursal": "PRINCIPAL", "cantidad": "-1", "valor_venta": "-500"},  # devolucion, no cuenta
                {"sucursal": "OTRA_DESCONOCIDA", "cantidad": "5", "valor_venta": "9999"},
            ],
        )
        try:
            volumen = construir_dim_sucursal.calcular_volumen_por_sucursal(path)
            self.assertEqual(volumen.get("PRINCIPAL"), 1000.0)
            self.assertNotIn("OTRA_DESCONOCIDA", volumen)
        finally:
            path.unlink(missing_ok=True)


class TestConsistenciaCSVsDeNegocio(unittest.TestCase):
    """Los 3 CSV de decisión de negocio deben ser consistentes con
    config.CATEGORIAS_OBJETIVO -- si alguien agrega una categoría nueva en
    uno de los CSV sin agregarla a config.py, dim_producto.categoria
    quedaría con un valor fuera de la taxonomía documentada."""

    def _categorias_usadas(self, path: Path) -> set:
        if not path.is_file():
            return set()
        with open(path, newline="", encoding="utf-8-sig") as f:
            return {row["categoria"] for row in csv.DictReader(f)}

    def test_categoria_manual_override_usa_solo_categorias_validas(self):
        usadas = self._categorias_usadas(config.CATEGORIA_MANUAL_OVERRIDE_CSV)
        if not usadas:
            self.skipTest("categoria_manual_override.csv no presente en este checkout")
        invalidas = usadas - set(config.CATEGORIAS_OBJETIVO)
        self.assertEqual(invalidas, set(),
                          f"Categorías fuera de config.CATEGORIAS_OBJETIVO: {invalidas}")

    def test_correccion_heuristica_usa_solo_categorias_validas(self):
        usadas = self._categorias_usadas(config.CORRECCION_HEURISTICA_CSV)
        if not usadas:
            self.skipTest("correccion_heuristica.csv no presente en este checkout")
        invalidas = usadas - set(config.CATEGORIAS_OBJETIVO)
        self.assertEqual(invalidas, set(),
                          f"Categorías fuera de config.CATEGORIAS_OBJETIVO: {invalidas}")

    def test_categoria_manual_override_sin_codigos_duplicados(self):
        path = config.CATEGORIA_MANUAL_OVERRIDE_CSV
        if not path.is_file():
            self.skipTest("categoria_manual_override.csv no presente en este checkout")
        with open(path, newline="", encoding="utf-8-sig") as f:
            codigos = [row["codigo_producto"] for row in csv.DictReader(f)]
        duplicados = {c for c in codigos if codigos.count(c) > 1}
        self.assertEqual(duplicados, set(), f"Códigos duplicados en el override: {duplicados}")

    def test_productos_excluidos_tiene_columna_motivo(self):
        path = config.PRODUCTOS_EXCLUIDOS_CSV
        if not path.is_file():
            self.skipTest("productos_excluidos.csv no presente en este checkout")
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            self.assertIn("motivo", reader.fieldnames)
            for row in reader:
                self.assertTrue(row["motivo"].strip(), f"Fila sin motivo: {row}")


if __name__ == "__main__":
    unittest.main()
