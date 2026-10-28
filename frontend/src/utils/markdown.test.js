import { describe, expect, it } from 'vitest'
import { bloques, textoPlano } from './markdown'

describe('bloques del Markdown de Vera', () => {
  it('párrafos, listas con viñetas y numeradas, y títulos', () => {
    const texto = '## Resumen\nEn GLORIETA hay:\n\n- **OK**: 1.287  \n* Bajo: 79\n\n3. Uno\n4) Dos\nFin\r\notra línea'
    expect(bloques(texto)).toEqual([
      { tipo: 'h', lineas: ['Resumen'] },
      { tipo: 'p', lineas: ['En GLORIETA hay:'] },
      { tipo: 'ul', lineas: ['**OK**: 1.287  ', 'Bajo: 79'], inicio: 1 },
      { tipo: 'ol', lineas: ['Uno', 'Dos'], inicio: 3 },
      { tipo: 'p', lineas: ['Fin', 'otra línea'] },
    ])
  })

  it('una lista que cambia de tipo abre otra', () => {
    expect(bloques('- a\n1. b').map(b => b.tipo)).toEqual(['ul', 'ol'])
    expect(bloques('')).toEqual([])
  })
})

describe('textoPlano (M9)', () => {
  it('quita negritas, código y títulos; deja listas y párrafos', () => {
    const texto = '## Resumen\r\nEn GLORIETA hay **243** alertas y __109__ altas.  \n\n1. `uno`\n- dos\n'
    expect(textoPlano(texto)).toBe('Resumen\nEn GLORIETA hay 243 alertas y 109 altas.\n\n1. uno\n- dos')
  })
})
