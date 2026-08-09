// 补充审计：通知面板展开溢出 / 礼物墙解锁态 / 点击目标 <40px
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'ux-shots')
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 })

await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.type('input[placeholder="用户名"]', 'e2e_alice_mslziob9')
await page.type('input[placeholder="密码"]', 'Alice1234')
await page.click('button[type="submit"]')
await page.waitForFunction(() => !location.pathname.includes('/login'), { timeout: 20000 })
await sleep(400)

// 1) 通知面板展开
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await page.click('.notif-bell')
await sleep(500)
const notif = await page.evaluate(() => {
  const panel = document.querySelector('.notif-panel')
  if (!panel) return { missing: true }
  const r = panel.getBoundingClientRect()
  return { left: Math.round(r.left), right: Math.round(r.right), vw: window.innerWidth, sw: document.documentElement.scrollWidth }
})
console.log('[notif-panel]', JSON.stringify(notif))
await page.screenshot({ path: path.join(OUT, '12-notif-panel-open.png') })
await page.click('.notif-bell') // 关闭

// 2) 礼物墙解锁态（E2E 活动 AW9BCN：3/3 晒图）
await page.goto(`${BASE}/events/AW9BCN/gift-wall`, { waitUntil: 'networkidle2' })
await sleep(600)
const gw = await page.evaluate(() => {
  const unlocked = !!document.querySelector('.gw-grid') || document.body.textContent.includes('已解锁')
  return { unlocked, sw: document.documentElement.scrollWidth, vw: window.innerWidth }
})
console.log('[gift-wall-AW9BCN]', JSON.stringify(gw))
await page.screenshot({ path: path.join(OUT, '13-gift-wall-unlocked.png') })

// 3) 点击目标 <40px（可见可交互元素，375px 下）
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await sleep(500)
const targets = await page.evaluate(() => {
  const vw = window.innerWidth
  const small = []
  const els = document.querySelectorAll('button, a, input[type="checkbox"], input[type="radio"], .gw-like-btn, .gw-star, .pwd-toggle')
  for (const el of els) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || r.height === 0) continue
    const style = getComputedStyle(el)
    if (style.visibility === 'hidden' || style.display === 'none') continue
    if (r.left >= vw || r.right <= 0) continue // 屏幕外
    if (r.height < 40 || r.width < 40) {
      const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 2).join('.') : el.tagName
      small.push(`${el.tagName}.${cls} ${Math.round(r.width)}x${Math.round(r.height)} "${(el.textContent || el.placeholder || '').trim().slice(0, 12)}"`)
    }
  }
  return small
})
console.log('[tap-targets<40px @events]')
for (const t of targets) console.log('   ', t)

await browser.close()
