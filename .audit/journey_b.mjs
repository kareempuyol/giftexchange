// 交互旅程录制 B：组织者视角（建活动→邀请→管理台→抽签→礼物墙点赞）
// 凭据从 /tmp/audit_creds.json 读取
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const orgToken = creds.orgToken
const unlockedCode = creds.events.unlocked
const BASE = 'http://127.0.0.1:8080'
const OUT = process.env.HOME + '/giftexchange/ui-shots/journey_b'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` })

// 点击含文本的按钮（puppeteer 兼容）
async function clickText(selector, text) {
  const el = await page.evaluateHandle(({ sel, txt }) => {
    const nodes = [...document.querySelectorAll(sel)]
    return nodes.find(n => n.textContent.includes(txt)) || null
  }, { sel: selector, txt: text })
  if (el) { await el.asElement()?.click(); return true }
  return false
}

// 注入 token（localStorage）
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.evaluate((t) => {
  localStorage.setItem('gift_token', t)
}, orgToken)

try {
  // 1. 登录态首页（活动列表，有数据）
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1000))
  await shot('01-events-list-loggedin')
  console.log('01: 活动列表(登录)')

  // 2. 创建活动页（表单 + 封面上传组件）
  await page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 600))
  await shot('02-create-event-form')
  console.log('02: 创建活动表单')
  await clickText('button', '创建活动')
  await new Promise(r => setTimeout(r, 400))
  await shot('03-create-event-validation')
  console.log('03: 创建校验错误')

  // 3. 填表创建（React 受控 input：用原生 setter + 事件触发）
  const reactType = async (selector, text) => {
    const el = await page.$(selector)
    if (!el) return false
    await el.evaluate((node, value) => {
      const proto = node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set
      setter.call(node, value)
      node.dispatchEvent(new Event('input', { bubbles: true }))
      node.dispatchEvent(new Event('change', { bubbles: true }))
    }, text)
    return true
  }
  await reactType('input[placeholder*="活动名称"], input[placeholder*="圣诞"]', '审计测试活动 UX')
  await reactType('input[placeholder*="预算"], input[type="number"]', '100')
  await reactType('input[type="datetime-local"], input[type="date"]', '2026-12-25T20:00')
  await reactType('textarea', '这是一个测试活动')
  await new Promise(r => setTimeout(r, 500))
  await shot('04-create-event-filled')
  console.log('04: 表单填完')
  await clickText('button', '创建活动')
  await new Promise(r => setTimeout(r, 3000))
  await shot('05-created-event-detail')
  console.log('05: 创建成功→详情页', page.url())

  // 4. 邀请区（短码+复制按钮）
  const inviteText = await page.evaluate(() => document.body.innerText.includes('邀请码'))
  console.log('06: 邀请区存在:', inviteText)
  await shot('06-invite-section')
  console.log('06: 邀请区截图')

  // 5. 管理台（含催办区）
  const code = page.url().split('/events/')[1]
  if (code) {
    await page.goto(`${BASE}/events/${code}/dashboard`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 800))
    await shot('07-dashboard')
    console.log('07: 管理台')
  }

  // 6. 已解锁活动：礼物墙 + 点赞动效
  await page.goto(`${BASE}/events/${unlockedCode}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1000))
  await shot('08-gift-wall-unlocked')
  console.log('08: 礼物墙(解锁)')

  // 点点赞（如果有卡片）
  const likeBtn = await page.$('.gw-like-btn')
  if (likeBtn) {
    const before = await page.evaluate(() => document.querySelector('.gw-like-btn')?.textContent || '')
    await likeBtn.click()
    await new Promise(r => setTimeout(r, 600))
    await shot('09-like-after-click')
    const after = await page.evaluate(() => document.querySelector('.gw-like-btn')?.textContent || '')
    console.log('09: 点赞前:', before.trim(), '→ 后:', after.trim())
  } else {
    console.log('09: 无礼物卡片可点赞')
  }

  // 7. 未解锁活动：礼物墙进度条
  await page.goto(`${BASE}/events/${creds.events.drawn}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('10-gift-wall-locked-progress')
  console.log('10: 礼物墙(未解锁进度条)')

  // 8. 通知列表（找铃铛/通知入口）
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  const bell = await page.evaluateHandle(() => {
    const candidates = [...document.querySelectorAll('button, a, [role="button"]')]
    return candidates.find(n => /通知|铃|🔔|🔔/.test(n.textContent || '')) || null
  })
  if (bell && (await bell.asElement())) {
    await bell.asElement().click()
    await new Promise(r => setTimeout(r, 600))
    await shot('11-notifications')
    console.log('11: 通知面板')
  } else {
    console.log('11: 未找到通知入口')
    await shot('11-notifications-missing')
  }

  console.log('\n旅程B完成，截图在', OUT)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
