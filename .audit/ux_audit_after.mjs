// ============================================================
// UX 打磨波次1-B：修复后全面验证
//  - 375px 横滚复检（含新空态/错误态页面）
//  - 新用户空态截图（mine/joined/archived/public 无结果）
//  - 错误边界实测（响应拦截注入崩溃数据）
//  - 点击目标 ≥40px 复检
// 用法: node ux_audit_after.mjs
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const PORT = process.argv.includes('--port') ? process.argv[process.argv.indexOf('--port') + 1] : '8080'
const BASE = `http://127.0.0.1:${PORT}`
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'ux-shots')
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const ALICE = { username: 'e2e_alice_mslziob9', password: 'Alice1234' }
const FRESH = { username: `ux_fresh_${Date.now().toString(36)}`, password: 'Fresh123' }

async function newPage(browser, ctx) {
  const page = await browser.newPage()
  await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 })
  return page
}

async function login(page, u) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  await page.type('input[placeholder="用户名"]', u.username)
  await page.type('input[placeholder="密码"]', u.password)
  await page.click('button[type="submit"]')
  await page.waitForFunction(() => !location.pathname.includes('/login'), { timeout: 20000 })
  await sleep(400)
}

async function audit(page, name) {
  await sleep(500)
  const m = await page.evaluate(() => {
    const vw = window.innerWidth
    const sw = document.documentElement.scrollWidth
    const off = []
    if (sw > vw + 1) {
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect()
        if (r.right > vw + 1 && r.width > 4) {
          const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 2).join('.') : el.tagName
          off.push(`${el.tagName}.${cls} right=${Math.round(r.right)}`)
          if (off.length >= 6) break
        }
      }
    }
    return { vw, sw, overflow: sw > vw + 1, off }
  })
  console.log(`[${m.overflow ? 'OVERFLOW' : 'ok'}] ${name} scrollW=${m.sw}${m.off.length ? '  ' + m.off.join(' | ') : ''}`)
  await page.screenshot({ path: path.join(OUT, `${name}.png`) })
  return m
}

async function tapTargets(page, name) {
  const small = await page.evaluate(() => {
    const vw = window.innerWidth
    const out = []
    for (const el of document.querySelectorAll('button, a, input[type="checkbox"], input[type="radio"]')) {
      const r = el.getBoundingClientRect()
      const st = getComputedStyle(el)
      if (r.width === 0 || r.height === 0 || st.visibility === 'hidden' || st.display === 'none') continue
      if (r.left >= vw || r.right <= 0) continue
      if (r.height < 40 || r.width < 40) {
        const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 2).join('.') : el.tagName
        out.push(`${el.tagName}.${cls} ${Math.round(r.width)}x${Math.round(r.height)} "${(el.textContent || '').trim().slice(0, 10)}"`)
      }
    }
    return out
  })
  console.log(`[tap-targets] ${name}: ${small.length ? small.join(' ; ') : '全部 ≥40px'}`)
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })

// ================= 新用户：注册 + 建公开活动（空态素材） =================
const fresh = await newPage(browser)
await fresh.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
await fresh.type('input[placeholder="用户名"]', FRESH.username)
await fresh.type('input[placeholder="邮箱"]', `${FRESH.username}@test.com`)
await fresh.type('input[placeholder="密码"]', FRESH.password)
await fresh.type('input[placeholder="确认密码"]', FRESH.password)
await fresh.click('button[type="submit"]')
await fresh.waitForFunction(() => !location.pathname.includes('/register'), { timeout: 20000 })
await sleep(500)
console.log('fresh user registered:', FRESH.username)

// 创建公开活动（通过 API，快；页面空态由 /events 与详情页展示）
const freshCode = await fresh.evaluate(async (u) => {
  const token = localStorage.getItem('gift_token')
  const res = await fetch('/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ title: 'UX 空态验证活动', budget: 100, isPublic: true, matchVisibility: 'private' }),
  })
  const body = await res.json()
  return body.data?.code || ''
})
console.log('fresh event created:', freshCode)

