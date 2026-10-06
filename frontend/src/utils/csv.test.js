import { describe, expect, it, vi } from 'vitest'
import { aCSV, celdaCSV, descargarCSV } from './csv'

describe('csv.js (V12)', () => {
  it('números con coma decimal y sin separador de miles', () => {
    expect([celdaCSV(77.145), celdaCSV(41952), celdaCSV(3366.01), celdaCSV(-0.04), celdaCSV(0), celdaCSV(146.79500000000002)])
      .toEqual(['77,145', '41952', '3366,01', '-0,04', '0', '146,795'])
  })

  it('vacíos, sí/no y fechas ISO tal cual', () => {
    expect([celdaCSV(null), celdaCSV(undefined), celdaCSV(true), celdaCSV(false), celdaCSV('2026-01-09')])
      .toEqual(['', '', 'sí', 'no', '2026-01-09'])
  })

  it('escapa con comillas dobles los campos con ;, comillas o saltos de línea', () => {
    expect([celdaCSV('VINO; TINTO'), celdaCSV('ACEITE "LA FINA"'), celdaCSV('dos\nlíneas'), celdaCSV('HUEVOS *UND')])
      .toEqual(['"VINO; TINTO"', '"ACEITE ""LA FINA"""', '"dos\nlíneas"', 'HUEVOS *UND'])
  })

  it('empieza con BOM, separa con ; y termina cada línea con CRLF', () => {
    const texto = aCSV(
      [{ titulo: 'Producto', valor: f => f.nombre }, { titulo: 'Cantidad', valor: f => f.cantidad }, { titulo: 'Unidad', valor: f => f.unidad }],
      [{ nombre: 'PAPA PASTUSA *KL', cantidad: 77.1, unidad: 'kg' }, { nombre: 'HUEVOS *UND', cantidad: 489, unidad: 'unidad' }],
    )
    expect(texto.charCodeAt(0)).toBe(0xFEFF)
    expect(texto.slice(1)).toBe('Producto;Cantidad;Unidad\r\nPAPA PASTUSA *KL;77,1;kg\r\nHUEVOS *UND;489;unidad\r\n')
  })

  it('descarga el texto como archivo', () => {
    const crear = vi.fn(() => 'blob:csv')
    const liberar = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: crear, revokeObjectURL: liberar })
    const clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    descargarCSV('compras.csv', 'a;b\r\n')
    expect(crear.mock.calls[0][0]).toBeInstanceOf(Blob)
    expect(crear.mock.calls[0][0].type).toBe('text/csv;charset=utf-8')
    expect(clic).toHaveBeenCalledTimes(1)
    expect(clic.mock.instances[0].download).toBe('compras.csv')
    expect(liberar).toHaveBeenCalledWith('blob:csv')
    expect(document.querySelector('a[download]')).toBeNull()
  })
})
