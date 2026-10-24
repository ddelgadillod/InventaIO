"""
Mejoras del desempeño en el bucle (INV-33, §3f de docs/INV-33-requerimientos.md, decisiones del 23-oct).

Con un modelo de 8B, las reglas del prompt no generalizaron (holdout del 23-oct): las decisiones se sacan del
modelo y se toman aquí, en código determinista y medible. Cada una va con su interruptor (`MEJORAS`):

- `argumentos` (P1): quita los filtros opcionales que la pregunta no nombra (con sinónimos por valor) y las
  llamadas que quedan repetidas (una por sucursal sin que se pidieran, H7).
- `agrupacion` (P6): «histórico», «por año» o «años anteriores» en `historial_ventas` sin periodo → agrupación
  por año (o por trimestre, si lo dice).
- `aclaracion` (P2): si la ronda solo trae resultados «ambiguo», el bucle pregunta cuál, con las opciones; y si el
  modelo pregunta «¿cuál?» sin nombrar las opciones que trajo la herramienta, la pregunta se arma con ellas.
- `sin_datos` (P3): si las herramientas no trajeron nada y la respuesta afirma contenido, se reintenta.
- `seguir` (P4): si la respuesta solo ofrece consultar algo y quedan rondas, el bucle contesta «sí» una vez.
- `razonar` (P7, experimento): el reintento del verificador va con razonamiento.

Correcciones del 24-oct (§3g), también con interruptor: `periodo` (C1), `categoria` (C2 y C3), `cobertura` (C4),
`glosario` (C5), `meses` (C6), `relleno` (C7), `totales` (C8) y `busqueda` (C9). Las de la guarda están aquí; las
de las herramientas las leen con `Contexto.activa`.

Los textos que mira la guarda son los mensajes del usuario de la conversación (sin los automáticos).
"""
import re
from dataclasses import dataclass, fields

from herramientas.contexto import normal

MARCA_AUTOMATICA = "("        # «(Verificación automática) …», «(Continuación automática) …»
CONTINUAR = "(Continuación automática) Sí, consúltalo y responde la pregunta completa con esos datos."
TODAS = ("catalogo", "argumentos", "agrupacion", "aclaracion", "sin_datos", "seguir")   # P7 es un experimento aparte
ACTIVAS_23OCT = ("catalogo", "argumentos", "agrupacion", "aclaracion", "sin_datos")     # la regla del 23-oct
CORRECCIONES = ("periodo", "categoria", "cobertura", "glosario", "meses", "relleno", "totales")   # C9 aparte
# La regla preregistrada sobre la serie del 24-oct (91 preguntas): C1 y C9 apagadas
ACTIVAS_24OCT = ACTIVAS_23OCT + ("categoria", "cobertura", "glosario", "meses", "relleno", "totales")


@dataclass(frozen=True)
class Mejoras:
    argumentos: bool = False
    agrupacion: bool = False
    aclaracion: bool = False
    sin_datos: bool = False
    seguir: bool = False
    razonar: bool = False
    # Correcciones del 24-oct (§3g)
    periodo: bool = False
    categoria: bool = False
    cobertura: bool = False
    glosario: bool = False
    meses: bool = False
    relleno: bool = False
    totales: bool = False
    busqueda: bool = False
    entidades: bool = False          # alternativa 1 (24-oct): agente/entidades.py
    # Los cambios del 23-oct que no tenían interruptor (P5 cobertura en el pronóstico, P6 destino y origen, la
    # ambigüedad del inventario y la oferta de P3 en el prompt). Las corridas del 23 y 24-oct los tenían siempre
    catalogo: bool = False

    @classmethod
    def desde_texto(cls, texto: str | None) -> "Mejoras":
        """«todas», «ninguna», «activas» (las del 23-oct), «correcciones» (C1 a C8), «final» (la regla del 24-oct) o
        los nombres separados por coma."""
        nombres = {n.strip() for n in (texto or "").split(",") if n.strip()}
        for grupo, incluye in (("todas", TODAS), ("activas", ACTIVAS_23OCT), ("correcciones", CORRECCIONES),
                               ("final", ACTIVAS_24OCT)):
            if grupo in nombres:
                nombres = (nombres - {grupo}) | set(incluye)
        validos = {f.name for f in fields(cls)}
        if desconocidos := nombres - validos - {"ninguna"}:
            raise ValueError(f"Mejoras desconocidas: {', '.join(sorted(desconocidos))}; válidas: {', '.join(sorted(validos))}")
        return cls(**{n: True for n in nombres & validos})

    def como_texto(self) -> str:
        return ",".join(f.name for f in fields(self) if getattr(self, f.name)) or "ninguna"


