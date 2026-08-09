import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { applyTheme } from './utils/theme'
import './tokens/tokens.css'
import './styles/global.css'
import './styles/auth.css'
import './styles/events.css'
import './styles/event-detail.css'
import './styles/dashboard.css'
import './styles/gift-wall.css'
import './styles/image-upload.css'
import './styles/header.css'

// 暗色模式：渲染前先应用主题，避免首帧闪白
applyTheme()

// PWA：注册 service worker（仅生产构建；dev 由 vite 托管无 /sw.js）
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* 注册失败（如非 HTTPS）静默降级为普通网页 */
    })
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
