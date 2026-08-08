// R3 动效连拍：点击揭晓瞬间多帧捕捉
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r3_frames'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 定位第一张卡片区域，准备连拍
  const firstCard = await page.$('.gw-item-card')
  if (!firstCard) { console.log('未找到礼物卡片'); process.exit(1) }
  const box = await firstCard.boundingBox()

  // 点击揭晓（触发动画）
  const mask = await page.$('.gw-mask')
  if (!mask) { console.log('未找到遮罩'); process.exit(1) }
  await mask.click()

  // 立即连拍：40ms 间隔 × 15 帧（覆盖 0.55s 翻转 + 0.45s 弹入）
  const clips = []
  for (let i = 0; i < 15; i++) {
    await new Promise(r => setTimeout(r, 40))
    const shot = await page.screenshot({
      path: `${OUT}/frame-${String(i).padStart(2, '0')}.png`,
      clip: { x: Math.max(0, box.x - 20), y: Math.max(0, box.y - 20), width: Math.min(600, box.width + 40), height: Math.min(500, box.height + 40) }
    })
    clips.push(shot.length)
  }
  console.log('连拍完成 12 帧:', OUT)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
