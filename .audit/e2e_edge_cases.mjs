// ============================================================
// 异常路径 E2E（hackathon 波次6）— 390px 移动视口
// 覆盖 14 个用户会踩但主旅程测不到的异常路径：
//   重复加入 / 满员拒绝 / 截止后加入 / 礼物墙 403 / 未抽签 my-match
//   / 并发抽签 / 晒图评分边界 / 物流单号边界 / 游客受限页回跳
//   / 断网降级 / 404 活动 / 归档后访问 / 注销旧会话 / 通知角标 9+
// 每场景：断言 + 截图到 .audit/e2e-edge-shots/，异常记录缺陷不中断。
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'e2e-edge-shots')
const DB_PATH = path.join(__dirname, '..', 'data', 'gift_exchange.db')
fs.mkdirSync(OUT, { recursive: true })

// ---------------- 结果收集 ----------------
const results = [] // {scenario, name, pass}
const defects = [] // {scenario, name, severity, message}
let shotN = 0
const shot = async (page, name) => {
  shotN += 1
  const file = `${String(shotN).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: path.join(OUT, file), fullPage: true })
  console.log(`📸 ${file}`)
  return file
}
function check(scenario, name, cond, message = '', severity = 'P1') {
  const pass = !!cond
  results.push({ scenario, name, pass })
  console.log(`  [${pass ? 'PASS' : 'FAIL'}] ${name}${pass ? '' : ' — ' + message}`)
  if (!pass) defects.push({ scenario, name, severity, message })
  return pass
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function waitFor(page, fn, timeout = 20000, interval = 250, arg) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    try {
      if (await page.evaluate(fn, arg)) return true
    } catch { /* ignore */ }
    await sleep(interval)
  }
  return false
}
const waitText = (page, text, timeout = 15000) =>
  waitFor(page, (t) => !!(document.body && document.body.innerText.includes(t)), timeout, 250, text).catch(() => false)
const waitURL = (page, substr, timeout = 15000) =>
  waitFor(page, (s) => location.href.includes(s), timeout, 250, substr).catch(() => false)

// React 受控输入：原生 setter + input/change 事件
async function reactType(page, selector, text) {
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
async function clickText(page, text, selector = 'button,a') {
  return page.evaluate(({ sel, txt }) => {
    const nodes = [...document.querySelectorAll(sel)]
    const el = nodes.find((n) => n.textContent.trim().includes(txt) && n.offsetParent !== null)
    if (el) { el.click(); return true }
    return false
  }, { sel: selector, txt: text })
}

// ---------------- API 辅助（Node 侧直连后端，注册/建活动/加入） ----------------
const api = async (method, p, body, token) => {
  const res = await fetch(`${BASE}/api${p}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  let json = null
  try { json = await res.json() } catch { /* noop */ }
  return { status: res.status, body: json }
}
const register = async (username) => {
  const r = await api('POST', '/auth/register', { username, email: `${username}@edge.test`, password: 'EdgeTest123' })
  if (r.status !== 201) throw new Error(`register ${username}: ${r.status} ${JSON.stringify(r.body)}`)
  return r.body.data // {token, user}
}
const createEvent = async (token, title, opts = {}) => {
  const r = await api('POST', '/events', { title, note: '异常路径测试活动', budget: 100, drawDate: opts.drawDate || '2099-01-01', ...(opts.maxParticipants ? { maxParticipants: opts.maxParticipants } : {}) }, token)
  if (r.status !== 201) throw new Error(`createEvent: ${r.status} ${JSON.stringify(r.body)}`)
  return r.body.data.code
}
const joinViaApi = async (token, code, name = '收件人') => {
  const r = await api('POST', `/events/${code}/join`, { receiverName: name, phone: '13800138000', address: '广东省深圳市南山区科技园路 1 号' }, token)
  return r
}

// 页面上下文内用 token 直接调后端（带统一错误展示的边界注入）
const pageFetch = (page, method, p, body, token) =>
  page.evaluate(
    async ({ method, p, body, token }) => {
      const res = await fetch(`/api${p}`, {
        method,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      })
      const json = await res.json().catch(() => null)
      return { status: res.status, message: json ? json.message : '', code: json ? json.code : null, data: json ? json.data : null }
    },
    { method, p, body, token }
  )

