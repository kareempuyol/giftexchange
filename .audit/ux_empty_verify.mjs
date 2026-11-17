// 验证空态改进：标题/CTA/邀请码按钮
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/ux2'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }])
  // 新注册用户 = 空态
  const u = 'uxv_' + Math.floor(Math.random() * 100000)
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async (u) => {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, email: u + '@e.com', password: 'Test1234' }) })
    const d = await r.json()
    localStorage.setItem('gift_token', d.data.token)
  }, u)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1800))

  const info = await page.evaluate(() => {
    const title = document.querySelector('.empty-title')
    const btns = [...document.querySelectorAll('.empty-state button, .empty-state a')]
    const t = title ? getComputedStyle(title) : null
    const main = btns.find(b => b.textContent.includes('创建第一个活动'))
    const join = btns.find(b => b.textContent.includes('用邀请码加入'))
    const ms = main ? getComputedStyle(main) : null
    const js = join ? getComputedStyle(join) : null
    return {
      title: t ? { size: t.fontSize, weight: t.fontWeight, color: t.color } : null,
      mainCta: ms ? { h: ms.height, bg: ms.backgroundColor } : null,
      joinBtn: js ? { bg: js.backgroundColor, border: js.borderColor, color: js.color } : null,
    }
  })
  console.log(JSON.stringify(info, null, 1))
  await page.screenshot({ path: `${OUT}/empty-state-v2.png` })
  console.log('shot ok')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
