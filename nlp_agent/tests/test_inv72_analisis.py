"""INV-72 (recibido de INV-82: decisiones 3 a 5, hallazgos H1 a H8) — El análisis de ventas de historial_ventas, la búsqueda
tolerante, las llamadas escritas como texto y la regla del verificador sobre la historia, contra el Core API simulado
(tests/core_falso.py, datos al 2025-12-31)."""
import pytest

from agente import entidades as ent
from agente.bucle import EjecutorCoreAPI, llamadas_en_texto
from agente.fidelidad import INICIO_RESPALDO, niega_historia, verificar
from herramientas import analisis
from herramientas.catalogo import POR_NOMBRE
from tests.test_bucle import Guion, correr, correr_verificado

H = POR_NOMBRE["historial_ventas"]


async def _historial(ctx, **argumentos):
    return await H.ejecutar(ctx, H.validar(argumentos))


# ── Parámetros y camino ─────────────────────────────

@pytest.mark.parametrize("argumentos, por, y_por", [
    ({"por": "anio,sucursal"}, "anio", "sucursal"),
    ({"por": ["año", "sucursales"]}, "anio", "sucursal"),
    ({"por": '["mes", "categoria"]'}, "mes", "categoria"),
    ({"por": "anio y sucursal"}, "anio", "sucursal"),
    ({"por": "Mes"}, "mes", None),
])
def test_dos_dimensiones_en_por(argumentos, por, y_por):
    p = H.validar(argumentos)
    assert (p.por, p.y_por) == (por, y_por)


@pytest.mark.parametrize("argumentos, es", [
    ({}, False), ({"dias": 90}, False), ({"periodo": "2025-11"}, False), ({"agrupacion": "semana"}, False),
    ({"agrupacion": "mes"}, True), ({"agrupacion": "anio", "dias": 400}, False), ({"por": "sucursal"}, True),
    ({"comparar": True}, True), ({"grupo": True, "producto": "arroz"}, True),
])
def test_cuando_va_al_analisis(argumentos, es):
    assert H.es_analisis(H.validar(argumentos)) is es


async def test_mismo_mes_en_varios_anios_por_sucursal(ctx, core_api):
    """H1: «los septiembre de los últimos 3 años por sucursal» en una llamada: septiembre es el de 2025 (datos al
    31-dic-2025), repetido en 2023, 2024 y 2025."""
    r = await _historial(ctx, periodo="septiembre", anios=3, por="anio", y_por="sucursal")
    assert core_api.params() == {"dimensiones": "anio,sucursal", "meses": "9", "anios": "2023,2024,2025", "orden": "natural"}
    m = r.para_modelo
    assert m["consulta"] == {"por": ["año", "sucursal"], "periodo": "septiembre de 2023 a 2025", "orden": "natural"}
    assert r.data["titulo"] == "Ventas por año y sucursal · septiembre de 2023 a 2025"
    assert m["historia_desde"] == "2022-01-02" and m["periodo_desde"] == "2023-09-01"
    # 9 filas de 1.000 a 9.000: la mayor es la última (2025 · GLORIETA) y la menor, la primera
    assert m["conclusiones"][1] == ("Más venta: 2025 · GLORIETA, $ 9.000 (20,0 % del total); menos venta: 2023 · PRINCIPAL, "
                                    "$ 1.000 (2,2 % del total).")
    assert "Variación de las ventas: GLORIETA: +200,0 % de 2023 a 2025; LA 21: +300,0 % de 2023 a 2025; PRINCIPAL: " \
           "+600,0 % de 2023 a 2025." in m["conclusiones"]
    assert "Mayor venta de cada sucursal: GLORIETA, 2025 ($ 9.000); LA 21, 2025 ($ 8.000); PRINCIPAL, 2025 ($ 7.000)." \
           in m["conclusiones"]
    g = r.data["grafico"]
    assert g["tipo"] == "barras" and [s["etiqueta"] for s in g["series"]] == ["GLORIETA", "LA 21", "PRINCIPAL"]
    assert [d["periodo"] for d in g["datos"]] == ["2023", "2024", "2025"]
    assert "nota" in m and "cantidad" not in r.data["filas"][0]       # sin producto: no se suman unidades


