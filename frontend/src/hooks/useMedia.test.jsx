import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import useMedia from './useMedia'

describe('useMedia', () => {
  it('sin matchMedia (jsdom) toma la pantalla como ancha', () => {
    expect(renderHook(() => useMedia('(min-width: 40rem)')).result.current).toBe(true)
  })

  it('sigue los cambios de la media query y deja de escuchar al desmontarse', () => {
    let oyente = null
    const mq = {
      matches: false,
      addEventListener: vi.fn((_e, f) => { oyente = f }),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal('matchMedia', () => mq)
    const { result, unmount } = renderHook(() => useMedia('(min-width: 40rem)'))
    expect(result.current).toBe(false)
    mq.matches = true
    act(() => oyente())
    expect(result.current).toBe(true)
    unmount()
    expect(mq.removeEventListener).toHaveBeenCalledWith('change', oyente)
  })
})
