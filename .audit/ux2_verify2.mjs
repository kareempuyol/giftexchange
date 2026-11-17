// 双主题验证：tab 激活态 + 复制收件信息 + 选填标注
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/ux2'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  for (const scheme of ['light', 'dark']) {
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
    await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
    await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
    await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 1800))
    const tab = await page.evaluate(() => {
      const el = document.querySelector('.tab-active')
      if (!el) return null
      const s = getComputedStyle(el)
      return { bg: s.backgroundColor, color: s.color, weight: s.fontWeight, theme: document.documentElement.dataset.theme || 'light' }
    })
    console.log(`[${scheme}] tab-active:`, JSON.stringify(tab))
    await page.screenshot({ path: `${OUT}/tabs-${scheme}.png` })
  }

  // 亮色下看复制收件信息（截图）
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }])
  const code = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    const ev = (d.data || []).find(e => e.status === 'drawn')
    return ev ? ev.code : ''
  })
  if (code) {
    await page.goto(`${PUBLIC}/events/${code}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2200))
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('复制收件信息'))
      if (btn) btn.scrollIntoView({ block: 'center' })
    })
    await new Promise(r => setTimeout(r, 600))
    await page.screenshot({ path: `${OUT}/copy-contact-light.png` })
    console.log('copy contact shot ok')
  }
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
