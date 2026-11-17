// 最终验证：礼物墙揭晓提示 + 退出按钮 + 复制收件信息（亮色/暗色）
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
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }])
  // 用 demo_alice（有解锁礼物墙）
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.demoToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))

  const code = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    const ev = (d.data || []).find(e => e.status === 'drawn')
    return ev ? ev.code : ''
  })
  console.log('event:', code || 'none')
  if (code) {
    await page.goto(`${PUBLIC}/events/${code}/gift-wall`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2200))
    const hint = await page.evaluate(() => {
      const el = document.querySelector('.gw-mask-hint')
      if (!el) return null
      const s = getComputedStyle(el)
      return { text: el.textContent.trim(), bg: s.backgroundColor, color: s.color }
    })
    console.log('揭晓提示:', JSON.stringify(hint))
    await page.screenshot({ path: `${OUT}/giftwall-hint.png` })

    // 退出按钮样式
    const logout = await page.evaluate(() => {
      const btn = document.querySelector('.app-logout')
      if (!btn) return null
      const s = getComputedStyle(btn)
      return { text: btn.textContent.trim(), color: s.color, weight: s.fontWeight }
    })
    console.log('退出按钮:', JSON.stringify(logout))
  }
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
