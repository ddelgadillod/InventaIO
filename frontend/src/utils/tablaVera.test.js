import { describe, expect, it } from 'vitest'
import { nombreCSV, numeroEsCO, tablaACSV } from './tablaVera'

const lineas = texto => texto.replace('﻿', '').trimEnd().split('\r\n')

describe('numeroEsCO', () => {
  it('lee miles con punto y decimales con coma', () => {
    expect(numeroEsCO('1.092')).toBe(1092)
    expect(numeroEsCO('1.665.352.671')).toBe(1665352671)
    expect(numeroEsCO('243')).toBe(243)
    expect(numeroEsCO('-27,6')).toBe(-27.6)
    expect(numeroEsCO(' 1,5 ')).toBe(1.5)
  })

  it('lo que no es un número en es-CO da null', () => {
    for (const v of ['1.5', '12.34', '5 unidades', 'GLORIETA', '', null, undefined, 7]) {
      expect(numeroEsCO(v)).toBeNull()
    }
  })
})

describe('tablaACSV', () => {
  it('números, cantidades de una sola unidad y montos salen como números (M4)', () => {
    const datos = {
      columnas: [
        { clave: 'producto', titulo: 'Producto', tipo: 'texto' },
        { clave: 'stock', titulo: 'Stock', tipo: 'cantidad' },
        { clave: 'critica', titulo: 'Crítica', tipo: 'numero' },
        { clave: 'valor', titulo: 'Valor', tipo: 'texto' },
        { clave: 'cobertura', titulo: 'Cobertura', tipo: 'texto' },
        { clave: 'fecha', titulo: 'Llega', tipo: 'fecha' },
      ],
      filas: [
        { producto: 'LECHE; DESLACTOSADA', stock: '-3 unidades', critica: '1.092', valor: '$ 151.640', cobertura: '-27,6 d', fecha: '2026-01-02' },
        { producto: 'ARROZ', stock: '1 unidad', critica: '', valor: '$ 2.500', cobertura: '9,4 d', fecha: '2026-01-03' },
      ],
    }
    expect(lineas(tablaACSV(datos))).toEqual([
      'Producto;Stock (unidades);Crítica;Valor ($);Cobertura;Llega',
      '"LECHE; DESLACTOSADA";-3;1092;151640;-27,6 d;2026-01-02',
      'ARROZ;1;;2500;9,4 d;2026-01-03',
    ])
    expect(tablaACSV(datos).startsWith('﻿')).toBe(true)
  })

  it('kilos con decimales; unidades mezcladas o texto que no es número quedan como texto', () => {
    const datos = {
      columnas: [
        { clave: 'kg', titulo: 'Demanda', tipo: 'cantidad' },
        { clave: 'mixta', titulo: 'Cantidad', tipo: 'cantidad' },
        { clave: 'raro', titulo: 'Total', tipo: 'numero' },
        { clave: 'vacia', titulo: 'Vacía', tipo: 'cantidad' },
      ],
      filas: [
        { kg: '1,5 kg', mixta: '5 unidades', raro: '12', vacia: '' },
        { kg: '20 kg', mixta: '5 unidades y 2,3 kg', raro: 'n/d' },
      ],
    }
    expect(lineas(tablaACSV(datos))).toEqual([
      'Demanda (kg);Cantidad;Total;Vacía',
      '1,5;5 unidades;12;',
      '20;5 unidades y 2,3 kg;n/d;',
    ])
    expect(lineas(tablaACSV({}))).toEqual([''])
  })
})

describe('nombreCSV', () => {
  it('sin tildes ni símbolos, con el prefijo de Vera', () => {
    expect(nombreCSV('Resumen de alertas · GLORIETA')).toBe('vera-resumen-de-alertas-glorieta.csv')
    expect(nombreCSV('Compras sugeridas · PRINCIPAL · urgente')).toBe('vera-compras-sugeridas-principal-urgente.csv')
    expect(nombreCSV('')).toBe('vera-datos.csv')
    expect(nombreCSV('···')).toBe('vera-datos.csv')
  })
})
