import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../api/AuthContext'
import { login, getProfile } from '../api/client'
import { Loader2 } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { loginSuccess } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      const profile = await getProfile()
      loginSuccess(profile)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message || 'Error al iniciar sesión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50"
         style={{backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none'%3E%3Cg fill='%232563eb' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`}}>

      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-xl border border-slate-200/60 p-8">
          {/* Logo */}
          <div className="text-center mb-7">
            <svg viewBox="0 0 512 512" className="w-14 h-14 mx-auto mb-3">
              <path d="M256 20 L462 148 L462 364 L256 492 L50 364 L50 148 Z" fill="#2563EB"/>
              <path d="M256 60 L422 168 L422 344 L256 452 L90 344 L90 168 Z" fill="#3B82F6"/>
              <path d="M256 140 L360 200 L256 260 L152 200 Z" fill="#93C5FD"/>
              <path d="M152 200 L256 260 L256 370 L152 310 Z" fill="#2563EB"/>
              <path d="M360 200 L256 260 L256 370 L360 310 Z" fill="#1D4ED8"/>
              <circle cx="310" cy="280" r="14" fill="#14B8A6"/>
              <circle cx="310" cy="280" r="6" fill="#FFF"/>
            </svg>
            <h1 className="text-2xl font-bold text-brand-navy">InventAI/o</h1>
            <p className="text-sm text-slate-500 mt-1">Consulta inteligente de inventarios</p>
          </div>

          <hr className="border-slate-200 mb-6" />

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-1">
                Correo electrónico
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="tucorreo@inventaio.co"
                required
                className="w-full h-11 px-4 rounded-lg border border-slate-200 text-sm
                  focus:ring-2 focus:ring-brand-blue focus:border-transparent
                  placeholder:text-slate-400 outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-800 mb-1">
                Contraseña
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full h-11 px-4 rounded-lg border border-slate-200 text-sm
                  focus:ring-2 focus:ring-brand-blue focus:border-transparent
                  placeholder:text-slate-400 outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-brand-blue hover:bg-blue-700 disabled:bg-blue-400
                text-white font-semibold rounded-lg shadow-sm flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Ingresando...
                </>
              ) : 'Iniciar sesión'}
            </button>
          </form>

          {/* Demo credentials hint */}
          <div className="mt-5 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <p className="text-xs text-slate-500 font-medium mb-1">Demo — Usuarios disponibles:</p>
            <p className="text-xs text-slate-400">gerente@inventaio.co</p>
            <p className="text-xs text-slate-400">admin.principal@inventaio.co</p>
            <p className="text-xs text-slate-400">bodega@inventaio.co</p>
            <p className="text-xs text-slate-400 mt-1">Contraseña: <span className="font-mono">admin123</span></p>
          </div>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          v1.0 — Universidad del Valle · 2026
        </p>
      </div>
    </div>
  )
}
