// 列表封面缩略图验收（mine 页有带封面活动了）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r10'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  const thumbs = await page.evaluate(() => [...document.querySelectorAll('.event-card img')].map(i => ({ w: i.offsetWidth, h: i.offsetHeight, visible: i.offsetHeight > 0 })))
  console.log('封面缩略图:', JSON.stringify(thumbs))
  await page.screenshot({ path: `${OUT}/03-cover-list.png` })
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
