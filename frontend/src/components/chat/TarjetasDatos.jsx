// INV-40 (contrato v1.2): las cifras destacadas de una consulta. El valor llega ya formateado en es-CO, como las
// filas; el tono colorea, pero la etiqueta dice siempre qué es (el estado no depende solo del color, WCAG 1.4.1)
const TONO = {
  neutro: 'border-slate-200 bg-white text-slate-800',
  ok: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  atencion: 'border-amber-200 bg-amber-50 text-amber-900',
  critico: 'border-red-200 bg-red-50 text-red-900',
}

export default function TarjetasDatos({ tarjetas }) {
  return (
    <ul className="mt-2 grid grid-cols-2 @lg:grid-cols-3 gap-1.5" aria-label="Cifras destacadas">
      {tarjetas.map((t, i) => (
        <li key={`${t.etiqueta}-${i}`} className={`rounded-lg border px-2.5 py-1.5 min-w-0 ${TONO[t.tono] ?? TONO.neutro}`}>
          <p className="text-[11px] font-medium opacity-80">{t.etiqueta}</p>
          {/* «$ 3.986.592.834»: el signo no se separa de la cifra al partir la línea */}
          <p className={`${String(t.valor).length > 13 ? 'text-xs' : 'text-sm'} font-semibold tabular-nums`}>
            {String(t.valor).replace('$ ', '$\u00a0')}
          </p>
          {t.detalle && <p className="text-[11px] opacity-75 break-words">{t.detalle}</p>}
        </li>
      ))}
    </ul>
  )
}
