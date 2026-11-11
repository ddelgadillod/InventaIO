import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App'
// INV-68 (U5): DM Sans va con la aplicación, sin Google Fonts: un archivo variable para los pesos 400 a 700
import '@fontsource-variable/dm-sans'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
