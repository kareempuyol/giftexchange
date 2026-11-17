// 最终视觉终审：核心页面截图
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/final'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)

  const shots = [
    ['01-login', '/login'],
    ['02-events', '/events'],
    ['03-profile', '/profile'],
  ]
  for (const [name, path] of shots) {
    await page.goto(`${PUBLIC}${path}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 1800))
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
    console.log(name, 'ok')
  }
  // 礼物墙（demo 活动解锁态）
  await page.evaluate((t) => localStorage.setItem('gift_token', t), '')
  await page.evaluate(async () => {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'demo_alice', password: 'Demo1234' }) })
    const d = await r.json()
    if (d.data?.token) localStorage.setItem('gift_token', d.data.token)
  })
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const code = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    const ev = (d.data || []).find(e => e.title.includes('圣诞'))
    return ev ? ev.code : ''
  })
  if (code) {
    await page.goto(`${PUBLIC}/events/${code}/gift-wall`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2000))
    await page.screenshot({ path: `${OUT}/04-giftwall.png`, fullPage: true })
    console.log('giftwall ok')
  }
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
