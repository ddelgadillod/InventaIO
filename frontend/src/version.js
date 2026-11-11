// INV-68 (U2): versión de la interfaz. La versión sale de package.json al compilar (vite.config.js) y el
// commit, de VITE_COMMIT, que la imagen web recibe como ARG (frontend/Dockerfile; INV-34 le pasa el valor)
export const VERSION = __APP_VERSION__
export const COMMIT = (import.meta.env.VITE_COMMIT || '').slice(0, 7)
export const VERSION_TEXTO = COMMIT ? `v${VERSION} · ${COMMIT}` : `v${VERSION}`
