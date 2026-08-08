// 公网终验截图：登录态注入 + 关键页面 + 移动端
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/public_final'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })

// 桌面端
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` })

try {
  // 1. 未登录：公网首页（应跳登录）
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('01-public-login-page')
  console.log('01: 公网登录页', page.url())

  // 2. 注入 token（公网 origin 的 localStorage）
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('02-public-events-list')
  console.log('02: 公网活动列表', page.url())

  // 3. 活动详情（open 活动：邀请区）
  await page.goto(`${PUBLIC}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1200))
  await shot('03-public-event-detail')
  console.log('03: 公网活动详情')

  // 4. 礼物墙（已解锁）
  await page.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1200))
  await shot('04-public-giftwall')
  console.log('04: 公网礼物墙')

  // 5. 管理台
  await page.goto(`${PUBLIC}/events/${creds.events.open}/dashboard`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1200))
  await shot('05-public-dashboard')
  console.log('05: 公网管理台')

  // 6. 通知面板（Header 铃铛）
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1000))
  const bell = await page.evaluateHandle(() => {
    const c = [...document.querySelectorAll('button')]
    return c.find(n => (n.getAttribute('aria-label') || '').includes('通知')) || null
  })
  if (bell && (await bell.asElement())) {
    await bell.asElement().click()
    await new Promise(r => setTimeout(r, 800))
    await shot('06-public-notifications')
    console.log('06: 公网通知面板')
  } else {
    console.log('06: 通知铃铛未找到')
    await shot('06-public-notifications-missing')
  }

  // 7. 移动端
  const mpage = await browser.newPage()
  await mpage.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })
  await mpage.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await mpage.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await mpage.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await mpage.screenshot({ path: `${OUT}/07-public-mobile-events.png` })
  console.log('07: 公网移动端列表')
  await mpage.goto(`${PUBLIC}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1200))
  await mpage.screenshot({ path: `${OUT}/08-public-mobile-detail.png` })
  console.log('08: 公网移动端详情')
  await mpage.close()

  console.log('\n公网终验截图完成 →', OUT)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
