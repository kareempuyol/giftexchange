// 交互旅程录制 A：参与者视角（新用户走完 邀请→注册→加入→发货）
// 凭据从 /tmp/audit_creds.json 读取
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const orgToken = creds.orgToken
const openCode = creds.events.open
const shortCode = creds.shortCode
const BASE = 'http://127.0.0.1:8080'
const OUT = process.env.HOME + '/giftexchange/ui-shots/journey_a'
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

try {
  // 1. 未登录访问邀请链接 → 应跳登录（带 from）
  await page.goto(`${BASE}/events/${shortCode}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('01-invite-redirect-login')
  console.log('01: 邀请链接→登录页（带from）', page.url())

  // 2. 注册新用户
  await page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
  const uname = 'audit_u' + Date.now().toString().slice(-6)
  const inputs = await page.$$('input.form-input, input')
  // 注册页 4 个输入：用户名/邮箱/密码/确认密码
  await inputs[0].type(uname)
  await inputs[1].type(`${uname}@example.com`)
  await inputs[2].type('Test1234')
  await inputs[3].type('Test1234')
  await new Promise(r => setTimeout(r, 300))
  await shot('02-register-filled')
  console.log('02: 注册表单已填')
  await clickText('button', '注册')
  await new Promise(r => setTimeout(r, 2500))
  await shot('03-after-register')
  console.log('03: 注册后', page.url())

  // 3. 是否回跳到活动页
  if (!page.url().includes('/events/')) {
    await page.goto(`${BASE}/events/${shortCode}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 800))
    await shot('04-event-page')
    console.log('04: 手动回活动页（from回跳未生效?）', page.url())
  }

  // 4. 加入活动 - 步骤1 故意不填必填项
  await clickText('button', '加入')
  await new Promise(r => setTimeout(r, 600))
  await shot('05-join-step1-empty')
  console.log('05: 加入步骤1（空）')
  await clickText('button', '下一步')
  await new Promise(r => setTimeout(r, 400))
  await shot('06-join-step1-validation-error')
  console.log('06: 必填校验错误')

  // 5. 填必填项（步骤1：收件人姓名/电话/地址）
  const jinputs = await page.$$('.modal .form-input, .modal input, .modal textarea')
  if (jinputs[0]) await jinputs[0].type('审计小明')
  if (jinputs[1]) await jinputs[1].type('13712345678')
  if (jinputs[2]) await jinputs[2].type('深圳市南山区科技园')
  await new Promise(r => setTimeout(r, 300))
  await shot('07-join-step1-filled')
  console.log('07: 步骤1填完')
  await clickText('button', '下一步')
  await new Promise(r => setTimeout(r, 500))
  await shot('08-join-step2-wishlist')
  console.log('08: 步骤2 心愿单')

  // 6. 填心愿单并提交（步骤2：喜欢/不喜欢/尺码/颜色/链接/备注）
  const winputs = await page.$$('.modal .form-input, .modal textarea')
  if (winputs[0]) await winputs[0].type('手冲咖啡、好书')
  if (winputs[1]) await winputs[1].type('香水')
  if (winputs[2]) await winputs[2].type('L')
  if (winputs[3]) await winputs[3].type('蓝色系')
  if (winputs[4]) await winputs[4].type('https://item.jd.com/10001.html')
  await new Promise(r => setTimeout(r, 300))
  await shot('09-join-step2-filled')
  console.log('09: 心愿单填完')
  await clickText('button', '确认加入')
  await new Promise(r => setTimeout(r, 2000))
  await shot('10-joined-success')
  console.log('10: 加入成功', page.url())

  // 7. 查看活动详情（参与者视角）
  await page.goto(`${BASE}/events/${openCode}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('11-event-detail-joined')
  console.log('11: 活动详情（已加入）')

  // 8. 活动列表
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 800))
  await shot('12-events-list')
  console.log('12: 活动列表')

  console.log('\n旅程A完成，截图在', OUT)
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