def texto_usuario(mensajes: list[dict]) -> str:
    """Lo que escribió el usuario en la conversación, normalizado; sin los mensajes automáticos del bucle."""
    return normal(" ".join(m["content"] for m in mensajes if m.get("role") == "user" and isinstance(m.get("content"), str)
                           and not m["content"].startswith(MARCA_AUTOMATICA)))


# P1: cuándo la pregunta nombra cada valor de un filtro opcional (raíces normalizadas, sin acentos)
SUCURSALES = {"PRINCIPAL": ("principal",), "LA 21": ("21", "la21"), "GLORIETA": ("glorieta",),
              "BODEGA_CENTRAL": ("bodega", "cedi", "centro de distribucion")}
VALORES = {
    "urgencia": {"urgente": ("urgent", "prioritar", "inmediat"), "alta": ("alta", "prioritar"), "normal": ("normal",),
                 "vigilancia": ("vigila",), "critica": ("critic",), "media": ("media",)},
    "estado": {"ok": ("ok ", "bien", "verde"), "bajo": ("bajo", "baja", "poco", "amarill"),
               "critico": ("critic", "rojo", "agotad", "agotan", "quiebre"), "inconsistencia": ("inconsisten", "negativ")},
    "tipo": {"stock_critico": ("critic", "agot"), "stock_bajo": ("bajo", "baja"),
             "sin_movimiento": ("sin movimiento", "no se mueve", "quiet", "estancad", "sin venta"),
             "rotacion_baja": ("rotacion",), "inconsistencia_inventario": ("inconsisten", "negativ"),
             "riesgo_desabastecimiento_ml": ("agot", "desabastec", "riesgo", "quiebre"),
             "sobrestock_previsto_ml": ("sobrestock", "exceso", "sobra")},
    "origen": {"reglas": ("regla",),
               "ia": ("ia ", "inteligencia", "predic", "pronost", "modelo", "agot", "riesgo", "sobrestock", "desabastec")},
    "agrupacion": {"quincena": ("quincen", "15 dias", "quince dias"), "semana": ("seman",), "mes": ("mes", "mensual"),
                   "trimestre": ("trimestr",), "anio": ("ano", "anos", "anual", "histori", "anio")},
}
LUGARES = ("sucursal", "destino", "origen")
DIAS = re.compile(r"\b\d+\s*(dias|semanas|meses)\b|\bultim|\bpasad|\breciente|\beste mes\b|\besta semana\b|\bmes\b")
HISTORICO = re.compile(r"\bhistori|\bpor ano\b|\banos\b|\banual|\banteriores\b")
# C6: un mes o un año nombrados son un periodo; «urgencia» es «urgente»
NOMBRES_MES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
               "noviembre", "diciembre")
MESES = re.compile(r"\b(" + "|".join(NOMBRES_MES) + r"|setiembre)\b")
ANIO = re.compile(r"\b20\d\d\b")
# C7: valores que no filtran nada
RELLENO = {"todo", "todos", "todas", "cualquiera", "cualquier", "general", "all", "n a", "ninguno", "varios"}


def _nombra(texto: str, raices) -> bool:
    """Cada raíz, al comienzo de una palabra; con un espacio al final («ia »), la palabra completa."""
    return any(re.search(rf"\b{re.escape(r)}", texto + " ") for r in raices)


def _nombra_categoria(texto: str, categoria: str) -> bool:
    """«aseo hogar», «licor» por «Licores»: alguna palabra de la categoría (por su raíz de 5 letras)."""
    return any(re.search(rf"\b{re.escape(p[:5])}", texto) for p in normal(categoria).split() if len(p) >= 4)