// 空态页面（fresh user 无任何活动）
await fresh.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await audit(fresh, 'A01-events-mine-empty')
await fresh.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.includes('我参与的'))?.click() })
await sleep(600)
await audit(fresh, 'A02-events-joined-empty')
await fresh.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.includes('发现活动'))?.click() })
await sleep(600)
await fresh.type('input[placeholder="搜索活动名称 / 邀请码"]', 'zzzz-不存在-zzzz')
await fresh.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '搜索')?.click() })
await sleep(800)
await audit(fresh, 'A03-events-public-no-result')
// 清空搜索 → 公开列表应有新活动
await fresh.evaluate(() => {
  const input = document.querySelector('input[placeholder="搜索活动名称 / 邀请码"]')
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(input, '')
  input.dispatchEvent(new Event('input', { bubbles: true }))
  ;[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '搜索')?.click()
})
await sleep(800)
await audit(fresh, 'A04-events-public-found')
await fresh.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.includes('已归档'))?.click() })
await sleep(600)
await audit(fresh, 'A05-events-archived-empty')
// 详情（自己创建，0 参与者 → 参与者空态）
await fresh.goto(`${BASE}/events/${freshCode}`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(fresh, 'A06-event-detail-participants-empty')
await fresh.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.includes('加入这个活动'))?.click() })
await sleep(400)
await audit(fresh, 'A06b-join-form')
await fresh.click('.modal-overlay .modal .btn-secondary') // 取消
await fresh.goto(`${BASE}/events/${freshCode}/dashboard`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(fresh, 'A07-dashboard-empty')
await fresh.goto(`${BASE}/events/${freshCode}/gift-wall`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(fresh, 'A08-gift-wall-locked-empty')
await fresh.close()

// ================= alice：数据丰富页面 =================
const alice = await newPage(browser)
await login(alice, ALICE)
await alice.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(alice, 'B01-events-mine')
await tapTargets(alice, 'B01-events-mine')
await alice.evaluate(() => { [...document.querySelectorAll('button')].find((b) => b.textContent.includes('发现活动'))?.click() })
await sleep(600)
await audit(alice, 'B02-events-public')
await alice.goto(`${BASE}/events/AW9BCN`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(alice, 'B03-event-detail-drawn')
await tapTargets(alice, 'B03-event-detail-drawn')
await alice.goto(`${BASE}/events/AW9BCN/dashboard`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(alice, 'B04-dashboard')
await alice.goto(`${BASE}/events/AW9BCN/gift-wall`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(alice, 'B05-gift-wall-unlocked')
await tapTargets(alice, 'B05-gift-wall-unlocked')
await alice.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
await sleep(400)
await audit(alice, 'B06-create')
await alice.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
await sleep(500)
await audit(alice, 'B07-profile')
await alice.click('.notif-bell')
await sleep(500)
await audit(alice, 'B08-notif-panel-open')
// 复用同一登录会话做错误边界实测（不再二次登录，避免触发登录限速）

// ================= 错误边界实测（响应拦截注入崩溃数据） =================
// 1) App 级：礼物墙接口返回畸形数据（items 含 null）→ GiftWallPage 渲染崩溃 → App 兜底
await alice.setRequestInterception(true)
alice.on('request', (req) => {
  if (req.url().includes('/api/events/AW9BCN/gift-wall')) {
    req.respond({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, data: { unlocked: true, posted: 1, total: 3, progress: { posted: 1, total: 3, unlocked: true, remaining: 2 }, items: [null] }, message: 'ok' }),
    })
  } else {
    req.continue()
  }
})
await alice.goto(`${BASE}/events/AW9BCN/gift-wall`, { waitUntil: 'networkidle2' })
await sleep(800)
const appBoundary = await alice.evaluate(() => ({
  boundary: !!document.querySelector('.error-boundary'),
  text: document.querySelector('.error-boundary')?.textContent?.slice(0, 40) || document.body.textContent.slice(0, 60),
}))
console.log('[ErrorBoundary App级]', JSON.stringify(appBoundary))
await audit(alice, 'D01-error-boundary-app')

// 2) 详情页级：my-match 返回 preference=null → 详情页渲染崩溃 → 详情级兜底（Header 仍在）
alice.removeAllListeners('request')
alice.on('request', (req) => {
  if (req.url().includes('/api/events/AW9BCN/my-match')) {
    req.respond({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, data: { matchId: 1, receiverDisplayName: '测试', preference: null }, message: 'ok' }),
    })
  } else {
    req.continue()
  }
})
await alice.goto(`${BASE}/events/AW9BCN`, { waitUntil: 'networkidle2' })
await sleep(800)
const detailBoundary = await alice.evaluate(() => ({
  boundary: !!document.querySelector('.error-boundary'),
  headerAlive: !!document.querySelector('.app-header'),
}))
console.log('[ErrorBoundary 详情级]', JSON.stringify(detailBoundary))
await audit(alice, 'D02-error-boundary-detail')
await alice.close()

// ================= 未登录页面 =================
const guest = await newPage(browser)
for (const [name, url] of [['C01-login', '/login'], ['C02-register', '/register'], ['C03-forgot', '/forgot-password']]) {
  await guest.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
  await audit(guest, name)
}

await browser.close()
console.log('\ndone')
