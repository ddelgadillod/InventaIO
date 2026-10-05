import { Navigate } from 'react-router'
import { useAuth } from '../api/AuthContext'

/**
 * Guarda de una ruta por rol (INV-26 fix, A2.9): quien no tiene el rol vuelve
 * a su página de inicio, también si entra escribiendo la URL.
 */
export default function GuardaRol({ roles, inicio, children }) {
  const { user } = useAuth()
  if (!roles.includes(user?.rol)) return <Navigate to={inicio} replace />
  return children
}