// 登录会话注入：seed token 后整页刷新（AuthContext /auth/me 恢复用户）
async function seedSession(page, token) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), token)
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  return waitText(page, '我的活动')
}

// 每个场景独立 try/catch：异常记录缺陷，不中断
let lastPage = null
async function step(name, fn) {
  console.log(`\n== ${name} ==`)
  try {
    await fn()
  } catch (e) {
    const f = lastPage ? await shot(lastPage, name.replace(/[^\w]+/g, '-')) : null
    defects.push({ scenario: name, name: '异常', severity: 'P0', message: e.message, shot: f })
    console.log(`  [EXC] ${name}: ${e.message}`)
  }
}

// ---------------- 启动浏览器 ----------------
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
})
const mkCtx = async () => {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 390, height: 844 })
  return { ctx, page }
}
const A = await mkCtx()
const B = await mkCtx()
const C = await mkCtx()
const E = await mkCtx()
lastPage = A.page

const ts = Date.now().toString(36)
const NAME = (s) => `edge_${s}_${ts}`
const USERS = { A: NAME('a'), B: NAME('b'), C: NAME('c'), E: NAME('e'), F: NAME('f'), G: NAME('g') }
const PWD = 'EdgeTest123'

let cur = {} // 当前场景共享状态

// ================= 场景执行 =================
await step('S1 重复加入', async () => {
  const uA = await register(USERS.A)
  const uB = await register(USERS.B)
  const code = await createEvent(uA.token, '重复加入测试')
  await seedSession(B.page, uB.token)
  // B 打开加入弹窗并填好第一步
  await B.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(B.page, '加入这个活动')
  await clickText(B.page, '加入这个活动')
  await waitText(B.page, '收件人姓名')
  await reactType(B.page, 'input[placeholder="真实姓名"]', '重复加入者')
  await reactType(B.page, 'input[placeholder="手机号"]', '13800138000')
  await reactType(B.page, 'textarea[placeholder*="省市区"]', '广东省深圳市南山区')
  await clickText(B.page, '下一步')
  await waitText(B.page, '确认加入')
  // 弹窗开着期间，B 已在另一处加入成功（真实竞态：双标签页/慢网络）
  const dup = await pageFetch(B.page, 'POST', `/events/${code}/join`, { receiverName: '重复加入者', phone: '13800138000', address: '广东省深圳市南山区' }, uB.token)
  check('S1', '前置：另一处加入成功（构造竞态）', dup.status === 201, `status=${dup.status} msg=${dup.message}`)
  // 此刻再提交表单 → 后端 400「你已加入该活动」→ 前端弹窗内展示错误，不崩溃
  await clickText(B.page, '确认加入')
  const shown = await waitText(B.page, '你已加入该活动', 8000)
  check('S1', '前端弹窗内提示「你已加入该活动」不崩溃', shown)
  await shot(B.page, 's1-dup-join-error')
})

await step('S2 满员拒绝', async () => {
  const uA = await register(NAME('full_owner'))
  const uB = await register(NAME('full_b'))
  const uC = await register(NAME('full_c'))
  const code = await createEvent(uA.token, '满员测试', { maxParticipants: 2 })
  // 组织者自动加入（1/2），B 加入（2/2），C 加入 → 400
  const jb = await joinViaApi(uB.token, code, 'B')
  const jc = await joinViaApi(uC.token, code, 'C')
  check('S2', '第 3 人加入 → 400 活动人数已满', jc.status === 400 && jc.body.message === '活动人数已满', `status=${jc.status} msg=${jc.body && jc.body.message}`)
  await seedSession(C.page, uC.token)
  await C.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(C.page, '加入这个活动')
  await clickText(C.page, '加入这个活动')
  await waitText(C.page, '收件人姓名')
  await reactType(C.page, 'input[placeholder="真实姓名"]', '第三人')
  await reactType(C.page, 'input[placeholder="手机号"]', '13800138000')
  await reactType(C.page, 'textarea[placeholder*="省市区"]', '广东省深圳市南山区')
  await clickText(C.page, '下一步')
  await waitText(C.page, '确认加入')
  await clickText(C.page, '确认加入')
  const shown = await waitText(C.page, '活动人数已满', 8000)
  check('S2', '前端弹窗内提示「活动人数已满」不崩溃', shown)
  await shot(C.page, 's2-full-error')
})