def _extra(nombre: str, valor: str, texto: str) -> bool:
    """C6: lo que P1 no reconocía: «urgencia» por urgente, un mes nombrado por la agrupación mensual, un año."""
    if nombre == "urgencia" and valor == "urgente":
        return re.search(r"\burgen", texto) is not None
    if nombre == "agrupacion" and valor == "mes":
        return MESES.search(texto) is not None
    if nombre == "agrupacion" and valor in ("anio", "trimestre"):
        return ANIO.search(texto) is not None
    return False


def _sin_relleno(herramienta: str, argumentos: dict, correcciones: list[str]) -> None:
    """C7: «producto: todo» no filtra nada, y un destino en lista se toma por el primero."""
    for nombre, valor in list(argumentos.items()):
        if isinstance(valor, list):
            primero = next((v for v in valor if isinstance(v, str) and v), None)
            if primero is not None and (nombre in LUGARES):
                argumentos[nombre] = primero
                correcciones.append(f"{nombre}={valor} (se toma {primero})")
            else:
                del argumentos[nombre]
                correcciones.append(f"{nombre}={valor} (una lista no es un filtro)")
        elif isinstance(valor, str) and nombre in ("producto", "texto", "categoria") and normal(valor) in RELLENO:
            del argumentos[nombre]
            correcciones.append(f"{nombre}={valor} (no es un filtro)")


def _periodo_inventado(argumentos: dict, correcciones: list[str]) -> None:
    """C1: el modelo inventaba `anio` (y `mes`) en historial_ventas; son el `periodo`."""
    anio = argumentos.pop("anio", None) or argumentos.pop("año", None)
    mes = argumentos.pop("mes", None)
    if anio is None or not str(anio).isdigit() or argumentos.get("periodo"):
        if anio is not None or mes is not None:
            correcciones.append("anio/mes sin periodo válido (se quitan)")
        return
    periodo = str(anio)
    numero = mes if isinstance(mes, int) else (NOMBRES_MES.index(normal(mes)) + 1 if isinstance(mes, str) and normal(mes)
                                                in NOMBRES_MES else int(mes) if isinstance(mes, str) and mes.isdigit() else None)
    if numero and 1 <= numero <= 12:
        periodo += f"-{numero:02d}"
    argumentos["periodo"] = periodo
    correcciones.append(f"anio={anio}{f', mes={mes}' if mes is not None else ''} → periodo={periodo}")


def corregir_argumentos(herramienta: str, argumentos: dict, texto: str, filtros: bool = True,
                        agrupacion: bool = False, meses: bool = False, relleno: bool = False,
                        periodo: bool = False) -> tuple[dict, list[str]]:
    """P1 (`filtros`), P6 (`agrupacion`) y las correcciones C6 (`meses`), C7 (`relleno`) y C1 (`periodo`): los
    argumentos que se ejecutan y lo que se corrigió. `texto`: el de `texto_usuario`."""
    nuevos, correcciones = dict(argumentos), []
    if relleno:
        _sin_relleno(herramienta, nuevos, correcciones)
    if periodo and herramienta == "historial_ventas":
        _periodo_inventado(nuevos, correcciones)
    for nombre, valor in list(nuevos.items()) if filtros else ():
        if valor in (None, "", [], {}) or not isinstance(valor, str | int):
            continue
        es_lugar = nombre == "sucursal" or (herramienta == "recomendar_traslados" and nombre in LUGARES)
        if es_lugar:
            if isinstance(valor, str) and valor in SUCURSALES and not _nombra(texto, SUCURSALES[valor]):
                del nuevos[nombre]
                correcciones.append(f"{nombre}={valor} (la pregunta no la nombra)")
        elif nombre in VALORES and isinstance(valor, str) and valor in VALORES[nombre]:
            if not _nombra(texto, VALORES[nombre][valor]) and not (meses and _extra(nombre, valor, texto)):
                del nuevos[nombre]
                correcciones.append(f"{nombre}={valor} (la pregunta no lo pide)")
        elif nombre == "dias" and not DIAS.search(texto) and not (meses and (MESES.search(texto) or ANIO.search(texto))):
            del nuevos[nombre]
            correcciones.append(f"dias={valor} (la pregunta no da un periodo)")
        elif nombre == "categoria" and isinstance(valor, str) and not _nombra_categoria(texto, valor):
            del nuevos[nombre]
            correcciones.append(f"categoria={valor} (la pregunta no la nombra)")
    if (agrupacion and herramienta == "historial_ventas" and not nuevos.get("agrupacion") and not nuevos.get("dias")
            and HISTORICO.search(texto)):
        nuevos["agrupacion"] = "trimestre" if "trimestr" in texto else "anio"
        correcciones.append(f"agrupacion={nuevos['agrupacion']} (la pregunta pide el histórico)")
    return nuevos, correcciones


