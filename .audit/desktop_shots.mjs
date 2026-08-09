// 桌面/平板三视口截图 + 响应式断言（1280×800 / 1440×900 / 768×1024）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const orgToken = creds.orgToken
const BASE = 'http://127.0.0.1:8080'
const OUT = process.env.HOME + '/giftexchange/.audit/desktop-shots'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const VIEWPORTS = [
  { name: 'w1280', width: 1280, height: 800 },
  { name: 'w1440', width: 1440, height: 900 },
  { name: 'w768', width: 768, height: 1024 },
]

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })

// 等待图片/字体稳定
const settle = (ms = 900) => new Promise((r) => setTimeout(r, ms))

for (const vp of VIEWPORTS) {
  const dir = `${OUT}/${vp.name}`
  fs.mkdirSync(dir, { recursive: true })
  const page = await browser.newPage()
  await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 })
  const shot = (name) => page.screenshot({ path: `${dir}/${name}.png`, fullPage: false })

  const report = []
  const audit = async (name, url) => {
    await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
    await settle()
    await shot(name)
    const m = await page.evaluate(() => {
      const gw = document.querySelector('.gw-grid')
      const dl = document.querySelector('.detail-layout')
      const el = document.querySelector('.event-list')
      return {
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
        gwCols: gw ? getComputedStyle(gw).gridTemplateColumns.split(' ').length : null,
        detailDisplay: dl ? getComputedStyle(dl).display : null,
        eventListDisplay: el ? getComputedStyle(el).display : null,
        h1: document.querySelectorAll('h1').length,
      }
    })
    report.push({ name, url, ...m, hScroll: m.scrollW > m.clientW + 1 })
    console.log(`${vp.name} ${name}: hScroll=${m.scrollW > m.clientW + 1} gwCols=${m.gwCols} detail=${m.detailDisplay} list=${m.eventListDisplay} h1=${m.h1}`)
  }

  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), orgToken)

  await audit('01-events', '/events')
  await audit('02-create', '/events/new')
  await audit('03-detail-drawn', `/events/${creds.events.drawn}`)
  await audit('04-detail-open', `/events/${creds.events.open}`)
  await audit('05-giftwall', `/events/${creds.events.unlocked}/gift-wall`)
  await audit('06-dashboard', `/events/${creds.events.drawn}/dashboard`)
  await audit('07-profile', '/profile')

  // 登录页单独拍（未登录布局）
  await page.evaluate(() => localStorage.removeItem('gift_token'))
  await audit('08-login', '/login')

  fs.writeFileSync(`${dir}/metrics.json`, JSON.stringify(report, null, 2))
  await page.close()
}

await browser.close()
console.log('desktop shots done')
