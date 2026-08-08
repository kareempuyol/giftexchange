// 移动端视口截图（375px，关键页面）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const orgToken = creds.orgToken
const BASE = 'http://127.0.0.1:8080'
const OUT = process.env.HOME + '/giftexchange/ui-shots/mobile'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` })

await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.evaluate((t) => localStorage.setItem('gift_token', t), orgToken)

try {
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('01-events-mobile')
  console.log('01: 活动列表(移动)')

  await page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 600))
  await shot('02-create-mobile')
  console.log('02: 创建活动(移动)')

  await page.goto(`${BASE}/events/${creds.events.drawn}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('03-event-detail-mobile')
  console.log('03: 活动详情(移动)')

  await page.goto(`${BASE}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('04-giftwall-mobile')
  console.log('04: 礼物墙(移动)')

  await page.goto(`${BASE}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 600))
  await shot('05-invite-mobile')
  console.log('05: 邀请区(移动)')

  console.log('移动端截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
