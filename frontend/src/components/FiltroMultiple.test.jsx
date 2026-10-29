import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import FiltroMultiple from './FiltroMultiple'

const OPCIONES = { critica: 'Crítica', alta: 'Alta', media: 'Media' }

function Probar({ inicial = [], onChange = () => {} }) {
  const [valores, setValores] = useState(inicial)
  return (
    <div>
      <FiltroMultiple etiqueta="Urgencia" vacio="Todas las urgencias" plural="urgencias" opciones={OPCIONES}
        valores={valores} onChange={v => { setValores(v); onChange(v) }} />
      <p>fuera</p>
    </div>
  )
}

const boton = nombre => screen.getByRole('button', { name: `Urgencia: ${nombre}` })

describe('FiltroMultiple (INV-28, V13)', () => {
  it('resume la selección: ninguno, uno o varios', async () => {
    render(<Probar />)
    await userEvent.click(boton('Todas las urgencias'))
    const grupo = screen.getByRole('group', { name: 'Urgencia' })
    await userEvent.click(within(grupo).getByLabelText('Alta'))
    expect(boton('Alta')).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(within(grupo).getByLabelText('Crítica'))
    expect(boton('2 urgencias')).toBeInTheDocument()
  })

  it('conserva el orden de las opciones, no el de los clics', async () => {
    const onChange = vi.fn()
    render(<Probar onChange={onChange} />)
    await userEvent.click(boton('Todas las urgencias'))
    const grupo = screen.getByRole('group', { name: 'Urgencia' })
    await userEvent.click(within(grupo).getByLabelText('Media'))
    await userEvent.click(within(grupo).getByLabelText('Crítica'))
    expect(onChange).toHaveBeenLastCalledWith(['critica', 'media'])
    await userEvent.click(within(grupo).getByLabelText('Media'))
    expect(onChange).toHaveBeenLastCalledWith(['critica'])
  })

  it('"Todas las urgencias" desmarca todo', async () => {
    render(<Probar inicial={['alta', 'media']} />)
    await userEvent.click(boton('2 urgencias'))
    await userEvent.click(within(screen.getByRole('group', { name: 'Urgencia' })).getByRole('button', { name: 'Todas las urgencias' }))
    expect(boton('Todas las urgencias')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Urgencia' })).getAllByRole('checkbox').some(c => c.checked)).toBe(false)
  })

  it('se cierra con Escape y con un clic fuera', async () => {
    render(<Probar />)
    await userEvent.click(boton('Todas las urgencias'))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    await userEvent.click(boton('Todas las urgencias'))
    await userEvent.click(screen.getByText('fuera'))
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(boton('Todas las urgencias')).toHaveAttribute('aria-expanded', 'false')
  })
})
