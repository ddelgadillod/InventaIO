"""
Conjuntos de referencia: v0 del spike (INV-30, W6 y W9) y v1 de INV-31
(criterios 6 y 10).

`cargar("local")` lee las preguntas como están. `cargar("colab")` es la
variante para entornos externos (N9): cambia los nombres de las sucursales y la
fecha de los datos, así que nada de lo que sale del equipo identifica al
negocio. Las cantidades ya son sintéticas en las dos variantes.

En los resultados, `{fecha}` es la fecha de la foto de cada variante y
`{fecha-45}` (o `+2`) una fecha a esos días de ella, para que las fechas de las
filas (ventanas de ventas, fechas de pedido) también se muevan en Colab.

El v1 agrega a cada pregunta, opcionales: `bloque` (A–F de la plantilla),
`hechos_reales` y `hechos_alguno_reales` (los hechos con los datos reales al
31-dic-2025, para calificar contra el Core API, que en el v0 no se podía: T17
de INV-32) y `pendiente` (la herramienta que todavía no existe; esas preguntas
no se validan contra el catálogo ni se corren sin pedirlo).

El holdout de INV-33 agrega `turnos_previos`: la conversación que hubo antes de
la pregunta (usuario y agente, en orden), para medir el multi-turno.
"""
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from evaluacion import catalogo_v0
from herramientas.catalogo import esquemas

DIRECTORIO = Path(__file__).resolve().parent / "conjuntos"

# Variante de Colab: sucursales y fecha que no son las reales
SUCURSALES_COLAB = {"LA 21": "NORTE", "PRINCIPAL": "CENTRO", "GLORIETA": "SUR"}
FECHA_COLAB = "2024-06-28"


class Esperado(BaseModel):
    herramienta: str
    argumentos: dict[str, Any] = Field(default_factory=dict)
    opcionales: dict[str, Any] = Field(default_factory=dict)


class Turno(BaseModel):
    """Un mensaje anterior de la conversación (holdout de INV-33): lo que el agente ya respondió es contexto."""
    rol: Literal["usuario", "agente"]
    texto: str = Field(min_length=1)


class Pregunta(BaseModel):
    id: str
    variante_de: str | None = None        # otra forma de hacer una pregunta del conjunto
    rol: Literal["gerente", "admin_bodega", "admin_sucursal"]
    sucursal_usuario: str | None
    tipo: Literal["herramienta", "ambigua", "abstencion", "adversarial", "fuera_de_alcance"]
    pregunta: str = Field(min_length=3)
    esperado: list[Esperado] = Field(default_factory=list)
    abstencion: bool = False
    abstencion_valida: bool = False
    resultados: dict[str, Any] = Field(default_factory=dict)
    hechos_clave: list[str] = Field(default_factory=list)
    hechos_alguno: list[str] = Field(default_factory=list)
    prohibido: list[str] = Field(default_factory=list)
    aclaracion: bool = False
    rechazo: bool = False
    nota: str | None = None               # criterio que se revisa a mano
    bloque: str | None = None             # v1: bloque de la plantilla (A una herramienta … F adversarial)
    hechos_reales: list[str] = Field(default_factory=list)          # v1: con el Core API real
    hechos_alguno_reales: list[str] = Field(default_factory=list)
    pendiente: str | None = None          # v1: herramienta que todavía no está en el catálogo
    turnos_previos: list[Turno] = Field(default_factory=list)       # holdout: la conversación anterior

    @model_validator(mode="after")
    def _coherente(self):
        if self.abstencion == bool(self.esperado):
            raise ValueError(f"{self.id}: o es abstención o tiene llamadas esperadas, no ambas ni ninguna")
        if (self.rol == "gerente") != (self.sucursal_usuario is None):
            raise ValueError(f"{self.id}: solo el gerente no tiene sucursal")
        if self.turnos_previos and (self.turnos_previos[0].rol != "usuario" or self.turnos_previos[-1].rol != "agente"):
            raise ValueError(f"{self.id}: los turnos previos empiezan con el usuario y terminan con el agente")
        return self

    def mensajes(self) -> list[dict]:
        """La conversación en el formato del chat: los turnos previos y la pregunta."""
        roles = {"usuario": "user", "agente": "assistant"}
        return [{"role": roles[t.rol], "content": t.texto} for t in self.turnos_previos] + [
            {"role": "user", "content": self.pregunta}]


class Conjunto(BaseModel):
    version: str
    fecha_datos: str
    preguntas: list[Pregunta]

    def por_id(self, id_: str) -> Pregunta:
        return next(p for p in self.preguntas if p.id == id_)


