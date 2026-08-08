import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './tokens/tokens.css'
import './styles/global.css'
import './styles/auth.css'
import './styles/events.css'
import './styles/event-detail.css'
import './styles/dashboard.css'
import './styles/gift-wall.css'
import './styles/image-upload.css'
import './styles/header.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
