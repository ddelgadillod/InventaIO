"""
InventAI/o — ML Service: pronóstico de pares producto x sucursal
INV-22: el cálculo que antes vivía en el cuerpo de POST /api/predict, extraído
para que la recomendación de transferencias pronostique con exactamente el
mismo código, en el mismo proceso (sin llamarse por HTTP a sí mismo).

- `pronosticar_par`: un par (lo usa /api/predict).
- `pronosticar_lote`: muchos pares, con una predicción por rama del modelo en
  vez de una por par (lo usa el catálogo completo de transferencias). Da
  exactamente lo mismo que `pronosticar_par` par a par: las features son las
  mismas y `motor.predecir` es `motor.predecir_lote` sobre una fila.

Sin I/O: recibe la venta diaria ya leída de la bodega. Lanza (o, en el lote,
devuelve) HistoriaInsuficiente, y lanza CalendarioInsuficiente
(prediccion/features.py) igual que antes; el router decide el código HTTP.
"""
from dataclasses import dataclass

import pandas as pd

from prediccion.features import (
    Calendario,
    HistoriaInsuficiente,
    determinar_rama,
    factor_calendario,
    features_par,
    fila_para_motor,
)
from prediccion.motor import predecir, predecir_lote


@dataclass(frozen=True)
class Pronostico:
    """Demanda acumulada de un par en el horizonte del modelo (15 días hábiles)."""
    rama: str
    q50: float
    limite_superior: float
    alpha_negocio: float


def pronosticar_par(modelo_loader, producto: dict, sucursal: str, unidades: pd.Series,
                    calendario: Calendario, fecha) -> Pronostico:
    """Pronóstico del par a `fecha` (un día hábil de la historia).

    `producto`: fila de dw.dim_producto con los atributos del modelo;
    `unidades`: venta diaria neta del par hasta `fecha`."""
    parametros = modelo_loader.parametros_features
    features = features_par(unidades, calendario, fecha_origen=fecha, fecha_corte_estatica=fecha,
                            parametros=parametros, atributos=producto)
    fila = fila_para_motor(features, producto["codigo_item"], sucursal)
    rama = determinar_rama(fila.iloc[0])
    paquete = modelo_loader.get(rama)
    q50, limite_superior = predecir(paquete, fila)
    return Pronostico(rama=rama, q50=q50, limite_superior=limite_superior, alpha_negocio=paquete["alpha_negocio"])


def pronosticar_lote(modelo_loader, solicitudes: list, calendario: Calendario, fecha,
                     factor_calendario_ventana: float | None = None) -> list:
    """Pronósticos de muchos pares a la misma `fecha`.

    `solicitudes`: [(producto, sucursal, unidades)] como en pronosticar_par.
    Devuelve, en el mismo orden, un Pronostico o la HistoriaInsuficiente del
    par. `factor_calendario_ventana`: el de la fecha, si ya se calculó (es el
    mismo para todos los pares)."""
    parametros = modelo_loader.parametros_features
    resultados: list = [None] * len(solicitudes)
    filas, posiciones = [], []
    for i, (producto, sucursal, unidades) in enumerate(solicitudes):
        try:
            features = features_par(unidades, calendario, fecha_origen=fecha, fecha_corte_estatica=fecha,
                                    parametros=parametros, atributos=producto,
                                    factor_calendario_ventana=factor_calendario_ventana)
        except HistoriaInsuficiente as e:
            resultados[i] = e
            continue
        filas.append({**features, "codigo_item": producto["codigo_item"], "sucursal": sucursal})
        posiciones.append(i)

    if filas:
        tabla = pd.DataFrame(filas)
        tabla["rama"] = [determinar_rama(fila) for fila in filas]
        for rama, grupo in tabla.groupby("rama", sort=False):
            paquete = modelo_loader.get(rama)
            q50, limite = predecir_lote(paquete, grupo)
            for fila, a, b in zip(grupo.index, q50, limite):
                resultados[posiciones[fila]] = Pronostico(rama=rama, q50=float(a), limite_superior=float(b),
                                                          alpha_negocio=paquete["alpha_negocio"])
    return resultados


class PronosticadorNivel1:
    """Adaptador de los modelos de Nivel 1 a la interfaz que usa la
    recomendación de transferencias (`pronosticar_lote(solicitudes, calendario,
    fecha)`). Las pruebas la reemplazan por pronósticos fijos.

    Guarda el factor de calendario por (calendario, fecha): es el mismo para
    todos los pares. La clave conserva el objeto calendario, así que un
    calendario nuevo (la bodega lo relee cada tanto) nunca usa un factor viejo."""

    MAX_FACTORES = 64

    def __init__(self, modelo_loader):
        self.modelo_loader = modelo_loader
        self._factores: dict = {}

    def _factor(self, calendario: Calendario, fecha) -> float:
        clave = (id(calendario), pd.Timestamp(fecha))
        guardado = self._factores.get(clave)
        if guardado is not None and guardado[0] is calendario:
            return guardado[1]
        factor = factor_calendario(calendario, fecha, self.modelo_loader.parametros_features)
        if len(self._factores) >= self.MAX_FACTORES:
            self._factores.clear()
        self._factores[clave] = (calendario, factor)
        return factor

    def pronosticar_lote(self, solicitudes: list, calendario: Calendario, fecha) -> list:
        # Atajo del catálogo completo: un par sin ventas no tiene historia
        # (features_par llegaría a la misma conclusión, más tarde).
        resultados = [HistoriaInsuficiente(f"sin ventas del producto en {sucursal}")
                      for _, sucursal, _ in solicitudes]
        con_ventas = [i for i, (_, _, unidades) in enumerate(solicitudes) if not unidades.empty]
        if con_ventas:
            lote = pronosticar_lote(self.modelo_loader, [solicitudes[i] for i in con_ventas], calendario, fecha,
                                    factor_calendario_ventana=self._factor(calendario, fecha))
            for i, resultado in zip(con_ventas, lote):
                resultados[i] = resultado
        return resultados
