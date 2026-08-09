// 补充：真正无活动的「我创建的」空态截图（新用户不建活动直接访问 /events）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8081'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'ux-shots')
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const USER = { username: `ux_empty_${Date.now().toString(36)}`, password: 'Empty123' }

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 2 })

await page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
await page.type('input[placeholder="用户名"]', USER.username)
await page.type('input[placeholder="邮箱"]', `${USER.username}@test.com`)
await page.type('input[placeholder="密码"]', USER.password)
await page.type('input[placeholder="确认密码"]', USER.password)
await page.click('button[type="submit"]')
await page.waitForFunction(() => !location.pathname.includes('/register'), { timeout: 20000 })
await sleep(600)
console.log('registered', USER.username, '→', page.url())

const state = await page.evaluate(() => ({
  title: document.querySelector('.empty-title')?.textContent,
  hasCta: !!document.querySelector('.empty-state .btn-primary'),
  ctaText: document.querySelector('.empty-state .btn-primary')?.textContent?.trim(),
  sw: document.documentElement.scrollWidth,
}))
console.log('[mine-empty]', JSON.stringify(state))
await page.screenshot({ path: path.join(OUT, 'A01-events-mine-empty.png') })
await browser.close()
