import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BloqueDatos from './BloqueDatos'
import { colorSerie, etiquetaEje, tieneVisual, valorCorto, valorLargo } from '../../utils/datosVera'

// INV-40 (contrato v1.2): tarjetas y gráfica arriba, la tabla plegada debajo; sin ellas, la tabla como antes
const COLUMNAS = [{ clave: 'sucursal', titulo: 'Sucursal', tipo: 'texto' }, { clave: 'ok', titulo: 'OK', tipo: 'numero' }]
const FILAS = [{ sucursal: 'PRINCIPAL', ok: '1.200' }, { sucursal: 'GLORIETA', ok: '980' }]
const BASE = { id: '1-1', titulo: 'Resumen del inventario', columnas: COLUMNAS, filas: FILAS, total: 2, mostrando: 2 }
const VISUAL = {
  ...BASE,
  tarjetas: [{ etiqueta: 'Crítico', valor: '412', tono: 'critico' }, { etiqueta: 'En riesgo', valor: '900', detalle: 'bajo + crítico', tono: 'neutro' }],
  grafico: { tipo: 'apiladas', x: 'sucursal', unidad: 'productos',
             series: [{ clave: 'ok', etiqueta: 'OK' }, { clave: 'critico', etiqueta: 'Crítico' }],
             datos: [{ sucursal: 'PRINCIPAL', ok: 1200, critico: 200 }, { sucursal: 'GLORIETA', ok: 980, critico: 212 }] },
}

describe('BloqueDatos', () => {
  it('sin tarjetas ni gráfica muestra la tabla abierta, como antes', () => {
    const { container } = render(<BloqueDatos datos={BASE} />)
    expect(container.querySelector('details').open).toBe(true)
    expect(screen.queryByRole('list', { name: 'Cifras destacadas' })).toBeNull()
    expect(screen.queryByRole('figure')).toBeNull()
  })

  it('con tarjetas y gráfica las pone arriba y pliega la tabla', () => {
    const { container } = render(<BloqueDatos datos={VISUAL} />)
    const tarjetas = screen.getByRole('list', { name: 'Cifras destacadas' })
    expect(within(tarjetas).getAllByRole('listitem')).toHaveLength(2)
    expect(within(tarjetas).getByText('412')).toBeInTheDocument()
    expect(within(tarjetas).getByText('bajo + crítico')).toBeInTheDocument()
    const figura = screen.getByRole('figure')
    expect(figura).toHaveAccessibleName(/Resumen del inventario: gráfica de OK, Crítico por sucursal, 2 datos/)
    const tabla = container.querySelector('details')
    expect(tabla.open).toBe(false)
    expect(within(tabla).getByText('Ver la tabla · Resumen del inventario')).toBeInTheDocument()
  })

  it('solo tarjetas, sin filas: no hay tabla vacía', () => {
    render(<BloqueDatos datos={{ ...BASE, filas: [], tarjetas: VISUAL.tarjetas }} />)
    expect(screen.queryByRole('group')).toBeNull()
    expect(screen.getByText('En riesgo')).toBeInTheDocument()
  })

  it('una gráfica sin datos no cuenta como visual', () => {
    expect(tieneVisual({ ...BASE, grafico: { ...VISUAL.grafico, datos: [] } })).toBe(false)
    expect(tieneVisual(VISUAL)).toBe(true)
  })
})

describe('formato de la gráfica', () => {
  it('valores cortos y largos en pesos, unidades y kilos', () => {
    expect(valorCorto(1250000, '$')).toMatch(/^\$ 1,3\s?M/)
    expect(valorLargo(1250000, '$')).toBe('$ 1.250.000')
    expect(valorLargo(77.14, 'kg')).toBe('77,1 kg')
    expect(valorLargo(3366, 'unidades')).toBe('3.366 unidades')
    expect(valorLargo(null, '$')).toBe('—')
  })

  it('periodos legibles y nombres largos recortados en el eje', () => {
    expect(etiquetaEje('2025-12')).toBe('dic 2025')
    expect(etiquetaEje('2025-W49')).toBe('Sem 49 2025')
    expect(etiquetaEje('ARROZ CAROLINA *5000 GR PREMIUM EXTRA')).toBe('ARROZ CAROLINA *5000 …')
  })

  it('colores por estado y una paleta para las demás series', () => {
    expect(colorSerie('critico', 0)).toBe('#DC2626')
    expect(colorSerie('PRINCIPAL', 1)).toBe('#14B8A6')
  })
})
