import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import { RUTAS, inicioDelRol, rutasDelRol } from './rutas'
import GuardaRol from './components/GuardaRol'
import { renderConUsuario, USUARIOS } from './test/utils'

const PRUEBA = [
  { path: '/a', roles: ['gerente'] },
  { path: '/b', roles: ['gerente', 'admin_bodega'] },
]

describe('rutas (A2.9)', () => {
  it('los tres roles ven todas las vistas y entran al Dashboard (H2, K5, V6)', () => {
    for (const rol of ['gerente', 'admin_sucursal', 'admin_bodega']) {
      expect(rutasDelRol(rol).map(r => r.path)).toEqual(['/dashboard', '/inventario', '/alertas', '/reportes', '/predicciones', '/recomendaciones'])
      expect(inicioDelRol(rol)).toBe('/dashboard')
    }
    expect(RUTAS.every(r => r.label && r.icon && r.pagina)).toBe(true)
  })

  it('el menú y el inicio salen de los roles de cada entrada', () => {
    expect(rutasDelRol('admin_bodega', PRUEBA).map(r => r.path)).toEqual(['/b'])
    expect(inicioDelRol('admin_bodega', PRUEBA)).toBe('/b')
    expect(inicioDelRol('desconocido', PRUEBA)).toBe('/login')
  })
})

describe('GuardaRol', () => {
  const app = (
    <Routes>
      <Route path="/a" element={<GuardaRol roles={['gerente']} inicio="/b"><p>página A</p></GuardaRol>} />
      <Route path="/b" element={<p>inicio B</p>} />
    </Routes>
  )

  it('deja pasar al rol permitido', () => {
    renderConUsuario(app, USUARIOS.gerente, { ruta: '/a' })
    expect(screen.getByText('página A')).toBeInTheDocument()
  })

  it('devuelve a su inicio a quien entra por URL sin el rol', () => {
    renderConUsuario(app, USUARIOS.bodega, { ruta: '/a' })
    expect(screen.getByText('inicio B')).toBeInTheDocument()
    expect(screen.queryByText('página A')).not.toBeInTheDocument()
  })
})
