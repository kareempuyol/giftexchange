// 状态机进度条前端验收
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r9'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)

  // 找一个已抽签活动（verify_user 参与的 drawn 活动）
  const code = await page.evaluate(async () => {
    const res = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const data = await res.json()
    const ev = (data.data || []).find(e => e.status === 'drawn')
    return ev ? ev.code : ''
  })
  if (!code) { console.log('无已抽签活动'); process.exit(1) }

  await page.goto(`${PUBLIC}/events/${code}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const hasStepper = await page.evaluate(() => {
    const steps = [...document.querySelectorAll('.ship-step, .shipment-step, [class*=step]')]
    return steps.length
  })
  const bodyText = await page.evaluate(() => document.body.innerText)
  const hasLabels = ['待购买', '已发货', '已签收', '已晒图'].filter(t => bodyText.includes(t))
  console.log('进度条元素:', hasStepper, '| 标签命中:', hasLabels.join(','))
  await page.screenshot({ path: `${OUT}/01-stepper.png` })

  console.log('状态机前端验收完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
