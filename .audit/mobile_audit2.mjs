// 移动端全场景截图（375px，含交互状态）—— 重点审计
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/mobile_audit2'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` })

const clickText = async (sel, txt) => {
  const el = await page.evaluateHandle(({ s, t }) => {
    const nodes = [...document.querySelectorAll(s)]
    return nodes.find(n => n.textContent.includes(t)) || null
  }, { s: sel, t: txt })
  if (el && (await el.asElement())) { await el.asElement().click(); return true }
  return false
}

try {
  // 1. 登录页（未登录）
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('01-login')
  console.log('01 登录页')

  // 2. 注册页
  await page.goto(`${PUBLIC}/register`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1200))
  await shot('02-register')
  console.log('02 注册页')

  // 3. 注入 token → 活动列表
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('03-events-list')
  console.log('03 活动列表')

  // 4. 活动详情（open 邀请区）
  await page.goto(`${PUBLIC}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('04-event-detail')
  console.log('04 活动详情')

  // 5. 加入弹窗-步骤1
  await clickText('button', '加入')
  await new Promise(r => setTimeout(r, 800))
  await shot('05-join-step1')
  console.log('05 加入弹窗步骤1')

  // 6. 加入弹窗-步骤2（点下一步触发校验→直接填完再进）
  await clickText('button', '下一步')
  await new Promise(r => setTimeout(r, 500))
  await shot('06-join-step1-error')
  console.log('06 步骤1校验错误')
  // 填必填
  const j1 = await page.$$('.modal input, .modal textarea')
  if (j1[0]) await j1[0].type('手机测试')
  if (j1[1]) await j1[1].type('13800138000')
  if (j1[2]) await j1[2].type('广州市天河区测试路88号')
  await new Promise(r => setTimeout(r, 300))
  await clickText('button', '下一步')
  await new Promise(r => setTimeout(r, 600))
  await shot('07-join-step2')
  console.log('07 步骤2心愿单')

  // 7. 礼物墙（已解锁）
  await page.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('08-giftwall')
  console.log('08 礼物墙')

  // 8. 管理台
  await page.goto(`${PUBLIC}/events/${creds.events.open}/dashboard`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('09-dashboard')
  console.log('09 管理台')

  // 9. 创建活动页
  await page.goto(`${PUBLIC}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('10-create-event')
  console.log('10 创建活动')

  // 10. 通知面板
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1000))
  const bell = await page.evaluateHandle(() => {
    const c = [...document.querySelectorAll('button')]
    return c.find(n => (n.getAttribute('aria-label') || '').includes('通知')) || null
  })
  if (bell && (await bell.asElement())) {
    await bell.asElement().click()
    await new Promise(r => setTimeout(r, 800))
    await shot('11-notifications')
    console.log('11 通知面板')
  }

  // 12. 活动详情（已抽签状态：我的任务+发货区）
  await page.goto(`${PUBLIC}/events/${creds.events.drawn}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  await shot('12-event-drawn')
  console.log('12 已抽签详情')

  console.log('\n移动端全场景截图完成 →', OUT)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
