/**
 * InventAI/o — Bloques del Markdown de Vera (INV-35, Y1)
 * Parte el texto en párrafos, listas y títulos; el formato en línea y el
 * render a nodos de React están en components/chat/Markdown.jsx.
 */
const VINETA = /^\s*[-*•]\s+(.*)$/
const NUMERADA = /^\s*(\d+)[.)]\s+(.*)$/
const TITULO = /^#{1,6}\s+(.*)$/

export function bloques(texto) {
  const resultado = []
  let actual = null // { tipo: 'p' | 'ul' | 'ol', lineas: [] }
  const cerrar = () => { if (actual) resultado.push(actual); actual = null }
  for (const linea of texto.replace(/\r\n?/g, '\n').split('\n')) {
    if (!linea.trim()) { cerrar(); continue }
    const titulo = TITULO.exec(linea)
    const vineta = VINETA.exec(linea)
    const numerada = NUMERADA.exec(linea)
    if (titulo) { cerrar(); resultado.push({ tipo: 'h', lineas: [titulo[1]] }) }
    else if (vineta || numerada) {
      const tipo = vineta ? 'ul' : 'ol'
      if (actual?.tipo !== tipo) { cerrar(); actual = { tipo, lineas: [], inicio: numerada ? Number(numerada[1]) : 1 } }
      actual.lineas.push(vineta ? vineta[1] : numerada[2])
    } else {
      if (actual?.tipo !== 'p') { cerrar(); actual = { tipo: 'p', lineas: [] } }
      actual.lineas.push(linea.trim())
    }
  }
  cerrar()
  return resultado
}
