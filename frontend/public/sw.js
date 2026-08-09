/* 互送礼物 Service Worker
 *
 * 缓存策略（quick tunnel 域名每次变化，SW 按 origin 独立安装，scope="/" 相对路径安全）：
 * - 静态资源（/assets/* 哈希文件名、/icons/*、/manifest.json、favicon）→ cache-first
 * - 页面导航 → network-first，离线回退到缓存的应用 shell（index.html）
 * - /api/* → 不拦截（天然网络优先；含用户私有数据，不做缓存兜底，离线走页面自带错误/重试 UI）
 * - 其余（POST 等）→ 只走网络
 *
 * 发版时把 VERSION +1（旧缓存会在 activate 时清理）。
 */
const VERSION = 'v1'
const CACHE_STATIC = `gift-static-${VERSION}`
const CACHE_PAGES = `gift-pages-${VERSION}`

const PRECACHE_URLS = ['/', '/index.html', '/manifest.json', '/icons/icon-192.png', '/icons/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_STATIC)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !k.startsWith('gift-')).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return

  // 静态资源：cache-first
  if (
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname === '/manifest.json' ||
    url.pathname === '/app-icon-mondrian.svg'
  ) {
    event.respondWith(cacheFirst(req))
    return
  }

  // 页面导航：network-first，离线回退 shell
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone()
            caches.open(CACHE_PAGES).then((c) => c.put('/index.html', copy))
          }
          return res
        })
        .catch(() =>
          caches.match('/index.html').then((hit) => hit || caches.match('/'))
        )
    )
  }
})

async function cacheFirst(req) {
  const hit = await caches.match(req)
  if (hit) return hit
  const res = await fetch(req)
  if (res.ok) {
    const copy = res.clone()
    caches.open(CACHE_STATIC).then((c) => c.put(req, copy))
  }
  return res
}
