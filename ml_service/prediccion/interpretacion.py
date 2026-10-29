"""
InventAI/o — ML Service: interpretación en lenguaje directo
INV-20 (a pedido del usuario, tras revisar manualmente las 3 ramas):
traduce los números de la predicción a una frase corta y accionable,
por reglas fijas -- sin modelo de lenguaje, 100% determinístico y
testeable. El agente NLP (Llama 3.1/RAG) que use InventaIO más adelante
puede construir sobre esto, no lo reemplaza acá (fuera de alcance de
esta HU).

INV-26 fix (A12): las cantidades van en la unidad de venta del producto y
con el formato de la app (es-CO): "1.235 unidades", "1 unidad", "0,4 kg".
Antes eran siempre enteros en "unidades": un producto por kilo con q50 de
0,01 kg salía "0 unidades".
"""
from decimal import ROUND_HALF_UP, Decimal


def _redondear(valor, decimales: int) -> Decimal:
    """Como Intl.NumberFormat en la app y texto_cantidad en el Core API: sobre
    el decimal corto del número y los empates lejos de 0."""
    redondeado = Decimal(repr(float(valor))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return abs(redondeado) if redondeado == 0 else redondeado


def texto_cantidad(valor, se_vende_por_kilo: bool) -> str:
    """La regla de fmtCantidad (app) y de texto_cantidad (Core API): un decimal
    en kg, enteros en unidades y una cantidad distinta de 0 nunca se escribe 0."""
    decimales = 1 if se_vende_por_kilo else 0
    while decimales < 3 and valor != 0 and _redondear(valor, decimales) == 0:
        decimales += 1
    redondeado = _redondear(valor, decimales)
    numero = f"{redondeado:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if se_vende_por_kilo:
        return f"{numero} kg"
    return f"{numero} {'unidad' if abs(redondeado) == 1 else 'unidades'}"


def generar_interpretacion(
    rama: str, prediccion_q50: float, limite_superior: float, alpha_negocio: float, horizonte: int,
    se_vende_por_kilo: bool = False,
) -> str:
    if rama == "intermitente":
        patron = "Demanda intermitente"
    elif rama == "suave_perecedero":
        patron = "Demanda estable, producto perecedero"
    elif rama == "suave_no_perecedero":
        patron = "Demanda estable"
    else:
        patron = "Demanda"

    base = f"{patron}. Proyección: {texto_cantidad(prediccion_q50, se_vende_por_kilo)} en {horizonte} días hábiles."

    if alpha_negocio < 0.5:
        # Cuantil de negocio BAJO (perecederos, INV-17 §2): el modelo
        # sub-pronostica a propósito para evitar merma -- el límite
        # superior no es una cota de seguridad de reposición.
        detalle = (
            " El límite superior no incluye margen de seguridad: el modelo "
            "evita sobre-stock para reducir merma. No usar como cota de reposición."
        )
    else:
        detalle = f" Cobertura recomendada: hasta {texto_cantidad(limite_superior, se_vende_por_kilo)}."

    return base + detalle