await step('S3 截止后加入', async () => {
  const uA = await register(NAME('dead_owner'))
  const uB = await register(NAME('dead_b'))
  const code = await createEvent(uA.token, '已截止活动', { drawDate: '2020-01-01' })
  const jc = await joinViaApi(uB.token, code, 'B')
  check('S3', '已过 drawDate 加入 → 400 活动已截止报名', jc.status === 400 && jc.body.message === '活动已截止报名', `status=${jc.status} msg=${jc.body && jc.body.message}`)
  await seedSession(B.page, uB.token)
  await B.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(B.page, '加入这个活动')
  await clickText(B.page, '加入这个活动')
  await waitText(B.page, '收件人姓名')
  await reactType(B.page, 'input[placeholder="真实姓名"]', '迟到者')
  await reactType(B.page, 'input[placeholder="手机号"]', '13800138000')
  await reactType(B.page, 'textarea[placeholder*="省市区"]', '广东省深圳市南山区')
  await clickText(B.page, '下一步')
  await waitText(B.page, '确认加入')
  await clickText(B.page, '确认加入')
  const shown = await waitText(B.page, '活动已截止报名', 8000)
  check('S3', '前端弹窗内提示「活动已截止报名」不崩溃', shown)
  await shot(B.page, 's3-deadline-join-error')
})

await step('S4 未加入访问礼物墙', async () => {
  const uA = await register(NAME('wall_owner'))
  const uB = await register(NAME('wall_b'))
  const uC = await register(NAME('wall_c'))
  const uE = await register(NAME('wall_e'))
  const code = await createEvent(uA.token, '礼物墙权限测试')
  await joinViaApi(uB.token, code, 'B')
  await joinViaApi(uC.token, code, 'C')
  const dr = await api('POST', `/events/${code}/draw`, {}, uA.token)
  check('S4', '抽签成功（3 人）', dr.status === 200, `status=${dr.status} msg=${dr.body && dr.body.message}`)
  cur.wallCode = code
  cur.wallOwner = uA.token
  await seedSession(E.page, uE.token)
  await E.page.goto(`${BASE}/events/${code}/gift-wall`, { waitUntil: 'networkidle2' })
  const shown = await waitText(E.page, '无权访问', 10000)
  check('S4', '非参与者访问礼物墙 → 提示「无权访问」非白屏', shown)
  await shot(E.page, 's4-wall-403')
})

await step('S5 未抽签访问 my-match', async () => {
  const uA = await register(NAME('mm_owner'))
  const uB = await register(NAME('mm_b'))
  const code = await createEvent(uA.token, '未抽签活动', { drawDate: '2099-12-31' })
  await joinViaApi(uB.token, code, 'B')
  // API 层：open 态 my-match 返回 200 + 无数据（友好，非 500）
  const mm = await api('GET', `/events/${code}/my-match`, undefined, uB.token)
  check('S5', 'open 态 my-match → 200 无数据非报错', mm.status === 200 && mm.body && mm.body.data == null, `status=${mm.status}`)
  await seedSession(B.page, uB.token)
  await B.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  // 友好提示：已加入成员看到「等待组织者抽签」，且页面无「加载失败」
  const hint = await waitText(B.page, '等待组织者抽签', 10000)
  const noError = !(await B.page.evaluate(() => document.body.innerText.includes('加载失败')))
  check('S5', '详情页友好提示「等待组织者抽签」且无报错', hint && noError)
  await shot(B.page, 's5-my-match-open-hint')
})

