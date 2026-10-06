/**
 * InventAI/o — Ayudas para las gráficas de recharts (INV-26 fix, validación de pantallas)
 */

// En una serie con huecos, un punto sin vecinos con valor no traza ningún
// segmento, y con `dot={false}` recharts no lo dibuja: el mes desaparece de la
// gráfica. Pasó con "Sin sucursal" en sep 2025 (ago 2025 no tiene ventas).
export function esPuntoAislado(datos, clave, i) {
  const valor = j => datos[j]?.[clave]
  return valor(i) != null && valor(i - 1) == null && valor(i + 1) == null
}
