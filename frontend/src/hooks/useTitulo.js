import { useEffect } from 'react'

const APP = 'InventAI/o'

// Título de la pestaña: «Alertas · InventAI/o» (M6 de INV-35, WCAG 2.4.2)
export default function useTitulo(titulo) {
  useEffect(() => {
    document.title = titulo ? `${titulo} · ${APP}` : APP
  }, [titulo])
}
