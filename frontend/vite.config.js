import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'

// INV-68 (U2): la versión que muestran la barra superior y el login sale de package.json (src/version.js)
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'))

// La primera consulta de recomendaciones tarda hasta 40 s en frío y el Core
// API espera a ml_service hasta 120 s: el proxy no debe cortar antes (G4).
// En producción, Nginx espera 135 s (nginx.conf)
const PROXY_TIMEOUT_MS = 130_000

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(version) },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: PROXY_TIMEOUT_MS,
        proxyTimeout: PROXY_TIMEOUT_MS,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // Cobertura de H5: la base compartida, las páginas adaptadas y las vistas nuevas (V9)
      include: [
        'src/api/**', 'src/hooks/**', 'src/utils/**', 'src/components/**', 'src/rutas.js',
        'src/pages/Dashboard.jsx', 'src/pages/Inventario.jsx', 'src/pages/Alertas.jsx', 'src/pages/Reportes.jsx',
        'src/pages/Login.jsx', 'src/pages/Predicciones.jsx', 'src/pages/Recomendaciones.jsx',
      ],
      exclude: ['src/**/*.test.{js,jsx}', 'src/test/**'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
})