def para_modo_real(pregunta: Pregunta) -> Pregunta | None:
    """La pregunta con los hechos de los datos reales, o None si no los tiene (el v0: T17)."""
    if not (pregunta.hechos_reales or pregunta.hechos_alguno_reales):
        return None
    return pregunta.model_copy(update={"hechos_clave": pregunta.hechos_reales,
                                       "hechos_alguno": pregunta.hechos_alguno_reales})


def _normal(valor: Any) -> str:
    """Sin mayúsculas, acentos ni espacios sobrantes."""
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


def _vale(esperado: Any, recibido: Any) -> bool:
    if esperado == "*":
        return True
    if isinstance(esperado, dict):
        return _normal(esperado["contiene"]) in _normal(recibido)
    return _normal(esperado) == _normal(recibido)


def coincide(esperado: Esperado, herramienta: str, argumentos: dict[str, Any]) -> bool:
    """La regla de `esperado` del conjunto: los listados coinciden; los demás faltan o son opcionales aceptados."""
    if herramienta != esperado.herramienta:
        return False
    presentes = {k: v for k, v in argumentos.items() if v not in (None, "", [], {})}
    for nombre, valor in esperado.argumentos.items():
        if nombre not in presentes or not _vale(valor, presentes[nombre]):
            return False
    for nombre, valor in presentes.items():
        if nombre in esperado.argumentos:
            continue
        if nombre not in esperado.opcionales or not _vale(esperado.opcionales[nombre], valor):
            return False
    return True


def _cumple(si: dict[str, Any], argumentos: dict[str, Any]) -> bool:
    presentes = {k: v for k, v in argumentos.items() if v not in (None, "", [], {})}
    for nombre, valor in si.items():
        if valor is None:
            if nombre in presentes:
                return False
        elif nombre not in presentes or not _vale(valor, presentes[nombre]):
            return False
    return True


def resultado_para(pregunta: Pregunta, herramienta: str, argumentos: dict[str, Any], fecha: str) -> dict:
    """Lo que la herramienta devuelve en esta pregunta.

    Un resultado puede ser fijo o una lista de casos {"si": {...}, "resultado": {...}}:
    gana el primero cuyas condiciones cumplan los argumentos (null = el argumento falta).
    Una herramienta sin resultado listado devuelve una lista vacía. Si el modelo pide una
    sucursal y las filas la traen, solo llegan las de esa sucursal, como en la herramienta real.
    """
    r = pregunta.resultados.get(herramienta)
    if isinstance(r, list):
        r = next((caso["resultado"] for caso in r if _cumple(caso.get("si", {}), argumentos)), None)
    if r is None:
        return {"fecha_dato": fecha, "total": 0, "filas": []}
    return _filtrar_por_sucursal(r, argumentos.get("sucursal"))


def _filtrar_por_sucursal(resultado: dict, sucursal: Any) -> dict:
    """Como la herramienta real: con sucursal, solo las filas de esa sucursal (si las filas la traen)."""
    filas = resultado.get("filas")
    if not sucursal or not isinstance(filas, list) or not filas or not all(isinstance(f, dict) and "sucursal" in f for f in filas):
        return resultado
    elegidas = [f for f in filas if _normal(f["sucursal"]) == _normal(sucursal)]
    filtrado = {k: v for k, v in resultado.items() if k != "mostrando"}
    return {**filtrado, "filas": elegidas, "total": len(elegidas)}


_NOMBRE_REAL = re.compile(r"\b(?:" + "|".join(re.escape(r) for r in SUCURSALES_COLAB) + r")\b", re.IGNORECASE)
# Valores que no son nombres de sucursal aunque coincidan («tipo»: «principal»)
_CLAVES_SIN_CAMBIO = {"tipo", "tipo_destino"}


def _como_original(original: str, ficticio: str) -> str:
    """Conserva el estilo: GLORIETA → SUR, Glorieta → Sur, glorieta → sur."""
    if original.isupper():
        return ficticio.upper()
    if original[:1].isupper():
        return ficticio.capitalize()
    return ficticio.lower()


def _texto_colab(texto: str) -> str:
    """Reemplaza los nombres reales sin importar mayúsculas (los usuarios escriben «glorieta»)."""
    reales = {r.lower(): f for r, f in SUCURSALES_COLAB.items()}
    return _NOMBRE_REAL.sub(lambda m: _como_original(m.group(), reales[m.group().lower()]), texto)


def _anonimizar(valor: Any, clave: str | None = None) -> Any:
    if isinstance(valor, str):
        return valor if clave in _CLAVES_SIN_CAMBIO else _texto_colab(valor)
    if isinstance(valor, list):
        return [_anonimizar(x, clave) for x in valor]
    if isinstance(valor, dict):
        # Las claves también: el historial trae {"suma_por_sucursal": {"GLORIETA": …}}
        return {_texto_colab(k): _anonimizar(v, k) for k, v in valor.items()}
    return valor


