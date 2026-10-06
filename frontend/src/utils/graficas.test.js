import { describe, expect, it } from 'vitest'
import { esPuntoAislado } from './graficas'

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
