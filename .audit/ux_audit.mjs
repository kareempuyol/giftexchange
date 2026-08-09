// ============================================================
// UX 打磨波次1-B：375px 移动端横滚审计 + 截图
// 用法: node .audit/ux_audit.mjs [--only=NAME,...] [--out=ux-shots]
// 每页: 测量 document.scrollWidth vs innerWidth，定位溢出元素，截图
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : 'ux-shots')
fs.mkdirSync(OUT, { recursive: true })

const only = (() => {
  const i = process.argv.indexOf('--only')
  return i >= 0 ? new Set(process.argv[i + 1].split(',')) : null
})()

const USER = { username: 'verify_user', password: 'Verify123' }

const PAGES = [
  { name: '01-events-mine', url: '/events' },
  { name: '02-events-public', url: '/events', tab: 'public' },
  { name: '03-event-detail-open', url: '/events/J38ZGK' },        // open, 0 参与者
  { name: '04-event-detail-drawn', url: '/events/RM6BF4' },       // drawn, 有任务
  { name: '05-dashboard', url: '/events/RM6BF4/dashboard' },
  { name: '06-gift-wall-locked', url: '/events/RM6BF4/gift-wall' },
  { name: '07-create', url: '/events/new' },
  { name: '08-profile', url: '/profile' },
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function audit(page, name) {
  await sleep(600)
  const metrics = await page.evaluate(() => {
    const vw = window.innerWidth
    const sw = document.documentElement.scrollWidth
    const offenders = []
    if (sw > vw + 1) {
      // 找出宽出视口的元素（取样前 8 个）
      const all = document.querySelectorAll('body *')
      for (const el of all) {
        const r = el.getBoundingClientRect()
        if (r.right > vw + 1 && r.width > 4) {
          const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 3).join('.') : el.tagName
          offenders.push(`${el.tagName}.${cls} right=${Math.round(r.right)} w=${Math.round(r.width)}`)
          if (offenders.length >= 8) break
        }
      }
    }
    return { vw, sw, overflow: sw > vw + 1, offenders }
  })
  const flag = metrics.overflow ? 'OVERFLOW' : 'ok'
  console.log(`[${flag}] ${name}  vw=${metrics.vw} scrollW=${metrics.sw}`)
  for (const o of metrics.offenders) console.log(`        ${o}`)
  await page.screenshot({ path: path.join(OUT, `${name}.png`) })
  return metrics
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 })

// ---- 登录 ----
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.type('input[placeholder="用户名"]', USER.username)
await page.type('input[placeholder="密码"]', USER.password)
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.click('button[type="submit"]')])
console.log('logged in, url =', page.url())

const results = {}
for (const p of PAGES) {
  if (only && !only.has(p.name)) continue
  await page.goto(`${BASE}${p.url}`, { waitUntil: 'networkidle2' })
  if (p.tab === 'public') {
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')]
      const b = btns.find((x) => x.textContent.includes('发现活动'))
      b?.click()
    })
    await sleep(800)
  }
  results[p.name] = await audit(page, p.name)
}

// ---- 未登录页面 ----
for (const [name, url] of [['09-login', '/login'], ['10-register', '/register'], ['11-forgot', '/forgot-password']]) {
  if (only && !only.has(name)) continue
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
  results[name] = await audit(page, name)
}

await browser.close()
const bad = Object.values(results).filter((r) => r.overflow)
console.log(`\n=== ${Object.keys(results).length} pages, ${bad.length} with horizontal overflow ===`)
for (const r of bad) console.log(`  - ${r.offenders.join(' | ')}`)
