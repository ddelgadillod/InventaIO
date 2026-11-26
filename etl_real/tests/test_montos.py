"""INV-82 — Montos del reporte en una sola base: venta sin IVA (D1) y costos imposibles imputados (D2), con datos de juguete.
Cada caso arma filas con la misma estructura del reporte del punto de venta (docs/INV-82-requerimientos.md, sección 6)."""
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import construir_dim_producto  # noqa: E402
import construir_fact_ventas  # noqa: E402
import montos  # noqa: E402

CAMPOS = ["archivo_origen", "codigo_producto", "nombre_producto", "sucursal", "fecha_venta", "cantidad", "valor_venta",
          "costo", "utilidad", "valor_iva"]


def fila(archivo, codigo, cantidad, venta, costo, iva, con_iva=True, fecha="2025-03-01", sucursal="NORTE"):
    """Una fila como las del reporte: con IVA, utilidad = venta − costo − IVA; sin IVA, venta − costo."""
    utilidad = venta - costo - iva if con_iva else venta - costo
    return {"archivo_origen": archivo, "codigo_producto": codigo, "nombre_producto": f"PRODUCTO {codigo}",
            "sucursal": sucursal, "fecha_venta": fecha, "cantidad": cantidad, "valor_venta": venta, "costo": costo,
            "utilidad": round(utilidad, 2), "valor_iva": iva}


def escribir(ruta: Path, filas: list[dict], campos=CAMPOS):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


class TestClasificarArchivos(unittest.TestCase):
    def test_cada_archivo_toma_la_regla_de_su_utilidad(self):
        filas = [fila("con.xlsx", "A", 1, 1190, 800, 190), fila("con.xlsx", "B", 2, 2000, 1500, 0),
                 fila("sin.xlsx", "A", 1, 1000, 800, 190, con_iva=False),
                 fila("sin_iva_alguno.xlsx", "C", 1, 500, 400, 0)]
        self.assertEqual(montos.clasificar_archivos(filas),
                         {"con.xlsx": montos.CON_IVA, "sin.xlsx": montos.SIN_IVA, "sin_iva_alguno.xlsx": montos.SIN_IVA})

    def test_un_archivo_mezclado_detiene_el_etl_y_se_nombra(self):
        filas = [fila("mezcla.xlsx", "A", 1, 1190, 800, 190), fila("mezcla.xlsx", "B", 1, 1000, 800, 190, con_iva=False)]
        with self.assertRaisesRegex(montos.ErrorMontos, "mezcla.xlsx"):
            montos.clasificar_archivos(filas)

    def test_una_fila_rara_entre_cien_no_cambia_el_tipo(self):
        filas = [fila("casi.xlsx", str(i), 1, 1190, 800, 190) for i in range(99)]
        filas.append({**fila("casi.xlsx", "X", 1, 1190, 800, 190), "utilidad": 5})   # no cumple ninguna regla
        self.assertEqual(montos.clasificar_archivos(filas), {"casi.xlsx": montos.CON_IVA})

    def test_con_menos_de_un_peso_de_iva_la_fila_no_decide(self):
        self.assertIsNone(montos.regla_de_fila(fila("x", "A", 1, 100, 80, 0.4)))


class TestVentaSinIvaYCostos(unittest.TestCase):
    TIPOS = {"con.xlsx": montos.CON_IVA, "sin.xlsx": montos.SIN_IVA}

    def test_con_iva_se_resta_y_sin_iva_queda_igual(self):
        self.assertEqual(montos.venta_sin_iva(fila("con.xlsx", "A", 1, 1190, 800, 190), self.TIPOS), 1000)
        self.assertEqual(montos.venta_sin_iva(fila("sin.xlsx", "A", 1, 1000, 800, 190, con_iva=False), self.TIPOS), 1000)

    def test_una_devolucion_en_negativo_queda_en_valor_absoluto(self):
        self.assertEqual(montos.venta_sin_iva(fila("con.xlsx", "A", -1, -1190, -800, -190), self.TIPOS), 1000)

    def test_costo_imposible_solo_con_venta_y_mas_de_tres_veces(self):
        self.assertTrue(montos.costo_imposible(1000, 3000.01))
        self.assertFalse(montos.costo_imposible(1000, 3000))
        self.assertFalse(montos.costo_imposible(0, 500))           # un obsequio no se imputa


