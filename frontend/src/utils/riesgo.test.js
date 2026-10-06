import { describe, expect, it } from 'vitest'
import { calcularRiesgo } from './riesgo'

// Pares reales, foto y features al 2025-12-31 (docs/INV-26-27-requerimientos.md, Fase B)
describe('riesgo.js (V5)', () => {
  it('HUEVOS *UND en PRINCIPAL: 489 de stock y q50 3.366,01 → urgente, 2,2 días hábiles', () => {
    expect(calcularRiesgo(489, 3366.01)).toEqual({ nivel: 'urgente', dias: 2.2 })
  })

  it('ARROZ ZULIA *500 GR en PRINCIPAL: 556 y q50 1.251,25 → alta, 6,7 días hábiles', () => {
    expect(calcularRiesgo(556, 1251.25)).toEqual({ nivel: 'alta', dias: 6.7 })
  })

  it('los umbrales de INV-21 incluyen el límite: 5 es urgente, 10 es alta', () => {
    expect([calcularRiesgo(5, 15).nivel, calcularRiesgo(10, 15).nivel, calcularRiesgo(10.1, 15).nivel])
      .toEqual(['urgente', 'alta', 'normal'])
    expect(calcularRiesgo(0, 15)).toEqual({ nivel: 'urgente', dias: 0 })
  })

  it('compara los días redondeados que se ven: HUEVOS en LA 21, 525 y q50 1.567 → 5,03 se ve "5,0" y es urgente', () => {
    expect(calcularRiesgo(525, 1567)).toEqual({ nivel: 'urgente', dias: 5 })
    expect(calcularRiesgo(10.05, 15).nivel).toBe('normal')               // 10,05 se ve "10,1"
  })

  it('sin demanda prevista no es urgente ni tiene días', () => {
    expect(calcularRiesgo(38, 0)).toEqual({ nivel: 'sin_demanda', dias: null })
    expect(calcularRiesgo(0, 0)).toEqual({ nivel: 'sin_demanda', dias: null })
  })

  it('con stock negativo es una inconsistencia de inventario', () => {
    expect(calcularRiesgo(-44, 120)).toEqual({ nivel: 'inconsistencia', dias: null })
  })
})