async def test_mejor_mes_de_un_producto_en_toda_la_historia(ctx, core_api):
    """H2 y H5: «en qué mes se vendió más»: por mes, orden cantidad, sobre toda la historia; la conclusión la da el código."""
    r = await _historial(ctx, producto="P618", por="mes", orden="cantidad")
    assert core_api.params() == {"dimensiones": "mes", "productos": "P618", "orden": "cantidad"}
    m = r.para_modelo
    assert m["filas"][0]["d_mes"] == "dic 2025" and m["consulta"]["orden"] == "cantidad de mayor a menor"
    assert m["conclusiones"][2].startswith("Más unidades: dic 2025, 120 unidades")
    assert r.data["grafico"]["tipo"] == "barras" and len(r.data["grafico"]["datos"]) == 12   # todas, en orden del tiempo
    assert [d["periodo"] for d in r.data["grafico"]["datos"]][:2] == ["ene 2025", "feb 2025"]


async def test_el_peor_primero(ctx, core_api):
    await _historial(ctx, por="sucursal", orden="valor", menor_primero=True)
    assert core_api.params()["ascendente"] == "true" and core_api.params()["orden"] == "valor"


async def test_grupo_de_productos_sumado(ctx, core_api):
    """H3: «todos los arroz carolina» se suman en una consulta, sin preguntar cuál."""
    r = await _historial(ctx, producto="arroz carolina", grupo=True, por="anio")
    assert core_api.params()["productos"] == "P618,P617,P615,P614"           # en el orden de la búsqueda
    m = r.para_modelo
    assert m["consulta"]["filtros"] == ["4 productos «arroz carolina»"]
    assert m["conclusiones"][-1].startswith("Se sumaron 4 productos: ARROZ CAROLINA")
    assert "nota" not in m and m["conclusiones"][0].endswith("unidades.")       # todos por unidad: se suman


async def test_grupo_sin_productos_no_inventa(ctx):
    r = await _historial(ctx, producto="xyzzy", grupo=True)
    assert r.para_modelo["resultado"] == "no_encontrado" and r.data is None


async def test_comparar_con_el_anio_anterior(ctx, core_api):
    r = await _historial(ctx, por="sucursal", periodo="2025-09", comparar=True)
    assert core_api.params()["comparar"] == "true"
    assert core_api.params()["fecha_inicio"] == "2025-09-01" and core_api.params()["fecha_fin"] == "2025-09-30"
    m = r.para_modelo
    assert m["filas"][0]["d_sucursal"] == "GLORIETA"                         # orden natural
    assert m["filas"][0]["variacion"] == "+25,0 %" and m["filas"][0]["valor_anterior"] == "$ 2.400"
    assert any(c.startswith("Frente al mismo periodo un año antes: ventas $ 6.000 contra $ 4.800 (+25,0 %)")
               for c in m["conclusiones"])
    assert [c.titulo for c in analisis.columnas(["sucursal"], False, True)][-2:] == ["Ventas un año antes", "Variación"]


async def test_por_producto_trae_los_20_de_mayor_venta(ctx, core_api):
    r = await _historial(ctx, por="producto", categoria="arroz")
    assert core_api.params()["orden"] == "valor" and core_api.params()["limite"] == "20"
    assert r.data["grafico"]["tipo"] == "barras_h" and r.para_modelo["filas"][0]["codigo"] == "P618"


