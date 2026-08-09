// 截图活动详情页步骤条区域（完整页面长截图）
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

  // 完整页长截图（fullPage）
  await page.screenshot({ path: `${OUT}/02-fullpage.png`, fullPage: true })

  // 定位 flow-steps 并单独截它
  const stepsBox = await page.evaluate(() => {
    const el = document.querySelector('.flow-steps')
    if (!el) return null
    const r = el.getBoundingClientRect()
    // 检查每个 label 是否溢出/重叠
    const labels = [...el.querySelectorAll('.flow-step-label')].map(l => {
      const lr = l.getBoundingClientRect()
      return { text: l.textContent.trim(), w: Math.round(lr.width), scrollW: l.scrollWidth, overflow: l.scrollWidth > l.clientWidth }
    })
    const dots = [...el.querySelectorAll('.flow-step-dot')].map(d => {
      const dr = d.getBoundingClientRect()
      return { w: Math.round(dr.width), h: Math.round(dr.height) }
    })
    const wraps = [...el.querySelectorAll('.flow-step-wrap')].map(w => {
      const wr = w.getBoundingClientRect()
      return { w: Math.round(wr.width), h: Math.round(wr.height) }
    })
    return { top: Math.round(r.top), h: Math.round(r.height), labels, dots, wraps }
  })
  console.log('flow-steps 详情:', JSON.stringify(stepsBox, null, 1))

  // 滚动到步骤条位置截图
  if (stepsBox) {
    await page.evaluate(() => {
      const el = document.querySelector('.flow-steps')
      if (el) el.scrollIntoView({ block: 'center' })
    })
    await new Promise(r => setTimeout(r, 800))
    await page.screenshot({ path: `${OUT}/03-steps-closeup.png` })
  }
  console.log('截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
