// 打开邀请海报弹窗 → 截图海报（真二维码验证）
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

  // 点"邀请海报"按钮
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('邀请海报'))
    if (btns.length) btns[0].click()
  })
  await new Promise(r => setTimeout(r, 1500))

  // 海报 canvas 截图（元素级）
  const canvas = await page.$('canvas')
  if (canvas) {
    await canvas.screenshot({ path: `${OUT}/08-poster-qr.png` })
    console.log('海报截图完成')
  } else {
    console.log('未找到 canvas')
  }

  // 校验：canvas 里二维码区域是否真的有密矩阵（非 5x5 棋盘）
  const stats = await page.evaluate(() => {
    const c = document.querySelector('canvas')
    if (!c) return null
    const ctx = c.getContext('2d')
    if (!ctx) return null
    // 邀请海报 750x1000，二维码区域约 (305, 590, 140, 140)
    const img = ctx.getImageData(305, 590, 140, 140)
    let dark = 0, total = 0
    for (let i = 0; i < img.data.length; i += 4) {
      const lum = 0.299 * img.data[i] + 0.587 * img.data[i + 1] + 0.114 * img.data[i + 2]
      total++
      if (lum < 100) dark++
    }
    return { darkRatio: (dark / total).toFixed(3), totalPx: total }
  })
  console.log('二维码区域黑像素占比:', JSON.stringify(stats))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
