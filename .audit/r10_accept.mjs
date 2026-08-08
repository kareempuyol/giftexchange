// Profile 页 + 封面展示验收
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
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

  // 1. Header 用户名入口 → /profile
  await page.goto(`${PUBLIC}/profile`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const body = await page.evaluate(() => document.body.innerText)
  console.log('1. 常用信息区块:', body.includes('常用信息'))
  console.log('   修改密码区块:', body.includes('修改密码'))
  console.log('   昵称输入框:', body.includes('昵称'))
  console.log('   礼物偏好:', body.includes('礼物偏好'))
  await page.screenshot({ path: `${OUT}/01-profile.png` })

  // 2. 封面展示（带封面的活动详情）
  const coverCode = await page.evaluate(async () => {
    const res = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const data = await res.json()
    const ev = (data.data || []).find(e => e.coverImage)
    return ev ? ev.code : ''
  })
  if (coverCode) {
    await page.goto(`${PUBLIC}/events/${coverCode}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 1500))
    const coverVisible = await page.evaluate(() => {
      const imgs = [...document.querySelectorAll('img[alt="活动封面"]')]
      return imgs.length > 0 && imgs[0].offsetHeight > 0
    })
    console.log('2. 详情页封面可见:', coverVisible)
    await page.screenshot({ path: `${OUT}/02-cover-detail.png` })
  } else {
    console.log('2. 无带封面活动（可接受）')
  }

  // 3. 列表页封面缩略图
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const thumbs = await page.evaluate(() => {
    return [...document.querySelectorAll('.event-card img')].length
  })
  console.log('3. 列表封面缩略图数:', thumbs)

  console.log('验收完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
