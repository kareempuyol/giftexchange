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
await new Promise((r) => setTimeout(r, 2500))
const state = await page.evaluate(() => ({
  url: location.pathname,
  errors: [...document.querySelectorAll('.form-error')].map((e) => e.textContent),
  body: document.body.textContent.slice(0, 200),
}))
console.log(JSON.stringify(state, null, 2))
await browser.close()
