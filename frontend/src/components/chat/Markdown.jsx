import { Fragment } from 'react'
import { bloques } from '../../utils/markdown'

// Markdown mínimo y seguro para el texto de Vera (INV-35, Y1): párrafos, **negritas**,
// `código`, listas con viñetas y numeradas, y títulos como línea en negrita. Todo sale
// como nodos de React, nunca como HTML: lo que el modelo escriba entre < > se ve como texto.

function enLinea(texto) {
  const partes = []
  const patron = /\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`/g
  let resto = 0
  let m
  while ((m = patron.exec(texto)) !== null) {
    if (m.index > resto) partes.push(texto.slice(resto, m.index))
    if (m[3] !== undefined) {
      partes.push(<code key={m.index} className="px-1 rounded bg-white/70 text-[0.85em]">{m[3]}</code>)
    } else {
      partes.push(<strong key={m.index} className="font-bold text-brand-navy">{m[1] ?? m[2]}</strong>)
    }
    resto = m.index + m[0].length
  }
  if (resto < texto.length) partes.push(texto.slice(resto))
  return partes.map((p, i) => <Fragment key={i}>{p}</Fragment>)
}

export default function Markdown({ texto }) {
  return (
    <div className="space-y-2 break-words">
      {bloques(texto).map((b, i) => {
        if (b.tipo === 'h') return <p key={i} className="font-bold text-brand-navy">{enLinea(b.lineas[0])}</p>
        if (b.tipo === 'ul') {
          return <ul key={i} className="list-disc pl-5 space-y-0.5">{b.lineas.map((l, j) => <li key={j}>{enLinea(l)}</li>)}</ul>
        }
        if (b.tipo === 'ol') {
          return <ol key={i} start={b.inicio} className="list-decimal pl-5 space-y-0.5">{b.lineas.map((l, j) => <li key={j}>{enLinea(l)}</li>)}</ol>
        }
        return <p key={i}>{b.lineas.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{enLinea(l)}</Fragment>)}</p>
      })}
    </div>
  )
}
