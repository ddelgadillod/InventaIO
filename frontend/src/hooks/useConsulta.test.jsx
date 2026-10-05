import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, getAlertas } from '../api/client'
import { useConsulta } from './useConsulta'
import { simularApi } from '../test/utils'

describe('useConsulta (A2.10)', () => {
  it('nunca deja en pantalla la respuesta de un filtro anterior', async () => {
    const api = simularApi({
      'GET /api/alertas': ({ params }) => ({
        body: { tipo: params.tipo },
        demoraMs: params.tipo === 'stock_bajo' ? 60 : 0,
      }),
    })
    const { result, rerender } = renderHook(
      ({ tipo }) => useConsulta(op => getAlertas({ tipo }, op), [tipo]),
      { initialProps: { tipo: 'stock_bajo' } },
    )
    expect(result.current.cargando).toBe(true)
    rerender({ tipo: 'stock_critico' })
    await waitFor(() => expect(result.current.datos).toEqual({ tipo: 'stock_critico' }))
    await new Promise(r => setTimeout(r, 80))          // la respuesta vieja ya habría llegado
    expect(result.current).toMatchObject({ datos: { tipo: 'stock_critico' }, error: null, cargando: false })
    expect(api.llamadas.map(l => l.params.tipo)).toEqual(['stock_bajo', 'stock_critico'])
  })

  it('con activo: false no consulta', async () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useConsulta(fn, [], { activo: false }))
    expect(result.current).toMatchObject({ datos: null, cargando: false, error: null })
    await new Promise(r => setTimeout(r, 10))
    expect(fn).not.toHaveBeenCalled()
  })

  it('un error queda con su código y sin cargando', async () => {
    const fn = vi.fn().mockRejectedValue(new ApiError(404, 'historia insuficiente'))
    const { result } = renderHook(() => useConsulta(fn, []))
    await waitFor(() => expect(result.current.cargando).toBe(false))
    expect([result.current.error.status, result.current.datos]).toEqual([404, null])
  })

  it('una consulta cancelada no se reporta como error', async () => {
    const fn = vi.fn().mockRejectedValue(new ApiError(0, 'Consulta cancelada', { cancelada: true }))
    const { result } = renderHook(() => useConsulta(fn, []))
    await new Promise(r => setTimeout(r, 10))
    expect(result.current.error).toBeNull()
  })

  it('pasa signal y timeoutMs a la función y cancela al desmontar', async () => {
    let opciones
    const fn = vi.fn(op => { opciones = op; return new Promise(() => {}) })
    const { unmount } = renderHook(() => useConsulta(fn, [], { timeoutMs: 130_000 }))
    await waitFor(() => expect(fn).toHaveBeenCalled())
    expect(opciones.timeoutMs).toBe(130_000)
    expect(opciones.signal.aborted).toBe(false)
    unmount()
    expect(opciones.signal.aborted).toBe(true)
  })

  it('recargar repite la consulta', async () => {
    let n = 0
    const fn = vi.fn(async () => ++n)
    const { result } = renderHook(() => useConsulta(fn, []))
    await waitFor(() => expect(result.current.datos).toBe(1))
    act(() => result.current.recargar())
    await waitFor(() => expect(result.current.datos).toBe(2))
  })
})
