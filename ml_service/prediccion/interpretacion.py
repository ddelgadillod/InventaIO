"""
InventAI/o — ML Service: interpretación en lenguaje directo
INV-20 (a pedido del usuario, tras revisar manualmente las 3 ramas):
traduce los números de la predicción a una frase corta y accionable,
por reglas fijas -- sin modelo de lenguaje, 100% determinístico y
testeable. El agente NLP (Llama 3.1/RAG) que use InventaIO más adelante
puede construir sobre esto, no lo reemplaza acá (fuera de alcance de
esta HU).
"""

def generar_interpretacion(
    rama: str, prediccion_q50: float, limite_superior: float, alpha_negocio: float, horizonte: int
) -> str:
    if rama == "intermitente":
        patron = "Demanda intermitente"
    elif rama == "suave_perecedero":
        patron = "Demanda estable, producto perecedero"
    elif rama == "suave_no_perecedero":
        patron = "Demanda estable"
    else:
        patron = "Demanda"

    base = f"{patron}. Proyección: {prediccion_q50:.0f} unidades en {horizonte} días hábiles."

    if alpha_negocio < 0.5:
        # Cuantil de negocio BAJO (perecederos, INV-17 §2): el modelo
        # sub-pronostica a propósito para evitar merma -- el límite
        # superior no es una cota de seguridad de reposición.
        detalle = (
            " El límite superior no incluye margen de seguridad: el modelo "
            "evita sobre-stock para reducir merma. No usar como cota de reposición."
        )
    else:
        detalle = f" Cobertura recomendada: hasta {limite_superior:.0f} unidades."

    return base + detalle
