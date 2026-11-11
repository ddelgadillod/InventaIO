import { afterEach, describe, expect, it, vi } from 'vitest'
import paquete from '../package.json'

// INV-68 (U2): la versión sale de package.json y el commit, de VITE_COMMIT (lo pasa el build de la imagen)
describe('version', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('sin commit muestra solo la versión de package.json', async () => {
    vi.stubEnv('VITE_COMMIT', '')
    const { VERSION, VERSION_TEXTO } = await import('./version')
    expect(VERSION).toBe(paquete.version)
    expect(VERSION_TEXTO).toBe(`v${paquete.version}`)
  })

  it('con commit agrega sus primeros 7 caracteres', async () => {
    vi.stubEnv('VITE_COMMIT', 'a1b2c3d4e5f60718')
    const { VERSION_TEXTO } = await import('./version')
    expect(VERSION_TEXTO).toBe(`v${paquete.version} · a1b2c3d`)
  })
})
