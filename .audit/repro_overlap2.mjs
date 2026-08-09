// 直接用已知 code 复现
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

  // 试两个候选 code
  for (const code of ['8715bec9-c612-4810-b8c4-db670a8b60a2']) {
    await page.goto(`${PUBLIC}/events/${code}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2500))
    const title = await page.evaluate(() => document.querySelector('.page-title')?.textContent || '')
    console.log(`code ${code.slice(0,8)} → 标题: ${title}`)
    if (title.includes('隐私')) break
  }

  await page.screenshot({ path: `${OUT}/05-repro-fullpage.png`, fullPage: true })

  // 文字重叠检测
  const overlaps = await page.evaluate(() => {
    const issues = []
    const els = [...document.querySelectorAll('.gift-card *')].filter(el => {
      const t = el.textContent.trim()
      return t && t.length > 0 && el.children.length === 0
    })
    for (const el of els) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      for (const other of els) {
        if (other === el) continue
        const r2 = other.getBoundingClientRect()
        if (r2.width === 0 || r2.height === 0) continue
        const x1 = Math.max(r.left, r2.left)
        const y1 = Math.max(r.top, r2.top)
        const x2 = Math.min(r.right, r2.right)
        const y2 = Math.min(r.bottom, r2.bottom)
        if (x2 > x1 && y2 > y1) {
          const overlapArea = (x2 - x1) * (y2 - y1)
          const minArea = Math.min(r.width * r.height, r2.width * r2.height)
          if (minArea > 0 && overlapArea / minArea > 0.3) {
            issues.push(`${el.tagName}「${el.textContent.trim().slice(0, 15)}」× ${other.tagName}「${other.textContent.trim().slice(0, 15)}」`)
          }
        }
      }
    }
    return [...new Set(issues)].slice(0, 15)
  })
  console.log('文字重叠检测:', overlaps.length === 0 ? '无重叠 ✅' : '')
  overlaps.forEach(o => console.log('  ⚠️', o))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
