import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建输出到后端 wxcloudrun/static/（assets），SPA 模板由 Flask 渲染
// Flask 的 render_template 优先读 wxcloudrun/templates/index.html，
// 所以构建后用 extra 步骤把 index.html 同步到 templates/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../wxcloudrun/static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
})