_FECHA_RELATIVA = re.compile(r"\{fecha([+-]\d+)?(?::(texto|dia_mes))?\}")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def _escrita(d: date, forma: str | None) -> str:
    if forma == "texto":
        return f"{d.day} de {MESES[d.month - 1]} de {d.year}"
    if forma == "dia_mes":
        return f"{d.day} de {MESES[d.month - 1]}"
    return d.isoformat()


_PERIODO_RELATIVO = re.compile(r"\{periodo:(anio|trimestre|mes|semana)([+-]\d+)?\}")


def periodo(base: date, tipo: str, n: int = 0) -> str:
    """El periodo de los reportes de ventas n periodos antes o después del de `base`: 2025, 2025-T4, 2025-12, 2025-W01."""
    if tipo == "anio":
        return str(base.year + n)
    if tipo == "trimestre":
        q = base.year * 4 + (base.month - 1) // 3 + n
        return f"{q // 4}-T{q % 4 + 1}"
    if tipo == "mes":
        m = base.year * 12 + base.month - 1 + n
        return f"{m // 12}-{m % 12 + 1:02d}"
    anio, semana, _ = (base + timedelta(weeks=n)).isocalendar()
    return f"{anio}-W{semana:02d}"


def con_fechas(texto: str, fecha: str) -> str:
    """{fecha} y {fecha±n} (días) con la fecha de la foto de la variante; con «:texto», escrita
    («31 de diciembre de 2025»), y con «:dia_mes», sin el año. {periodo:tipo±n}: el periodo de un reporte de
    ventas (INV-33, B4), contado desde el de la fecha."""
    base = date.fromisoformat(fecha)
    texto = _PERIODO_RELATIVO.sub(lambda m: periodo(base, m.group(1), int(m.group(2) or 0)), texto)
    return _FECHA_RELATIVA.sub(lambda m: _escrita(base + timedelta(days=int(m.group(1) or 0)), m.group(2)), texto)


def cargar(variante: Literal["local", "colab"] = "local", version: str = "v0") -> Conjunto:
    crudo = (DIRECTORIO / version / "preguntas.json").read_text(encoding="utf-8")
    datos = json.loads(crudo)
    fecha = datos["fecha_datos"]
    if variante == "colab":
        datos = _anonimizar(datos)
        fecha = FECHA_COLAB
        # Los hechos reales no salen del equipo (N9)
        for p in datos["preguntas"]:
            p.pop("hechos_reales", None)
            p.pop("hechos_alguno_reales", None)
    datos["fecha_datos"] = fecha
    datos["preguntas"] = json.loads(con_fechas(json.dumps(datos["preguntas"], ensure_ascii=False), fecha))
    return Conjunto(**datos)


def herramientas(variante: Literal["local", "colab"] = "local", version: str = "v0") -> list[dict]:
    """El catálogo de cada conjunto: el provisional del spike para el v0; el real (INV-32) desde el v1."""
    if version == "v0":
        sucursales = catalogo_v0.SUCURSALES
        if variante == "colab":
            sucursales = [SUCURSALES_COLAB.get(s, s) for s in sucursales]
        return catalogo_v0.herramientas(sucursales)
    catalogo = esquemas()
    return _anonimizar(catalogo) if variante == "colab" else catalogo


def errores_contra_catalogo(conjunto: Conjunto, catalogo: list[dict], incluir_pendientes: bool = False) -> list[str]:
    """Cada llamada esperada usa una herramienta y argumentos del catálogo, con valores válidos.
    Las preguntas `pendiente` (su herramienta no existe todavía) se saltan, salvo que se pidan."""
    por_nombre = {h["function"]["name"]: h["function"]["parameters"] for h in catalogo}
    errores = []
    for p in conjunto.preguntas:
        if p.pendiente and not incluir_pendientes:
            continue
        for e in p.esperado:
            if e.herramienta not in por_nombre:
                errores.append(f"{p.id}: herramienta desconocida {e.herramienta}")
                continue
            propiedades = por_nombre[e.herramienta]["properties"]
            for arg, valor in {**e.argumentos, **e.opcionales}.items():
                if arg not in propiedades:
                    errores.append(f"{p.id}: {e.herramienta} no tiene el argumento {arg}")
                elif isinstance(valor, str) and valor != "*" and "enum" in propiedades[arg] and valor not in propiedades[arg]["enum"]:
                    errores.append(f"{p.id}: {arg}={valor} no está en {propiedades[arg]['enum']}")
        for nombre in p.resultados:
            if nombre not in por_nombre:
                errores.append(f"{p.id}: resultado para una herramienta desconocida {nombre}")
    return errores
