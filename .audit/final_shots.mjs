// ============================================================
// 终审截图：6 个核心页面（登录/活动列表/详情/礼物墙/个人中心/创建页）
// 移动视口 390x844，登录 verify_user
// 输出到 .audit/final-shots/
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'final-shots')
fs.mkdirSync(OUT, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
})
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 })

const shot = async (name) => {
  // 等待网络空闲后稳定渲染
  await new Promise(r => setTimeout(r, 600))
  const p = path.join(OUT, name)
  await page.screenshot({ path: p, fullPage: false })
  console.log('📸', name)
}

// 1. 登录页
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 })
await shot('01-login.png')

// React 受控输入：原生 setter + input/change 事件
async function reactType(page, selector, text) {
  const el = await page.$(selector)
  if (!el) { console.log('⚠️ 未找到:', selector); return false }
  await el.evaluate((node, value) => {
    const proto = node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set
    setter.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
    node.dispatchEvent(new Event('change', { bubbles: true }))
  }, text)
  return true
}

// 登录 verify_user
await reactType(page, 'input[placeholder="用户名"]', 'verify_user')
await reactType(page, 'input[placeholder="密码"]', 'Verify123')
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('登录'))
  btn?.click()
})
await page.waitForFunction(() => location.pathname.startsWith('/events'), { timeout: 20000 })
console.log('登录成功:', page.url())

const sleep = (ms) => new Promise(r => setTimeout(r, ms))
// 2. 活动列表
await sleep(800)
await shot('02-events.png')

// 3. 详情页（取第一个活动）
const codes = await page.evaluate(async () => {
  const token = localStorage.getItem('gift_token')
  const r = await fetch('/api/events/mine', { headers: { Authorization: `Bearer ${token}` } })
  const d = await r.json()
  const arr = Array.isArray(d.data) ? d.data : (d.data?.events || [])
  return arr.map(e => e.code || e.short_code || e.id)
})
const code = codes[0]
if (code) {
  await page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2', timeout: 30000 })
  await shot('03-detail.png')
  // 4. 礼物墙
  await page.goto(`${BASE}/events/${code}/gift-wall`, { waitUntil: 'networkidle2', timeout: 30000 })
  await shot('04-gift-wall.png')
} else {
  console.log('⚠️ 无活动可截详情/礼物墙')
}

// 5. 个人中心
await page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2', timeout: 30000 })
await shot('05-profile.png')

// 6. 创建页
await page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2', timeout: 30000 })
await shot('06-create.png')

await browser.close()
console.log('完成，输出目录:', OUT)