async def test_los_ultimos_anios_sin_periodo_y_las_series_largas(ctx, core_api):
    r = await _historial(ctx, anios=2, por="mes")
    assert core_api.params()["anios"] == "2024,2025"
    assert r.data["grafico"]["tipo"] == "linea" and len(r.data["grafico"]["datos"]) == 24
    assert r.data["titulo"] == "Ventas por mes · 2024 a 2025"


async def test_etiquetas_con_el_periodo_en_palabras(ctx):
    """H7: «por año», no «anio»."""
    assert H.etiqueta(H.validar({"agrupacion": "semana", "dias": 30})) == "Historial de ventas · por semana"
    assert H.etiqueta(H.validar({"agrupacion": "anio"})) == "Ventas por año"
    assert H.etiqueta(H.validar({"por": "anio", "y_por": "sucursal", "sucursal": "GLORIETA"})) == \
        "Ventas por año y sucursal · GLORIETA"
    assert analisis.periodo_en_palabras(None, None, "2022-01-02", "2025-12-31") == "ene 2022 a dic 2025"
    assert analisis.periodo_en_palabras([7, 8, 9], [2025], "x", "y") == "julio, agosto y septiembre de 2025"


def _fila(sucursal, valor):
    return {"dimensiones": {"sucursal": sucursal}, "cantidad": 1.0, "valor_total": valor, "costo_total": valor * 0.85,
            "margen": valor * 0.15, "margen_pct": 15.0, "transacciones": 1}


def test_sin_sucursal_cuenta_en_el_total_pero_no_compite():
    """Las ventas sin terminal (SIN_SUCURSAL) no son «la sucursal que menos vende»."""
    filas = [_fila("PRINCIPAL", 3000.0), _fila("GLORIETA", 2000.0), _fila("SIN_SUCURSAL", 10.0)]
    d = {"filas": filas, "filas_totales": 3, "unidades_mixtas": True,
         "total": {"cantidad": 3.0, "valor_total": 5010.0, "costo_total": 4258.5, "margen": 751.5, "margen_pct": 15.0}}
    c = analisis.conclusiones(["sucursal"], d, None)
    assert c[0].startswith("Total: ventas $ 5.010")
    assert c[1] == "Más venta: PRINCIPAL, $ 3.000 (59,9 % del total); menos venta: GLORIETA, $ 2.000 (39,9 % del total)."
    assert c[-1].startswith("Las ventas sin sucursal asignada")
    assert analisis.texto_valor("sucursal", "SIN_SUCURSAL") == "Sin sucursal"


def _anio(anio, valor, dias):
    return {"dimensiones": {"anio": anio}, "cantidad": 1.0, "valor_total": valor, "costo_total": valor * 0.85,
            "margen": valor * 0.15, "margen_pct": 15.0, "transacciones": 1, "dias_con_ventas": dias}


def test_los_periodos_parciales_no_se_comparan():
    """2022 sin noviembre ni diciembre y 2026 hasta septiembre: «2026 frente a 2025 −25 %» no es una conclusión."""
    filas = [_anio("2022", 800.0, 300), _anio("2023", 1000.0, 360), _anio("2024", 1100.0, 362),
             _anio("2025", 1200.0, 361), _anio("2026", 900.0, 272)]
    d = {"filas": filas, "filas_totales": 5, "unidades_mixtas": True,
         "total": {"cantidad": 5.0, "valor_total": 5000.0, "costo_total": 4250.0, "margen": 750.0, "margen_pct": 15.0}}
    c = analisis.conclusiones(["anio"], d, None)
    assert "Más venta: 2025, $ 1.200 (24,0 % del total); menos venta: 2023, $ 1.000 (20,0 % del total)." in c
    assert "Periodos con datos parciales, fuera de las comparaciones: 2022 y 2026." in c
    assert "Variación de las ventas: +20,0 % de 2023 a 2025 (2024 frente a 2023 +10,0 %; 2025 frente a 2024 +9,1 %)." in c
    filas_texto = [analisis.fila_texto(f, ["anio"], False, None, False) for f in filas]
    assert [f["d_anio"] for f in filas_texto] == ["2022 (parcial)", "2023", "2024", "2025", "2026 (parcial)"]


