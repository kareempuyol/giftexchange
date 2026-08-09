// 验证：meta-grid 与 flow-steps 间距
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r11'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events/L9UMHF`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2500))

  const gap = await page.evaluate(() => {
    const meta = document.querySelector('.event-meta-grid')
    const steps = document.querySelector('.flow-steps')
    if (!meta || !steps) return 'no elements'
    const mr = meta.getBoundingClientRect()
    const sr = steps.getBoundingClientRect()
    return { metaBottom: Math.round(mr.bottom), stepsTop: Math.round(sr.top), gap: Math.round(sr.top - mr.bottom) }
  })
  console.log('间距:', JSON.stringify(gap))

  await page.screenshot({ path: `${OUT}/07-gap-fixed.png` })
  console.log('截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
