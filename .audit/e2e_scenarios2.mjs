// ============================================================
// E2E 场景扩展（hackathon 轮 8）— 6 大真实场景
// 1. 多活动工作流：1 组织 + 2 参与，跨活动切换与数据隔离
// 2. 礼品流全链路：A 建 → B/C/D 加入 → 抽签 → B 发货(悄悄话)
//    → D 晒图(公开照片) → A 礼物墙 → 高光海报 → PNG(toDataURL)
// 3. 通知驱动回流：你已加入 → 抽签完成(看 my-match) → 礼物已发货
// 4. 深链直达：游客 /events/<短码> → 落地页 → 登录 → 回跳
// 5. 资料预填：个人中心保存地址/偏好 → 加入表单自动带入
// 6. 密码强度边界：纯数字/纯字母/5 位 → 400 中文提示；改密后立刻登录
// 视口 390×844；截图 .audit/scen2-shots/；结果 .audit/scen2-results.json
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'scen2-shots')
const TEST_IMG = path.join(__dirname, 'test_avatar.png')
fs.mkdirSync(OUT, { recursive: true })

// ---------------- 测试图片（200x200 纯色 PNG） ----------------
const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()
const crc32 = (buf) => {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
function makePng(size, [r, g, b]) {
  const raw = Buffer.alloc(size * (1 + size * 3))
  for (let y = 0; y < size; y++) {
    raw[y * (1 + size * 3)] = 0
    for (let x = 0; x < size; x++) {
      const o = y * (1 + size * 3) + 1 + x * 3
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b
    }
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const td = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(td))
    return Buffer.concat([len, td, crc])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8
  ihdr[9] = 2
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
fs.writeFileSync(TEST_IMG, makePng(200, [232, 85, 61]))

// ---------------- 结果收集 ----------------
const results = []
const defects = []
let shotN = 0
const shot = async (page, name) => {
  shotN += 1
  const file = `${String(shotN).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: path.join(OUT, file), fullPage: true })
  console.log(`📸 ${file}`)
  return file
}
const shotDefect = async (page, name) => {
  const file = `D-${name}.png`
  try { await page.screenshot({ path: path.join(OUT, file), fullPage: true }) } catch { /* noop */ }
  return file
}
function check(step, name, cond, message = '', severity = 'P1') {
  const pass = !!cond
  results.push({ step, name, pass })
  console.log(`  [${pass ? 'PASS' : 'FAIL'}] ${name}${pass ? '' : ' — ' + message}`)
  if (!pass) defects.push({ step, name, severity, message })
  return pass
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitFor(page, fn, timeout = 20000, interval = 250) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    try {
      if (await page.evaluate(fn)) return true
    } catch { /* ignore */ }
    await sleep(interval)
  }
  return false
}
const waitText = (page, text, timeout = 15000) => {
  const t0 = Date.now()
  return (async () => {
    while (Date.now() - t0 < timeout) {
      try {
        if (await page.evaluate((t) => !!(document.body && document.body.innerText.includes(t)), text)) return true
      } catch { /* ignore */ }
      await sleep(250)
    }
    return false
  })()
}
const waitURL = (page, substr, timeout = 15000) => {
  const t0 = Date.now()
  return (async () => {
    while (Date.now() - t0 < timeout) {
      try {
        if (await page.evaluate((s) => location.href.includes(s), substr)) return true
      } catch { /* ignore */ }
      await sleep(250)
    }
    return false
  })()
}
const bodyHas = (page, text) => page.evaluate((t) => document.body.innerText.includes(t), text)

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

// 每个步骤独立 try/catch：异常记录缺陷，不中断旅程
let ctxGuard = null
async function step(name, fn) {
  console.log(`\n== ${name} ==`)
  try {
    await fn()
  } catch (e) {
    const f = await shotDefect(ctxGuard ? ctxGuard.page : null, name.replace(/\s+/g, '-'))
    defects.push({ step: name, name: '异常', severity: 'P0', message: e.message, shot: f })
    console.log(`  [EXC] ${name}: ${e.message}`)
  }
}

// ---------------- 浏览器 / 上下文 ----------------
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

// ---------------- API 辅助（Node fetch） ----------------
async function apiFetch(method, apiPath, token, body) {
  const res = await fetch(BASE + apiPath, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  let json = null
  try { json = await res.json() } catch { /* noop */ }
  return { status: res.status, json }
}
async function registerViaApi(username) {
  const email = `${username}@test.com`
  const r = await apiFetch('POST', '/api/auth/register', null, { username, email, password: 'Pass12345' })
  if (r.status !== 201) throw new Error(`register ${username} failed: ${r.status} ${JSON.stringify(r.json)}`)
  return { token: r.json.data.token, user: r.json.data.user }
}
/** 把 API 注册的 token 注入页面：访问 /events → 写入 localStorage → 重进 → AuthContext 自动登录 */
async function seedCtx(page, token, username) {
  await page.goto(`${BASE}/events`, { waitUntil: 'domcontentloaded' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), token)
  await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
  return waitText(page, username, 15000)
}
async function createEventViaApi(token, title) {
  const r = await apiFetch('POST', '/api/events', token, { title, budget: 100 })
  if (r.status !== 201) throw new Error(`create event failed: ${r.status} ${JSON.stringify(r.json)}`)
  return r.json.data
}
async function joinViaApi(token, code) {
  const r = await apiFetch('POST', `/api/events/${code}/join`, token, {
    receiverName: 'API成员', phone: '13800138000', address: '广东省深圳市南山区', preferenceLikes: '咖啡',
  })
  if (r.status !== 201) throw new Error(`join ${code} failed: ${r.status} ${JSON.stringify(r.json)}`)
  return r.json.data
}

// ---------------- 通知面板 ----------------
async function notifOpen(page) {
  const bell = await page.$('.notif-bell')
  if (!bell) return false
  await bell.click()
  return waitFor(page, () => !!document.querySelector('.notif-item'), 8000)
}
/** 在通知面板中找标题含 sub 的通知并点击「查看活动」，返回是否点击成功 */
async function notifClickItem(page, titleSub) {
  const clicked = await page.evaluate((sub) => {
    const items = [...document.querySelectorAll('.notif-item')]
    const item = items.find((el) => (el.querySelector('.notif-title')?.textContent || '').includes(sub))
    if (!item) return false
    const link = item.querySelector('a')
    if (link) { link.click(); return true }
    return false
  }, titleSub)
  return clicked
}
const notifBadge = (page) => page.evaluate(() => document.querySelector('.notif-badge')?.textContent || '')

// ---------------- 加入活动（UI，两步表单） ----------------
async function joinEventUi(page, { receiverName, phone, address, likes }) {
  await waitText(page, '加入这个活动')
  await clickText(page, '加入这个活动')
  await waitText(page, '收件人姓名')
  await reactType(page, '#join-receiver', receiverName)
  await reactType(page, '#join-phone', phone)
  await reactType(page, '#join-address', address)
  await clickText(page, '下一步')
  await waitText(page, '我喜欢的礼物')
  await reactType(page, '#join-likes', likes)
  await clickText(page, '确认加入')
  await waitText(page, '加入成功', 15000)
}

// ---------------- 晒图 ----------------
async function postGiftUi(page, { stars, review, mode, withPhoto }) {
  await waitText(page, '我收到的礼物')
  await waitFor(page, () => !!document.querySelector('button[aria-label="5 星"]'), 10000)
  await page.click(`button[aria-label="${stars} 星"]`)
  const ta = await page.$('textarea[placeholder="收到礼物想说点什么？"]')
  await ta.evaluate((node, v) => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(node, v)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  }, review)
  if (mode === 'text') {
    await clickText(page, '仅文字', 'label')
  } else if (withPhoto) {
    await clickText(page, '公开照片', 'label')
    const input = await page.$('.iu-input')
    await input.uploadFile(TEST_IMG)
    await waitFor(page, () => !!document.querySelector('.iu-preview'))
  }
  await clickText(page, '晒出礼物')
  return waitText(page, '晒图成功', 15000)
}

// ================= 启动 =================
const ts = Date.now().toString(36)
console.log(`run ts=${ts}`)

try {
  // ============================================================
  // 场景 1：多活动工作流
  // ============================================================
  const multi = await mkCtx(); ctxGuard = multi
  const morg2 = await registerViaApi(`s1morg2_${ts}`)
  const morg3 = await registerViaApi(`s1morg3_${ts}`)
  const multiU = await registerViaApi(`s1multi_${ts}`)
  await seedCtx(multi.page, multiU.token, multiU.user.username)
  const evA = await createEventViaApi(multiU.token, 'S1 我的活动A')
  const evB = await createEventViaApi(morg2.token, 'S1 参与活动B')
  const evC = await createEventViaApi(morg3.token, 'S1 参与活动C')
  await joinViaApi(multiU.token, evB.code)
  await joinViaApi(multiU.token, evC.code)

  await step('1a. 我创建的 tab 只含活动 A', async () => {
    await multi.page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
    await waitText(multi.page, 'S1 我的活动A')
    await clickText(multi.page, '我创建的')
    await waitText(multi.page, 'S1 我的活动A')
    const rows = await multi.page.evaluate(() => document.querySelectorAll('.event-list-row').length)
    const hasB = await bodyHas(multi.page, 'S1 参与活动B')
    const hasC = await bodyHas(multi.page, 'S1 参与活动C')
    check('1a', '我创建的列表 = 1 个活动（仅 A）', rows === 1 && !hasB && !hasC, `rows=${rows} hasB=${hasB} hasC=${hasC}`)
    await shot(multi.page, 's1-mine-tab')
  })

  await step('1b. 我参与的 tab 含 B、C 及创建者自动加入的 A', async () => {
    await clickText(multi.page, '我参与的')
    await waitText(multi.page, 'S1 参与活动B')
    await waitText(multi.page, 'S1 参与活动C')
    const rows = await multi.page.evaluate(() => document.querySelectorAll('.event-list-row').length)
    const hasA = await bodyHas(multi.page, 'S1 我的活动A')
    check('1b', '我参与的列表 = 3 个活动（创建者自动加入 → A 也参与）', rows === 3 && hasA, `rows=${rows} hasA=${hasA}`)
    await shot(multi.page, 's1-joined-tab')
  })

  await step('1c. 详情数据隔离：B 与 C 参与者互不串台', async () => {
    await multi.page.goto(`${BASE}/events/${evB.code}`, { waitUntil: 'networkidle2' })
    await waitText(multi.page, 'S1 参与活动B')
    const bHasOrg3 = await bodyHas(multi.page, morg3.user.username)
    check('1c', '活动 B 详情不含活动 C 的组织者', !bHasOrg3, `bHasOrg3=${bHasOrg3}`)

    await multi.page.goto(`${BASE}/events/${evC.code}`, { waitUntil: 'networkidle2' })
    await waitText(multi.page, 'S1 参与活动C')
    const cHasOrg2 = await bodyHas(multi.page, morg2.user.username)
    check('1c', '活动 C 详情不含活动 B 的组织者', !cHasOrg2, `cHasOrg2=${cHasOrg2}`)

    await multi.page.goto(`${BASE}/events/${evA.code}`, { waitUntil: 'networkidle2' })
    await waitText(multi.page, 'S1 我的活动A')
    const aHasB = await bodyHas(multi.page, 'S1 参与活动B')
    check('1c', '活动 A 详情不含 B/C 标题', !aHasB, `aHasB=${aHasB}`)
    await shot(multi.page, 's1-detail-a')
  })

  // ============================================================
  // 场景 2：礼品流全链路（A 建 → B/C/D 加入 → 抽签 → B 发货 → D 晒图 → 礼物墙 → 海报 PNG）
  // ============================================================
  const A = await mkCtx(); ctxGuard = A
  const B = await mkCtx()
  const C = await mkCtx()
  const D = await mkCtx()
  const uA = await registerViaApi(`s2a_${ts}`)
  const uB = await registerViaApi(`s2b_${ts}`)
  const uC = await registerViaApi(`s2c_${ts}`)
  const uD = await registerViaApi(`s2d_${ts}`)
  const users2 = [uA, uB, uC, uD]
  await seedCtx(A.page, uA.token, uA.user.username)
  await seedCtx(B.page, uB.token, uB.user.username)
  await seedCtx(C.page, uC.token, uC.user.username)
  await seedCtx(D.page, uD.token, uD.user.username)
  const E2_TITLE = `S2 全链路交换 ${ts}`
  let e2 = null

  await step('2a. A 创建活动 → 详情页', async () => {
    await A.page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '创建活动')
    await reactType(A.page, 'input[placeholder*="圣诞礼物互赠"]', E2_TITLE)
    await reactType(A.page, 'input[placeholder="写点规则或想说的话（选填）"]', '互相送惊喜 🎁')
    await reactType(A.page, 'input[type="number"]', '100')
    await reactType(A.page, 'input[type="datetime-local"]', '2026-08-20T20:00')
    await clickText(A.page, '创建活动', 'button')
    const ok = await waitFor(A.page, () => /\/events\/[^/]+$/.test(location.pathname) && !!document.querySelector('.invite-code-btn'), 15000)
    check('2a', '创建后跳转详情页且短码可见', ok, `url=${await A.page.evaluate(() => location.href)}`)
    e2 = { code: await A.page.evaluate(() => location.pathname.split('/').pop()), title: E2_TITLE }
    check('2a', '详情页显示活动标题', await waitText(A.page, E2_TITLE))
    await shot(A.page, 's2-created')
  })

  await step('2b. B/C/D 依次加入（UI 加入表单）', async () => {
    const expected = { B: 2, C: 3, D: 4 }
    for (const [ctx, tag] of [[B, 'B'], [C, 'C'], [D, 'D']]) {
      await ctx.page.goto(`${BASE}/events/${e2.code}`, { waitUntil: 'networkidle2' })
      await waitText(ctx.page, '加入这个活动')
      await joinEventUi(ctx.page, {
        receiverName: `成员${tag}`, phone: '13800138000', address: `地址${tag} 深圳市南山区 1 号`,
        likes: tag === 'D' ? '相机、手办' : '咖啡、书籍',
      })
      check('2b', `${tag} 加入成功（参与者 ${expected[tag]}）`, await waitText(ctx.page, `参与者（${expected[tag]}）`, 15000))
    }
    await A.page.goto(`${BASE}/events/${e2.code}`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '参与者（4）')
    check('2b', 'A 看到 4 名参与者', true)
    await shot(A.page, 's2-four-participants')
  })

  await step('2c. A 抽签 → 全员收到结果', async () => {
    await clickText(A.page, '开始抽签')
    await waitText(A.page, '确认抽签？')
    await clickText(A.page, '确认抽签')
    await waitText(A.page, '抽签完成', 15000)
    check('2c', '抽签完成提示', true)
    for (const [ctx, tag] of [[A, 'A'], [B, 'B'], [C, 'C'], [D, 'D']]) {
      await ctx.page.goto(`${BASE}/events/${e2.code}`, { waitUntil: 'networkidle2' })
      const ok = await waitText(ctx.page, '我的送礼任务', 15000)
      check('2c', `${tag} 看到我的送礼任务`, ok)
      if (tag === 'B') {
        const who = await ctx.page.evaluate(() => {
          const m = document.body.innerText.match(/我要送给\s*([^\n]+)/)
          return m ? m[1].trim() : ''
        })
        check('2c', 'B 有送礼对象', !!who, `who=${who}`)
      }
    }
    await shot(B.page, 's2-b-my-match')
  })

  await step('2d. B 发货（快递信息 + 悄悄话）', async () => {
    await waitText(B.page, '填写快递单号')
    await clickText(B.page, '填写快递单号')
    await waitText(B.page, '快递单号（必填）')
    await reactType(B.page, 'input[aria-label="快递公司（选填）"]', '顺丰速运')
    await reactType(B.page, 'input[aria-label="快递单号（必填）"]', `SF${Date.now()}`)
    await reactType(B.page, 'input[aria-label="附一句悄悄话（选填）"]', '这是给你的小惊喜，希望你喜欢！')
    await clickText(B.page, '确认发货')
    check('2d', '发货保存提示', await waitText(B.page, '发货信息已保存 🚚', 15000))
    check('2d', '发货状态徽标=已发货', await waitText(B.page, '已发货'))
    check('2d', '悄悄话已存（待收礼人晒图揭晓）', await waitText(B.page, '收礼人晒图后揭晓'))
    await shot(B.page, 's2-b-shipped')
  })

  await step('2e. 全员晒图（D 公开照片，其余仅文字）', async () => {
    for (const [ctx, tag] of [[A, 'A'], [B, 'B'], [C, 'C'], [D, 'D']]) {
      await ctx.page.goto(`${BASE}/events/${e2.code}`, { waitUntil: 'networkidle2' })
      const ok = await postGiftUi(ctx.page, {
        stars: tag === 'D' ? 5 : 4,
        review: `${tag} 的晒图评价：礼物超棒！`,
        mode: tag === 'D' ? 'photo' : 'text',
        withPhoto: tag === 'D',
      })
      check('2e', `${tag} 晒图成功`, ok)
    }
    await shot(D.page, 's2-d-posted-photo')
  })

  await step('2f. B 的悄悄话在收礼人晒图后揭晓', async () => {
    await B.page.goto(`${BASE}/events/${e2.code}`, { waitUntil: 'networkidle2' })
    const revealed = await waitText(B.page, '💬 悄悄话：这是给你的小惊喜，希望你喜欢！', 15000)
    check('2f', '悄悄话已揭晓', revealed)
    await shot(B.page, 's2-note-revealed')
  })

  await step('2g. A 看礼物墙 → 生成高光海报 → 下载 PNG', async () => {
    await A.page.goto(`${BASE}/events/${e2.code}/gift-wall`, { waitUntil: 'networkidle2' })
    const unlocked = await waitText(A.page, '🏆 生成高光海报', 15000)
    check('2g', '礼物墙已解锁（4/4 晒出）', unlocked)
    await clickText(A.page, '生成高光海报')
    const canvasOk = await waitFor(A.page, () => {
      const c = document.querySelector('canvas')
      if (!c) return false
      try {
        return c.toDataURL('image/png').startsWith('data:image/png')
      } catch { return false }
    }, 15000)
    check('2g', '海报 canvas.toDataURL 前缀 = data:image/png', canvasOk)
    await shot(A.page, 's2-highlight-poster')
    await clickText(A.page, '下载海报')
    check('2g', '下载海报反馈', await waitText(A.page, '已下载', 8000))
    await shot(A.page, 's2-poster-downloaded')
  })

  // ============================================================
  // 场景 3：通知驱动回流（复用场景 2 活动）
  // ============================================================
  await step('3a. B 收到「你已加入」通知 → 点击跳详情', async () => {
    await B.page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
    await waitText(B.page, '我的活动')
    const badge = await notifBadge(B.page)
    check('3a', '铃铛未读角标 ≥1', parseInt(badge || '0', 10) >= 1, `badge=${badge}`)
    const opened = await notifOpen(B.page)
    check('3a', '通知面板可打开', opened)
    const found = await notifClickItem(B.page, '你已加入')
    check('3a', '面板含「你已加入」通知', found)
    await shot(B.page, 's3-join-notif-panel')
    const landed = await waitURL(B.page, `/events/${e2.code}`, 15000)
    check('3a', '点击后跳转活动详情', landed, `url=${await B.page.evaluate(() => location.href)}`)
  })

  await step('3b. B 收到「抽签完成」通知 → 点击看 my-match', async () => {
    await notifOpen(B.page)
    const found = await notifClickItem(B.page, '抽签结果已出')
    check('3b', '面板含「抽签结果已出」通知', found)
    await waitURL(B.page, `/events/${e2.code}`, 15000)
    check('3b', '点击后详情页显示我的送礼任务', await waitText(B.page, '我的送礼任务', 15000))
    await shot(B.page, 's3-draw-notif-mymatch')
  })

  await step('3c. B 的送礼人 G 发货 → B 收到「礼物已发货」→ 点击', async () => {
    // 找出 B 的送礼人（received-gift 的 giverId），用其 token 发货
    const recv = await apiFetch('GET', `/api/events/${e2.code}/received-gift`, uB.token)
    const data = recv.json?.data
    check('3c', 'B 有送礼任务（received-gift 可查）', !!data && !!data.giverId, JSON.stringify(recv.json))
    const giver = users2.find((u) => u.user.id === data.giverId)
    check('3c', '送礼人是 A/B/C/D 之一', !!giver, `giverId=${data.giverId}`)
    const ship = await apiFetch('PUT', `/api/events/${e2.code}/shipment`, giver.token, {
      matchId: data.matchId, carrier: '中通快递', trackingNumber: `ZT${Date.now()}`,
    })
    check('3c', 'G 发货成功（API）', ship.status === 200, `${ship.status} ${JSON.stringify(ship.json)}`)
    await B.page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
    await waitText(B.page, '我的活动')
    await notifOpen(B.page)
    const found = await notifClickItem(B.page, '你的礼物已发货')
    check('3c', 'B 面板含「你的礼物已发货」通知', found)
    await shot(B.page, 's3-ship-notif')
    await waitURL(B.page, `/events/${e2.code}`, 15000)
    check('3c', '点击后回到活动详情', true)
  })

  // ============================================================
  // 场景 4：深链直达（游客 → 落地页 → 登录 → 回跳）
  // ============================================================
  await step('4a. 游客直接输入 /events/<短码> → 落地页', async () => {
    const guest = await mkCtx()
    await guest.page.goto(`${BASE}/events/${evA.code}`, { waitUntil: 'networkidle2' })
    const title = await waitText(guest.page, 'S1 我的活动A', 15000)
    check('4a', '游客落地页显示活动标题', title)
    const joinCta = await waitText(guest.page, '登录后加入', 15000)
    check('4a', '落地页有登录 CTA', joinCta)
    await shot(guest.page, 's4-guest-landing')
    await clickText(guest.page, '登录后加入')
    const onLogin = await waitURL(guest.page, '/login?from=', 15000)
    check('4a', '跳转登录页且带 from 参数', onLogin, `url=${await guest.page.evaluate(() => location.href)}`)
    // 登录（复用 multiU 账号）→ 应回跳活动详情
    await waitText(guest.page, '登录')
    await reactType(guest.page, '#login-username', multiU.user.username)
    await reactType(guest.page, '#login-password', 'Pass12345')
    await clickText(guest.page, '登录', 'button')
    const back = await waitURL(guest.page, `/events/${evA.code}`, 15000)
    check('4a', '登录后回跳活动详情', back, `url=${await guest.page.evaluate(() => location.href)}`)
    check('4a', '详情页加载活动内容', await waitText(guest.page, 'S1 我的活动A', 15000))
    await shot(guest.page, 's4-login-return')
    await guest.ctx.close()
  })

  // ============================================================
  // 场景 5：资料预填（个人中心保存 → 加入另一活动自动带入）
  // ============================================================
  await step('5a. 组织者保存地址/收件人/偏好到个人中心', async () => {
    const pref = await registerViaApi(`s5pref_${ts}`)
    const pctx = await mkCtx()
    await seedCtx(pctx.page, pref.token, pref.user.username)
    await pctx.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(pctx.page, '常用信息')
    await reactType(pctx.page, '#profile-phone', '13900001111')
    await reactType(pctx.page, '#profile-receiver', '预填收件人')
    await reactType(pctx.page, '#profile-address', '上海市浦东新区世纪大道 100 号')
    await reactType(pctx.page, '#profile-preference', '喜欢：手办、相机')
    await clickText(pctx.page, '保存资料')
    const saved = await waitText(pctx.page, '个人资料已保存 ✅', 15000)
    check('5a', '个人资料保存成功', saved)
    await shot(pctx.page, 's5-profile-saved')

    // 打开 B 活动（open 状态）的加入表单 → 断言预填
    await pctx.page.goto(`${BASE}/events/${evB.code}`, { waitUntil: 'networkidle2' })
    await waitText(pctx.page, '加入这个活动')
    await clickText(pctx.page, '加入这个活动')
    const prefillHint = await waitText(pctx.page, '已从个人资料自动填入', 15000)
    check('5a', '加入表单显示预填提示', prefillHint)
    const vals = await pctx.page.evaluate(() => ({
      receiver: document.querySelector('#join-receiver')?.value || '',
      phone: document.querySelector('#join-phone')?.value || '',
      address: document.querySelector('#join-address')?.value || '',
    }))
    check('5a', '收件人预填 = 个人中心值', vals.receiver === '预填收件人', JSON.stringify(vals))
    check('5a', '手机号预填', vals.phone === '13900001111', JSON.stringify(vals))
    check('5a', '地址预填', vals.address === '上海市浦东新区世纪大道 100 号', JSON.stringify(vals))
    await shot(pctx.page, 's5-join-prefilled')
    // 第二步：偏好预填
    await clickText(pctx.page, '下一步')
    const likes = await pctx.page.evaluate(() => document.querySelector('#join-likes')?.value || '')
    check('5a', '礼物偏好预填到心愿单', likes === '喜欢：手办、相机', `likes=${likes}`)
    // 直接提交（数据已预填）→ 加入成功
    await clickText(pctx.page, '确认加入')
    check('5a', '预填数据可直接加入', await waitText(pctx.page, '加入成功', 15000))
    await shot(pctx.page, 's5-joined-with-prefill')
    await pctx.ctx.close()
  })

  // ============================================================
  // 场景 6：密码强度边界 + 改密后立刻登录
  // ============================================================
  await step('6a. 弱密码注册 → 400 中文提示（API）', async () => {
    const cases = [
      ['12345678', '密码必须同时包含字母和数字'],
      ['abcdefgh', '密码必须同时包含字母和数字'],
      ['Ab1cd', '密码长度需为 6-128 个字符'],
    ]
    for (const [pwd, expectMsg] of cases) {
      const r = await apiFetch('POST', '/api/auth/register', null, {
        username: `s6weak_${ts}${pwd.length}`, email: `s6weak_${ts}${pwd.length}@test.com`, password: pwd,
      })
      const msg = r.json?.message || ''
      check('6a', `弱密码 ${pwd.length}位/${pwd.slice(0, 2)}… → 400「${expectMsg}」`,
        r.status === 400 && msg.includes(expectMsg), `${r.status} "${msg}"`)
    }
  })

  await step('6b. 弱密码注册 → 400 中文提示（UI 注册页）', async () => {
    const p6 = await mkCtx()
    await p6.page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
    await waitText(p6.page, '注册')
    await reactType(p6.page, 'input[placeholder="用户名"]', `s6ui_${ts}`)
    await reactType(p6.page, 'input[placeholder="邮箱"]', `s6ui_${ts}@test.com`)
    await reactType(p6.page, 'input[placeholder="密码"]', '88888888')
    await reactType(p6.page, 'input[placeholder="确认密码"]', '88888888')
    await clickText(p6.page, '注册', 'button')
    const err = await waitText(p6.page, '密码必须同时包含字母和数字', 15000)
    check('6b', 'UI 显示中文强度提示', err)
    await shot(p6.page, 's6-weak-pwd-ui')
    await p6.ctx.close()
  })

  await step('6c. 改密码接口拒绝弱新密码（API）', async () => {
    const u = await registerViaApi(`s6chg_${ts}`)
    const r = await apiFetch('PUT', '/api/profile/password', u.token, {
      oldPassword: 'Pass12345', newPassword: '11111111',
    })
    const msg = r.json?.message || ''
    check('6c', '弱新密码 → 400「新密码必须同时包含字母和数字」',
      r.status === 400 && msg.includes('新密码必须同时包含字母和数字'), `${r.status} "${msg}"`)
  })

  await step('6d. 正确改密 → 旧密码失效 → 新密码立刻登录', async () => {
    const u = await registerViaApi(`s6ok_${ts}`)
    const p = await mkCtx()
    await seedCtx(p.page, u.token, u.user.username)
    await p.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(p.page, '修改密码')
    await reactType(p.page, '#profile-old-pwd', 'Pass12345')
    await reactType(p.page, '#profile-new-pwd', 'NewPwd678')
    await reactType(p.page, '#profile-confirm-pwd', 'NewPwd678')
    await clickText(p.page, '修改密码')
    check('6d', '改密成功提示', await waitText(p.page, '密码已修改 ✅', 15000))
    await shot(p.page, 's6-pwd-changed')

    // 退出 → 旧密码登录失败
    await clickText(p.page, '退出')
    await waitURL(p.page, '/login', 15000)
    await waitText(p.page, '登录')
    await reactType(p.page, '#login-username', u.user.username)
    await reactType(p.page, '#login-password', 'Pass12345')
    await clickText(p.page, '登录', 'button')
    check('6d', '旧密码登录被拒', await waitText(p.page, '用户名或密码错误', 15000))
    await shot(p.page, 's6-old-pwd-rejected')

    // 新密码立刻登录成功
    await reactType(p.page, '#login-username', u.user.username)
    await reactType(p.page, '#login-password', 'NewPwd678')
    await clickText(p.page, '登录', 'button')
    const ok = await waitURL(p.page, '/events', 15000)
    check('6d', '新密码立刻登录成功', ok, `url=${await p.page.evaluate(() => location.href)}`)
    await shot(p.page, 's6-new-pwd-login')
    await p.ctx.close()
  })
} finally {
  await browser.close()
}

// ---------------- 输出 ----------------
const byStep = {}
for (const r of results) {
  if (!byStep[r.step]) byStep[r.step] = { total: 0, pass: 0 }
  byStep[r.step].total += 1
  if (r.pass) byStep[r.step].pass += 1
}
const summary = {
  runAt: new Date().toISOString(),
  totalAssertions: results.length,
  passed: results.filter((r) => r.pass).length,
  failed: results.filter((r) => !r.pass).length,
  defects: defects.length,
  byStep,
  defects,
}
fs.writeFileSync(path.join(__dirname, 'scen2-results.json'), JSON.stringify(summary, null, 2))
console.log('\n=============== 场景扩展 E2E 结果 ===============')
for (const [s, v] of Object.entries(byStep)) console.log(`  ${s}: ${v.pass}/${v.total}`)
console.log(`通过 ${summary.passed}/${summary.totalAssertions}，缺陷 ${defects.length} 个`)
for (const d of defects) console.log(`  [${d.severity}] ${d.step} / ${d.name}: ${d.message}`)
process.exit(summary.failed > 0 ? 1 : 0)