await step('S6 并发抽签', async () => {
  const uA = await register(NAME('conc_owner'))
  const uB = await register(NAME('conc_b'))
  const uC = await register(NAME('conc_c'))
  const code = await createEvent(uA.token, '并发抽签测试')
  await joinViaApi(uB.token, code, 'B')
  await joinViaApi(uC.token, code, 'C')
  await seedSession(A.page, uA.token)
  await A.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(A.page, '开始抽签')
  // 两个请求同时发（Promise.all）：恰一个成功，一个 409
  const results2 = await A.page.evaluate(async (code) => {
    const token = localStorage.getItem('gift_token')
    const fire = async () => {
      const res = await fetch(`/api/events/${code}/draw`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } })
      const json = await res.json().catch(() => null)
      return { status: res.status, message: json ? json.message : '' }
    }
    return Promise.all([fire(), fire()])
  }, code)
  const okN = results2.filter((r) => r.status === 200).length
  const conflictN = results2.filter((r) => r.status === 409).length
  check('S6', '并发抽签 → 恰一个成功', okN === 1, JSON.stringify(results2))
  check('S6', '并发抽签 → 恰一个 409', conflictN === 1 && results2.some((r) => r.message.includes('已抽签')), JSON.stringify(results2))
  await shot(A.page, 's6-concurrent-draw')
})

await step('S7 晒图评分边界', async () => {
  const uA = await register(NAME('rate_owner'))
  const uB = await register(NAME('rate_b'))
  const uC = await register(NAME('rate_c'))
  const code = await createEvent(uA.token, '晒图边界测试')
  await joinViaApi(uB.token, code, 'B')
  await joinViaApi(uC.token, code, 'C')
  await api('POST', `/events/${code}/draw`, {}, uA.token)
  const rg = await api('GET', `/events/${code}/received-gift`, undefined, uB.token)
  const matchId = rg.body.data.matchId
  await seedSession(B.page, uB.token)
  await B.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(B.page, '我收到的礼物')
  // API 边界：rating=0 / 6 / 空评价 → 400 中文提示
  const r0 = await pageFetch(B.page, 'PUT', `/events/${code}/received-gift`, { matchId, rating: 0, review: 'ok', privacy: 'text' }, uB.token)
  check('S7', 'rating=0 → 400 评分需在 1-5 之间', r0.status === 400 && r0.message === '评分需在 1-5 之间', `status=${r0.status} msg=${r0.message}`)
  const r6 = await pageFetch(B.page, 'PUT', `/events/${code}/received-gift`, { matchId, rating: 6, review: 'ok', privacy: 'text' }, uB.token)
  check('S7', 'rating=6 → 400 评分需在 1-5 之间', r6.status === 400 && r6.message === '评分需在 1-5 之间', `status=${r6.status} msg=${r6.message}`)
  const re = await pageFetch(B.page, 'PUT', `/events/${code}/received-gift`, { matchId, rating: 5, review: '   ', photoUrl: '/uploads/x.png', privacy: 'photo' }, uB.token)
  check('S7', '空评价 → 400 请填写评价内容', re.status === 400 && re.message === '请填写评价内容', `status=${re.status} msg=${re.message}`)
  // UI 层：0 星直接晒 → 前端 toast 拦截
  await waitText(B.page, '晒出礼物')
  await clickText(B.page, '晒出礼物')
  const toast0 = await waitFor(B.page, () => [...document.querySelectorAll('.toast')].some((t) => t.textContent.includes('请先给礼物评分')), 6000)
  check('S7', 'UI 0 星 → toast「请先给礼物评分」', toast0)
  await shot(B.page, 's7-rating-zero-toast')
})

await step('S8 物流单号边界', async () => {
  const uA = await register(NAME('ship_owner'))
  const uB = await register(NAME('ship_b'))
  const uC = await register(NAME('ship_c'))
  const code = await createEvent(uA.token, '物流边界测试')
  await joinViaApi(uB.token, code, 'B')
  await joinViaApi(uC.token, code, 'C')
  await api('POST', `/events/${code}/draw`, {}, uA.token)
  const mm = await api('GET', `/events/${code}/my-match`, undefined, uA.token)
  const matchId = mm.body.data.matchId
  await seedSession(A.page, uA.token)
  await A.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(A.page, '填写快递单号')
  // API 边界：空单号 / 超长单号 → 400
  const e1 = await pageFetch(A.page, 'PUT', `/events/${code}/shipment`, { matchId, carrier: '顺丰', trackingNumber: '', status: 'shipped' }, uA.token)
  check('S8', '空单号 → 400 请填写快递单号', e1.status === 400 && e1.message === '请填写快递单号', `status=${e1.status} msg=${e1.message}`)
  const e2 = await pageFetch(A.page, 'PUT', `/events/${code}/shipment`, { matchId, carrier: '顺丰', trackingNumber: 'T'.repeat(121), status: 'shipped' }, uA.token)
  check('S8', '超长单号(121) → 400 快递单号过长', e2.status === 400 && e2.message === '快递单号过长', `status=${e2.status} msg=${e2.message}`)
  // UI 层：空单号点确认发货 → toast 拦截
  await clickText(A.page, '填写快递单号')
  await waitText(A.page, '确认发货')
  await clickText(A.page, '确认发货')
  const toastE = await waitFor(A.page, () => [...document.querySelectorAll('.toast')].some((t) => t.textContent.includes('请填写快递单号')), 6000)
  check('S8', 'UI 空单号 → toast「请填写快递单号」', toastE)
  await shot(A.page, 's8-empty-tracking-toast')
})

