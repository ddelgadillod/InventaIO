/**
 * InventAI/o — Ayudas para las gráficas de recharts (INV-26 fix, validación de
 * pantallas; INV-26). Lo que alimenta una gráfica va aquí, en funciones puras
 * con prueba: recharts no dibuja en jsdom.
 */
import { fmtFecha, fmtPeriodo } from './formato'

// En una serie con huecos, un punto sin vecinos con valor no traza ningún
// segmento, y con `dot={false}` recharts no lo dibuja: el mes desaparece de la
// gráfica. Pasó con "Sin sucursal" en sep 2025 (ago 2025 no tiene ventas).
export function esPuntoAislado(datos, clave, i) {
  const valor = j => datos[j]?.[clave]
  return valor(i) != null && valor(i - 1) == null && valor(i + 1) == null
}

// Predicciones (INV-26, C3): las ventanas de 15 días hábiles en orden,
// rotuladas con la fecha en que terminan, y al final el pronóstico q50, que
// sigue a la última. Ventas y pronóstico van en claves distintas para
// dibujarse con estilos distintos; `periodo` es el texto del tooltip
export function barrasPronostico(ventanas, q50, horizonte) {
  const historia = [...ventanas]
    .sort((a, b) => a.hasta.localeCompare(b.hasta))
    .map(v => ({ etiqueta: fmtPeriodo(v.hasta), periodo: `${fmtFecha(v.desde)} – ${fmtFecha(v.hasta)}`, ventas: v.unidades }))
  if (q50 === null || q50 === undefined) return historia
  return [...historia, { etiqueta: 'Pronóstico IA', periodo: `Próximos ${horizonte} días hábiles`, pronostico: q50 }]
}
