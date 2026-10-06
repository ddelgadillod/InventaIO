import { describe, expect, it } from 'vitest'
import { barrasPronostico, esPuntoAislado } from './graficas'

describe('graficas.js', () => {
  // "Sin sucursal" en 2025: hay ventas de feb a jul y en sep, pero no en ago
  const meses = [
    { periodo: 'jul 2025', GLORIETA: 120, 'Sin sucursal': 748650 },
    { periodo: 'ago 2025', GLORIETA: 130 },
    { periodo: 'sep 2025', GLORIETA: 110, 'Sin sucursal': 682600 },
    { periodo: 'oct 2025', GLORIETA: 140 },
  ]

  it('un mes sin vecinos con valor está aislado', () => {
    expect(esPuntoAislado(meses, 'Sin sucursal', 2)).toBe(true)
  })

  it('un mes con un vecino, un mes sin valor o una serie continua no lo están', () => {
    const conVecino = [{ s: 1 }, { s: 2 }, {}]
    expect(esPuntoAislado(conVecino, 's', 0)).toBe(false)
    expect(esPuntoAislado(conVecino, 's', 1)).toBe(false)
    expect(esPuntoAislado(meses, 'Sin sucursal', 1)).toBe(false)
    expect(esPuntoAislado(meses, 'GLORIETA', 2)).toBe(false)
  })

  it('en los extremos solo cuenta el vecino que existe; el valor 0 cuenta como venta', () => {
    expect(esPuntoAislado(meses, 'Sin sucursal', 0)).toBe(true)
    expect(esPuntoAislado([{}, { s: 0 }], 's', 1)).toBe(true)
    expect(esPuntoAislado([{ s: 0 }, { s: 5 }], 's', 1)).toBe(false)
  })
})

describe('barrasPronostico (INV-26)', () => {
  // Las 3 últimas de las 8 ventanas de HUEVOS *UND en PRINCIPAL, desordenadas
  const ventanas = [
    { desde: '2025-12-17', hasta: '2025-12-31', unidades: 4608 },
    { desde: '2025-11-17', hasta: '2025-12-01', unidades: 2426 },
    { desde: '2025-12-02', hasta: '2025-12-16', unidades: 3522 },
  ]

  it('las ventanas van en orden, rotuladas con su fin, y el pronóstico al final', () => {
    expect(barrasPronostico(ventanas, 3366.01, 15)).toEqual([
      { etiqueta: '1 dic', periodo: '17 nov 2025 – 1 dic 2025', ventas: 2426 },
      { etiqueta: '16 dic', periodo: '2 dic 2025 – 16 dic 2025', ventas: 3522 },
      { etiqueta: '31 dic', periodo: '17 dic 2025 – 31 dic 2025', ventas: 4608 },
      { etiqueta: 'Pronóstico IA', periodo: 'Próximos 15 días hábiles', pronostico: 3366.01 },
    ])
  })

  it('sin pronóstico (404 de predict) quedan solo las ventanas, también las que valen 0', () => {
    const ceros = ventanas.map(v => ({ ...v, unidades: 0 }))
    expect(barrasPronostico(ceros, undefined, 15).map(b => b.ventas)).toEqual([0, 0, 0])
    expect(barrasPronostico(ventanas, 0, 15).at(-1).pronostico).toBe(0)
  })
})
