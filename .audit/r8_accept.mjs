// 晒图隐私前端验收 v2：text/blur/photo 卡片展示
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const d = JSON.parse(fs.readFileSync('/tmp/privacy_final.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r8'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), d.token)

  await page.goto(`${PUBLIC}/events/${d.code}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  await page.screenshot({ path: `${OUT}/01-wall.png` })

  const info = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.gw-item-card')]
    const badges = [...document.querySelectorAll('.gw-text-badge')].map(b => b.textContent.trim())
    const photos = [...document.querySelectorAll('.gw-photo-wrap')].length
    const blur = [...document.querySelectorAll('.gw-photo-blur')].length
    return { cards: cards.length, badges, photos, blur }
  })
  console.log('礼物墙:', JSON.stringify(info))
  console.log('text 徽标:', info.badges.length, '| blur 照片:', info.blur, '| 普通照片区:', info.photos)

  // 晒图表单隐私选项
  await page.goto(`${PUBLIC}/events/${d.code}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const body = await page.evaluate(() => document.body.innerText)
  const hasPrivacy = body.includes('仅文字') || body.includes('模糊照片') || body.includes('公开照片')
  console.log('晒图隐私选项存在:', hasPrivacy)
  await page.screenshot({ path: `${OUT}/02-privacy-form.png` })

  console.log('前端隐私验收完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
