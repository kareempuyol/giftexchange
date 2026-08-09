// 复验：0 参与者礼物墙文案 + 375px 无溢出
import puppeteer from 'puppeteer-core'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8081'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'ux-shots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 })
await page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
const u = `ux_wall_${Date.now().toString(36)}`
await page.type('input[placeholder="用户名"]', u)
await page.type('input[placeholder="邮箱"]', `${u}@test.com`)
await page.type('input[placeholder="密码"]', 'Wall123')
await page.type('input[placeholder="确认密码"]', 'Wall123')
await page.click('button[type="submit"]')
await page.waitForFunction(() => !location.pathname.includes('/register'), { timeout: 20000 })
const code = await page.evaluate(async () => {
  const token = localStorage.getItem('gift_token')
  const res = await fetch('/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ title: '空活动墙验证', budget: 100, isPublic: true }),
  })
  return (await res.json()).data.code
})
await page.goto(`${BASE}/events/${code}/gift-wall`, { waitUntil: 'networkidle2' })
await sleep(600)
const r = await page.evaluate(() => ({
  text: document.querySelector('.gw-progress-text')?.textContent?.trim(),
  hasCta: !!document.querySelector('.gw-progress-card .btn'),
  sw: document.documentElement.scrollWidth,
}))
console.log('[gw-zero-participants]', JSON.stringify(r))
await page.screenshot({ path: path.join(OUT, 'A08-gift-wall-locked-empty.png') })
await browser.close()
