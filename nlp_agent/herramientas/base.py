"""
Piezas comunes del catálogo (INV-32).

- `Herramienta`: nombre, descripción, parámetros en Pydantic (criterio 1, T12),
  los endpoints que llama (para la prueba de contrato, T13), su `etiqueta` y si
  es `lenta` (evento `tool`, T7) y `ejecutar`, que devuelve un `Resultado`.
- `validar`: argumentos tolerantes (criterio 13). Antes de validar se quitan los
  filtros vacíos que los modelos llenan («null», «todos»), se convierten las
  listas que llegan como texto JSON y los enums se comparan sin mayúsculas ni
  tildes («glorieta», «crítico»). Lo que no valida vuelve al modelo como un 422
  con lo que debe corregir.
- `Resultado`: lo que lee el modelo y, si hay filas para mostrar, el `data` del
  contrato v1 con las mismas filas (T5).
"""
import json
import types
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from herramientas.contexto import Contexto, normal

MAX_FILAS = 10
# Sin esto, los modelos llenan los filtros opcionales (sondeo del 17-oct, INV-30)
OMITIR = "Omítelo para no filtrar."
VACIOS = {"", "null", "none", "todos", "todas", "cualquiera", "cualquier"}


class ErrorArgumentos(Exception):
    pass


@dataclass
class Columna:
    clave: str
    titulo: str
    tipo: str = "texto"             # texto | cantidad | numero | fecha | semaforo | urgencia

    def como_dict(self) -> dict:
        return {"clave": self.clave, "titulo": self.titulo, "tipo": self.tipo}


@dataclass
class Resultado:
    para_modelo: dict
    data: dict | None = None
    fecha_dato: str | None = None


def tabla(titulo: str, columnas: list[Columna], filas: list[dict], total: int, forma: str = "tabla") -> dict:
    """El cuerpo de `data` (contrato v1): las filas con solo las columnas declaradas."""
    claves = [c.clave for c in columnas]
    return {
        "forma": forma, "titulo": titulo, "columnas": [c.como_dict() for c in columnas],
        "filas": [{k: f.get(k) for k in claves} for f in filas], "total": total, "mostrando": len(filas),
    }


def _sin_none(anotacion):
    if get_origin(anotacion) in (Union, types.UnionType):
        return next(a for a in get_args(anotacion) if a is not type(None))
    return anotacion


def _opciones(anotacion) -> tuple | None:
    base = _sin_none(anotacion)
    return get_args(base) if get_origin(base) is Literal else None


def esquema_parametros(modelo: type[BaseModel]) -> dict:
    """JSON Schema compacto, como el del catálogo v0 que midió el spike: sin títulos ni anyOf."""
    propiedades, requeridos = {}, []
    for nombre, campo in modelo.model_fields.items():
        base = _sin_none(campo.annotation)
        opciones = _opciones(campo.annotation)
        prop: dict[str, Any] = {"type": {int: "integer", bool: "boolean"}.get(base, "string")}
        if opciones:
            prop["enum"] = list(opciones)
        descripcion = campo.description or ""
        if campo.is_required():
            requeridos.append(nombre)
        else:
            descripcion = f"{descripcion} {OMITIR}".strip()
        if descripcion:
            prop["description"] = descripcion
        propiedades[nombre] = prop
    return {"type": "object", "properties": propiedades, "required": requeridos}


def _tolerante(modelo: type[BaseModel], argumentos: dict) -> dict:
    limpios = {}
    for clave, valor in argumentos.items():
        if isinstance(valor, str):
            texto = valor.strip()
            if texto.lower() in VACIOS:
                continue
            if texto[:1] in "[{":
                try:
                    valor = json.loads(texto)
                except json.JSONDecodeError:
                    pass
        if isinstance(valor, list) and len(valor) == 1:
            valor = valor[0]
        if valor is None or valor == []:
            continue
        campo = modelo.model_fields.get(clave)
        opciones = _opciones(campo.annotation) if campo else None
        if opciones and isinstance(valor, str):
            valor = next((o for o in opciones if normal(o).replace(" ", "") == normal(valor).replace(" ", "")), valor)
        limpios[clave] = valor
    return limpios


def _explicar(exc: ValidationError) -> str:
    partes = []
    for e in exc.errors():
        campo = ".".join(str(x) for x in e["loc"]) or "argumentos"
        if e["type"] == "missing":
            partes.append(f"falta «{campo}»")
        elif e["type"] == "literal_error":
            partes.append(f"«{campo}» no admite {e['input']!r}; válidos: {e['ctx']['expected']}")
        else:
            partes.append(f"«{campo}»: {e['msg']}")
    return "Argumentos inválidos: " + "; ".join(partes) + ". Corrígelos o responde sin esta herramienta."


class Herramienta:
    nombre: str
    descripcion: str
    Parametros: type[BaseModel]
    # (método, ruta del OpenAPI, parámetros o campos que envía): prueba de contrato (T13)
    endpoints: tuple[tuple[str, str, frozenset[str]], ...] = ()

    def esquema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.nombre, "description": self.descripcion, "parameters": esquema_parametros(self.Parametros)}}

    def validar(self, argumentos: dict) -> BaseModel:
        try:
            return self.Parametros.model_validate(_tolerante(self.Parametros, argumentos))
        except ValidationError as exc:
            raise ErrorArgumentos(_explicar(exc)) from exc

    def etiqueta(self, p: BaseModel) -> str:
        """Texto del evento `tool`: solo con valores ya validados (enums), nunca con texto libre."""
        return self.titulo_base

    def lenta(self, p: BaseModel) -> bool:
        return False

    titulo_base = ""

    async def ejecutar(self, ctx: Contexto, p: BaseModel) -> Resultado:
        raise NotImplementedError
