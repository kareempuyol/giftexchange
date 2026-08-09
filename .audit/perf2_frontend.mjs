// ============================================================
// 前端性能复测：首屏加载指标 + 主 bundle 传输大小 + 懒加载验证
// - /login（游客）：TTFB / DOMContentLoaded / Load + 断言不加载海报 chunk
// - /events（登录 verify_user）：同上 + 断言不加载详情 chunk
// 输出 .audit/perf2-frontend-results.json
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// 当前构建产物（与 wxcloudrun/static/assets/ 对齐；以下均为文件名 basename）
const MAIN_BUNDLE = /^index-[A-Za-z0-9_-]+\.js$/
const DETAIL_CHUNK = /^EventDetailPage-[A-Za-z0-9_-]+\.js$/
const POSTER_CHUNK = /^PosterModal-[A-Za-z0-9_-]+\.js$/
const ALL_PAGE_CHUNKS = /^(EventDetailPage|PosterModal|CreateEventPage|DashboardPage|GiftWallPage|ProfilePage|ImageUpload)-[A-Za-z0-9_-]+\.js$/

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
})

async function collectMetrics(page, label, targetPath) {
  await page.setViewport({ width: 390, height: 844 })
  const requests = []
  page.on('request', (req) => {
    const u = req.url()
    if (u.startsWith(BASE) && /\.js$/.test(u)) requests.push(u.split('/').pop())
  })
  await page.goto(`${BASE}${targetPath}`, { waitUntil: 'networkidle0', timeout: 30000 })
  await new Promise((r) => setTimeout(r, 300))
  const nav = await page.evaluate(() => {
    const t = performance.getEntriesByType('navigation')[0]
    return t ? {
      ttfbMs: Math.round(t.responseStart),
      domContentLoadedMs: Math.round(t.domContentLoadedEventEnd),
      loadMs: Math.round(t.loadEventEnd),
      transferSize: t.transferSize,
    } : null
  })
  const resources = await page.evaluate(() =>
    performance.getEntriesByType('resource')
      .filter((r) => r.name.includes('/assets/') && r.name.endsWith('.js'))
      .map((r) => ({ name: r.name.split('/').pop(), transferSize: r.transferSize, durationMs: Math.round(r.duration) }))
  )
  const main = resources.find((r) => MAIN_BUNDLE.test(r.name))
  const jsRequests = [...new Set(requests)]
  return { label, nav, resources, mainBundle: main, jsRequests }
}

const guest = await browser.createBrowserContext()
const guestPage = await guest.newPage()
const login = await collectMetrics(guestPage, 'login(guest)', '/login')

// 登录态 /events
const auth = await browser.createBrowserContext()
const authPage = await auth.newPage()
await authPage.goto(`${BASE}/events`, { waitUntil: 'domcontentloaded' })
// 通过真实登录拿 token（verify_user）后注入
const loginRes = await fetch(`${BASE}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'verify_user', password: 'Verify123' }),
})
const loginJson = await loginRes.json()
await authPage.evaluate((tok) => localStorage.setItem('gift_token', tok), loginJson.data.token)
const events = await collectMetrics(authPage, 'events(logged-in)', '/events')

// ---- 懒加载断言 ----
const assertions = [
  { name: '/login 不加载海报 chunk（PosterModal）', pass: !login.jsRequests.some((u) => POSTER_CHUNK.test(u)) },
  { name: '/login 不加载详情 chunk（EventDetailPage）', pass: !login.jsRequests.some((u) => DETAIL_CHUNK.test(u)) },
  { name: '/login 不加载任何页面懒加载 chunk', pass: !login.jsRequests.some((u) => ALL_PAGE_CHUNKS.test(u)) },
  { name: '/events 不加载详情 chunk（EventDetailPage）', pass: !events.jsRequests.some((u) => DETAIL_CHUNK.test(u)) },
  { name: '/events 不加载海报 chunk（PosterModal）', pass: !events.jsRequests.some((u) => POSTER_CHUNK.test(u)) },
  { name: '/events 主 bundle 已加载', pass: !!events.mainBundle },
]

// 真实性校验：确认 /events 页面确实为登录后的列表页（非重定向到 /login）
const eventsPageState = await authPage.evaluate(() => ({
  path: location.pathname,
  hasList: !!document.querySelector('.event-list') || document.body.innerText.includes('我的活动'),
  hasHeaderUser: !!document.querySelector('.app-username'),
}))
assertions.push({ name: '/events 为登录态列表页（未重定向）', pass: eventsPageState.path === '/events' && eventsPageState.hasList && eventsPageState.hasHeaderUser })
for (const a of assertions) console.log(`  [${a.pass ? 'PASS' : 'FAIL'}] ${a.name}`)

const out = {
  runAt: new Date().toISOString(),
  login: {
    nav: login.nav,
    mainBundle: login.mainBundle,
    allJs: login.resources,
    jsRequests: login.jsRequests,
  },
  events: {
    nav: events.nav,
    mainBundle: events.mainBundle,
    allJs: events.resources,
    jsRequests: events.jsRequests,
  },
  assertions,
  passed: assertions.filter((a) => a.pass).length,
  total: assertions.length,
}
fs.writeFileSync(path.join(__dirname, 'perf2-frontend-results.json'), JSON.stringify(out, null, 2))
console.log('\n--- /login nav ---', JSON.stringify(login.nav))
console.log('--- /events nav ---', JSON.stringify(events.nav))
console.log(`--- main bundle: login=${login.mainBundle?.name} (${login.mainBundle?.transferSize}B) | events=${events.mainBundle?.name} (${events.mainBundle?.transferSize}B)`)
console.log(`断言 ${out.passed}/${out.total}`)
await browser.close()
process.exit(out.passed === out.total ? 0 : 1)