await step('S9 游客访问受限页', async () => {
  const guest = await mkCtx()
  lastPage = guest.page
  // /events/new → 登录页带 from
  await guest.page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
  const r1 = await waitURL(guest.page, '/login?from=events%2Fnew', 10000)
  check('S9', '/events/new 未登录 → 跳登录带 from=events/new', r1, `url=${await guest.page.evaluate(() => location.href)}`)
  await shot(guest.page, 's9-guest-events-new-redirect')
  // /profile → 登录页带 from
  await guest.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
  const r2 = await waitURL(guest.page, '/login?from=profile', 10000)
  check('S9', '/profile 未登录 → 跳登录带 from=profile', r2, `url=${await guest.page.evaluate(() => location.href)}`)
  await shot(guest.page, 's9-guest-profile-redirect')
  // 回跳验证：登录后回到 /profile
  const uP = await register(NAME('from_user'))
  await reactType(guest.page, 'input[placeholder="用户名"]', uP.user.username)
  await reactType(guest.page, 'input[placeholder="密码"]', PWD)
  await clickText(guest.page, '登录', 'button')
  const back = await waitURL(guest.page, '/profile', 15000)
  check('S9', '登录后回跳 /profile', back, `url=${await guest.page.evaluate(() => location.href)}`)
  await shot(guest.page, 's9-login-return-profile')
})

await step('S10 断网降级', async () => {
  const uA = await register(NAME('off_owner'))
  const uB = await register(NAME('off_b'))
  const code = await createEvent(uA.token, '断网测试活动')
  await joinViaApi(uB.token, code, 'B')
  await seedSession(A.page, uA.token)
  await A.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(A.page, '开始抽签')
  // 断网后操作：POST /draw → 中文网络错误提示，非白屏/无限 loading
  await A.page.setOfflineMode(true)
  await clickText(A.page, '开始抽签')
  await waitText(A.page, '确认抽签？')
  await clickText(A.page, '确认抽签')
  const toastNet = await waitFor(A.page, () => [...document.querySelectorAll('.toast')].some((t) => t.textContent.includes('网络连接失败')), 15000)
  check('S10', '断网操作 → toast「网络连接失败，请检查网络后重试」', toastNet)
  const notBlank = await A.page.evaluate(() => document.body.innerText.length > 50 && !document.body.innerText.includes('加载中…'))
  check('S10', '断网后页面非白屏/非无限 loading', notBlank)
  await A.page.setOfflineMode(false)
  await shot(A.page, 's10-offline-toast')
})

await step('S11 404 活动', async () => {
  const uA = await register(NAME('nf_owner'))
  await seedSession(A.page, uA.token)
  // 无效短码
  await A.page.goto(`${BASE}/events/ZZZZZZ`, { waitUntil: 'networkidle2' })
  const t1 = await waitText(A.page, '活动不存在', 10000)
  check('S11', '无效短码 → 友好 404「活动不存在」', t1)
  await shot(A.page, 's11-notfound-shortcode')
  // 无效 uuid
  await A.page.goto(`${BASE}/events/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`, { waitUntil: 'networkidle2' })
  const t2 = await waitText(A.page, '活动不存在', 10000)
  check('S11', '无效 uuid → 友好 404「活动不存在」', t2)
  await shot(A.page, 's11-notfound-uuid')
})