class TestRazones(unittest.TestCase):
    def test_mediana_del_producto_y_luego_categoria_y_bodega(self):
        r = montos.Razones(categoria_de={"A": "Lácteos", "B": "Lácteos", "C": "Aseo"})
        for venta, costo in ((1000, 700), (1000, 800), (1000, 900), (1000, 99999)):   # la última no cuenta
            r.agregar("A", venta, costo)
        r.agregar("D", 1000, 500)
        self.assertEqual(r.razon("A"), (0.8, "producto"))
        self.assertEqual(r.razon("B"), (0.8, "categoria"))       # sin líneas válidas: las de su categoría
        self.assertEqual(r.razon("C"), (0.75, "bodega"))          # su categoría no tiene líneas: toda la bodega

    def test_sin_ninguna_linea_valida_no_inventa(self):
        with self.assertRaises(montos.ErrorMontos):
            montos.Razones().razon("A")


class TestConstruirConMontos(unittest.TestCase):
    """De punta a punta: construir_fact_ventas y el precio del catálogo con un reporte de juguete."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tidy = self.tmp / "ventas_tidy.csv"
        escribir(self.tidy, [
            fila("2025.xlsx", "A", 1, 1190, 800, 190, fecha="2025-03-01"),
            fila("2025.xlsx", "A", 2, 2380, 1600, 380, fecha="2025-03-02"),
            fila("2026.xlsx", "A", 1, 1000, 840, 190, con_iva=False, fecha="2026-03-01"),
            fila("2026.xlsx", "A", 1, 1000, 350000, 190, con_iva=False, fecha="2026-03-02"),   # costo imposible
            fila("2026.xlsx", "B", 1, 0, 300, 0, con_iva=False, fecha="2026-03-03"),           # obsequio
        ])
        escribir(self.tmp / "producto_proveedor.csv", [{"codigo_item": "A", "codigo_proveedor": "P1"}],
                 ["codigo_item", "codigo_proveedor"])
        escribir(self.tmp / "dim_producto.csv", [{"codigo_item": "A", "categoria": "Lácteos"}], ["codigo_item", "categoria"])
        self.parches = [mock.patch.object(config, "SALIDA_DIR", self.tmp),
                        mock.patch.object(config, "VENTAS_TIDY_CSV", self.tidy),
                        mock.patch.object(config, "PRODUCTOS_EXCLUIDOS_CSV", self.tmp / "no-existe.csv")]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        shutil.rmtree(self.tmp)

    def _leer(self, nombre):
        with open(self.tmp / nombre, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_la_venta_queda_sin_iva_y_el_costo_imposible_imputado(self):
        construir_fact_ventas.construir()
        filas = self._leer("fact_ventas.csv")
        self.assertEqual([float(f["valor_total"]) for f in filas], [1000, 2000, 1000, 1000, 0])
        self.assertEqual([f["costo_imputado"] for f in filas], ["False", "False", "False", "True", "False"])
        # Mediana del producto en sus líneas válidas, ya sin IVA: 0,8, 0,8 y 0,84
        self.assertEqual(float(filas[3]["costo_total"]), 800.0)
        self.assertEqual(float(filas[4]["costo_total"]), 300.0)        # el obsequio no se toca
        imputados = self._leer("costos_imputados.csv")
        self.assertEqual(len(imputados), 1)
        self.assertEqual((imputados[0]["codigo_item"], float(imputados[0]["costo_reporte"]), imputados[0]["origen_razon"]),
                         ("A", 350000.0, "producto"))

    def test_el_catalogo_toma_el_precio_sin_iva_de_la_ultima_venta_con_costo_valido(self):
        precios = construir_dim_producto.extraer_precio_costo_iva(self.tidy)
        # La última de A (2026-03-02) tiene el costo imposible: vale la del 2026-03-01
        self.assertEqual(precios["A"], {"precio_base": 1000.0, "costo_base": 840.0, "iva_pct": 19.0})


if __name__ == "__main__":
    unittest.main()
