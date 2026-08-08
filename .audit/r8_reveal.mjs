// 揭晓后隐私展示截图
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const d = JSON.parse(fs.readFileSync('/tmp/privacy_final.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r8'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), d.token)
  await page.goto(`${PUBLIC}/events/${d.code}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 全部揭晓
  const masks = await page.$$('.gw-mask')
  for (const m of masks) { await m.click(); await new Promise(r => setTimeout(r, 700)) }
  await new Promise(r => setTimeout(r, 1000))
  await page.screenshot({ path: `${OUT}/03-revealed-wall.png` })
  console.log('揭晓完成截图')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
