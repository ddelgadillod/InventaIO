/**
 * Mensaje de error de una consulta (INV-26 fix, A2.11). Los 4xx del Core API
 * traen un `detail` en español que se muestra tal cual (403 sucursal ajena,
 * 404 historia insuficiente, 409 foto posterior, 422 validación); los 5xx,
 * el timeout y la falta de conexión, un texto fijo.
 */
const TEXTOS_SERVIDOR = {
  502: 'Un servicio interno respondió con un error. Intente de nuevo.',
  503: 'El servicio no está disponible en este momento.',
  504: 'El servicio no respondió a tiempo. Intente de nuevo en unos minutos.',
}

export function textoError(error) {
  if (error.timeout) return error.message
  if (error.status === 0) return 'No hay conexión con el servidor.'
  if (error.status >= 500) return TEXTOS_SERVIDOR[error.status] ?? 'Error del servidor. Intente de nuevo.'
  return error.detail || error.message || 'Ocurrió un error inesperado.'
}

export default function MensajeError({ error, onReintentar }) {
  if (!error || error.cancelada) return null
  return (
    <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex items-center justify-between gap-3">
      <span>{textoError(error)}</span>
      {onReintentar && (
        <button onClick={onReintentar} className="text-xs font-semibold text-red-700 underline whitespace-nowrap">
          Reintentar
        </button>
      )}
    </div>
  )
}
