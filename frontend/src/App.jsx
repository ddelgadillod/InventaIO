import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router'
import { AuthProvider, useAuth } from './api/AuthContext'
import Login from './pages/Login'
import GuardaRol from './components/GuardaRol'
import CambiarPassword from './components/CambiarPassword'
import Cargando from './components/Cargando'
import { RUTAS, rutasDelRol, inicioDelRol } from './rutas'
import ChatProvider from './components/chat/ChatProvider'
import useChatPanel from './hooks/useChatPanel'
import useMedia from './hooks/useMedia'
import useTitulo from './hooks/useTitulo'
import BotonChat from './components/chat/BotonChat'
import { KeyRound, LogOut, Menu, X } from 'lucide-react'
import { Suspense, lazy, useState } from 'react'

// Vera se carga al abrirla por primera vez: no pesa en el arranque (INV-35)
const PanelChat = lazy(() => import('./components/chat/PanelChat'))

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <LoadingScreen />
  if (!user) return <Navigate to="/login" replace />
  return children
}

function LoadingScreen() {
  return (
    <div className="h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <Logo className="w-12 h-12 mx-auto mb-3" />
        <div className="w-8 h-8 border-3 border-brand-blue/20 border-t-brand-blue rounded-full animate-spin mx-auto" />
      </div>
    </div>
  )
}

function Logo({ className = "w-8 h-8" }) {
  return (
    <svg viewBox="0 0 512 512" className={className}>
      <path d="M256 20 L462 148 L462 364 L256 492 L50 364 L50 148 Z" fill="#2563EB"/>
      <path d="M256 60 L422 168 L422 344 L256 452 L90 344 L90 168 Z" fill="#3B82F6"/>
      <path d="M256 140 L360 200 L256 260 L152 200 Z" fill="#93C5FD"/>
      <path d="M152 200 L256 260 L256 370 L152 310 Z" fill="#2563EB"/>
      <path d="M360 200 L256 260 L256 370 L360 310 Z" fill="#1D4ED8"/>
      <circle cx="310" cy="280" r="14" fill="#14B8A6"/>
      <circle cx="310" cy="280" r="6" fill="#FFF"/>
    </svg>
  )
}

// Desde lg (64rem en Tailwind 4) el menú lateral está siempre a la vista; más
// angosto es un panel que se abre con "Abrir menú" y, cerrado, queda fuera de
// la pantalla: sin `inert` seguía recibiendo el foco con Tab
const PANTALLA_ANCHA = '(min-width: 64rem)'

// Vera flota sobre la página (position: fixed) y no la angosta (Y3, revisada el 27-oct).
// Ver PanelChat para cada tamaño
function VentanaChat() {
  const { abierto } = useChatPanel()
  return (
    <>
      {abierto && (
        <Suspense fallback={null}>
          <PanelChat />
        </Suspense>
      )}
      <BotonChat />
    </>
  )
}

function AppShell() {
  return (
    <ChatProvider>
      <AppShellContenido />
    </ChatProvider>
  )
}

function AppShellContenido() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [cambiandoPassword, setCambiandoPassword] = useState(false)
  const ancha = useMedia(PANTALLA_ANCHA)
  const menuFueraDePantalla = !ancha && !sidebarOpen
  // Maximizada o en el celular, Vera tapa la página: lo de atrás no debe recibir el foco
  const { modal: chatTapa } = useChatPanel()

  // Menú y rutas salen de RUTAS (A2.9); el título de la pestaña, también (M6)
  const nav = rutasDelRol(user?.rol)
  const inicio = inicioDelRol(user?.rol)
  useTitulo(RUTAS.find(r => r.path === location.pathname)?.label)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const initials = user?.nombre?.split(' ').map(n => n[0]).join('').slice(0, 2) || '??'

  // h-dvh: en el celular, h-screen (100vh) incluye la barra del navegador y la página se desplazaba
  // M13: el primer Tab ofrece saltar el menú (WCAG 2.4.1); solo se ve con el foco
  const saltarAlContenido = (e) => {
    e.preventDefault()
    document.getElementById('contenido')?.focus()
  }

  return (
    <div className="h-dvh flex overflow-hidden">
      <a href="#contenido" onClick={saltarAlContenido} inert={chatTapa ? '' : undefined}
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-white focus:text-brand-navy focus:text-sm focus:font-semibold focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-brand-blue">
        Saltar al contenido
      </a>

      {/* Sidebar backdrop (mobile) */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside id="menu-lateral" inert={menuFueraDePantalla || chatTapa ? '' : undefined} className={`
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-brand-navy flex flex-col
        transform transition-transform duration-200 ease-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="p-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Logo className="w-8 h-8" />
            <span className="text-lg font-bold text-white tracking-tight">InventAI/o</span>
          </div>
          <button onClick={() => setSidebarOpen(false)} aria-label="Cerrar menú" className="lg:hidden text-white/60 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 mt-2 space-y-1">
          {nav.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path
            return (
              <button
                key={path}
                onClick={() => { navigate(path); setSidebarOpen(false) }}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all
                  ${active ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white hover:bg-white/5'}`}
              >
                <Icon className="w-5 h-5" />
                {label}
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-3 px-2 mb-3">
            <div className="w-9 h-9 rounded-full bg-brand-blue flex items-center justify-center text-white text-xs font-bold">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">{user?.nombre}</p>
              <p className="text-xs text-white/50 capitalize">{user?.rol?.replace(/_/g, ' ')}</p>
            </div>
          </div>
          <button
            onClick={() => setCambiandoPassword(true)}
            className="w-full flex items-center gap-2 px-4 py-2 rounded-lg text-white/50 hover:text-white hover:bg-white/5 text-sm transition-all"
          >
            <KeyRound className="w-4 h-4" />
            Cambiar contraseña
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-4 py-2 rounded-lg text-white/50 hover:text-red-400 hover:bg-white/5 text-sm transition-all"
          >
            <LogOut className="w-4 h-4" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {cambiandoPassword && <CambiarPassword onCerrar={() => setCambiandoPassword(false)} />}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden" inert={chatTapa ? '' : undefined}>
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0">
          <button onClick={() => setSidebarOpen(true)} aria-label="Abrir menú" aria-expanded={sidebarOpen} aria-controls="menu-lateral" className="lg:hidden p-1.5 rounded-lg hover:bg-slate-100 text-slate-600">
            <Menu className="w-6 h-6" />
          </button>
          <div className="hidden lg:block" />
          {/* Solo admin_sucursal muestra la etiqueta fija — los demás tienen el selector en cada página */}
          {user?.rol === 'admin_sucursal' && user?.sucursal_nombre && (
            <span className="text-xs text-brand-blue bg-blue-50 px-3 py-1 rounded-full font-medium">
              {user.sucursal_nombre}
            </span>
          )}
        </header>

        {/* Page content: pb-20 deja subir lo último (la paginación) por encima del botón de Vera */}
        <main id="contenido" tabIndex={-1} className="flex-1 overflow-y-auto pb-20 focus:outline-none">
          <Suspense fallback={<Cargando alto="h-full" />}>
            <Routes>
              {RUTAS.map(({ path, roles, pagina: Pagina }) => (
                <Route key={path} path={path} element={
                  <GuardaRol roles={roles} inicio={inicio}><Pagina /></GuardaRol>
                } />
              ))}
              <Route path="*" element={<Navigate to={inicio} replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>

      {/* Fija (position: fixed): no ocupa lugar entre las columnas */}
      <VentanaChat />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        } />
      </Routes>
    </AuthProvider>
  )
}
