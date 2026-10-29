import { createContext, useContext, useState, useEffect } from 'react'
import { getProfile, getTokens, clearTokens, logout as apiLogout } from '../api/client'

// Exportado para que las pruebas inyecten el usuario (src/test/utils.jsx)
export const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // Sin token no hay perfil que cargar: se arranca sin esperar, y el efecto no cambia el estado de inmediato
  const [loading, setLoading] = useState(() => Boolean(getTokens().access))

  useEffect(() => {
    if (!getTokens().access) return
    getProfile()
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setLoading(false))
  }, [])

  const loginSuccess = (userData) => {
    setUser(userData)
  }

  const logout = async () => {
    await apiLogout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, loginSuccess, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
