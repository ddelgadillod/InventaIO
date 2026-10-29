import { describe, expect, it } from 'vitest'
import { AGRUPACION_DEL_ATAJO, rangoDelAtajo } from './periodos'
import { fmtPeriodo } from './formato'

const DATOS = { desde: '2022-01-02', hasta: '2025-12-31' }

describe('periodos.js (K7)', () => {
  it.each([
    ['mes', '2025-12-01'],
    ['trimestre', '2025-10-01'],
    ['anio', '2025-01-01'],
    ['todo', '2022-01-02'],
  ])('%s empieza el %s y termina en la última venta', (atajo, desde) => {
    expect(rangoDelAtajo(atajo, DATOS)).toEqual({ desde, hasta: '2025-12-31' })
  })

  it('el trimestre sale de la última venta y nunca empieza antes de la primera', () => {
    expect(rangoDelAtajo('trimestre', { desde: '2022-01-02', hasta: '2025-05-20' })).toEqual({ desde: '2025-04-01', hasta: '2025-05-20' })
    expect(rangoDelAtajo('anio', { desde: '2022-01-02', hasta: '2022-03-31' })).toEqual({ desde: '2022-01-02', hasta: '2022-03-31' })
  })

  it('cada atajo abre con una agrupación', () => {
    expect(AGRUPACION_DEL_ATAJO).toEqual({ mes: 'dia', trimestre: 'semana', anio: 'mes', todo: 'mes', rango: 'dia' })
  })

  it('fmtPeriodo según la agrupación', () => {
    expect([fmtPeriodo('2025-12-31'), fmtPeriodo('2025-W49'), fmtPeriodo('2025-12')]).toEqual(['31 dic', 'Sem 49 2025', 'dic 2025'])
  })
})
