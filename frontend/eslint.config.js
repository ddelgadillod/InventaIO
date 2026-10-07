// InventAI/o — ESLint del frontend (INV-24, D7). `npm run lint`; el CI falla con
// los errores y reporta los avisos.
import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

// Las reglas de hooks del preset de react-hooks 7: `rules-of-hooks` es error; las
// demás (`exhaustive-deps` y las del compilador de React, como `refs` y
// `set-state-in-effect`) son avisos. useConsulta y AuthContext las incumplen por
// diseño y su refactor queda fuera de INV-24
const reglasHooks = Object.fromEntries(
  Object.keys(reactHooks.configs.flat.recommended.rules).map((regla) => [
    regla,
    regla === 'react-hooks/rules-of-hooks' ? 'error' : 'warn',
  ]),
)

export default [
  { ignores: ['dist', 'coverage'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...js.configs.recommended.rules,
      ...reglasHooks,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  // La configuración de Vite y de ESLint corren en Node
  { files: ['vite.config.js', 'eslint.config.js'], languageOptions: { globals: { ...globals.node } } },
]
