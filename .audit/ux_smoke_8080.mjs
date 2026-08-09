// 8080 最终冒烟：登录 + 关键页渲染（非白屏）
import puppeteer from 'puppeteer-core'
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812 })
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.type('input[placeholder="用户名"]', 'e2e_alice_mslziob9')
await page.type('input[placeholder="密码"]', 'Alice1234')
await page.click('button[type="submit"]')
await page.waitForFunction(() => !location.pathname.includes('/login'), { timeout: 20000 })
const checks = []
for (const url of ['/events', '/events/AW9BCN', '/events/AW9BCN/gift-wall', '/events/new']) {
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
  const r = await page.evaluate(() => ({
    mainText: document.querySelector('.app-main')?.textContent?.length || 0,
    boundary: !!document.querySelector('.error-boundary'),
    sw: document.documentElement.scrollWidth,
  }))
  checks.push({ url, ...r })
}
console.log(JSON.stringify(checks, null, 1))
await browser.close()
