import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CambiarPassword from './CambiarPassword'
import { simularApi } from '../test/utils'

async function llenar(actual, nueva, confirmacion) {
  await userEvent.type(screen.getByLabelText('Contraseña actual'), actual)
  await userEvent.type(screen.getByLabelText('Nueva contraseña'), nueva)
  await userEvent.type(screen.getByLabelText('Confirmar nueva contraseña'), confirmacion)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
}

describe('CambiarPassword (A3.7)', () => {
  it('valida el largo y la confirmación sin llamar a la API', async () => {
    const api = simularApi()
    render(<CambiarPassword onCerrar={() => {}} />)
    await llenar('admin123', 'corta', 'corta')
    expect(screen.getByRole('alert')).toHaveTextContent('al menos 8 caracteres')
    await userEvent.clear(screen.getByLabelText('Nueva contraseña'))
    await userEvent.clear(screen.getByLabelText('Confirmar nueva contraseña'))
    await userEvent.type(screen.getByLabelText('Nueva contraseña'), 'nuevaClave1')
    await userEvent.type(screen.getByLabelText('Confirmar nueva contraseña'), 'otraClave1')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
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
    await userEvent.click(screen.getByLabelText('Cerrar'))
    expect(onCerrar).toHaveBeenCalled()
  })
})
