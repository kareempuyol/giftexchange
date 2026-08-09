// 复测：completed 活动步骤条几何 + 重叠检测 + 元素截图
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
  await page.goto(`${PUBLIC}/events/8715bec9-c612-4810-b8c4-db670a8b60a2`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2500))

  // 几何
  const geo = await page.evaluate(() => {
    const steps = document.querySelector('.flow-steps')
    if (!steps) return 'no steps'
    return [...steps.querySelectorAll('.flow-step-wrap')].map(w => {
      const r = w.getBoundingClientRect()
      return { left: Math.round(r.left), width: Math.round(r.width) }
    })
  })
  console.log('wrap 几何:', JSON.stringify(geo))

  // 重叠检测（label 之间）
  const overlaps = await page.evaluate(() => {
    const issues = []
    const labels = [...document.querySelectorAll('.flow-step-label')]
    for (const el of labels) {
      const r = el.getBoundingClientRect()
      for (const other of labels) {
        if (other === el) continue
        const r2 = other.getBoundingClientRect()
        const x1 = Math.max(r.left, r2.left), y1 = Math.max(r.top, r2.top)
        const x2 = Math.min(r.right, r2.right), y2 = Math.min(r.bottom, r2.bottom)
        if (x2 > x1 && y2 > y1) {
          const a = (x2-x1)*(y2-y1), m = Math.min(r.width*r.height, r2.width*r2.height)
          if (m > 0 && a/m > 0.2) issues.push(`${el.textContent.trim()} × ${other.textContent.trim()}`)
        }
      }
    }
    return [...new Set(issues)]
  })
  console.log('label 重叠:', overlaps.length ? overlaps : '无 ✅')

  // 元素截图
  const el = await page.$('.flow-steps')
  if (el) await el.screenshot({ path: `${OUT}/06-steps-fixed.png` })
  console.log('元素截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