def test_un_mes_con_un_dia_es_parcial_y_el_mismo_mes_en_varios_anios_cuenta_ese_mes():
    febrero = {"dimensiones": {"mes": "2023-02"}, "dias_con_ventas": 1}
    assert analisis.parcial(febrero, ["mes"]) and not analisis.parcial({**febrero, "dias_con_ventas": 27}, ["mes"])
    septiembre = {"dimensiones": {"anio": "2025", "sucursal": "LA 21"}, "dias_con_ventas": 30}
    assert not analisis.parcial(septiembre, ["anio", "sucursal"], [9])          # 30 de los 30 días de septiembre
    assert analisis.parcial(septiembre, ["anio", "sucursal"])                     # 30 de 365 días del año
    assert not analisis.parcial({"dimensiones": {"sucursal": "LA 21"}, "dias_con_ventas": 3}, ["sucursal"])
    assert analisis.dias_del_periodo("trimestre", "2024-T1") == 91              # bisiesto


def test_la_guarda_no_fuerza_dias_en_un_analisis():
    from datetime import date
    e = ent.Entidades(periodo=ent.Periodo("septiembre de 2025", date(2025, 9, 1), date(2025, 9, 30), "2025-09"))
    nuevos, hecho = ent.completar("historial_ventas", {"por": "sucursal", "periodo": "2025-09"}, e, date(2025, 12, 31))
    assert "dias" not in nuevos and not hecho
    nuevos, _ = ent.completar("historial_ventas", {"periodo": "2025-09"}, e, date(2025, 12, 31))
    assert nuevos["dias"] == 122                                # sin análisis, como antes


# ── Búsqueda tolerante (D5) ─────────────────────────

async def test_busqueda_tolerante_corrige_y_lo_dice(ctx, core_api):
    ejecutor = EjecutorCoreAPI(ctx)
    prep = ejecutor.preparar("historial_ventas", {"producto": "huebos", "por": "anio"})
    r = await ejecutor.ejecutar(prep)
    productos = [p for p in core_api.peticiones if p.url.path == "/api/consulta/productos"]
    assert dict(productos[0].url.params)["tolerante"] == "true"
    assert r.para_modelo["busqueda_corregida"] == "«huebos» no está en el catálogo: se buscó «huevos». Dilo en la respuesta."
    assert r.para_modelo["consulta"]["filtros"] == ["HUEVOS *UND"]


async def test_busqueda_por_palabras_con_la_palabra_corregida(ctx):
    """«arrox carolina 500»: la palabra larga se corrige y las demás se exigen con la corregida."""
    total, productos = await ctx.buscar_productos("arrox carolina 500")
    assert total == 1 and productos[0].codigo == "P618"
    assert ctx.correcciones == {"arrox carolina 500": "arroz carolina 500"}


# ── Llamadas escritas como texto (H6) ───────────────

@pytest.mark.parametrize("texto", [
    '{"name": "listar_sucursales", "arguments": {}}</tool_call>',
    '{"name": "listar_sucursales", "arguments": {}}',
    '<tool_call>{"name": "listar_sucursales", "arguments": {}}',
    '[{"name": "listar_sucursales", "arguments": {}}]',
])
def test_reconoce_la_llamada_sin_etiqueta_de_apertura(texto):
    assert [x.nombre for x in llamadas_en_texto(texto)] == ["listar_sucursales"]


@pytest.mark.parametrize("texto", ['{"nombre": "x"}', "Ventas de 2025: {total}", "[Ver la guía]"])
def test_no_confunde_texto_con_llamadas(texto):
    assert llamadas_en_texto(texto) is None


