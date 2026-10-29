import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import Cargando from './Cargando'
import EstadoConsulta from './EstadoConsulta'
import MensajeError, { textoError } from './MensajeError'

describe('Cargando', () => {
  it('muestra el aviso de espera larga pasado el tiempo', () => {
    vi.useFakeTimers()
    render(<Cargando aviso="La primera consulta tarda hasta 40 s" avisoTrasMs={5000} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText(/tarda hasta 40 s/)).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.getByText('La primera consulta tarda hasta 40 s')).toBeInTheDocument()
  })

  it('sin aviso solo muestra el spinner', () => {
    render(<Cargando />)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando')
  })
})

describe('MensajeError', () => {
  it.each([
    [new ApiError(404, 'El par no tiene historia suficiente'), 'El par no tiene historia suficiente'],
    [new ApiError(403, 'Solo puede consultar su sucursal (PRINCIPAL)'), 'Solo puede consultar su sucursal (PRINCIPAL)'],
    [new ApiError(409, 'La foto es posterior a la última venta'), 'La foto es posterior a la última venta'],
    [new ApiError(502, 'x'), 'Un servicio interno respondió con un error. Intente de nuevo.'],
    [new ApiError(503, 'x'), 'El servicio no está disponible en este momento.'],
    [new ApiError(504, 'x'), 'El servicio no respondió a tiempo. Intente de nuevo en unos minutos.'],
    [new ApiError(500, 'x'), 'Error del servidor. Intente de nuevo.'],
    [new ApiError(0, 'La consulta tardó más de 130 s', { timeout: true }), 'La consulta tardó más de 130 s'],
    [new ApiError(0, 'No hay conexión con el servidor'), 'No hay conexión con el servidor.'],
    [new Error('algo falló'), 'algo falló'],
    [{}, 'Ocurrió un error inesperado.'],
  ])('%o', (error, texto) => {
    expect(textoError(error)).toBe(texto)
  })

  it('no muestra nada sin error o con una consulta cancelada', () => {
    const { container } = render(<><MensajeError error={null} /><MensajeError error={new ApiError(0, 'c', { cancelada: true })} /></>)
    expect(container).toBeEmptyDOMElement()
  })

  it('ofrece reintentar', async () => {
    const reintentar = vi.fn()
    render(<MensajeError error={new ApiError(504, 'x')} onReintentar={reintentar} />)
    await userEvent.click(screen.getByText('Reintentar'))
    expect(reintentar).toHaveBeenCalled()
  })
})

describe('EstadoConsulta', () => {
  const contenido = datos => <p>datos: {datos.n}</p>

  it('cargando, error, vacío y datos', () => {
    const { rerender, container } = render(
      <EstadoConsulta consulta={{ cargando: true, error: null, datos: null }}>{contenido}</EstadoConsulta>)
    expect(screen.getByRole('status')).toBeInTheDocument()
    rerender(<EstadoConsulta consulta={{ cargando: false, error: new ApiError(404, 'no está'), datos: null, recargar: vi.fn() }}>{contenido}</EstadoConsulta>)
    expect(screen.getByRole('alert')).toHaveTextContent('no está')
    rerender(<EstadoConsulta consulta={{ cargando: false, error: null, datos: null }}>{contenido}</EstadoConsulta>)
    expect(container).toBeEmptyDOMElement()
    rerender(<EstadoConsulta consulta={{ cargando: false, error: null, datos: { n: 3 } }}>{contenido}</EstadoConsulta>)
    expect(screen.getByText('datos: 3')).toBeInTheDocument()
  })
})
