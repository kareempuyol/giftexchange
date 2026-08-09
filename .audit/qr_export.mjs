// 导出海报 canvas 为高清 PNG（原尺寸 750x1000）→ 供解码验证
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r11'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events/L9UMHF`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2500))
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('邀请海报'))
    if (btns.length) btns[0].click()
  })
  await new Promise(r => setTimeout(r, 1500))

  // 直接从 canvas 取高清数据（750x1000 原尺寸）
  const b64 = await page.evaluate(() => {
    const c = document.querySelector('canvas')
    if (!c) return ''
    return c.toDataURL('image/png')
  })
  if (b64) {
    const buf = Buffer.from(b64.split(',')[1], 'base64')
    fs.writeFileSync(`${OUT}/09-poster-hd.png`, buf)
    console.log('高清海报已导出', buf.length, 'bytes')
  } else {
    console.log('无 canvas')
  }
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