await step('S12 归档后访问', async () => {
  // 复用 S4 的 drawn 活动：A 归档 → 直接 URL 仍可看详情
  const code = cur.wallCode
  const uA = { token: cur.wallOwner }
  await seedSession(A.page, uA.token)
  await A.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  await waitText(A.page, '归档活动')
  await clickText(A.page, '归档活动')
  await waitText(A.page, '确认归档？')
  await clickText(A.page, '确认归档')
  const archived = await waitFor(A.page, () => location.pathname === '/events', 10000)
  check('S12', '归档成功回列表', archived, `url=${await A.page.evaluate(() => location.href)}`)
  // 直接 URL 访问归档活动详情
  await A.page.goto(`${BASE}/events/${code}`, { waitUntil: 'networkidle2' })
  const viewable = await waitText(A.page, '礼物墙', 10000) || await waitText(A.page, '重新抽签', 10000)
  const noErr = !(await A.page.evaluate(() => document.body.innerText.includes('加载失败')))
  check('S12', '归档后直接 URL 详情可看（不报错）', viewable && noErr)
  await shot(A.page, 's12-archived-detail-ok')
})

await step('S13 注销用户旧会话', async () => {
  const uF = await register(NAME('deact'))
  await seedSession(A.page, uF.token)
  // 注销账号（服务端标记 deactivated → 旧 JWT 立即失效）
  const de = await A.page.evaluate(async (pwd) => {
    const token = localStorage.getItem('gift_token')
    const res = await fetch('/api/auth/deactivate', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ password: pwd }) })
    const json = await res.json().catch(() => null)
    return { status: res.status, message: json ? json.message : '' }
  }, PWD)
  check('S13', '注销接口成功', de.status === 200, `status=${de.status} msg=${de.message}`)
  // 旧 token 访问受限页 → 401 → 跳登录带 from
  await A.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
  const redirected = await waitURL(A.page, '/login?from=profile', 10000)
  check('S13', '旧会话访问受限页 → 401 后跳登录带 from=profile', redirected, `url=${await A.page.evaluate(() => location.href)}`)
  const tokenGone = await A.page.evaluate(() => !localStorage.getItem('gift_token'))
  check('S13', '401 后本地 token 已清除', tokenGone)
  await shot(A.page, 's13-deactivated-session-redirect')
  // 旧 token 直接调 API → 401「账号已注销」
  const old = await pageFetch(A.page, 'GET', '/events/mine', undefined, uF.token)
  check('S13', '旧 token 调 API → 401 账号已注销', old.status === 401 && old.message === '账号已注销', `status=${old.status} msg=${old.message}`)
})

await step('S14 通知角标边界', async () => {
  const uG = await register(NAME('notif'))
  // 直插 100 条未读通知（本地 dev 库，WAL 并发安全）
  const uid = uG.user.id
  const values = Array.from({ length: 100 }, (_, i) => `(${uid}, NULL, NULL, 'edge_test', '角标测试 ${i}', '第 ${i} 条', NULL)`).join(',')
  execFileSync('sqlite3', [DB_PATH, `INSERT INTO notifications (user_id, event_id, match_id, type, title, message, read_at) VALUES ${values};`])
  await seedSession(A.page, uG.token)
  await waitFor(A.page, () => !!document.querySelector('.notif-badge'), 15000)
  const badge = await A.page.evaluate(() => document.querySelector('.notif-badge')?.textContent || '')
  check('S14', '100 条未读 → 角标显示 9+', badge === '9+', `badge="${badge}"`)
  await shot(A.page, 's14-notif-badge-9plus')
  // 清理：清掉这批角标测试通知，不污染后续开发
  execFileSync('sqlite3', [DB_PATH, `DELETE FROM notifications WHERE user_id = ${uid} AND type = 'edge_test';`])
})

// ---------------- 汇总 ----------------
await browser.close()
const passN = results.filter((r) => r.pass).length
console.log(`\n===== 汇总：${passN}/${results.length} 断言通过，${defects.length} 项缺陷 =====`)
for (const d of defects) console.log(`  [${d.severity}] ${d.scenario} ${d.name}: ${d.message}`)
fs.writeFileSync(path.join(__dirname, 'e2e-edge-results.json'), JSON.stringify({ results, defects, pass: passN, total: results.length }, null, 2))
process.exit(defects.filter((d) => d.severity === 'P0').length ? 2 : 0)