async def test_la_llamada_sin_apertura_se_ejecuta(ctx):
    llm = Guion('{"name": "listar_sucursales", "arguments": {}}</tool_call>', "Hay 4 ubicaciones.")
    eventos, r, _ = await correr(llm, ctx, "¿Qué sucursales hay?")
    assert r.llamadas_en_texto == 1 and r.texto.strip() == "Hay 4 ubicaciones." and "tool_call" not in r.texto


@pytest.mark.parametrize("verificado", [False, True])
async def test_en_la_ultima_ronda_la_llamada_escrita_no_llega(ctx, verificado):
    """H6: con las rondas agotadas, el modelo vuelve a escribir la llamada: va la respuesta de respaldo."""
    llamada = [("listar_sucursales", {})]
    escrita = '{"name": "historial_ventas", "arguments": {"por": "anio"}}'
    llm = Guion(llamada, llamada, llamada, escrita)
    _, r, _ = await (correr_verificado(llm, ctx) if verificado else correr(llm, ctx))
    assert "historial_ventas" not in r.texto and r.respaldo and r.llamadas_en_texto == 1
    assert r.texto.startswith(INICIO_RESPALDO) or r.texto.startswith("No hay datos")


# ── Verificador: la historia negada (H4) ────────────

RESULTADO = {"historia_desde": "2022-01-02", "periodo_desde": "2026-09-01", "filas": [{"valor": "$ 5.000"}]}


@pytest.mark.parametrize("texto, niega", [
    ("No hay datos de años anteriores; solo septiembre de 2026.", True),
    ("Solo tengo información de septiembre de 2026.", True),
    ("No tengo datos históricos de esa sucursal.", True),
    ("En septiembre de 2026 se vendieron $ 5.000.", False),
    ("No hay ventas en la Bodega Central: solo abastece.", False),
])
def test_niega_la_historia(texto, niega):
    assert (niega_historia(texto, [RESULTADO]) == "2022-01-02") is niega


def test_con_toda_la_historia_consultada_no_hay_falta():
    completo = {**RESULTADO, "periodo_desde": "2022-01-02"}
    assert niega_historia("No hay datos de años anteriores a 2022.", [completo]) is None


def test_la_correccion_dice_desde_cuando():
    v = verificar("No hay datos de años anteriores.", "", [RESULTADO], reglas_inv40=True)
    assert not v.ok and "hay ventas desde el 2 de enero de 2022" in v.correccion()
    assert verificar("No hay datos de años anteriores.", "", [RESULTADO]).niega_historia is None   # sin las reglas


# ── Arreglos tras la primera corrida de inv82 (26-nov) ──

async def test_con_anios_cada_anio_va_en_su_fila(ctx, core_api):
    """inv82-06: «agosto contra el año pasado por sucursal» con anios=2 y sin el año como dimensión sumaba los dos agostos
    por sucursal; ahora el año va primero."""
    await _historial(ctx, periodo="2025-08", anios=2, por="sucursal", comparar=True)
    assert core_api.params()["dimensiones"] == "anio,sucursal" and core_api.params()["anios"] == "2024,2025"
    assert "comparar" not in core_api.params()      # inv82-09: con el año como dimensión, la variación ya va entre años
    await _historial(ctx, anios=2, por="mes")                                  # el mes ya lleva el año
    assert core_api.params()["dimensiones"] == "mes"


def test_con_anios_y_dos_dimensiones_sin_el_anio_se_corrige():
    from herramientas.base import ErrorArgumentos
    with pytest.raises(ErrorArgumentos, match="por o y_por es anio"):
        H.validar({"por": "sucursal", "y_por": "categoria", "anios": 2})
    assert H.validar({"por": "sucursal", "y_por": "anio", "anios": 2}).y_por == "anio"