def sin_repetidas(llamadas: list[tuple[str, dict]]) -> tuple[list[int], int]:
    """Los índices de las llamadas que quedan (la primera de cada grupo idéntico) y cuántas se quitaron."""
    vistas, quedan = set(), []
    for i, (nombre, argumentos) in enumerate(llamadas):
        clave = (nombre, tuple(sorted((k, str(v)) for k, v in argumentos.items() if v not in (None, "", [], {}))))
        if clave not in vistas:
            vistas.add(clave)
            quedan.append(i)
    return quedan, len(llamadas) - len(quedan)


# P2: la aclaración, armada con las opciones de la herramienta
MAX_OPCIONES = 5


def pregunta_con_opciones(resultados: list) -> str | None:
    """La pregunta «¿cuál?» con las opciones que trajeron las herramientas: los candidatos de un «ambiguo», los
    productos de una búsqueda o las categorías de la pista de Z5. Sin opciones, None."""
    for r in resultados:
        if isinstance(r, dict) and r.get("resultado") == "ambiguo" and r.get("candidatos"):
            return _pregunta(r["candidatos"], int(r.get("total") or 0), r.get("busqueda"))
    for r in resultados:
        if isinstance(r, dict) and r.get("filas") and all(isinstance(f, dict) and "codigo" in f and "nombre" in f
                                                          for f in r["filas"]):
            return _pregunta(r["filas"], int(r.get("total") or 0), None)
    for r in resultados:
        if isinstance(r, dict) and r.get("aclarar") and r.get("categorias"):
            return f"Hay productos de varias categorías: {', '.join(r['categorias'])}. ¿De cuál quieres los datos?"
    return None


def _pregunta(candidatos: list[dict], total: int, busqueda: str | None) -> str:
    elegidos = candidatos[:MAX_OPCIONES]
    total = max(total, len(elegidos))
    que = f"que coinciden con «{busqueda}»" if busqueda else "que coinciden"
    lineas = [f"Hay {total} productos {que}. ¿Cuál de ellos?", ""]
    lineas += [f"- {c['nombre']} (código {c['codigo']})" for c in elegidos]
    if total > len(elegidos):
        lineas += ["", f"Son los primeros {len(elegidos)}; si no está, dime el nombre completo o el código."]
    return "\n".join(lineas)


def aclaracion(resultados: list) -> str | None:
    """Si los resultados de la ronda son solo «ambiguo» (o errores), la pregunta con las opciones; si no, None."""
    ambiguos = [r for r in resultados if isinstance(r, dict) and r.get("resultado") == "ambiguo" and r.get("candidatos")]
    if not ambiguos or any(isinstance(r, dict) and r.get("resultado") != "ambiguo" and "error" not in r for r in resultados):
        return None
    return pregunta_con_opciones(ambiguos)


# P4: la respuesta solo ofrece consultar algo que el bucle puede consultar ya
OFRECE = re.compile(r"(te gustaria|quieres|quisieras|deseas|prefieres|puedo)\s+(?:\w+\s+){0,4}?"
                    r"(consulte|consultar|revise|revisar|busque|buscar|verifique|verificar|muestre|mostrar|ver|"
                    r"compare|comparar|traiga|calcule|conocer|saber)\b(?P<resto>[^?]*)\?\s*$")
NO_SEGUIR = re.compile(r"\b(mas|otro|otra|otros|otras|algo|alguna|algun)\b")


def ofrece_consultar(texto: str) -> bool:
    """«¿Te gustaría ver el historial de ventas de este producto?»: sí. «¿Quieres ver más detalles?» o «¿Necesitas
    algo más?»: no. Solo la última frase, y solo si es una pregunta."""
    ultima = re.split(r"(?<=[.!])\s+|\n+", texto.strip())[-1] if texto.strip() else ""
    m = OFRECE.search(normal(ultima) + ("?" if ultima.rstrip().endswith("?") else ""))
    return bool(m) and not NO_SEGUIR.search(m.group("resto"))
