"""
Conjunto de referencia del spike (INV-30, W6 y W9; INV-31, criterios 6 y 10).

`cargar("local")` lee las preguntas como están. `cargar("colab")` es la
variante para entornos externos (N9): cambia los nombres de las sucursales y la
fecha de los datos, así que nada de lo que sale del equipo identifica al
negocio. Las cantidades ya son sintéticas en las dos variantes.
"""
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from evaluacion import catalogo_v0

DIRECTORIO = Path(__file__).resolve().parent / "conjuntos"

# Variante de Colab: sucursales y fecha que no son las reales
SUCURSALES_COLAB = {"LA 21": "NORTE", "PRINCIPAL": "CENTRO", "GLORIETA": "SUR"}
FECHA_COLAB = "2024-06-28"


class Esperado(BaseModel):
    herramienta: str
    argumentos: dict[str, Any] = Field(default_factory=dict)
    opcionales: dict[str, Any] = Field(default_factory=dict)


class Pregunta(BaseModel):
    id: str
    variante_de: str | None = None        # otra forma de hacer una pregunta del conjunto
    rol: Literal["gerente", "admin_bodega", "admin_sucursal"]
    sucursal_usuario: str | None
    tipo: Literal["herramienta", "ambigua", "abstencion", "adversarial"]
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

    @model_validator(mode="after")
    def _coherente(self):
        if self.abstencion == bool(self.esperado):
            raise ValueError(f"{self.id}: o es abstención o tiene llamadas esperadas, no ambas ni ninguna")
        if (self.rol == "gerente") != (self.sucursal_usuario is None):
            raise ValueError(f"{self.id}: solo el gerente no tiene sucursal")
        return self


class Conjunto(BaseModel):
    version: str
    fecha_datos: str
    preguntas: list[Pregunta]

    def por_id(self, id_: str) -> Pregunta:
        return next(p for p in self.preguntas if p.id == id_)


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
        return {k: _anonimizar(v, k) for k, v in valor.items()}
    return valor


def cargar(variante: Literal["local", "colab"] = "local", version: str = "v0") -> Conjunto:
    crudo = (DIRECTORIO / version / "preguntas.json").read_text(encoding="utf-8")
    datos = json.loads(crudo)
    fecha = datos["fecha_datos"]
    if variante == "colab":
        datos = _anonimizar(datos)
        fecha = FECHA_COLAB
    datos["fecha_datos"] = fecha
    # {fecha} dentro de los resultados es la fecha de la foto de cada variante
    datos["preguntas"] = json.loads(json.dumps(datos["preguntas"], ensure_ascii=False).replace("{fecha}", fecha))
    return Conjunto(**datos)


def herramientas(variante: Literal["local", "colab"] = "local") -> list[dict]:
    sucursales = catalogo_v0.SUCURSALES
    if variante == "colab":
        sucursales = [SUCURSALES_COLAB.get(s, s) for s in sucursales]
    return catalogo_v0.herramientas(sucursales)


def errores_contra_catalogo(conjunto: Conjunto, catalogo: list[dict]) -> list[str]:
    """Cada llamada esperada usa una herramienta y argumentos del catálogo, con valores válidos."""
    por_nombre = {h["function"]["name"]: h["function"]["parameters"] for h in catalogo}
    errores = []
    for p in conjunto.preguntas:
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