@pytest.mark.parametrize("texto, falla", [
    ("Sí, hay datos de ventas desde 2024. En 2024 se vendieron $ 5.000.", True),
    ("Tenemos registros desde el 1 de enero de 2024.", True),
    ("Los datos disponibles desde 2024 muestran un alza.", True),
    ("Sí, hay ventas desde 2022.", False),
    ("Las ventas de PRINCIPAL crecieron desde 2024.", False),
    ("PRINCIPAL tiene la mayor venta desde 2024.", False),
])
def test_afirmar_un_comienzo_posterior_es_negar_la_historia(texto, falla):
    assert (niega_historia(texto, [RESULTADO]) == "2022-01-02") is falla


async def test_comparar_se_mantiene_por_mes(ctx, core_api):
    await _historial(ctx, anios=2, por="mes", comparar=True)
    assert core_api.params()["comparar"] == "true"
    await _historial(ctx, por="anio", comparar=True)                            # toda la historia: varios años
    assert "comparar" not in core_api.params()
    await _historial(ctx, periodo="2025-T1", por="anio", y_por="trimestre", comparar=True)   # un solo periodo
    assert core_api.params()["comparar"] == "true"


def test_el_analisis_no_pide_el_total_de_filas():
    """inv82-b-05: las conclusiones del análisis cubren todas las filas; la lista de otra herramienta sí lo pide."""
    from agente.fidelidad import totales_omitidos
    analisis_ = {"total": 55, "mostrando": 24, "conclusiones": ["Total: …"], "filas": []}
    lista = {"total": 55, "mostrando": 10, "filas": []}
    assert totales_omitidos("El mejor mes fue mayo de 2025.", [analisis_]) == []
    assert totales_omitidos("Estos son los productos.", [lista]) == [55]


def _dos(anio, otra, valor_otra, valor):
    return {"dimensiones": {"anio": anio, otra: valor_otra}, "cantidad": 1.0, "valor_total": valor,
            "costo_total": valor * 0.85, "margen": valor * 0.15, "margen_pct": 15.0, "transacciones": 1, "dias_con_ventas": 90}


@pytest.mark.parametrize("otra, valores, nombre", [
    ("trimestre", ("2025-T1", "2026-T1"), "T1"),
    ("mes", ("2025-09", "2026-09"), "septiembre"),
])
def test_el_mismo_periodo_en_dos_anios_tiene_variacion(otra, valores, nombre):
    """inv82-b-02: por año y trimestre, el trimestre lleva el año («2025-T1»); la variación compara el T1 de cada año."""
    filas = [_dos("2025", otra, valores[0], 1000.0), _dos("2026", otra, valores[1], 1072.0)]
    d = {"filas": filas, "filas_totales": 2, "unidades_mixtas": True,
         "total": {"cantidad": 2.0, "valor_total": 2072.0, "costo_total": 1761.2, "margen": 310.8, "margen_pct": 15.0}}
    c = analisis.conclusiones(["anio", otra], d, None)
    assert f"Variación de las ventas: {nombre}: +7,2 % de 2025 a 2026." in c
    assert not any(x.startswith("Mayor venta de cada") for x in c)          # un solo trimestre o mes: nada que elegir


def test_el_respaldo_trae_las_conclusiones_del_analisis():
    """inv82-09: si el borrador no pasa la verificación, el respaldo empieza con las conclusiones del código."""
    from agente.fidelidad import respaldo
    datos = [{"titulo": "Ventas por año", "total": 3, "columnas": [{"titulo": "Año", "clave": "d_anio"}],
              "filas": [{"d_anio": "2024"}, {"d_anio": "2025"}, {"d_anio": "2026 (parcial)"}]}]
    resultados = [{"conclusiones": ["Total: ventas $ 5.000.", "Variación de las ventas: +6,7 % de 2024 a 2025."]}]
    texto = respaldo(datos, "2026-09-30", resultados)
    assert texto.startswith(INICIO_RESPALDO)
    assert texto.index("Variación de las ventas: +6,7 %") < texto.index("**Ventas por año**")
    assert "- Total" not in respaldo(datos, "2026-09-30")                      # sin resultados del análisis, como antes
