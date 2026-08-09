import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建输出到后端 wxcloudrun/static/（assets），SPA 模板由 Flask 渲染
// Flask 的 render_template 优先读 wxcloudrun/templates/index.html，
// 所以构建后用 extra 步骤把 index.html 同步到 templates/
export default defineConfig({
  plugins: [react()],
  build: {
    // 明确兼容目标：es2019 = Safari 12+ / Chrome 70+ / Edge 79+ / Firefox 67+
    // （Vite 5 默认 'modules' 会保留原生 `??`，Safari 12–13.0 不支持会 SyntaxError）
    target: 'es2019',
    outDir: '../wxcloudrun/static',
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        // vendor 拆分：react 运行时与 router 各自独立 chunk（内容稳定 → 哈希长期不变，
        // 应用代码更新时浏览器只重下 app chunk，vendor 命中缓存；qrcode 留在懒加载 chunk）
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'vendor-react'
          if (id.includes('react-router') || id.includes('/history/') || id.includes('@remix-run')) return 'vendor-router'
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
})
