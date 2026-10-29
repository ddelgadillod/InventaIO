/**
 * InventAI/o — Rutas de la app (INV-26 fix, A2.9)
 * Una sola lista alimenta el menú y las rutas. Una vista nueva agrega aquí
 * su entrada con los roles que la ven (ver frontend/README.md).
 */
import { lazy } from 'react'
import { LayoutDashboard, Package, Bell, BarChart3, TrendingUp, ShoppingCart } from 'lucide-react'

// Cada vista se descarga al entrar a ella (A11): recharts y las páginas no
// viajan con el login
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Inventario = lazy(() => import('./pages/Inventario'))
const Alertas = lazy(() => import('./pages/Alertas'))
const Reportes = lazy(() => import('./pages/Reportes'))
const Predicciones = lazy(() => import('./pages/Predicciones'))
const Recomendaciones = lazy(() => import('./pages/Recomendaciones'))

export const ROLES = ['gerente', 'admin_sucursal', 'admin_bodega']

// admin_bodega ve el Dashboard desde INV-25 (D1) y el fix de INV-26 (H2)
export const RUTAS = [
  { path: '/dashboard',  label: 'Dashboard',  icon: LayoutDashboard, roles: ROLES, pagina: Dashboard },
  { path: '/inventario', label: 'Inventario', icon: Package,         roles: ROLES, pagina: Inventario },
  { path: '/alertas',    label: 'Alertas',    icon: Bell,            roles: ROLES, pagina: Alertas },
  // INV-26 fix (A9, K5): los tres roles, con la regla de permisos de INV-25
  { path: '/reportes',   label: 'Reportes',   icon: BarChart3,       roles: ROLES, pagina: Reportes },
  // INV-26 (V6): admin_sucursal queda fijo en su sucursal; la Bodega no se pronostica
  { path: '/predicciones', label: 'Predicciones', icon: TrendingUp, roles: ROLES, pagina: Predicciones },
  // INV-27 (V6): admin_sucursal ve solo su sucursal; admin_bodega, como el gerente
  { path: '/recomendaciones', label: 'Recomendaciones', icon: ShoppingCart, roles: ROLES, pagina: Recomendaciones },
]

export function rutasDelRol(rol, rutas = RUTAS) {
  return rutas.filter(r => r.roles.includes(rol))
}

// La página de inicio de un rol es la primera de la lista que puede ver
export function inicioDelRol(rol, rutas = RUTAS) {
  return rutasDelRol(rol, rutas)[0]?.path ?? '/login'
}
