/**
 * InventAI/o — Exportación a CSV (INV-27, V12)
 * El formato que Excel con la configuración de Colombia abre con los números
 * como números: UTF-8 con BOM, separador `;`, coma decimal y sin separador de
 * miles. Las fechas van en ISO, como llegan de la API.
 *
 *   const texto = aCSV([{ titulo: 'Cantidad', valor: f => f.cantidad }], filas)
 *   descargarCSV('compras.csv', texto)
 */

const BOM = '﻿'
const NUMERO = new Intl.NumberFormat('es-CO', { useGrouping: false, maximumFractionDigits: 3 })

export function celdaCSV(valor) {
  if (valor === null || valor === undefined) return ''
  if (typeof valor === 'number') return NUMERO.format(valor)
  if (typeof valor === 'boolean') return valor ? 'sí' : 'no'
  const texto = String(valor)
  return /[;"\r\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto
}

// columnas: [{ titulo, valor: fila => valor }]
export function aCSV(columnas, filas) {
  const lineas = [
    columnas.map(c => celdaCSV(c.titulo)).join(';'),
    ...filas.map(fila => columnas.map(c => celdaCSV(c.valor(fila))).join(';')),
  ]
  return BOM + lineas.join('\r\n') + '\r\n'
}

export function descargarCSV(nombre, texto) {
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }))
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}
