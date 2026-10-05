import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CambiarPassword from './CambiarPassword'
import { simularApi } from '../test/utils'

// Sin pausa entre teclas: los mismos eventos, sin depender de temporizadores.
// Con la pausa por defecto, escribir ~40 letras con la suite en paralelo y en
// frío (como en el CI) pasaba los 5 s de una prueba.
let user
beforeEach(() => { user = userEvent.setup({ delay: null }) })

async function llenar(actual, nueva, confirmacion) {
  await user.type(screen.getByLabelText('Contraseña actual'), actual)
  await user.type(screen.getByLabelText('Nueva contraseña'), nueva)
  await user.type(screen.getByLabelText('Confirmar nueva contraseña'), confirmacion)
  await user.click(screen.getByRole('button', { name: 'Guardar' }))
}

describe('CambiarPassword (A3.7)', () => {
  it('valida el largo y la confirmación sin llamar a la API', async () => {
    const api = simularApi()
    render(<CambiarPassword onCerrar={() => {}} />)
    await llenar('admin123', 'corta', 'corta')
    expect(screen.getByRole('alert')).toHaveTextContent('al menos 8 caracteres')
    await user.clear(screen.getByLabelText('Nueva contraseña'))
    await user.clear(screen.getByLabelText('Confirmar nueva contraseña'))
    await user.type(screen.getByLabelText('Nueva contraseña'), 'nuevaClave1')
    await user.type(screen.getByLabelText('Confirmar nueva contraseña'), 'otraClave1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('La confirmación no coincide')
    expect(api.llamadas).toHaveLength(0)
  })

  it('muestra el 400 del Core API', async () => {
    simularApi({ 'PATCH /api/auth/password': { status: 400, body: { detail: 'La contraseña actual es incorrecta' } } })
    render(<CambiarPassword onCerrar={() => {}} />)
    await llenar('mala', 'nuevaClave1', 'nuevaClave1')
    expect(await screen.findByRole('alert')).toHaveTextContent('La contraseña actual es incorrecta')
  })

  it('cambia la contraseña y limpia el formulario', async () => {
    const api = simularApi({ 'PATCH /api/auth/password': { body: { message: 'Contraseña actualizada exitosamente' } } })
    render(<CambiarPassword onCerrar={() => {}} />)
    await llenar('admin123', 'nuevaClave1', 'nuevaClave1')
    expect(await screen.findByRole('status')).toHaveTextContent('Contraseña actualizada exitosamente')
    expect(api.llamadas[0].body).toEqual({ current_password: 'admin123', new_password: 'nuevaClave1' })
    expect(screen.getByLabelText('Contraseña actual')).toHaveValue('')
  })

  it('se cierra', async () => {
    const onCerrar = vi.fn()
    render(<CambiarPassword onCerrar={onCerrar} />)
    await user.click(screen.getByLabelText('Cerrar'))
    expect(onCerrar).toHaveBeenCalled()
  })
})
