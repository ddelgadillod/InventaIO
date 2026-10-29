import { useState } from 'react'
import { X } from 'lucide-react'
import { cambiarPassword } from '../api/client'
import MensajeError from './MensajeError'

const MINIMO = 8 // el mismo mínimo de PATCH /api/auth/password

/**
 * Cambio de contraseña del usuario autenticado (INV-26 fix, A3.7, J4).
 * Valida en el navegador el largo y la confirmación; lo demás (contraseña
 * actual incorrecta o igual a la nueva) lo responde el Core API.
 */
export default function CambiarPassword({ onCerrar }) {
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [validacion, setValidacion] = useState(null)
  const [error, setError] = useState(null)
  const [exito, setExito] = useState(null)
  const [enviando, setEnviando] = useState(false)

  const enviar = async e => {
    e.preventDefault()
    setError(null)
    setExito(null)
    if (nueva.length < MINIMO) return setValidacion(`La nueva contraseña debe tener al menos ${MINIMO} caracteres`)
    if (nueva !== confirmacion) return setValidacion('La confirmación no coincide con la nueva contraseña')
    setValidacion(null)
    setEnviando(true)
    try {
      const r = await cambiarPassword(actual, nueva)
      setExito(r.message)
      setActual('')
      setNueva('')
      setConfirmacion('')
    } catch (err) {
      setError(err)
    } finally {
      setEnviando(false)
    }
  }

  const campo = (id, etiqueta, valor, setValor) => (
    <label htmlFor={id} className="block">
      <span className="text-xs font-semibold text-slate-600">{etiqueta}</span>
      <input
        id={id}
        type="password"
        value={valor}
        onChange={e => setValor(e.target.value)}
        required
        className="mt-1 w-full h-9 px-3 text-sm rounded-lg border border-slate-200 outline-hidden focus:border-brand-blue"
      />
    </label>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <form role="dialog" aria-label="Cambiar contraseña" onSubmit={enviar}
        className="w-full max-w-sm bg-white rounded-xl shadow-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-slate-800">Cambiar contraseña</h3>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="p-1 rounded-lg hover:bg-slate-100 text-slate-500">
            <X className="w-5 h-5" />
          </button>
        </div>
        {campo('password-actual', 'Contraseña actual', actual, setActual)}
        {campo('password-nueva', 'Nueva contraseña', nueva, setNueva)}
        {campo('password-confirmacion', 'Confirmar nueva contraseña', confirmacion, setConfirmacion)}
        {validacion && <p role="alert" className="text-xs text-red-600">{validacion}</p>}
        <MensajeError error={error} />
        {exito && <p role="status" className="text-sm text-green-700">{exito}</p>}
        <button type="submit" disabled={enviando}
          className="w-full h-9 rounded-lg bg-brand-blue text-white text-sm font-semibold disabled:opacity-50">
          {enviando ? 'Guardando…' : 'Guardar'}
        </button>
      </form>
    </div>
  )
}
