// 验证新布局：FlowSteps 移到 meta 之后 + 截图
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
  await page.screenshot({ path: `${OUT}/01-detail-fixed.png` })

  // 检查 DOM 顺序
  const order = await page.evaluate(() => {
    const card = document.querySelector('.gift-card')
    if (!card) return 'no card'
    const text = card.innerText
    const iBadge = text.indexOf('公开活动')
    const iInvite = text.indexOf('邀请码')
    const iMeta = text.indexOf('预算')
    const iFlow = text.indexOf('送礼进行中')
    const iHint = text.indexOf('报名截止前加入')
    const iBtn = text.indexOf('加入这个活动')
    return { iBadge, iInvite, iMeta, iFlow, iHint, iBtn }
  })
  console.log('顺序索引:', JSON.stringify(order))
  const ok = order.iBadge < order.iInvite && order.iInvite < order.iMeta && order.iMeta < order.iFlow && order.iFlow < order.iBtn
  console.log('新顺序正确（Badge→邀请→信息→步骤条→按钮）:', ok)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
