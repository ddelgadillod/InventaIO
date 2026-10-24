"""
Mejoras del desempeño en el bucle (INV-33, §3f de docs/INV-33-requerimientos.md, decisiones del 23-oct).

Con un modelo de 8B, las reglas del prompt no generalizaron (holdout del 23-oct): las decisiones se sacan del
modelo y se toman aquí, en código determinista y medible. Cada una va con su interruptor (`MEJORAS`):

- `argumentos` (P1): quita los filtros opcionales que la pregunta no nombra (con sinónimos por valor) y las
  llamadas que quedan repetidas (una por sucursal sin que se pidieran, H7).
- `agrupacion` (P6): «histórico», «por año» o «años anteriores» en `historial_ventas` sin periodo → agrupación
  por año (o por trimestre, si lo dice).
- `aclaracion` (P2): si la ronda solo trae resultados «ambiguo», el bucle pregunta cuál, con las opciones.
- `sin_datos` (P3): si las herramientas no trajeron nada y la respuesta afirma contenido, se reintenta.
- `seguir` (P4): si la respuesta solo ofrece consultar algo y quedan rondas, el bucle contesta «sí» una vez.
- `razonar` (P7, experimento): el reintento del verificador va con razonamiento.

Los textos que mira la guarda son los mensajes del usuario de la conversación (sin los automáticos).
"""
import re
from dataclasses import dataclass, fields

from herramientas.contexto import normal

MARCA_AUTOMATICA = "("        # «(Verificación automática) …», «(Continuación automática) …»
CONTINUAR = "(Continuación automática) Sí, consúltalo y responde la pregunta completa con esos datos."
TODAS = ("argumentos", "agrupacion", "aclaracion", "sin_datos", "seguir")       # P7 es un experimento aparte


@dataclass(frozen=True)
class Mejoras:
    argumentos: bool = False
    agrupacion: bool = False
    aclaracion: bool = False
    sin_datos: bool = False
    seguir: bool = False
    razonar: bool = False

    @classmethod
    def desde_texto(cls, texto: str | None) -> "Mejoras":
        """«todas», «ninguna» o los nombres separados por coma («argumentos,aclaracion»)."""
        nombres = {n.strip() for n in (texto or "").split(",") if n.strip()}
        if "todas" in nombres:
            nombres = (nombres - {"todas"}) | set(TODAS)
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


def _nombra(texto: str, raices) -> bool:
    """Cada raíz, al comienzo de una palabra; con un espacio al final («ia »), la palabra completa."""
    return any(re.search(rf"\b{re.escape(r)}", texto + " ") for r in raices)


def _nombra_categoria(texto: str, categoria: str) -> bool:
    """«aseo hogar», «licor» por «Licores»: alguna palabra de la categoría (por su raíz de 5 letras)."""
    return any(re.search(rf"\b{re.escape(p[:5])}", texto) for p in normal(categoria).split() if len(p) >= 4)


def corregir_argumentos(herramienta: str, argumentos: dict, texto: str, filtros: bool = True,
                        agrupacion: bool = False) -> tuple[dict, list[str]]:
    """P1 (`filtros`) y P6 (`agrupacion`): los argumentos que se ejecutan y lo que se corrigió. `texto`: el de
    `texto_usuario`."""
    nuevos, correcciones = dict(argumentos), []
    for nombre, valor in argumentos.items() if filtros else ():
        if valor in (None, "", [], {}) or not isinstance(valor, str | int):
            continue
        es_lugar = nombre == "sucursal" or (herramienta == "recomendar_traslados" and nombre in LUGARES)
        if es_lugar:
            if isinstance(valor, str) and valor in SUCURSALES and not _nombra(texto, SUCURSALES[valor]):
                del nuevos[nombre]
                correcciones.append(f"{nombre}={valor} (la pregunta no la nombra)")
        elif nombre in VALORES and isinstance(valor, str) and valor in VALORES[nombre]:
            if not _nombra(texto, VALORES[nombre][valor]):
                del nuevos[nombre]
                correcciones.append(f"{nombre}={valor} (la pregunta no lo pide)")
        elif nombre == "dias" and not DIAS.search(texto):
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


# P2: la aclaración, armada con los candidatos de la herramienta
MAX_OPCIONES = 5


def aclaracion(resultados: list) -> str | None:
    """Si los resultados de la ronda son solo «ambiguo» (o errores), la pregunta con las opciones; si no, None."""
    ambiguos = [r for r in resultados if isinstance(r, dict) and r.get("resultado") == "ambiguo" and r.get("candidatos")]
    if not ambiguos or any(isinstance(r, dict) and r.get("resultado") != "ambiguo" and "error" not in r for r in resultados):
        return None
    r = ambiguos[0]
    opciones = r["candidatos"][:MAX_OPCIONES]
    total = max(int(r.get("total") or 0), len(opciones))
    lineas = [f"Hay {total} productos que coinciden con «{r['busqueda']}». ¿Cuál de ellos?", ""]
    lineas += [f"- {c['nombre']} (código {c['codigo']})" for c in opciones]
    if total > len(opciones):
        lineas += ["", f"Son los primeros {len(opciones)}; si no está, dime el nombre completo o el código."]
    return "\n".join(lineas)


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
