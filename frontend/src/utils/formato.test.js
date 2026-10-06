import { describe, expect, it } from 'vitest'
import { fmtCantidad, fmtConteo, fmtDecimal, fmtFecha, fmtMonedaCorta, fmtNumero } from './formato'
import {
  COBERTURA_SIN_VENTAS, etiquetaTipoAlerta, nombreSerieVentas, nombreUbicacion, textoCobertura, textoUnidadVenta,
} from './etiquetas'

describe('formato.js', () => {
  it('números con separador de miles y un decimal', () => {
    expect([fmtNumero(4608), fmtNumero(-44), fmtNumero(1234567.6), fmtNumero(null)]).toEqual(['4.608', '-44', '1.234.568', '—'])
    expect([fmtDecimal(5.3), fmtDecimal(12), fmtDecimal(undefined)]).toEqual(['5,3', '12,0', '—'])
  })

  it('cantidades según la unidad del producto', () => {
    expect([fmtCantidad(77.145, 'kg'), fmtCantidad(556, 'unidad'), fmtCantidad(4024, undefined)]).toEqual(['77,1', '556', '4.024'])
    // Una cantidad distinta de 0 no se redondea a 0 (stock -0,01 kg en la foto)
    expect([fmtCantidad(-0.01, 'kg'), fmtCantidad(0.4, 'unidad'), fmtCantidad(-0.6, 'unidad'), fmtCantidad(0, 'kg'), fmtCantidad(null, 'kg')])
      .toEqual(['-0,01', '0,4', '-1', '0,0', '—'])
    // Empates lejos de 0: los mismos casos que api/tests/test_textos_alertas.py y ml_service
    expect([fmtCantidad(-2.05, 'kg'), fmtCantidad(-1.25, 'kg'), fmtCantidad(11.95, 'kg'), fmtCantidad(2.5, 'unidad'),
      fmtCantidad(0.5, 'unidad'), fmtCantidad(10.5, 'unidad')]).toEqual(['-2,1', '-1,3', '12,0', '3', '1', '11'])
  })

  it('conteos con el sustantivo en singular o plural', () => {
    expect([fmtConteo(1, 'producto', 'productos'), fmtConteo(0, 'producto', 'productos'), fmtConteo(4046, 'producto', 'productos')])
      .toEqual(['1 producto', '0 productos', '4.046 productos'])
  })

  it('moneda corta igual a la del Dashboard de Release 1', () => {
    expect([fmtMonedaCorta(737879055.35), fmtMonedaCorta(56756.2), fmtMonedaCorta(850)]).toEqual(['$737.9M', '$57K', '$850'])
  })

  it('fechas ISO sin pasar por la zona horaria', () => {
    expect([fmtFecha('2025-12-31'), fmtFecha('2026-01-02T00:00:00'), fmtFecha(null)]).toEqual(['31 dic 2025', '2 ene 2026', '—'])
  })
})

describe('etiquetas.js', () => {
  it('tipos de alerta con nombre, también el nuevo de INV-25', () => {
    expect(etiquetaTipoAlerta('inconsistencia_inventario')).toBe('Inconsistencia de inventario')
    expect(etiquetaTipoAlerta('tipo_futuro')).toBe('tipo futuro')
  })

  it('unidad de venta de los productos', () => {
    expect([textoUnidadVenta('kg'), textoUnidadVenta('unidad')]).toEqual(['Se vende por kilo (kg)', 'Se vende por unidad'])
  })

  it('la Bodega se muestra como "Bodega Central"', () => {
    expect(nombreUbicacion({ nombre: 'BODEGA_CENTRAL', tipo: 'bodega_central' })).toBe('Bodega Central')
    expect(nombreUbicacion({ nombre: 'LA 21', tipo: 'estandar' })).toBe('LA 21')
  })

  it('series de ventas: las ventas sin terminal como "Sin sucursal"', () => {
    expect([nombreSerieVentas('SIN_SUCURSAL'), nombreSerieVentas('LA 21'), nombreSerieVentas(undefined)])
      .toEqual(['Sin sucursal', 'LA 21', 'Total'])
  })

  it('cobertura con stock negativo y cobertura centinela', () => {
    expect([textoCobertura(-347.4, -44), textoCobertura(COBERTURA_SIN_VENTAS, 12), textoCobertura(5.3, 556)])
      .toEqual(['—', 'Sin ventas', '5,3 d'])
    // Más de 999 días es una cobertura real (vende muy poco), no el centinela
    expect(textoCobertura(1972.5, 282)).toBe('1.972,5 d')
  })
})
