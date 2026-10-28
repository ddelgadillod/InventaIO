import { describe, expect, it } from 'vitest'
import { PREGUNTAS_POR_PAGINA, PREGUNTAS_RAPIDAS, preguntaDeAlerta, preguntasRapidas, preguntasRapidasDelRol } from './preguntasRapidas'

describe('preguntas rápidas', () => {
  it('cada rol tiene 4 y un rol desconocido, ninguna', () => {
    expect(Object.keys(PREGUNTAS_RAPIDAS)).toEqual(['gerente', 'admin_bodega', 'admin_sucursal'])
    Object.values(PREGUNTAS_RAPIDAS).forEach(lista => expect(lista).toHaveLength(4))
    expect(preguntasRapidasDelRol('otro')).toEqual([])
  })

  it('la primera del gerente es la validada en M1, no la que caía en respaldo', () => {
    expect(PREGUNTAS_RAPIDAS.gerente[0]).toBe('Dame un ranking de alertas por sucursal')
    expect(Object.values(PREGUNTAS_RAPIDAS).flat()).not.toContain('Dame un reporte general de las alertas por nivel')
  })
})

describe('preguntaDeAlerta (M7)', () => {
  it('reglas: el inventario; riesgo con IA: si alcanza; sobrestock con IA: el pronóstico', () => {
    const base = { nombre_producto: 'VASO TUC 7 OZ *UND', sucursal: 'LA 21' }
    expect(preguntaDeAlerta({ ...base, tipo: 'inconsistencia_inventario' }))
      .toBe('¿Cómo está el inventario de VASO TUC 7 OZ *UND en LA 21?')
    expect(preguntaDeAlerta({ ...base, tipo: 'riesgo_desabastecimiento_ml' }))
      .toBe('¿Alcanza el stock de VASO TUC 7 OZ *UND en LA 21 para los próximos 15 días hábiles?')
    expect(preguntaDeAlerta({ ...base, tipo: 'sobrestock_previsto_ml' }))
      .toBe('¿Cuál es el pronóstico de VASO TUC 7 OZ *UND en LA 21?')
  })

  it('sin nombre usa el código del producto', () => {
    expect(preguntaDeAlerta({ codigo_item: '00196', sucursal: 'GLORIETA', tipo: 'stock_bajo' }))
      .toBe('¿Cómo está el inventario de 00196 en GLORIETA?')
  })
})

describe('preguntasRapidas por página (M12)', () => {
  it('en las páginas de datos, tres de esa página según quién ve la red o su sucursal', () => {
    for (const [ruta, pagina] of Object.entries(PREGUNTAS_POR_PAGINA)) {
      expect(pagina.red).toHaveLength(3)
      expect(pagina.sucursal).toHaveLength(3)
      expect(preguntasRapidas('gerente', ruta)).toEqual({ titulo: pagina.titulo, preguntas: pagina.red })
      expect(preguntasRapidas('admin_bodega', ruta)).toEqual({ titulo: pagina.titulo, preguntas: pagina.red })
      expect(preguntasRapidas('admin_sucursal', ruta)).toEqual({ titulo: pagina.titulo, preguntas: pagina.sucursal })
    }
    expect(Object.keys(PREGUNTAS_POR_PAGINA)).toEqual(['/alertas', '/inventario', '/recomendaciones', '/predicciones', '/reportes'])
  })

  it('en el Dashboard (o sin rol conocido) quedan las del rol', () => {
    expect(preguntasRapidas('gerente', '/dashboard')).toEqual({ titulo: null, preguntas: PREGUNTAS_RAPIDAS.gerente })
    expect(preguntasRapidas('otro', '/alertas')).toEqual({ titulo: null, preguntas: [] })
  })
})
