// 封面展示验收 v2（verify_user 有带封面活动了）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const cover = JSON.parse(fs.readFileSync('/tmp/cover_test.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r10'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)

  // 1. 详情页封面
  await page.goto(`${PUBLIC}/events/${cover.code}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const detailCover = await page.evaluate(() => {
    const img = document.querySelector('img[alt="活动封面"]')
    return img ? { visible: img.offsetHeight > 0, h: img.offsetHeight, src: img.src.slice(0, 60) } : null
  })
  console.log('1. 详情页封面:', JSON.stringify(detailCover))
  await page.screenshot({ path: `${OUT}/02-cover-detail.png` })

  // 2. 列表页封面缩略图
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const thumbs = await page.evaluate(() => [...document.querySelectorAll('.event-card img')].map(i => i.offsetWidth))
  console.log('2. 列表封面缩略图宽:', thumbs.join(','))
  await page.screenshot({ path: `${OUT}/03-cover-list.png` })

  console.log('验收完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
